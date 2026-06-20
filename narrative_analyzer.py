"""
narrative_analyzer.py  —  IAF & Indian Defence Narrative Shift Analyzer
========================================================================

What this does:
  Reads intelligence data from multiple sources, groups it by time period
  (daily and weekly), then detects narrative shifts across:
    - Topic evolution     (what defence topics are being discussed)
    - Keyword evolution   (which terms are rising, falling, or new)
    - Entity evolution    (which people, orgs, locations appear/disappear)
    - Signal evolution    (ESCALATION vs DIPLOMACY vs CAPABILITY shifts)

Input (flexible — all three modes work together):
  1. intelligence_output.json   — from intelligence_fusion_engine.py
  2. monitored_results.json     — from monitoring_engine.py
  3. Live URLs pasted directly  — fetched and analysed on the spot

Output:
  - narrative_results.json      — full structured timeline
  - Printed narrative report    — timeline + shift alerts in terminal

Shift Detection Rules:
  A NARRATIVE SHIFT is flagged when ANY of these occur:
    1. New keywords appear that were absent in previous period
    2. Old keywords vanish and are replaced by new ones
    3. Primary topic changes completely between periods
    4. A new signal type dominates (e.g. DIPLOMACY → ESCALATION)
    5. New entities (people/orgs) appear suddenly
    6. Credibility or confidence drops/rises significantly

Usage:
  # Interactive — choose input mode at startup
  python narrative_analyzer.py

  # Load from files only (no URL prompt)
  python narrative_analyzer.py --files-only

  # Load from files + add URLs from a text file
  python narrative_analyzer.py --url-file urls.txt

  # Analyse a single URL and add to timeline
  python narrative_analyzer.py --url "https://..."
"""

import os
import re
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from urllib.parse import urlparse


# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCY IMPORTS
# ═══════════════════════════════════════════════════════════════════════

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YT_OK = True
except ImportError:
    YT_OK = False


# ═══════════════════════════════════════════════════════════════════════
# IAF VOCABULARY  (shared with fusion engine)
# ═══════════════════════════════════════════════════════════════════════

IAF_DOMAIN_TERMS = {
    "rafale","tejas","sukhoi","mirage","jaguar","mig","hercules","chinook",
    "apache","dhruv","lca","amca","tapas","rustom","ghatak","ucav","awacs",
    "aew","isr","gripen","hawk","heron","male","ucav","tanker",
    "missile","missiles","bvr","astra","brahmos","nirbhay","rudram","spice",
    "scalp","warhead","seeker","guidance","interceptor","intercepted","downed",
    "agni","prithvi","shaurya","sagarika","k4",
    "s400","barak","akash","mrsam","lrsam","qrsam","sam","patriot","thaad",
    "iaccs","adcc","iads","intercept","radar","airspace",
    "electronic","warfare","ecm","eccm","stealth","rcs","avionics","aesa",
    "pesa","sensor","kaveri","tarang","ew","sigint","elint","datalink",
    "drdo","hal","bel","dassault","saab","boeing","lockheed","iaf","isro",
    "sindoor","operation","strike","sortie","mission","patrol","squadron",
    "standoff","combat","deterrence","retaliation","escalation","deployment",
    "j10","j20","jf17","f16","pl15","pakistani","pakistan","china","chinese",
    "pla","plaaf",
    "drone","uav","swarm","counter","border","loc","lac","ladakh",
    "cyber","hack","malware","ransomware","breach","intrusion","phishing",
    "asat","satellite","gps","jamming","spoofing","orbital",
    "pilot","marshal","commander","airbase","airfield","airstrip",
}

IAF_PHRASES = [
    "air defence","electronic warfare","air superiority","operation sindoor",
    "precision strike","beyond visual range","surface to air missile",
    "air to air missile","airborne early warning","stealth fighter",
    "missile defence","drone swarm","network centric warfare",
    "combat air patrol","integrated air defence","indian air force",
    "iaf chief","air marshal","counter drone","anti drone",
    "unmanned aerial vehicle","forward base","line of control",
    "line of actual control",
]

STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","are","was","were","be","been","have","has","had","will","would",
    "could","should","that","this","it","we","they","he","she","you","i",
    "from","by","as","if","not","no","more","some","any","all","about",
    "said","says","also","new","one","two","three","after","before","over",
    "india","indian","news","report","today","latest","government","national",
    "its","their","our","your","his","her","into","just","than","then",
    "when","which","who","how","what","where","year","years","time","get",
}

TOPIC_DEFINITIONS = {
    "IAF Aircraft & Operations":       ["rafale","tejas","sukhoi","amca","lca","mig","sortie","squadron","airbase","awacs","isr","tanker","airborne","hawk","kiran"],
    "Air Defence Systems":             ["s400","akash","barak","mrsam","lrsam","qrsam","iaccs","iads","adcc","intercept","sam","spyder","thaad","patriot"],
    "Missiles & Strategic Weapons":    ["brahmos","astra","rudram","nirbhay","agni","prithvi","missile","bvr","warhead","seeker","standoff","shaurya","sagarika"],
    "Electronic & Cyber Warfare":      ["electronic","warfare","ecm","radar","stealth","jamming","cyber","hack","malware","breach","aesa","pesa","sigint","elint","ew"],
    "Drone & UAV Operations":          ["drone","uav","ucav","swarm","rustom","tapas","heron","ghatak","counter","anti","unmanned"],
    "Border & Tactical Operations":    ["loc","lac","ladakh","ceasefire","border","infiltration","patrol","forward","srinagar","leh","pathankot","sindoor","strike"],
    "Space & Satellite Defence":       ["asat","satellite","isro","orbital","gps","spoofing","space","reconnaissance"],
    "Foreign Threats & Adversary":     ["pakistan","pakistani","china","chinese","plaaf","pla","j20","j10","jf17","f16","espionage","spy"],
}

SIGNAL_PATTERNS = {
    "ESCALATION":  ["escalat","war","conflict","attack","strike","retaliat","aggression","hostil","provoc"],
    "CAPABILITY":  ["induct","procure","test","trial","deploy","capabilit","acquir","commission","develop","launch"],
    "THREAT":      ["threat","warn","alert","danger","risk","vulner","intrusion","breach","incursion","violation","hack"],
    "DIPLOMACY":   ["agreement","treaty","dialogue","meet","summit","discuss","negotiat","bilateral","cooperat"],
    "TECHNOLOGY":  ["ai","stealth","hypersonic","electronic","quantum","cyber","radar","aesa","autonomous","network"],
}

KNOWN_ORGS      = ["DRDO","HAL","BEL","IAF","Indian Air Force","Indian Army","Indian Navy","ISRO","CERT-In","Dassault","Boeing","Lockheed","Saab","PLAAF","PLA","PAF","MOD"]
KNOWN_LOCATIONS = ["India","Pakistan","China","Ladakh","Srinagar","Leh","Pathankot","Ambala","Hindon","Jodhpur","Jaisalmer","Jammu","Kashmir","LAC","LOC","Aksai Chin","Arunachal","Rajasthan","Punjab","Tibet"]
IAF_TECHNOLOGIES= ["Rafale","Tejas","Sukhoi","BrahMos","Astra","Akash","S-400","AMCA","Rudram","Nirbhay","AWACS","AESA","Kaveri","IACCS","Drone","UAV","Stealth","Radar","ECM","GPS"]
IAF_EVENTS      = ["Operation Sindoor","Exercise","Aero India","DefExpo","Air Show","War Games","Drill","Test","Trial","Launch","Induction","Strike","Mission","Sortie","Deployment"]
PERSON_TITLES   = ["Air Chief Marshal","Air Marshal","Air Vice Marshal","Air Commodore","Wing Commander","Squadron Leader","Group Captain","General","Admiral","Minister","Secretary","Chief","Prime Minister","Dr.","Mr.","Ms."]

DOMAIN_CREDIBILITY = {
    "pib.gov.in":           95, "mod.gov.in":          95,
    "indianairforce.nic.in":95, "drdo.gov.in":         95,
    "isro.gov.in":          95, "cert-in.org.in":      95,
    "thehindu.com":         85, "ndtv.com":            85,
    "aninews.in":           85, "hindustantimes.com":  85,
    "timesofindia.com":     85, "indiatoday.in":       85,
    "wionews.com":          83, "theprint.in":         82,
    "economictimes.com":    83, "livemint.com":        82,
    "news18.com":           80, "zeenews.india.com":   80,
    "firstpost.com":        72, "thewire.in":          80,
    "youtube.com":          70, "youtu.be":            70,
    "instagram.com":        45,
}


