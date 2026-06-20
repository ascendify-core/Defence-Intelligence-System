"""
monitoring_engine.py  —  Real-Time Defence Intelligence Monitor
Team T1 | Day 6

What this does:
  - Watches 4 defence topics across real online sources
  - Can run ONCE manually, or run automatically every 30 minutes
  - Collects new articles, extracts keywords, scores credibility
  - Saves all results to monitored_results.json

Sources monitored:
  - Google News RSS       (all 4 topics)
  - PIB India RSS         (AI Defence, Border Security)
  - ANI News RSS          (all 4 topics)
  - The Hindu RSS         (all 4 topics)
  - CERT-In               (Cyber Attacks)

Usage:
  Run ONCE manually:
      python monitoring_engine.py --run-once

  Run automatically every 30 minutes:
      python monitoring_engine.py --schedule

  Change interval (e.g. every 10 minutes):
      python monitoring_engine.py --schedule --interval 10
"""

import json
import os
import re
import sys
import math
import hashlib
import argparse
from datetime import datetime, timezone
from collections import defaultdict

import feedparser
import requests
from apscheduler.schedulers.blocking import BlockingScheduler


# ═══════════════════════════════════════════════════════════════
# MONITORING TOPICS
# Each topic has a name, keywords to search, and relevant sources
# ═══════════════════════════════════════════════════════════════

TOPICS = {
    "AI in Defence": {
        "keywords": [
            "artificial intelligence defence", "AI military India",
            "autonomous drone india", "machine learning army",
            "defence AI policy", "AI weapons system",
            "neural network military", "AI surveillance india"
        ],
        "sources": ["google_news", "pib", "ani", "hindu"],
    },
    "Border Security": {
        "keywords": [
            "LOC violation india", "border tension india pakistan",
            "border tension india china", "troop deployment india border",
            "ceasefire violation", "LAC india china",
            "border infiltration india", "india border security"
        ],
        "sources": ["google_news", "pib", "ani", "hindu"],
    },
    "Cyber Attacks": {
        "keywords": [
            "cyber attack india", "india defence network hack",
            "malware india government", "critical infrastructure attack india",
            "state sponsored hacking india", "india cybersecurity breach",
            "CERT-In advisory", "india ransomware attack"
        ],
        "sources": ["google_news", "ani", "hindu", "cert_in"],
    },
    "Drone Activity": {
        "keywords": [
            "drone incursion india", "UAV india border",
            "counter drone india", "drone attack india",
            "drone sighting india", "anti drone system india",
            "unmanned aerial vehicle india military",
            "drone swarm india"
        ],
        "sources": ["google_news", "pib", "ani", "hindu"],
    },
}


# ═══════════════════════════════════════════════════════════════
# RSS FEED SOURCES
# All free, no API key needed
# ═══════════════════════════════════════════════════════════════

def build_google_news_url(keyword):
    """Google News RSS for a search keyword."""
    encoded = keyword.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

FIXED_FEEDS = {
    "pib": [
        "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",   # Defence
        "https://pib.gov.in/RssMain.aspx?ModId=2&Lang=1&Regid=3",   # Home Affairs
    ],
    "ani": [
        "https://www.aninews.in/rss/india.rss",
        "https://www.aninews.in/rss/national/defence.rss",
    ],
    "hindu": [
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://www.thehindu.com/sci-tech/technology/feeder/default.rss",
    ],
    "cert_in": [
        "https://www.cert-in.org.in/RSS/rss.xml",
    ],
}

# Channel → credibility category mapping
SOURCE_CREDIBILITY = {
    "pib":      ("PIB India",   "Government Source", 95),
    "ani":      ("ANI News",    "Verified Media",    85),
    "hindu":    ("The Hindu",   "Verified Media",    85),
    "cert_in":  ("CERT-In",     "Government Source", 95),
    "google_news": ("Google News", "Verified Media", 80),
}


# ═══════════════════════════════════════════════════════════════
# IAF / DEFENCE KEYWORD WHITELIST (from keyword_extraction.py)
# ═══════════════════════════════════════════════════════════════

IAF_DOMAIN_TERMS = {
    "rafale","tejas","sukhoi","mirage","jaguar","mig","hercules","chinook",
    "apache","dhruv","lca","amca","ucav","awacs","aew","isr","gripen",
    "missile","missiles","bvr","astra","brahmos","nirbhay","rudram","spice",
    "scalp","warhead","seeker","guidance","infrared","interceptor","downed",
    "s400","barak","akash","mrsam","lrsam","qrsam","sam","patriot","iaccs",
    "adcc","iads","intercept","radar","airspace","intercepted","threats",
    "electronic","warfare","ecm","stealth","rcs","avionics","aesa","pesa",
    "sensor","fusion","kaveri","indigenous","tarang","tara",
    "bel","drdo","hal","dassault","saab","boeing","lockheed",
    "sindoor","operation","strike","sortie","mission","patrol","precision",
    "standoff","combat","deterrence","retaliation","escalation","squadron",
    "j10","j20","jf17","f16","pl15","pakistani","pakistan","china","chinese",
    "drone","uav","ucav","autonomous","swarm","counter","border","loc","lac",
    "cyber","hack","malware","ransomware","breach","intrusion","phishing",
    "ai","artificial","intelligence","machine","learning","neural","network",
    "abinandan","pilot","commander","marshal","airbase","integrated",
}

STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","are","was","were","be","been","have","has","had","will","would",
    "could","should","that","this","it","we","they","he","she","you","i",
    "from","by","as","if","not","no","more","some","any","all","about",
    "said","says","also","new","one","two","three","after","before","over",
    "india","indian","news","report","today","latest","government","national",
}

# Terms that are too generic and cause false positives
_GENERIC_EXCLUDE = {
    "air", "rain", "remain", "remains", "raises", "raise",
    "against", "place", "places", "local", "operations",
    "located", "chairman", "complaint", "aitc", "nhai",
    "credai", "openai", "lack", "waiver", "rebel", "hailed",
    "aided", "blocking", "disruptions", "trains", "countering",
    "breaches", "blockade", "machine",
}

def is_iaf_term(token):
    t = token.lower()
    if t in _GENERIC_EXCLUDE:
        return False
    if len(t) < 4:   # skip very short tokens
        return False
    return any(t == term or t.startswith(term) or term in t
               for term in IAF_DOMAIN_TERMS)

def tokenize(text):
    raw = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [t for t in raw if t not in STOPWORDS]

def extract_keywords(text, top_n=8):
    tokens = tokenize(text)
    freq = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    iaf_tokens = {t: f for t, f in freq.items() if is_iaf_term(t)}
    top = sorted(iaf_tokens, key=lambda w: iaf_tokens[w], reverse=True)[:top_n]
    return top


# ═══════════════════════════════════════════════════════════════
# CREDIBILITY SCORING
# ═══════════════════════════════════════════════════════════════

def score_credibility(source_key, keywords, content):
    channel, category, base = SOURCE_CREDIBILITY.get(
        source_key, ("Unknown", "Unknown Source", 30))
    modifiers = {}
    if len(keywords) >= 5:  modifiers["rich_keywords"] = +5
    elif len(keywords) >= 2: modifiers["has_keywords"]  = +3
    if len(content) > 500:  modifiers["substantial_content"] = +3
    if len(content) < 100:  modifiers["short_content"] = -8
    total = sum(modifiers.values())
    final = max(0, min(100, base + total))
    label = (
        "Very High" if final >= 90 else
        "High"      if final >= 75 else
        "Medium"    if final >= 55 else
        "Low"       if final >= 35 else "Very Low"
    )
    alert = (
        "HIGH"   if final >= 95 else
        "MEDIUM" if final >= 60 else "LOW"
    )
    return {
        "channel": channel, "category": category,
        "base_score": base, "modifiers": modifiers,
        "modifier_total": total, "final_score": final,
        "credibility_label": label, "alert_level": alert,
    }


# ═══════════════════════════════════════════════════════════════
# RSS FETCHING
# ═══════════════════════════════════════════════════════════════

def fetch_feed(url, timeout=10):
    """Fetch and parse an RSS feed. Returns list of entries."""
    try:
        feed = feedparser.parse(url)
        return feed.entries if feed.entries else []
    except Exception as e:
        print(f"    ⚠ Feed error ({url[:60]}...): {e}")
        return []

def entry_to_doc(entry, source_key, topic):
    """Convert an RSS entry to a standardised document dict."""
    title   = getattr(entry, "title",   "") or ""
    summary = getattr(entry, "summary", "") or ""
    link    = getattr(entry, "link",    "") or ""
    pub     = getattr(entry, "published","") or ""

    # Clean HTML tags from summary
    summary_clean = re.sub(r"<[^>]+>", " ", summary).strip()
    content = f"{title}. {summary_clean}"

    doc_id = hashlib.md5(link.encode()).hexdigest()[:12]

    keywords = extract_keywords(content)
    cred     = score_credibility(source_key, keywords, content)

    return {
        "doc_id":       doc_id,
        "topic":        topic,
        "source_key":   source_key,
        "title":        title,
        "summary":      summary_clean[:300],
        "url":          link,
        "published":    pub,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "keywords":     keywords,
        "credibility":  cred,
        "alert_level":  cred["alert_level"],
    }


# ═══════════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════════

