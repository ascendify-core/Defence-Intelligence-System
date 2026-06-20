"""
query_engine.py — Defence Intelligence Query Engine
====================================================
Team 1 | Intelligence Query Engine

What this does:
  1. Accepts natural language analyst queries
  2. Maps queries to defence topics automatically
  3. Searches monitored_results.json, intelligence_output.json,
     source_credibility.json, trend_results.json, topic_results.json
  4. Accepts any URL (YouTube, news, article, Instagram, Shorts)
     and runs the full pipeline live on that content
  5. Outputs a structured Intelligence Object per result
  6. Saves to intelligence_query_results.json + prints a report

Usage:
  Interactive mode (default):
      python query_engine.py

  Direct query:
      python query_engine.py --query "show latest drone activity"

  Analyse a URL directly:
      python query_engine.py --url "https://..."

  Query + URL together:
      python query_engine.py --query "cyber attacks" --url "https://..."
"""

import os
import re
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone
from collections import defaultdict
from urllib.parse import urlparse

# ── Optional dependency check ──────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    print("⚠  pip install requests beautifulsoup4  (needed for URL analysis)")

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YT_OK = True
except ImportError:
    YT_OK = False


# ═══════════════════════════════════════════════════════════════
# QUERY → TOPIC MAPPING
# Natural language queries are mapped to canonical topic names
# ═══════════════════════════════════════════════════════════════

QUERY_MAP = {
    # Drone Activity
    "drone":            "Drone & UAV Operations",
    "uav":              "Drone & UAV Operations",
    "swarm":            "Drone & UAV Operations",
    "unmanned":         "Drone & UAV Operations",
    "counter drone":    "Drone & UAV Operations",
    "anti drone":       "Drone & UAV Operations",
    "drone activity":   "Drone & UAV Operations",
    "drone incursion":  "Drone & UAV Operations",

    # Cyber
    "cyber":            "Electronic & Cyber Warfare",
    "hack":             "Electronic & Cyber Warfare",
    "malware":          "Electronic & Cyber Warfare",
    "ransomware":       "Electronic & Cyber Warfare",
    "breach":           "Electronic & Cyber Warfare",
    "cybersecurity":    "Electronic & Cyber Warfare",
    "cyber attack":     "Electronic & Cyber Warfare",
    "electronic warfare":"Electronic & Cyber Warfare",
    "cyber incidents":  "Electronic & Cyber Warfare",

    # AI in Defence
    "ai":               "AI in Defence",
    "artificial intelligence": "AI in Defence",
    "autonomous":       "AI in Defence",
    "machine learning": "AI in Defence",
    "ai defence":       "AI in Defence",
    "military ai":      "AI in Defence",

    # Border Security
    "border":           "Border & Tactical Operations",
    "loc":              "Border & Tactical Operations",
    "lac":              "Border & Tactical Operations",
    "ceasefire":        "Border & Tactical Operations",
    "infiltration":     "Border & Tactical Operations",
    "border security":  "Border & Tactical Operations",
    "line of control":  "Border & Tactical Operations",

    # IAF Aircraft
    "rafale":           "IAF Aircraft & Operations",
    "tejas":            "IAF Aircraft & Operations",
    "sukhoi":           "IAF Aircraft & Operations",
    "aircraft":         "IAF Aircraft & Operations",
    "fighter":          "IAF Aircraft & Operations",
    "iaf":              "IAF Aircraft & Operations",
    "air force":        "IAF Aircraft & Operations",
    "sortie":           "IAF Aircraft & Operations",
    "squadron":         "IAF Aircraft & Operations",

    # Air Defence
    "air defence":      "Air Defence Systems",
    "air defense":      "Air Defence Systems",
    "s400":             "Air Defence Systems",
    "akash":            "Air Defence Systems",
    "missile defence":  "Air Defence Systems",
    "iaccs":            "Air Defence Systems",

    # Missiles
    "missile":          "Missiles & Strategic Weapons",
    "brahmos":          "Missiles & Strategic Weapons",
    "astra":            "Missiles & Strategic Weapons",
    "rudram":           "Missiles & Strategic Weapons",
    "bvr":              "Missiles & Strategic Weapons",
    "strategic weapons":"Missiles & Strategic Weapons",

    # Space
    "space":            "Space & Satellite Defence",
    "satellite":        "Space & Satellite Defence",
    "asat":             "Space & Satellite Defence",
    "gps":              "Space & Satellite Defence",
    "isro":             "Space & Satellite Defence",

    # Foreign Threats
    "pakistan":         "Foreign Threats & Adversary",
    "china":            "Foreign Threats & Adversary",
    "espionage":        "Foreign Threats & Adversary",
    "foreign":          "Foreign Threats & Adversary",
    "adversary":        "Foreign Threats & Adversary",
    "spy":              "Foreign Threats & Adversary",
    "pla":              "Foreign Threats & Adversary",

    # Operation Sindoor
    "sindoor":          "Border & Tactical Operations",
    "operation sindoor":"Border & Tactical Operations",
}