# ═══════════════════════════════════════════════════════════════════════
# MINI PIPELINE  (self-contained — no import of other files needed)
# ═══════════════════════════════════════════════════════════════════════

def tokenize(text):
    raw = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [t for t in raw if t not in STOPWORDS]

def extract_keywords(text, top_n=12):
    tokens = tokenize(text)
    freq   = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    scored = {t: f for t, f in freq.items()
              if any(t == d or d in t or t in d for d in IAF_DOMAIN_TERMS)}
    return sorted(scored, key=lambda w: scored[w], reverse=True)[:top_n]

def extract_phrases(text):
    tl = text.lower()
    return [p for p in IAF_PHRASES if p in tl]

def classify_topic(text, keywords, phrases):
    tl     = text.lower()
    kset   = set(keywords)
    pset   = set(phrases)
    best, best_score = "Unclassified", 0
    for topic, signals in TOPIC_DEFINITIONS.items():
        score = sum(1 for s in signals if s in kset or s in pset or s in tl)
        if score > best_score:
            best, best_score = topic, score
    return best

def extract_entities(text):
    people, orgs, locs, techs, events = [], [], [], [], []
    for title in PERSON_TITLES:
        for m in re.finditer(re.escape(title) + r'\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})', text):
            people.append(f"{title} {m.group(1)}")
    for o in KNOWN_ORGS:
        if o.lower() in text.lower(): orgs.append(o)
    for l in KNOWN_LOCATIONS:
        if re.search(r'\b' + re.escape(l) + r'\b', text, re.I): locs.append(l)
    for t in IAF_TECHNOLOGIES:
        if re.search(r'\b' + re.escape(t) + r'\b', text, re.I): techs.append(t)
    for e in IAF_EVENTS:
        if e.lower() in text.lower(): events.append(e)
    return {
        "people":        list(dict.fromkeys(people)),
        "organizations": list(dict.fromkeys(orgs)),
        "locations":     list(dict.fromkeys(locs)),
        "technologies":  list(dict.fromkeys(techs)),
        "events":        list(dict.fromkeys(events)),
    }

def detect_signals(text):
    tl = text.lower()
    out = []
    for stype, patterns in SIGNAL_PATTERNS.items():
        hits = [p for p in patterns if p in tl]
        if hits:
            out.append({"signal_type": stype, "evidence": hits[:3], "strength": min(len(hits),5)})
    return sorted(out, key=lambda x: x["strength"], reverse=True)

def get_credibility(url):
    domain = urlparse(url).netloc.lower().replace("www.","")
    for key, score in DOMAIN_CREDIBILITY.items():
        if key in domain:
            return score
    return 30

def build_record(url, title, text, collected_at=None):
    kw      = extract_keywords(text)
    phrases = extract_phrases(text)
    topic   = classify_topic(text, kw, phrases)
    ents    = extract_entities(text)
    sigs    = detect_signals(text)
    cred    = get_credibility(url)
    ts      = collected_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "doc_id":       hashlib.md5(url.encode()).hexdigest()[:12],
        "url":          url,
        "title":        title,
        "topic":        topic,
        "keywords":     kw,
        "phrases":      phrases,
        "entities":     ents,
        "signals":      sigs,
        "credibility":  cred,
        "collected_at": ts,
        "word_count":   len(text.split()),
    }


# ═══════════════════════════════════════════════════════════════════════
# URL FETCHER  (same logic as fusion engine)
# ═══════════════════════════════════════════════════════════════════════

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def extract_yt_id(url):
    m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else ""

