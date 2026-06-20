"""
intelligence_fusion_engine.py  —  Intelligence Fusion Engine
Team: Intelligence Fusion Team

What this does:
  Combines keywords, entities, topics, credibility, confidence,
  trends, and signals from ALL pipeline outputs into one unified
  Intelligence Object per topic.

Inputs (reads automatically from same folder):
  - ingested_dataa_master_keywords.json   (keywords, phrases, summaries, topics)
  - source_credibility.json               (credibility scores per source)
  - monitored_results.json                (real-time monitored articles)
  - trend_results.json                    (topic trend data)        [optional]
  - topic_results.json                    (topic document counts)   [optional]

Output:
  - intelligence_objects.json             (one object per topic)
  - Printed summary report to console

Intelligence Object Structure:
  {
    "topic":       "Drone Activity",
    "summary":     "...",
    "entities":    { "people": [], "organizations": [], "locations": [] },
    "keywords":    [],
    "phrases":     [],
    "signals":     [],
    "credibility": { "average": 83, "label": "High", "source_count": 5 },
    "confidence":  91,
    "trend":       { "direction": "Increasing", "growth_rate": 100.0 },
    "sources":     [],
    "fused_at":    "2026-06-10T..."
  }

Usage:
    python intelligence_fusion_engine.py
    python intelligence_fusion_engine.py --input-keywords my_keywords.json
"""

import json
import os
import re
import sys
import argparse
from collections import defaultdict
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — file paths
# ═══════════════════════════════════════════════════════════════

DEFAULT_KEYWORDS_FILE   = "ingested_dataa_master_keywords.json"
DEFAULT_CRED_FILE       = "source_credibility.json"
DEFAULT_MONITORED_FILE  = "monitored_results.json"
DEFAULT_TREND_FILE      = "trend_results.json"
DEFAULT_TOPIC_FILE      = "topic_results.json"
OUTPUT_FILE             = "intelligence_objects.json"


# ═══════════════════════════════════════════════════════════════
# ENTITY EXTRACTION
# Uses spaCy if available, falls back to regex if not installed
# ═══════════════════════════════════════════════════════════════

# Defence-domain technology keywords
DEFENCE_TECH_KEYWORDS = [
    "Rafale", "Tejas", "Sukhoi", "S-400", "Akash", "BrahMos",
    "Rudram", "AESA", "IACCS", "Drone", "UAV", "UCAV", "Missile",
    "Radar", "Electronic Warfare", "AI", "Machine Learning",
    "Autonomous", "Cyber", "Satellite", "ASAT", "GPS",
]

def load_spacy():
    """Try to load spaCy. Return nlp model or None."""
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
            return nlp
        except OSError:
            print("  ⚠ spaCy model not found — using regex fallback.")
            print("    To enable full NER: python -m spacy download en_core_web_sm")
            return None
    except ImportError:
        print("  ⚠ spaCy not installed — using regex fallback.")
        print("    To enable full NER: pip install spacy")
        return None

_NLP = None  # loaded once, reused

# Patterns that indicate noise/garbage entities to exclude
_ENTITY_NOISE = re.compile(
    r'(&nbsp;|&amp;|&lt;|&gt;|http|www\.|\.com|\.in|'
    r'^\d+$|<[^>]+>|Report\s*-|Explainer|Times of India|'
    r'Economic Times|Moneycontrol|Indiablooms|Defence\.in)',
    re.IGNORECASE
)

def _clean_entities(entities, min_len=3, max_len=40):
    """Filter out HTML artifacts, URLs, news source names, short tokens."""
    cleaned = []
    for e in entities:
        e = e.strip()
        if len(e) < min_len or len(e) > max_len:    continue
        if _ENTITY_NOISE.search(e):                  continue
        if e.isnumeric():                             continue
        if e.lower() in {"india", "indian", "the", "a", "an",
                          "this", "that", "but", "and", "or"}:
            continue
        cleaned.append(e)
    return list(dict.fromkeys(cleaned))  # deduplicate, preserve order