# Canonical topics list
ALL_TOPICS = [
    "Drone & UAV Operations",
    "Electronic & Cyber Warfare",
    "AI in Defence",
    "Border & Tactical Operations",
    "IAF Aircraft & Operations",
    "Air Defence Systems",
    "Missiles & Strategic Weapons",
    "Space & Satellite Defence",
    "Foreign Threats & Adversary",
]


# ═══════════════════════════════════════════════════════════════
# IAF VOCABULARY
# ═══════════════════════════════════════════════════════════════

IAF_DOMAIN_TERMS = {
    "rafale","tejas","sukhoi","mirage","jaguar","mig","hercules","chinook",
    "apache","dhruv","lca","amca","tapas","rustom","ghatak","ucav","awacs",
    "aew","isr","gripen","hawk","heron","tanker","kiran",
    "missile","missiles","bvr","astra","brahmos","nirbhay","rudram","spice",
    "scalp","warhead","seeker","guidance","interceptor","intercepted","downed",
    "agni","prithvi","shaurya","sagarika",
    "s400","barak","akash","mrsam","lrsam","qrsam","sam","patriot","thaad",
    "iaccs","adcc","iads","intercept","radar","airspace",
    "electronic","warfare","ecm","stealth","aesa","pesa","sensor","kaveri",
    "tarang","ew","sigint","elint","datalink",
    "drdo","hal","bel","dassault","saab","boeing","lockheed","iaf","isro",
    "sindoor","operation","strike","sortie","mission","patrol","squadron",
    "standoff","combat","deterrence","retaliation","escalation","deployment",
    "j10","j20","jf17","f16","pl15","pakistani","pakistan","china","chinese",
    "pla","plaaf",
    "drone","uav","swarm","counter","border","loc","lac","ladakh",
    "cyber","hack","malware","ransomware","breach","intrusion","phishing",
    "asat","satellite","gps","jamming","spoofing",
    "pilot","marshal","commander","airbase",
}

IAF_PHRASES = [
    "air defence","electronic warfare","air superiority","operation sindoor",
    "precision strike","beyond visual range","surface to air missile",
    "air to air missile","airborne early warning","stealth fighter",
    "missile defence","drone swarm","network centric warfare",
    "combat air patrol","integrated air defence","indian air force",
    "iaf chief","air marshal","counter drone","anti drone",
    "unmanned aerial vehicle","line of control","line of actual control",
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
    "show","latest","recent","give","find","search","tell","me","please",
}