def fetch_url(url):
    url = url.strip()
    ul  = url.lower()
    title, text, ts = "", "", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if "youtube.com/watch" in ul or "youtu.be/" in ul or "youtube.com/shorts" in ul:
        vid = extract_yt_id(url)
        transcript = ""
        if YT_OK and vid:
            try:
                entries    = YouTubeTranscriptApi.get_transcript(vid, languages=["en","en-IN","hi"])
                transcript = " ".join(e["text"] for e in entries)
                print(f"  ✔ YT transcript: {len(transcript.split())} words")
            except Exception as e:
                print(f"  ⚠ No transcript: {e}")
        try:
            r    = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            tag  = soup.find("meta", property="og:title")
            if tag: title = tag.get("content","")
            tag  = soup.find("meta", property="og:description")
            desc = tag.get("content","") if tag else ""
            text = f"{title} {desc} {transcript}".strip()
            print(f"  ✔ YouTube page scraped")
        except Exception as e:
            print(f"  ⚠ Scrape failed: {e}")

    elif "instagram.com" in ul:
        try:
            r    = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            tag  = soup.find("meta", property="og:title")
            if tag: title = tag.get("content","")
            tag  = soup.find("meta", property="og:description")
            desc = tag.get("content","") if tag else ""
            text = f"{title} {desc}".strip()
            print(f"  ✔ Instagram caption fetched")
        except Exception as e:
            print(f"  ⚠ Instagram fetch failed: {e}")

    else:
        try:
            r    = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, "html.parser")
            tag  = soup.find("meta", property="og:title") or soup.find("title")
            if tag: title = tag.get("content","") if tag.name=="meta" else tag.text.strip()
            for noise in soup(["script","style","nav","footer","header","aside","form","iframe"]):
                noise.decompose()
            art = soup.find("article")
            raw = art.get_text(" ", strip=True) if art else soup.get_text(" ", strip=True)
            text = re.sub(r'\s+',' ', f"{title}. {raw}").strip()
            print(f"  ✔ Article fetched: {len(text.split())} words")
        except Exception as e:
            print(f"  ⚠ Fetch failed: {e}")

    return title, text, ts


# ═══════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════════════

def load_intelligence_output(path="intelligence_output.json"):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for d in data:
        url   = d.get("source", {}).get("url", d.get("url",""))
        title = d.get("source", {}).get("title", d.get("title",""))
        ts    = d.get("collected_at","")
        text  = " ".join(d.get("keywords",[])) + " " + " ".join(d.get("phrases",[]))
        rec   = {
            "doc_id":       d.get("doc_id",""),
            "url":          url,
            "title":        title,
            "topic":        d.get("topic","Unclassified"),
            "keywords":     d.get("keywords",[]),
            "phrases":      d.get("phrases",[]),
            "entities":     d.get("entities",{}),
            "signals":      d.get("signals",[]),
            "credibility":  d.get("credibility",{}).get("final_score",50) if isinstance(d.get("credibility"),dict) else 50,
            "collected_at": ts,
            "word_count":   d.get("word_count",0),
        }
        records.append(rec)
    print(f"  ✔ Loaded {len(records)} records from intelligence_output.json")
    return records

def load_monitored_results(path="monitored_results.json"):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for d in data:
        url   = d.get("url","")
        title = d.get("title","")
        ts    = d.get("collected_at","")
        text  = title + " " + d.get("summary","")
        kw    = d.get("keywords",[])
        if not kw:
            kw = extract_keywords(text)
        phrases = extract_phrases(text)
        topic   = d.get("topic","") or classify_topic(text, kw, phrases)
        ents    = extract_entities(text)
        sigs    = detect_signals(text)
        cred    = d.get("credibility",{})
        cred_score = cred.get("final_score",50) if isinstance(cred,dict) else 50
        rec = {
            "doc_id":       d.get("doc_id",""),
            "url":          url,
            "title":        title,
            "topic":        topic,
            "keywords":     kw,
            "phrases":      phrases,
            "entities":     ents,
            "signals":      sigs,
            "credibility":  cred_score,
            "collected_at": ts,
            "word_count":   len(text.split()),
        }
        records.append(rec)
    print(f"  ✔ Loaded {len(records)} records from monitored_results.json")
    return records


# ═══════════════════════════════════════════════════════════════════════
# TIME BUCKETING
# ═══════════════════════════════════════════════════════════════════════

def parse_ts(ts_str):
    """Parse ISO8601 or RFC2822 timestamp → datetime. Returns None on failure."""
    if not ts_str:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_str[:25], fmt[:len(ts_str[:25])])
        except Exception:
            pass
    return None

def get_day_key(dt):
    return dt.strftime("%Y-%m-%d") if dt else "unknown"