def load_seen_ids(results_path):
    """Load already-collected doc IDs to avoid duplicates."""
    if not os.path.exists(results_path):
        return set()
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {d["doc_id"] for d in data}

def load_existing(results_path):
    if not os.path.exists(results_path):
        return []
    with open(results_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# MAIN MONITORING JOB
# ═══════════════════════════════════════════════════════════════

RESULTS_PATH = "monitored_results.json"

def run_monitoring_cycle():
    """One full monitoring cycle across all topics and sources."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'═'*60}")
    print(f"  🔍 Monitoring cycle started — {now}")
    print(f"{'═'*60}")

    seen_ids   = load_seen_ids(RESULTS_PATH)
    existing   = load_existing(RESULTS_PATH)
    new_docs   = []
    alert_high = []

    for topic, config in TOPICS.items():
        print(f"\n  📡 Topic: {topic}")
        topic_new = 0

        for source_key in config["sources"]:
            # Build feed URLs for this source+topic combination
            urls = []
            if source_key == "google_news":
                # Use first 2 keywords for Google News search
                for kw in config["keywords"][:2]:
                    urls.append(build_google_news_url(kw))
            else:
                urls = FIXED_FEEDS.get(source_key, [])

            for url in urls:
                entries = fetch_feed(url)
                for entry in entries:
                    doc = entry_to_doc(entry, source_key, topic)
                    if doc["doc_id"] in seen_ids:
                        continue  # already collected

                    # Strict relevance check — ALL words of at least
                    # one topic keyword phrase must appear in content
                    combined = (doc["title"] + " " + doc["summary"]).lower()
                    topic_keywords = [k.lower() for k in config["keywords"]]
                    def phrase_match(phrase, text):
                        # Every word in the phrase must appear in the text
                        words = phrase.split()
                        return all(w in text for w in words)
                    if not any(phrase_match(tk, combined) for tk in topic_keywords):
                        continue  # not relevant to this topic

                    seen_ids.add(doc["doc_id"])
                    new_docs.append(doc)
                    topic_new += 1

                    # Print new item
                    score = doc["credibility"]["final_score"]
                    alert = doc["alert_level"]
                    title_short = doc["title"][:55] + "..." \
                        if len(doc["title"]) > 55 else doc["title"]
                    alert_icon = "🔴" if alert=="HIGH" else \
                                 "🟡" if alert=="MEDIUM" else "🟢"
                    print(f"    {alert_icon} [{score:>3}/100] {title_short}")
                    if doc["keywords"]:
                        print(f"         Keywords: {', '.join(doc['keywords'][:5])}")

                    if alert == "HIGH":
                        alert_high.append(doc)

        print(f"    → {topic_new} new items collected")

    # Save results
    all_docs = existing + new_docs
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    # Summary
    print(f"\n{'─'*60}")
    print(f"  ✅ Cycle complete | {len(new_docs)} new items | "
          f"Total stored: {len(all_docs)}")
    print(f"  💾 Saved → {RESULTS_PATH}")

    # High alerts
    if alert_high:
        print(f"\n  🚨 HIGH ALERT — {len(alert_high)} critical item(s):")
        for doc in alert_high:
            print(f"     • [{doc['credibility']['channel']}] {doc['title'][:60]}")
    else:
        print(f"  ✔  No HIGH alerts this cycle.")
    print(f"{'─'*60}")


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Defence Intelligence Monitoring Engine")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one monitoring cycle and exit")
    parser.add_argument("--clear", action="store_true",
                        help="Clear stored results before running")
    parser.add_argument("--schedule", action="store_true",
                        help="Run automatically on a schedule")
    parser.add_argument("--interval", type=int, default=30,
                        help="Schedule interval in minutes (default: 30)")
    args = parser.parse_args()

    if args.clear and os.path.exists(RESULTS_PATH):
        os.remove(RESULTS_PATH)
        print(f"🗑  Cleared {RESULTS_PATH}")

    if args.run_once:
        print("▶ Running single monitoring cycle...")
        run_monitoring_cycle()

    elif args.schedule:
        print(f"⏱  Scheduler started — running every {args.interval} minutes.")
        print("   Press Ctrl+C to stop.\n")
        # Run immediately on start
        run_monitoring_cycle()
        # Then schedule
        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_monitoring_cycle,
            trigger="interval",
            minutes=args.interval,
            id="monitoring_job"
        )
        try:
            scheduler.start()
        except KeyboardInterrupt:
            print("\n⏹  Scheduler stopped.")
            scheduler.shutdown()

    else:
        print("Usage:")
        print("  Run once:     python monitoring_engine.py --run-once")
        print("  Auto schedule: python monitoring_engine.py --schedule")
        print("  Custom interval: python monitoring_engine.py --schedule --interval 10")

if __name__ == "__main__":
    main()