def extract_entities_spacy(text, nlp):
    """Extract entities using spaCy NER with noise filtering."""
    # Strip HTML entities before processing
    clean_text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
    doc = nlp(clean_text[:10000])
    people        = _clean_entities([e.text for e in doc.ents if e.label_ == "PERSON"])
    organizations = _clean_entities([e.text for e in doc.ents if e.label_ == "ORG"])
    locations     = _clean_entities([e.text for e in doc.ents if e.label_ in ("GPE", "LOC")])
    technologies  = [t for t in DEFENCE_TECH_KEYWORDS
                     if t.lower() in text.lower()]
    return {
        "people":        people[:8],
        "organizations": organizations[:8],
        "locations":     locations[:8],
        "technologies":  technologies,
    }

def extract_entities_regex(text):
    """Fallback entity extraction using regex patterns."""
    # Proper nouns — Title Case sequences
    proper = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', text)
    noise  = {"The", "A", "An", "India", "Indian", "Pakistan", "China",
               "This", "That", "These", "Those", "But", "And", "Or",
               "In", "On", "At", "To", "For", "Of", "With", "By"}
    proper = list({p for p in proper if p not in noise and len(p) > 3})

    # Locations — known country/region names
    location_patterns = [
        "India", "Pakistan", "China", "Russia", "Israel", "France",
        "Kashmir", "Rajasthan", "Punjab", "LAC", "LoC", "Ladakh",
        "J&K", "Jammu", "Poonch", "Kupwara", "Samba",
    ]
    locations = [loc for loc in location_patterns
                 if loc.lower() in text.lower()]

    technologies = [t for t in DEFENCE_TECH_KEYWORDS
                    if t.lower() in text.lower()]

    return {
        "people":        [],
        "organizations": proper[:8],
        "locations":     locations[:8],
        "technologies":  technologies,
    }

def extract_entities(text):
    """Extract entities from text — spaCy if available, regex otherwise."""
    global _NLP
    if _NLP is None:
        _NLP = load_spacy()

    if not text or not text.strip():
        return {"people": [], "organizations": [],
                "locations": [], "technologies": []}

    # Skip non-English (Devanagari) text
    devanagari = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    if devanagari / max(len(text), 1) > 0.3:
        return {"people": [], "organizations": [],
                "locations": [], "technologies": []}

    if _NLP:
        return extract_entities_spacy(text, _NLP)
    return extract_entities_regex(text)


# ═══════════════════════════════════════════════════════════════
# SIGNAL DETECTION
# Signals are high-value intelligence observations extracted
# from content — specific events, alerts, or notable findings
# ═══════════════════════════════════════════════════════════════

SIGNAL_PATTERNS = [
    # Operations
    (r'\boperation\s+\w+\b',             "Operation mentioned"),
    (r'\bstrike\b',                       "Strike activity"),
    (r'\bintercept\w*\b',                 "Interception event"),
    (r'\bdowned?\b',                      "Aircraft/drone downed"),
    # Threats
    (r'\bdrone\s+incursion\b',            "Drone incursion"),
    (r'\bceasefire\s+violation\b',        "Ceasefire violation"),
    (r'\bcyber\s+attack\b',              "Cyber attack"),
    (r'\bhack\w*\b',                      "Hacking activity"),
    (r'\bransomware\b',                   "Ransomware threat"),
    (r'\bmalware\b',                      "Malware detected"),
    # Defence assets
    (r'\bs[-\s]?400\b',                   "S-400 system mentioned"),
    (r'\brafale\b',                       "Rafale aircraft mentioned"),
    (r'\bbrahmos\b',                      "BrahMos missile mentioned"),
    (r'\bakash\b',                        "Akash missile mentioned"),
    (r'\bastra\b',                        "Astra missile mentioned"),
    (r'\brudram\b',                       "Rudram missile mentioned"),
    # Escalation
    (r'\bescalat\w*\b',                   "Escalation signal"),
    (r'\bnuclear\b',                      "Nuclear mention"),
    (r'\bmissile\s+test\b',              "Missile test"),
    (r'\btest.{0,10}fire\b',              "Test firing"),
    # Acquisition
    (r'\bacquisition\b',                  "Defence acquisition"),
    (r'\bprocure\w*\b',                   "Procurement activity"),
    (r'\bdeal\b.{0,30}\bcrore\b',        "Major defence deal"),
    # AI/Tech
    (r'\bautonomous\s+\w+\b',            "Autonomous system"),
    (r'\bai[-\s]powered\b',              "AI-powered system"),
    (r'\bswarm\b',                        "Swarm activity"),
]