def get_week_key(dt):
    if not dt:
        return "unknown"
    monday = dt - timedelta(days=dt.weekday())
    return f"Week of {monday.strftime('%d %b %Y')}"

def bucket_records(records):
    """Group records into daily and weekly buckets."""
    daily  = defaultdict(list)
    weekly = defaultdict(list)

    for r in records:
        dt = parse_ts(r.get("collected_at",""))
        if dt is None:
            dt = datetime.now()
        day  = get_day_key(dt)
        week = get_week_key(dt)
        daily[day].append(r)
        weekly[week].append(r)

    return dict(sorted(daily.items())), dict(sorted(weekly.items()))


# ═══════════════════════════════════════════════════════════════════════
# PERIOD SNAPSHOT
# Summarises one time period into a comparable structure
# ═══════════════════════════════════════════════════════════════════════

def build_snapshot(period_label, records):
    """Aggregate all records in a period into one snapshot."""
    topic_counter   = Counter()
    keyword_counter = Counter()
    phrase_counter  = Counter()
    signal_counter  = Counter()
    all_orgs        = Counter()
    all_people      = Counter()
    all_locations   = Counter()
    all_techs       = Counter()
    all_events      = Counter()
    cred_scores     = []

    for r in records:
        topic_counter[r.get("topic","Unclassified")] += 1
        for kw in r.get("keywords",[]):
            keyword_counter[kw] += 1
        for ph in r.get("phrases",[]):
            phrase_counter[ph] += 1
        for sig in r.get("signals",[]):
            signal_counter[sig["signal_type"]] += sig.get("strength",1)
        ents = r.get("entities",{})
        for o in ents.get("organizations",[]): all_orgs[o]      += 1
        for p in ents.get("people",[]):        all_people[p]    += 1
        for l in ents.get("locations",[]):     all_locations[l] += 1
        for t in ents.get("technologies",[]): all_techs[t]      += 1
        for e in ents.get("events",[]):        all_events[e]    += 1
        cred_scores.append(r.get("credibility", 50))

    primary_topic   = topic_counter.most_common(1)[0][0] if topic_counter   else "Unclassified"
    dominant_signal = signal_counter.most_common(1)[0][0] if signal_counter else "NONE"
    avg_cred        = round(sum(cred_scores)/len(cred_scores), 1) if cred_scores else 0

    return {
        "period":          period_label,
        "doc_count":       len(records),
        "primary_topic":   primary_topic,
        "topic_breakdown": dict(topic_counter.most_common()),
        "top_keywords":    [kw for kw, _ in keyword_counter.most_common(15)],
        "top_phrases":     [ph for ph, _ in phrase_counter.most_common(8)],
        "dominant_signal": dominant_signal,
        "signal_breakdown":dict(signal_counter.most_common()),
        "top_orgs":        [o for o, _ in all_orgs.most_common(6)],
        "top_people":      [p for p, _ in all_people.most_common(5)],
        "top_locations":   [l for l, _ in all_locations.most_common(6)],
        "top_technologies":[t for t, _ in all_techs.most_common(6)],
        "top_events":      [e for e, _ in all_events.most_common(5)],
        "avg_credibility": avg_cred,
        "keyword_set":     set(keyword_counter.keys()),   # for diff — removed in JSON
        "org_set":         set(all_orgs.keys()),
    }


# ═══════════════════════════════════════════════════════════════════════
# NARRATIVE SHIFT DETECTION
# ═══════════════════════════════════════════════════════════════════════

SHIFT_THRESHOLD_KW    = 0.40   # 40% of top keywords changed → shift
SHIFT_THRESHOLD_CRED  = 15     # credibility changed by 15+ points → shift