TOPIC_DEFINITIONS = {
    "IAF Aircraft & Operations":    ["rafale","tejas","sukhoi","amca","lca","mig","sortie","squadron","airbase","awacs","isr","tanker","hawk","kiran"],
    "Air Defence Systems":          ["s400","akash","barak","mrsam","lrsam","qrsam","iaccs","iads","adcc","intercept","sam","thaad","patriot"],
    "Missiles & Strategic Weapons": ["brahmos","astra","rudram","nirbhay","agni","prithvi","missile","bvr","warhead","seeker","standoff","shaurya"],
    "Electronic & Cyber Warfare":   ["electronic","warfare","ecm","radar","stealth","jamming","cyber","hack","malware","breach","aesa","sigint","elint"],
    "Drone & UAV Operations":       ["drone","uav","ucav","swarm","rustom","tapas","heron","ghatak","counter","unmanned"],
    "Border & Tactical Operations": ["loc","lac","ladakh","ceasefire","border","infiltration","patrol","sindoor","strike"],
    "Space & Satellite Defence":    ["asat","satellite","isro","orbital","gps","spoofing","space"],
    "Foreign Threats & Adversary":  ["pakistan","pakistani","china","chinese","plaaf","pla","j20","j10","jf17","espionage"],
    "AI in Defence":                ["artificial","intelligence","autonomous","machine","learning","neural","algorithm","ai"],
}

SIGNAL_PATTERNS = {
    "ESCALATION": ["escalat","war","conflict","attack","strike","retaliat","aggression","hostil","provoc"],
    "CAPABILITY": ["induct","procure","test","trial","deploy","capabilit","acquir","commission","develop","launch"],
    "THREAT":     ["threat","warn","alert","danger","risk","vulner","intrusion","breach","incursion","violation","hack"],
    "DIPLOMACY":  ["agreement","treaty","dialogue","meet","summit","discuss","negotiat","bilateral","cooperat"],
    "TECHNOLOGY": ["ai","stealth","hypersonic","electronic","quantum","cyber","radar","aesa","autonomous","network"],
}

KNOWN_ORGS      = ["DRDO","HAL","BEL","IAF","Indian Air Force","Indian Army","Indian Navy","ISRO","CERT-In","Dassault","Boeing","Lockheed","Saab","PLAAF","PLA","PAF","MOD"]
KNOWN_LOCATIONS = ["India","Pakistan","China","Ladakh","Srinagar","Leh","Pathankot","Ambala","Hindon","Jodhpur","Jaisalmer","Jammu","Kashmir","LAC","LOC","Aksai Chin","Arunachal","Rajasthan","Punjab"]
IAF_TECHNOLOGIES= ["Rafale","Tejas","Sukhoi","BrahMos","Astra","Akash","S-400","AMCA","Rudram","Nirbhay","AWACS","AESA","Kaveri","IACCS","Drone","UAV","Stealth","Radar","ECM","GPS"]
IAF_EVENTS      = ["Operation Sindoor","Exercise","Aero India","DefExpo","Air Show","War Games","Test","Trial","Launch","Induction","Strike","Mission","Sortie","Deployment"]
PERSON_TITLES   = ["Air Chief Marshal","Air Marshal","Air Vice Marshal","Air Commodore","Wing Commander","Squadron Leader","Group Captain","General","Admiral","Minister","Secretary","Prime Minister","Chief","Dr.","Mr.","Ms."]

DOMAIN_CREDIBILITY = {
    "pib.gov.in":95,"mod.gov.in":95,"indianairforce.nic.in":95,
    "drdo.gov.in":95,"isro.gov.in":95,"cert-in.org.in":95,
    "thehindu.com":85,"ndtv.com":85,"aninews.in":85,
    "hindustantimes.com":85,"timesofindia.com":85,"indiatoday.in":85,
    "wionews.com":83,"theprint.in":82,"economictimes.com":83,
    "news18.com":80,"zeenews.india.com":80,"firstpost.com":72,
    "youtube.com":70,"youtu.be":70,"instagram.com":45,
}


# ═══════════════════════════════════════════════════════════════
# MINI NLP PIPELINE
# ═══════════════════════════════════════════════════════════════

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
    tl = text.lower()
    kset, pset = set(keywords), set(phrases)
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
    tl  = text.lower()
    out = []
    for stype, patterns in SIGNAL_PATTERNS.items():
        hits = [p for p in patterns if p in tl]
        if hits:
            out.append({"signal_type": stype, "evidence": hits[:3],
                        "strength": min(len(hits), 5)})
    return sorted(out, key=lambda x: x["strength"], reverse=True)