def detect_signals(text):
    """Detect intelligence signals in text."""
    text_lower = text.lower()
    found = []
    seen  = set()
    for pattern, label in SIGNAL_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches and label not in seen:
            found.append({
                "signal":  label,
                "matches": list(set(matches))[:3],
            })
            seen.add(label)
    return found


# ═══════════════════════════════════════════════════════════════
# CONFIDENCE ENGINE  (from confidence_engine.py)
# ═══════════════════════════════════════════════════════════════

def calculate_confidence(credibility_score, doc_count, signal_count):
    """
    Calculate intelligence confidence score.

    Weights:
      credibility  50% — how reliable are the sources
      signal       30% — how many strong signals detected
      correlation  20% — how many documents corroborate the topic
    """
    # Correlation: more documents = higher corroboration
    correlation = min(doc_count * 10, 100) / 100

    # Signal strength: more signals = stronger intelligence
    signal_strength = min(signal_count * 8, 100)

    confidence = (
        credibility_score * 0.50 +
        correlation       * 20   +   # scale 0-1 → 0-20
        signal_strength   * 0.30
    )
    return round(min(confidence, 100), 2)


# ═══════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════

def load_json(path, label):
    """Load a JSON file, return [] or {} on missing/error."""
    if not os.path.exists(path):
        print(f"  ⚠ {label} not found at '{path}' — skipping.")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  ✔ Loaded {label} ({len(data)} records)")
        return data
    except Exception as e:
        print(f"  ⚠ Could not load {label}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# FUSION ENGINE — CORE
# ═══════════════════════════════════════════════════════════════

def fuse(keywords_data, cred_data, monitored_data,
         trend_data, topic_data):
    """
    Fuse all data sources into Intelligence Objects per topic.
    Returns list of intelligence objects.
    """

    # ── Build credibility lookup: source_id → record ──────────
    cred_lookup = {}
    if cred_data:
        for item in cred_data:
            sid = item.get("source_id", "")
            if sid:
                cred_lookup[sid] = item

    # ── Build trend lookup: topic → trend record ──────────────
    trend_lookup = {}
    if trend_data:
        for t in trend_data:
            trend_lookup[t.get("topic", "")] = t

    # ── Group keyword documents by topic ──────────────────────
    topic_docs = defaultdict(list)
    if keywords_data:
        for doc in keywords_data:
            topic = doc.get("metadata", {}).get("topic", "Unknown")
            topic_docs[topic].append(doc)

    # ── Group monitored articles by topic ──────────────────────
    monitored_by_topic = defaultdict(list)
    if monitored_data:
        for item in monitored_data:
            t = item.get("topic", "Unknown")
            monitored_by_topic[t].append(item)

    # ── Collect all topics from all sources ───────────────────
    all_topics = set(topic_docs.keys()) | set(monitored_by_topic.keys())
    if not all_topics:
        print("  ⚠ No topics found in any data source.")
        return []

    intelligence_objects = []
    fused_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for topic in sorted(all_topics):
        if topic in ("Unknown", ""):
            continue

        print(f"\n  🔗 Fusing topic: {topic}")

        # ── Collect all text content for this topic ───────────
        all_text_chunks = []

        # From keyword pipeline docs
        kw_docs = topic_docs.get(topic, [])
        for doc in kw_docs:
            content = doc.get("content", "")
            if content:
                all_text_chunks.append(content[:2000])

        # From monitored articles
        mon_docs = monitored_by_topic.get(topic, [])
        for item in mon_docs:
            t = item.get("title", "")
            s = item.get("summary", "")
            if t or s:
                all_text_chunks.append(f"{t}. {s}")

        full_text = " ".join(all_text_chunks)

        # ── Keywords — aggregate from all sources ─────────────
        kw_freq = defaultdict(int)
        for doc in kw_docs:
            for kw in doc.get("metadata", {}).get("keywords", []):
                if isinstance(kw, str) and len(kw) > 2:
                    kw_freq[kw.lower()] += 1
        for item in mon_docs:
            for kw in item.get("keywords", []):
                if isinstance(kw, str) and len(kw) > 2:
                    kw_freq[kw.lower()] += 1
        top_keywords = [k for k, _ in
                        sorted(kw_freq.items(),
                               key=lambda x: -x[1])[:15]]

        # ── Phrases — from keyword pipeline only ──────────────
        phrase_freq = defaultdict(int)
        for doc in kw_docs:
            for ph in doc.get("metadata", {}).get("phrases", []):
                if isinstance(ph, str):
                    phrase_freq[ph.lower()] += 1
        top_phrases = [p for p, _ in
                       sorted(phrase_freq.items(),
                              key=lambda x: -x[1])[:8]]

        # ── Entities — extract from all text ──────────────────
        entities = extract_entities(full_text)
        print(f"     Entities: {sum(len(v) for v in entities.values())} found")

        # ── Signals — detect from all text ────────────────────
        signals = detect_signals(full_text)
        print(f"     Signals : {len(signals)} detected")

        # ── Credibility — from source_credibility.json ─────────
        cred_scores = []
        source_records = []
        for doc in kw_docs:
            sid = doc.get("source_id", "")
            if sid in cred_lookup:
                cr = cred_lookup[sid]
                cred_scores.append(cr["final_score"])
                source_records.append({
                    "source_id":   sid,
                    "title":       doc.get("title", ""),
                    "channel":     cr.get("channel", ""),
                    "category":    cr.get("category", ""),
                    "score":       cr["final_score"],
                    "label":       cr.get("credibility_label", ""),
                })

        # Also add scores from monitored results
        for item in mon_docs:
            cred_obj = item.get("credibility", {})
            score = cred_obj.get("final_score", 0)
            if score:
                cred_scores.append(score)

        avg_cred = round(sum(cred_scores) / len(cred_scores), 2) \
                   if cred_scores else 0.0
        cred_label = (
            "Very High" if avg_cred >= 90 else
            "High"      if avg_cred >= 75 else
            "Medium"    if avg_cred >= 55 else
            "Low"       if avg_cred >= 35 else "Very Low"
        )

        # ── Confidence score ───────────────────────────────────
        total_docs   = len(kw_docs) + len(mon_docs)
        confidence   = calculate_confidence(avg_cred, total_docs,
                                            len(signals))
        conf_level   = (
            "VERY HIGH" if confidence >= 90 else
            "HIGH"      if confidence >= 75 else
            "MEDIUM"    if confidence >= 60 else "LOW"
        )

        # ── Trend data ─────────────────────────────────────────
        trend_info = {}
        if topic in trend_lookup:
            tr = trend_lookup[topic]
            trend_info = {
                "direction":    tr.get("trend", "Unknown"),
                "growth_rate":  tr.get("growth_rate", 0.0),
                "mentions":     tr.get("mentions", []),
                "current":      tr.get("current_mentions", 0),
            }
        elif mon_docs:
            trend_info = {
                "direction":   "Active",
                "growth_rate": 0.0,
                "mentions":    [len(mon_docs)],
                "current":     len(mon_docs),
            }

        # ── Summary — best LLM summary or auto-generated ───────
        summary = ""
        for doc in kw_docs:
            s = doc.get("nlp_features", {}).get("summary", "")
            if s and len(s) > 20:
                summary = s
                break
        if not summary and top_keywords:
            summary = (f"Intelligence fusion for '{topic}' topic. "
                       f"Key terms: {', '.join(top_keywords[:5])}. "
                       f"{len(signals)} signals detected across "
                       f"{total_docs} sources.")

        # ── Build Intelligence Object ──────────────────────────
        intel_obj = {
            "topic":    topic,
            "summary":  summary,
            "entities": entities,
            "keywords": top_keywords,
            "phrases":  top_phrases,
            "signals":  signals,
            "credibility": {
                "average":      avg_cred,
                "label":        cred_label,
                "source_count": len(cred_scores),
            },
            "confidence":       confidence,
            "confidence_level": conf_level,
            "trend":            trend_info,
            "document_count": {
                "from_pipeline":  len(kw_docs),
                "from_monitor":   len(mon_docs),
                "total":          total_docs,
            },
            "sources":   source_records,
            "fused_at":  fused_at,
        }

        intelligence_objects.append(intel_obj)
        print(f"     Credibility: {avg_cred} ({cred_label})")
        print(f"     Confidence : {confidence} ({conf_level})")

    return intelligence_objects


# ═══════════════════════════════════════════════════════════════
# REPORT PRINTER
# ═══════════════════════════════════════════════════════════════

def print_report(objects):
    print("\n")
    print("═" * 65)
    print("  INTELLIGENCE FUSION REPORT")
    print("═" * 65)

    for obj in objects:
        print(f"\n┌─ TOPIC: {obj['topic'].upper()}")
        print(f"│  Confidence   : {obj['confidence']} — {obj['confidence_level']}")
        print(f"│  Credibility  : {obj['credibility']['average']} "
              f"({obj['credibility']['label']}) "
              f"| {obj['credibility']['source_count']} sources")
        print(f"│  Documents    : {obj['document_count']['total']} total "
              f"({obj['document_count']['from_pipeline']} pipeline + "
              f"{obj['document_count']['from_monitor']} monitored)")

        if obj["trend"]:
            print(f"│  Trend        : {obj['trend'].get('direction','—')} "
                  f"(growth: {obj['trend'].get('growth_rate',0):.1f}%)")

        print(f"│")
        print(f"│  Summary      : {obj['summary'][:120]}")

        if obj["keywords"]:
            print(f"│  Keywords     : {', '.join(obj['keywords'][:8])}")
        if obj["phrases"]:
            print(f"│  Phrases      : {', '.join(obj['phrases'][:5])}")

        ents = obj["entities"]
        if ents.get("people"):
            print(f"│  People       : {', '.join(ents['people'][:5])}")
        if ents.get("organizations"):
            print(f"│  Orgs         : {', '.join(ents['organizations'][:5])}")
        if ents.get("locations"):
            print(f"│  Locations    : {', '.join(ents['locations'][:5])}")
        if ents.get("technologies"):
            print(f"│  Technologies : {', '.join(ents['technologies'][:5])}")

        if obj["signals"]:
            print(f"│  Signals ({len(obj['signals'])})  :")
            for sig in obj["signals"][:5]:
                print(f"│    • {sig['signal']}")

        print(f"└{'─' * 63}")

    print(f"\n{'─' * 65}")
    print(f"  Total Intelligence Objects : {len(objects)}")
    print(f"  Output saved to            : {OUTPUT_FILE}")
    print(f"{'─' * 65}\n")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Intelligence Fusion Engine")
    parser.add_argument("--input-keywords",  default=DEFAULT_KEYWORDS_FILE)
    parser.add_argument("--input-cred",      default=DEFAULT_CRED_FILE)
    parser.add_argument("--input-monitored", default=DEFAULT_MONITORED_FILE)
    parser.add_argument("--input-trends",    default=DEFAULT_TREND_FILE)
    parser.add_argument("--input-topics",    default=DEFAULT_TOPIC_FILE)
    args = parser.parse_args()

    print("\n📂 Intelligence Fusion Engine")
    print("─" * 65)
    print("Loading data sources...\n")

    keywords_data  = load_json(args.input_keywords,  "Keywords pipeline")
    cred_data      = load_json(args.input_cred,      "Source credibility")
    monitored_data = load_json(args.input_monitored, "Monitored results")
    trend_data     = load_json(args.input_trends,    "Trend results")
    topic_data     = load_json(args.input_topics,    "Topic results")

    if not any([keywords_data, monitored_data]):
        print("\n❌ No usable data found. "
              "Need at least keywords or monitored results.")
        sys.exit(1)

    print("\n─" * 33)
    print("Fusing intelligence objects...\n")

    objects = fuse(keywords_data or [], cred_data or [],
                   monitored_data or [], trend_data or [],
                   topic_data or [])

    if not objects:
        print("❌ No intelligence objects could be created.")
        sys.exit(1)

    # Save JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(objects, f, ensure_ascii=False, indent=2)

    # Print report
    print_report(objects)


if __name__ == "__main__":
    main()