def detect_shift(prev_snap, curr_snap):
    """
    Compare two consecutive period snapshots.
    Returns a list of shift objects, each describing one detected change.
    """
    shifts = []

    prev_kw = set(prev_snap["top_keywords"])
    curr_kw = set(curr_snap["top_keywords"])

    # ── 1. New keywords appeared ────────────────────────────────
    new_kw = curr_kw - prev_kw
    if new_kw:
        shifts.append({
            "shift_type":  "NEW_KEYWORDS_EMERGED",
            "severity":    "HIGH" if len(new_kw) >= 5 else "MEDIUM",
            "description": f"{len(new_kw)} new keywords appeared: {', '.join(list(new_kw)[:6])}",
            "detail":      sorted(new_kw),
        })

    # ── 2. Old keywords disappeared ─────────────────────────────
    dropped_kw = prev_kw - curr_kw
    if dropped_kw:
        shifts.append({
            "shift_type":  "KEYWORDS_DROPPED",
            "severity":    "MEDIUM" if len(dropped_kw) >= 3 else "LOW",
            "description": f"{len(dropped_kw)} keywords disappeared: {', '.join(list(dropped_kw)[:6])}",
            "detail":      sorted(dropped_kw),
        })

    # ── 3. Keyword replacement (old gone + new appeared) ────────
    if new_kw and dropped_kw:
        overlap = len(new_kw) / max(len(prev_kw), 1)
        if overlap >= SHIFT_THRESHOLD_KW:
            shifts.append({
                "shift_type":  "NARRATIVE_KEYWORD_SHIFT",
                "severity":    "HIGH",
                "description": (f"Major keyword replacement detected — "
                                f"{len(dropped_kw)} terms dropped, "
                                f"{len(new_kw)} new terms rose. "
                                f"Narrative vocabulary has shifted."),
                "detail":      {
                    "dropped": sorted(dropped_kw)[:8],
                    "emerged": sorted(new_kw)[:8],
                },
            })

    # ── 4. Topic changed completely ──────────────────────────────
    if prev_snap["primary_topic"] != curr_snap["primary_topic"]:
        shifts.append({
            "shift_type":  "TOPIC_CHANGED",
            "severity":    "HIGH",
            "description": (f"Primary topic shifted: "
                            f"'{prev_snap['primary_topic']}' → "
                            f"'{curr_snap['primary_topic']}'"),
            "detail":      {
                "from": prev_snap["primary_topic"],
                "to":   curr_snap["primary_topic"],
            },
        })

    # ── 5. Dominant signal changed ───────────────────────────────
    if prev_snap["dominant_signal"] != curr_snap["dominant_signal"]:
        shifts.append({
            "shift_type":  "SIGNAL_SHIFT",
            "severity":    "HIGH",
            "description": (f"Intelligence signal shifted: "
                            f"{prev_snap['dominant_signal']} → "
                            f"{curr_snap['dominant_signal']}"),
            "detail":      {
                "from": prev_snap["dominant_signal"],
                "to":   curr_snap["dominant_signal"],
            },
        })

    # ── 6. New organisations appeared ───────────────────────────
    new_orgs = curr_snap["org_set"] - prev_snap["org_set"]
    if new_orgs:
        shifts.append({
            "shift_type":  "NEW_ENTITIES_APPEARED",
            "severity":    "MEDIUM",
            "description": f"New organisations mentioned: {', '.join(list(new_orgs)[:5])}",
            "detail":      sorted(new_orgs),
        })

    # ── 7. Credibility changed significantly ────────────────────
    cred_diff = abs(curr_snap["avg_credibility"] - prev_snap["avg_credibility"])
    if cred_diff >= SHIFT_THRESHOLD_CRED:
        direction = "increased" if curr_snap["avg_credibility"] > prev_snap["avg_credibility"] else "decreased"
        shifts.append({
            "shift_type":  "CREDIBILITY_SHIFT",
            "severity":    "MEDIUM",
            "description": (f"Average source credibility {direction} by "
                            f"{cred_diff:.1f} points "
                            f"({prev_snap['avg_credibility']} → "
                            f"{curr_snap['avg_credibility']})"),
            "detail":      {
                "prev": prev_snap["avg_credibility"],
                "curr": curr_snap["avg_credibility"],
            },
        })

    return shifts


# ═══════════════════════════════════════════════════════════════════════
# TIMELINE BUILDER
# ═══════════════════════════════════════════════════════════════════════