def get_credibility_from_url(url):
    domain = urlparse(url).netloc.lower().replace("www.", "")
    for key, score in DOMAIN_CREDIBILITY.items():
        if key in domain:
            return score
    return 30

def compute_confidence(credibility, signals, keywords):
    cred_w  = credibility * 0.5
    sig_w   = min(len(signals) * 10, 100) * 0.2
    kw_w    = min(len(keywords) * 8, 100) * 0.3
    return round(min(cred_w + sig_w + kw_w, 100), 1)

def risk_level(signals):
    types = [s["signal_type"] for s in signals]
    if "ESCALATION" in types: return "HIGH"
    if "THREAT" in types:     return "MEDIUM"
    if signals:               return "LOW"
    return "NONE"

def build_intelligence_object(url, title, text, topic_override=None):
    """Build a full Intelligence Object from raw text."""
    keywords   = extract_keywords(text)
    phrases    = extract_phrases(text)
    topic      = topic_override or classify_topic(text, keywords, phrases)
    entities   = extract_entities(text)
    signals    = detect_signals(text)
    credibility= get_credibility_from_url(url)
    confidence = compute_confidence(credibility, signals, keywords)

    # One-line summary from title + top keywords
    kw_str  = ", ".join(keywords[:5]) if keywords else "no keywords detected"
    summary = f"{title[:120]} — Key terms: {kw_str}." if title else f"Key terms: {kw_str}."

    return {
        "doc_id":      hashlib.md5(url.encode()).hexdigest()[:12],
        "topic":       topic,
        "title":       title,
        "url":         url,
        "summary":     summary,
        "entities":    entities,
        "keywords":    keywords,
        "phrases":     phrases,
        "signals":     signals,
        "credibility": credibility,
        "confidence":  confidence,
        "risk":        risk_level(signals),
        "collected_at":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ═══════════════════════════════════════════════════════════════
# URL FETCHER  (reused from narrative_analyzer.py)
# ═══════════════════════════════════════════════════════════════

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def extract_yt_id(url):
    m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else ""

def fetch_url(url):
    url   = url.strip()
    ul    = url.lower()
    title, text = "", ""

    if "youtube.com" in ul or "youtu.be" in ul:
        vid        = extract_yt_id(url)
        transcript = ""
        if YT_OK and vid:
            try:
                entries    = YouTubeTranscriptApi.get_transcript(vid, languages=["en","en-IN","hi"])
                transcript = " ".join(e["text"] for e in entries)
                print(f"    ✔ YouTube transcript: {len(transcript.split())} words")
            except Exception as e:
                print(f"    ⚠ Transcript unavailable: {e}")
        if REQUESTS_OK:
            try:
                r    = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")
                tag  = soup.find("meta", property="og:title")
                if tag: title = tag.get("content", "")
                tag  = soup.find("meta", property="og:description")
                desc = tag.get("content", "") if tag else ""
                text = f"{title} {desc} {transcript}".strip()
                print(f"    ✔ YouTube page scraped")
            except Exception as e:
                print(f"    ⚠ Scrape failed: {e}")

    elif "instagram.com" in ul:
        if REQUESTS_OK:
            try:
                r    = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")
                tag  = soup.find("meta", property="og:title")
                if tag: title = tag.get("content", "")
                tag  = soup.find("meta", property="og:description")
                desc = tag.get("content", "") if tag else ""
                text = f"{title} {desc}".strip()
                print(f"    ✔ Instagram content fetched")
            except Exception as e:
                print(f"    ⚠ Instagram fetch failed: {e}")

    else:
        if REQUESTS_OK:
            try:
                r         = requests.get(url, headers=HEADERS, timeout=15)
                r.encoding= r.apparent_encoding
                soup      = BeautifulSoup(r.text, "html.parser")
                tag       = soup.find("meta", property="og:title") or soup.find("title")
                if tag:
                    title = tag.get("content","") if tag.name == "meta" else tag.text.strip()
                for noise in soup(["script","style","nav","footer","header","aside","form","iframe"]):
                    noise.decompose()
                art  = soup.find("article")
                raw  = art.get_text(" ", strip=True) if art else soup.get_text(" ", strip=True)
                text = re.sub(r'\s+', ' ', f"{title}. {raw}").strip()
                print(f"    ✔ Article fetched: {len(text.split())} words")
            except Exception as e:
                print(f"    ⚠ Fetch failed: {e}")

    return title, text


# ═══════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════

def load_monitored_results(path="monitored_results.json"):
    if not os.path.exists(path): return []
    with open(path,"r",encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for d in data:
        url   = d.get("url","")
        title = d.get("title","")
        text  = title + " " + d.get("summary","")
        kw    = d.get("keywords",[]) or extract_keywords(text)
        phrases = extract_phrases(text)
        topic   = d.get("topic","") or classify_topic(text, kw, phrases)
        ents    = extract_entities(text)
        sigs    = detect_signals(text)
        cred    = d.get("credibility",{})
        cred_score = cred.get("final_score",50) if isinstance(cred,dict) else int(cred or 50)
        records.append({
            "doc_id":      d.get("doc_id",""),
            "url":         url,
            "title":       title,
            "topic":       topic,
            "keywords":    kw,
            "phrases":     phrases,
            "entities":    ents,
            "signals":     sigs,
            "credibility": cred_score,
            "confidence":  compute_confidence(cred_score, sigs, kw),
            "risk":        risk_level(sigs),
            "summary":     d.get("summary",""),
            "collected_at":d.get("collected_at",""),
        })
    return records

def load_intelligence_output(path="intelligence_output.json"):
    if not os.path.exists(path): return []
    with open(path,"r",encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for d in data:
        url   = d.get("source",{}).get("url", d.get("url",""))
        title = d.get("source",{}).get("title", d.get("title",""))
        kw    = d.get("keywords",[])
        phrases = d.get("phrases",[])
        sigs  = d.get("signals",[])
        cred  = d.get("credibility",{})
        cred_score = cred.get("final_score",50) if isinstance(cred,dict) else int(cred or 50)
        records.append({
            "doc_id":      d.get("doc_id",""),
            "url":         url,
            "title":       title,
            "topic":       d.get("topic","Unclassified"),
            "keywords":    kw,
            "phrases":     phrases,
            "entities":    d.get("entities",{}),
            "signals":     sigs,
            "credibility": cred_score,
            "confidence":  compute_confidence(cred_score, sigs, kw),
            "risk":        risk_level(sigs),
            "summary":     d.get("summary",""),
            "collected_at":d.get("collected_at",""),
        })
    return records

def load_source_credibility(path="source_credibility.json"):
    if not os.path.exists(path): return {}
    with open(path,"r",encoding="utf-8") as f:
        data = json.load(f)
    return {d.get("source_id",""):d for d in data}

def load_trends(path="trend_results.json"):
    if not os.path.exists(path): return []
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def load_topics(path="topic_results.json"):
    if not os.path.exists(path): return []
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# QUERY PARSER
# ═══════════════════════════════════════════════════════════════

def parse_query(query_text):
    """Map a natural language query to a canonical topic + raw keywords."""
    ql = query_text.lower().strip()

    # Try multi-word phrases first (longest match wins)
    matched_topic = None
    best_len = 0
    for phrase, topic in QUERY_MAP.items():
        if phrase in ql and len(phrase) > best_len:
            matched_topic = topic
            best_len = len(phrase)

    # Extract raw search terms (remove common query verbs)
    raw_terms = tokenize(ql)

    return matched_topic, raw_terms


# ═══════════════════════════════════════════════════════════════
# SEARCH ENGINE
# ═══════════════════════════════════════════════════════════════

def search_records(records, topic_filter, raw_terms, limit=10):
    """Filter and rank records by topic + keyword relevance."""
    scored = []
    for rec in records:
        rec_topic = rec.get("topic","")
        rec_kws   = set(rec.get("keywords",[]))
        rec_title = rec.get("title","").lower()

        score = 0
        # Topic match
        if topic_filter and topic_filter.lower() in rec_topic.lower():
            score += 50
        # Keyword term match
        for term in raw_terms:
            if term in rec_kws:          score += 10
            if term in rec_title:        score += 5
        # Credibility bonus
        score += rec.get("credibility", 0) * 0.1

        if score > 0:
            scored.append((score, rec))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


# ═══════════════════════════════════════════════════════════════
# OUTPUT PRINTER
# ═══════════════════════════════════════════════════════════════

def print_intelligence_object(obj, idx=1):
    W   = 64
    bar = "─" * W
    print(f"\n{'═'*W}")
    print(f"  INTELLIGENCE OBJECT #{idx}")
    print(f"{'═'*W}")
    print(f"  Topic      : {obj.get('topic','—')}")
    print(f"  Title      : {obj.get('title','—')[:70]}")
    print(f"  URL        : {obj.get('url','—')[:70]}")
    print(bar)

    # Summary
    summary = obj.get("summary","")
    if summary:
        words, line = summary.split(), []
        print("  Summary    :", end=" ")
        for i, w in enumerate(words):
            line.append(w)
            if len(" ".join(line)) > 52:
                prefix = "             " if i > 0 else ""
                print(f"{prefix}{' '.join(line[:-1])}")
                line = [w]
        if line:
            print(f"             {' '.join(line)}" if len(words) > len(line) else f" {' '.join(line)}")

    print(bar)
    print(f"  Keywords   : {', '.join(obj.get('keywords',[])[:8]) or '—'}")
    print(f"  Phrases    : {', '.join(obj.get('phrases',[])[:5]) or '—'}")

    # Entities
    ents = obj.get("entities", {})
    if ents.get("people"):
        print(f"  People     : {', '.join(ents['people'][:5])}")
    if ents.get("organizations"):
        print(f"  Orgs       : {', '.join(ents['organizations'][:6])}")
    if ents.get("locations"):
        print(f"  Locations  : {', '.join(ents['locations'][:5])}")
    if ents.get("technologies"):
        print(f"  Technology : {', '.join(ents['technologies'][:5])}")
    if ents.get("events"):
        print(f"  Events     : {', '.join(ents['events'][:4])}")

    print(bar)
    # Signals
    sigs = obj.get("signals",[])
    if sigs:
        print(f"  Signals    :", end=" ")
        for s in sigs[:3]:
            strength_bar = "█" * s["strength"] + "░" * (5 - s["strength"])
        print("  " + "  |  ".join(
            f"{s['signal_type']} {'█'*s['strength']+'░'*(5-s['strength'])}"
            for s in sigs[:3]))
    else:
        print(f"  Signals    : None detected")

    print(bar)
    risk_icon = {"HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢","NONE":"⚪"}.get(obj.get("risk","NONE"),"⚪")
    print(f"  Risk       : {risk_icon} {obj.get('risk','NONE')}")
    print(f"  Credibility: {obj.get('credibility',0)}/100")
    print(f"  Confidence : {obj.get('confidence',0)}/100")
    ts = obj.get("collected_at","")
    if ts:
        print(f"  Collected  : {ts}")
    print(f"{'═'*W}")


def print_query_header(query_text, topic, count):
    print(f"\n{'═'*64}")
    print(f"  🔍 QUERY   : {query_text}")
    print(f"  📌 TOPIC   : {topic or 'All topics (no specific match)'}")
    print(f"  📄 RESULTS : {count} intelligence objects")
    print(f"{'═'*64}")


def print_trends(trends, topic_filter):
    if not trends: return
    print(f"\n  📈 TREND DATA:")
    for t in trends:
        if not topic_filter or topic_filter.lower() in t.get("topic","").lower():
            icon = "📈" if t.get("trend") == "Increasing" else "📉" if t.get("trend") == "Decreasing" else "➡"
            print(f"     {icon} {t['topic']}: {t['trend']} "
                  f"(current: {t.get('current_mentions',0)} mentions, "
                  f"growth: {t.get('growth_rate',0)}%)")


# ═══════════════════════════════════════════════════════════════
# MAIN QUERY RUNNER
# ═══════════════════════════════════════════════════════════════

OUTPUT_FILE = "intelligence_query_results.json"

def run_query(query_text, url_input=None, limit=10):
    """Run a full query and return intelligence objects."""
    print(f"\n{'═'*64}")
    print(f"  Defence Intelligence Query Engine")
    print(f"{'═'*64}")

    # ── Load all data sources ─────────────────────────────────
    print("\n  Loading data sources...")
    all_records = []
    mon = load_monitored_results()
    intel = load_intelligence_output()
    all_records = mon + intel
    trends = load_trends()
    topics = load_topics()
    credibility_db = load_source_credibility()

    if mon:   print(f"  ✔ monitored_results.json   — {len(mon)} records")
    if intel: print(f"  ✔ intelligence_output.json — {len(intel)} records")
    if not all_records:
        print("  ⚠ No existing data found. Run monitoring_engine.py first.")

    # ── URL live analysis ─────────────────────────────────────
    url_objects = []
    if url_input:
        print(f"\n  🔗 Fetching URL: {url_input[:62]}")
        title, text = fetch_url(url_input)
        if text.strip():
            obj = build_intelligence_object(url_input, title, text)
            url_objects.append(obj)
            print(f"  ✔ Intelligence object built from URL")
        else:
            print(f"  ✖ Could not extract content from URL")

    # ── Parse query ───────────────────────────────────────────
    topic_filter, raw_terms = parse_query(query_text)

    # ── Search existing records ───────────────────────────────
    results = search_records(all_records, topic_filter, raw_terms, limit=limit)

    # ── Combine URL result + search results ───────────────────
    all_objects = url_objects + results

    # ── Print results ─────────────────────────────────────────
    print_query_header(query_text, topic_filter, len(all_objects))
    print_trends(trends, topic_filter)

    for i, obj in enumerate(all_objects, 1):
        print_intelligence_object(obj, idx=i)

    # ── Save output ───────────────────────────────────────────
    output = {
        "query":          query_text,
        "topic_matched":  topic_filter,
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_results":  len(all_objects),
        "url_analysed":   url_input or None,
        "trend_summary":  trends,
        "topic_summary":  topics,
        "results":        all_objects,
    }

    with open(OUTPUT_FILE,"w",encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  💾 Saved → {OUTPUT_FILE}")
    print(f"  ✅ Query complete — {len(all_objects)} intelligence objects returned.\n")
    return all_objects


# ═══════════════════════════════════════════════════════════════
# INTERACTIVE MODE
# ═══════════════════════════════════════════════════════════════

def interactive_mode():
    print("\n" + "═"*64)
    print("  Defence Intelligence Query Engine — Interactive Mode")
    print("═"*64)
    print("\n  Example queries:")
    print("    show latest drone activity")
    print("    cybersecurity incidents")
    print("    AI defence developments")
    print("    border security updates")
    print("    rafale fighter jet news")
    print("    show all missile tests")
    print("    pakistan espionage activity")
    print("    space satellite threats")
    print("\n  Type 'exit' to quit.\n")

    while True:
        try:
            query = input("  🔍 Enter query: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Exiting.")
            break
        if not query or query.lower() in ("exit","quit","q"):
            break

        url = input("  🔗 Paste URL to analyse (or Enter to skip): ").strip()
        if not url:
            url = None

        run_query(query, url_input=url)

        again = input("\n  Run another query? (y/n): ").strip().lower()
        if again != "y":
            break


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Defence Intelligence Query Engine")
    parser.add_argument("--query", type=str, help="Natural language query")
    parser.add_argument("--url",   type=str, help="URL to fetch and analyse")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max results to return (default: 10)")
    args = parser.parse_args()

    if args.query or args.url:
        query = args.query or "general defence intelligence"
        run_query(query, url_input=args.url, limit=args.limit)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