def build_timeline(buckets, label="daily"):
    """
    Build narrative timeline from bucketed records.
    Returns list of period objects with snapshots + detected shifts.
    """
    periods     = sorted(buckets.keys())
    snapshots   = []
    timeline    = []

    for period in periods:
        snap = build_snapshot(period, buckets[period])
        snapshots.append(snap)

    for i, snap in enumerate(snapshots):
        # Clean snapshot for JSON (remove sets)
        snap_clean = {k: v for k, v in snap.items()
                      if k not in ("keyword_set","org_set")}

        entry = {
            "period":    snap["period"],
            "timeframe": label,
            "snapshot":  snap_clean,
            "shifts":    [],
        }

        if i > 0:
            shifts = detect_shift(snapshots[i-1], snap)
            entry["shifts"]          = shifts
            entry["shift_count"]     = len(shifts)
            entry["shift_detected"]  = len(shifts) > 0
            entry["shift_severity"]  = (
                "HIGH"   if any(s["severity"]=="HIGH"   for s in shifts) else
                "MEDIUM" if any(s["severity"]=="MEDIUM" for s in shifts) else
                "LOW"    if shifts else "NONE"
            )
        else:
            entry["shift_count"]    = 0
            entry["shift_detected"] = False
            entry["shift_severity"] = "NONE"

        timeline.append(entry)

    return timeline


# ═══════════════════════════════════════════════════════════════════════
# REPORT PRINTER
# ═══════════════════════════════════════════════════════════════════════

def print_timeline(timeline, label="DAILY"):
    W   = 66
    bar = "═" * W
    thin= "─" * W

    print(f"\n{bar}")
    print(f"  📊 NARRATIVE TIMELINE — {label}")
    print(bar)

    for i, entry in enumerate(timeline):
        period = entry["period"]
        snap   = entry["snapshot"]
        shifts = entry.get("shifts",[])
        sev    = entry.get("shift_severity","NONE")
        sev_icon = "🔴" if sev=="HIGH" else "🟡" if sev=="MEDIUM" else "🟢" if sev=="LOW" else "⚪"

        # Period header
        connector = "↓" if i < len(timeline)-1 else ""
        print(f"\n  {sev_icon}  {period}  ({snap['doc_count']} docs)")
        print(f"  {thin[:56]}")

        # Snapshot summary
        print(f"  Primary Topic    : {snap['primary_topic']}")
        print(f"  Dominant Signal  : {snap['dominant_signal']}")
        print(f"  Avg Credibility  : {snap['avg_credibility']}/100")

        if snap.get("top_keywords"):
            kw_line = ", ".join(snap["top_keywords"][:8])
            print(f"  Top Keywords     : {kw_line}")

        if snap.get("top_technologies"):
            print(f"  Technologies     : {', '.join(snap['top_technologies'][:5])}")

        if snap.get("top_locations"):
            print(f"  Locations        : {', '.join(snap['top_locations'][:5])}")

        # Shift alerts
        if shifts:
            print(f"\n  ⚡ NARRATIVE SHIFTS DETECTED ({len(shifts)}):")
            for s in shifts:
                sicon = "🔴" if s["severity"]=="HIGH" else "🟡" if s["severity"]=="MEDIUM" else "🟢"
                print(f"    {sicon} [{s['shift_type']}]")
                # Word-wrap description
                words = s["description"].split()
                line  = []
                for w in words:
                    line.append(w)
                    if len(" ".join(line)) > 52:
                        print(f"       {' '.join(line[:-1])}")
                        line = [w]
                if line:
                    print(f"       {' '.join(line)}")

        if connector:
            print(f"\n  {'↓':^{W}}")

    print(f"\n{bar}")


def print_summary(daily_tl, weekly_tl, total_records):
    W   = 66
    bar = "═" * W

    total_shifts_d = sum(e.get("shift_count",0) for e in daily_tl)
    total_shifts_w = sum(e.get("shift_count",0) for e in weekly_tl)
    high_d = sum(1 for e in daily_tl  if e.get("shift_severity")=="HIGH")
    high_w = sum(1 for e in weekly_tl if e.get("shift_severity")=="HIGH")

    print(f"\n{bar}")
    print(f"  📋 NARRATIVE ANALYSIS SUMMARY")
    print(bar)
    print(f"  Total records analysed : {total_records}")
    print(f"  Daily periods          : {len(daily_tl)}")
    print(f"  Weekly periods         : {len(weekly_tl)}")
    print(f"  Daily shifts detected  : {total_shifts_d}  ({high_d} HIGH severity)")
    print(f"  Weekly shifts detected : {total_shifts_w}  ({high_w} HIGH severity)")
    print(bar)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

OUTPUT_FILE = "narrative_results.json"

def main():
    parser = argparse.ArgumentParser(description="IAF Narrative Shift Analyzer")
    parser.add_argument("--files-only", action="store_true",
                        help="Load from JSON files only, skip URL prompt")
    parser.add_argument("--url",      type=str, help="Single URL to add")
    parser.add_argument("--url-file", type=str, help="Text file of URLs (one per line)")
    args = parser.parse_args()

    print("\n" + "═"*66)
    print("  IAF & Indian Defence — Narrative Shift Analyzer")
    print("═"*66)

    all_records = []

    # ── Load from intelligence_output.json ──────────────────────
    all_records += load_intelligence_output()

    # ── Load from monitored_results.json ────────────────────────
    all_records += load_monitored_results()

    # ── URL fetching ────────────────────────────────────────────
    urls_to_fetch = []

    if args.url:
        urls_to_fetch.append(args.url)

    if args.url_file and os.path.exists(args.url_file):
        with open(args.url_file,"r",encoding="utf-8") as f:
            urls_to_fetch += [l.strip() for l in f if l.strip()]

    if not args.files_only and not args.url and not args.url_file:
        print("\n  Optionally paste URLs to add to the analysis.")
        print("  Press Enter without a URL to skip and analyse existing data.\n")
        while True:
            try:
                url = input("  🔗 Paste URL (or Enter to skip): ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if not url or url.lower() in ("done","exit","quit","q"):
                break
            urls_to_fetch.append(url)

    # Fetch and process URLs
    if urls_to_fetch and REQUESTS_OK:
        print(f"\n  Fetching {len(urls_to_fetch)} URL(s)...")
        for url in urls_to_fetch:
            print(f"\n  🔗 {url[:62]}")
            title, text, ts = fetch_url(url)
            if text.strip():
                rec = build_record(url, title, text, ts)
                all_records.append(rec)
                print(f"  ✔ Added: {title[:55]}")
            else:
                print(f"  ✖ No content extracted")
    elif urls_to_fetch and not REQUESTS_OK:
        print("  ⚠ Cannot fetch URLs — run: pip install requests beautifulsoup4")

    if not all_records:
        print("\n  ✖ No data to analyse.")
        print("  Run monitoring_engine.py or intelligence_fusion_engine.py first,")
        print("  or paste a URL when prompted.")
        sys.exit(0)

    # Remove duplicate doc_ids
    seen, deduped = set(), []
    for r in all_records:
        did = r.get("doc_id","")
        if did and did not in seen:
            seen.add(did)
            deduped.append(r)
    all_records = deduped
    print(f"\n  Total unique records : {len(all_records)}")

    # ── Bucket records ───────────────────────────────────────────
    daily_buckets, weekly_buckets = bucket_records(all_records)

    # ── Build timelines ──────────────────────────────────────────
    daily_timeline  = build_timeline(daily_buckets,  "daily")
    weekly_timeline = build_timeline(weekly_buckets, "weekly")

    # ── Print reports ────────────────────────────────────────────
    if len(daily_timeline) > 1:
        print_timeline(daily_timeline,  "DAILY NARRATIVE TIMELINE")
    else:
        print("\n  ℹ  Not enough daily data for shift detection yet.")
        print("     Keep running the monitoring engine to accumulate data.")
        if daily_timeline:
            print_timeline(daily_timeline, "DAILY SNAPSHOT")

    if len(weekly_timeline) > 1:
        print_timeline(weekly_timeline, "WEEKLY NARRATIVE TIMELINE")
    else:
        print("\n  ℹ  Not enough weekly data yet — accumulate more data over days.")

    print_summary(daily_timeline, weekly_timeline, len(all_records))

    # ── Save results ─────────────────────────────────────────────
    output = {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_records":  len(all_records),
        "daily_periods":  len(daily_timeline),
        "weekly_periods": len(weekly_timeline),
        "daily_timeline": [
            {k: v for k, v in e.items() if k not in ("keyword_set","org_set")}
            for e in daily_timeline
        ],
        "weekly_timeline": [
            {k: v for k, v in e.items() if k not in ("keyword_set","org_set")}
            for e in weekly_timeline
        ],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  💾 Saved → {OUTPUT_FILE}")
    print(f"  ✅ Narrative analysis complete.\n")


if __name__ == "__main__":
    main()
