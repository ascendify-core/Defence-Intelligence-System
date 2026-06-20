"""
credibility_engine.py  (Day 5 — Source Credibility Scoring)
Team 1 – Source Credibility Team

Pipeline:
  1. Read ingested_dataa_master_keywords.json (output from v8 pipeline)
  2. Identify channel for each YouTube video
  3. Assign credibility category and base score
  4. Apply content-based modifiers
  5. Output source_credibility.json

Scoring Model:
  Government Source  = 95
  Verified Media     = 85
  Known Blog         = 60
  Unknown Source     = 30

Usage:
    python credibility_engine.py
    python credibility_engine.py --input ingested_dataa_master_keywords.json
    python credibility_engine.py --input ingested_dataa_master_keywords.json --report
"""

import json
import os
import sys
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════
# ── STEP 1: CHANNEL MAPPING TABLE ───────────────────────────
# Fill in the channel name for each video ID below.
# To find the channel: open youtube.com/watch?v=<VIDEO_ID>
# and note the channel name shown under the video title.
# ═══════════════════════════════════════════════════════════════

VIDEO_TO_CHANNEL = {
    "KkgSOzFZG-g": "HW News English",   # #Shorts | Indian Navy's Warning...
    "hAyYQT5gr1c": "ET Now",            # India Eyes 114 Rafales...
    "iJwzKd2CJPY": "NEWS9 Live",        # Drone provides real-time intelligence...
    "_Ah0weIMrYk": "ANI News",          # Some people very close to me said...
    "K08GpKx5OJM": "Hindustan Times",   # What PM Modi Told Pakistan...
    "04sNLYhCenM": "ANI News",          # Insights on India's Kiran MK-II...
    "hLbNKU4TSJI": "India Today",       # IAF Chief AP Singh: Rafale...
    "bC_m1bd_emg": "India Today",       # India Shot Down High-tech Pakistani Jets...
    "rKSRxl-54sM": "The Buzz",          # List of all Indian air defense systems
    "FykUA3wD1o4": "The War Index",     # India's Air Defense Can Stop Anything
    "ckAedg7-EYk": "StudyIQ IAS",       # How India Protects Its Skies?
    "Tcc2-6V6LI8": "WION",              # Indian Air Force Wants to Acquire S-400
    "2lrnVAsiF0M": "WION",              # IAF Releases Official Video of Sudarshan
    "u4iVgP-Zueg": "Orbital Defense",   # India 8 Most Powerful Air Defense Systems
    "4gMn97Lvye0": "The Hindu",         # Guardians of the skies
    "scILbvGT0_c": "SosinIAS Academy",  # India's Air Defence Shield Inside IACCS
    "ub-WKCevFUw": "IndiRoutes",        # Indian Air Force Gets BIG Tactical Boost
    "lNwqG4zR77c": "NewsX Live",        # Rudram-2 Missile Test
}

# ═══════════════════════════════════════════════════════════════
# ── STEP 2: CHANNEL CREDIBILITY DATABASE ────────────────────
# Maps channel names to their credibility category.
# Add more channels here as needed.
# ═══════════════════════════════════════════════════════════════

CHANNEL_CREDIBILITY = {
    # ── Government / Official Sources (Score: 95) ─────────────
    "PIB India":                    "Government Source",
    "PIB":                          "Government Source",
    "DD News":                      "Government Source",
    "Doordarshan National":         "Government Source",
    "Ministry of Defence":          "Government Source",
    "Press Information Bureau":     "Government Source",
    "Indian Air Force":             "Government Source",
    "Indian Navy":                  "Government Source",
    "Indian Army":                  "Government Source",
    "DRDO":                         "Government Source",
    "Sansad TV":                    "Government Source",
    "Rajya Sabha TV":               "Government Source",
    "Lok Sabha TV":                 "Government Source",

    # ── Verified / Major News Media (Score: 85) ───────────────
    # ── Channels identified in this dataset ──────────────────
    "HW News English":              "Unknown Source",    # ← corrected: unrecognised channel
    "ET Now":                       "Verified Media",    # Economic Times TV — major business/news
    "NEWS9 Live":                   "Verified Media",    # News9, Times Network group
    "ANI News":                     "Verified Media",    # Asian News International — wire agency
    "Hindustan Times":              "Verified Media",    # Major national newspaper/media
    "India Today":                  "Verified Media",    # Major national news channel
    "WION":                         "Verified Media",    # World Is One News — international
    "NewsX Live":                   "Verified Media",    # National news channel
    "The Hindu":                    "Verified Media",    # Major national newspaper
    "The Buzz":                     "Unknown Source",    # ← corrected: unrecognised channel
    "The War Index":                "Known Blog",        # Defence analysis channel
    "StudyIQ IAS":                  "Known Blog",        # Educational/IAS prep channel
    "Orbital Defense":              "Unknown Source",    # ← corrected: unrecognised channel
    "SosinIAS Academy":             "Known Blog",        # Educational/IAS prep channel
    "IndiRoutes":                   "Unknown Source",    # ← corrected: unrecognised channel
    # ── Standard channels ─────────────────────────────────────
    "NDTV":                         "Verified Media",
    "NDTV India":                   "Verified Media",
    "India Today":                  "Verified Media",
    "Aaj Tak":                      "Verified Media",
    "Republic TV":                  "Verified Media",
    "Republic World":               "Verified Media",
    "Times Now":                    "Verified Media",
    "Mirror Now":                   "Verified Media",
    "CNN-News18":                   "Verified Media",
    "News18 India":                 "Verified Media",
    "Zee News":                     "Verified Media",
    "Zee Business":                 "Verified Media",
    "ANI News":                     "Verified Media",
    "The Hindu":                    "Verified Media",
    "Hindustan Times":              "Verified Media",
    "The Print":                    "Verified Media",
    "The Wire":                     "Verified Media",
    "Wion":                         "Verified Media",
    "WION":                         "Verified Media",
    "Al Jazeera English":           "Verified Media",
    "BBC News India":               "Verified Media",
    "Reuters":                      "Verified Media",

    # ── Known Defence / Analysis Channels (Score: 60) ─────────
    "Defence Decode":               "Known Blog",
    "National Defence":             "Known Blog",
    "Indian Defence Updates":       "Known Blog",
    "Indian Defence News":          "Known Blog",
    "Abhijit Chavda":               "Known Blog",
    "Geopolitics In Depth":         "Known Blog",
    "Defence XP":                   "Known Blog",
    "Defenceview":                  "Known Blog",
    "Manohar Parrikar Institute":   "Known Blog",
    "IDSA":                         "Known Blog",
    "StratNewsGlobal":              "Known Blog",
    "Chanakya Forum":               "Known Blog",
    "The Quint":                    "Known Blog",
    "Firstpost":                    "Known Blog",
    "Newsx":                        "Known Blog",
}

# ── Base scores per category ──────────────────────────────────
BASE_SCORES = {
    "Government Source": 95,
    "Verified Media":    85,
    "Known Blog":        60,
    "Unknown Source":    30,
}

# ── Credibility labels by score range ────────────────────────
def score_to_label(score: int) -> str:
    if score >= 90: return "Very High"
    if score >= 75: return "High"
    if score >= 55: return "Medium"
    if score >= 35: return "Low"
    return "Very Low"


# ═══════════════════════════════════════════════════════════════
# ── STEP 3: CONTENT-BASED MODIFIERS ─────────────────────────
# These adjust the base score based on document quality signals
# from the v8 keyword extraction pipeline output.
# ═══════════════════════════════════════════════════════════════

def compute_modifiers(doc: dict) -> dict:
    """
    Analyse document content signals and return score modifiers.
    All modifiers are additive (can be negative).
    """
    metadata    = doc.get("metadata", {})
    nlp         = doc.get("nlp_features", {})
    keywords    = metadata.get("keywords", [])
    phrases     = metadata.get("phrases", [])
    summary     = nlp.get("summary", "")
    word_count  = metadata.get("word_count", 0)
    entities    = nlp.get("entities", [])

    modifiers = {}

    # Positive: has meaningful IAF keywords extracted
    if len(keywords) >= 5:
        modifiers["rich_keywords"] = +5
    elif len(keywords) >= 2:
        modifiers["has_keywords"] = +3
    else:
        modifiers["no_keywords"] = 0

    # Positive: has multi-word military phrases
    if len(phrases) >= 3:
        modifiers["rich_phrases"] = +5
    elif len(phrases) >= 1:
        modifiers["has_phrases"] = +3
    else:
        modifiers["no_phrases"] = 0

    # Positive: LLM generated a summary (content was substantial enough)
    if summary and len(summary.split()) >= 8:
        modifiers["has_summary"] = +3

    # Positive: named entities detected (suggests real reporting)
    if len(entities) >= 5:
        modifiers["rich_entities"] = +3
    elif len(entities) >= 2:
        modifiers["has_entities"] = +1

    # Negative: very short content (likely a short/clip)
    if word_count < 50:
        modifiers["very_short_content"] = -15
    elif word_count < 150:
        modifiers["short_content"] = -8

    # Negative: title contains #Shorts (YouTube short = low depth)
    title = doc.get("title", "").lower()
    if "#shorts" in title or "#short" in title:
        modifiers["is_short_video"] = -10

    return modifiers


# ═══════════════════════════════════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════════════════════════════════

def resolve_channel(video_id: str) -> tuple:
    """
    Return (channel_name, category) for a given video ID.
    Uses VIDEO_TO_CHANNEL mapping + CHANNEL_CREDIBILITY database.
    """
    channel = VIDEO_TO_CHANNEL.get(video_id, "Unknown")
    if channel == "Unknown":
        return channel, "Unknown Source"
    category = CHANNEL_CREDIBILITY.get(channel, "Unknown Source")
    return channel, category


def score_document(doc: dict) -> dict:
    """Score a single document and return credibility record."""
    video_id   = doc.get("source_id", "")
    title      = doc.get("title", "")
    source_url = doc.get("source_url", "")
    language   = doc.get("language", "")

    channel, category = resolve_channel(video_id)
    base_score        = BASE_SCORES.get(category, 30)
    modifiers         = compute_modifiers(doc)
    modifier_total    = sum(modifiers.values())

    # Clamp final score to 0-100
    final_score = max(0, min(100, base_score + modifier_total))
    label       = score_to_label(final_score)

    return {
        "source_id":         video_id,
        "title":             title,
        "source_url":        source_url,
        "language":          language,
        "channel":           channel,
        "category":          category,
        "base_score":        base_score,
        "modifiers":         modifiers,
        "modifier_total":    modifier_total,
        "final_score":       final_score,
        "credibility_label": label,
    }


def run(input_path: str, save_report: bool = False):
    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        documents = json.load(f)
    if isinstance(documents, dict):
        documents = [documents]

    print(f"\n📂 Input  : {input_path}")
    print(f"📄 Docs   : {len(documents)}")
    print("─" * 60)

    # ── Warn if channel table is mostly unfilled ──────────────
    unknown_count = sum(1 for v in VIDEO_TO_CHANNEL.values() if v == "Unknown")
    if unknown_count > 0:
        print(f"\n⚠  {unknown_count}/{len(VIDEO_TO_CHANNEL)} channels not yet identified.")
        print("   Open each YouTube link, note the channel name,")
        print("   and fill in the VIDEO_TO_CHANNEL table at the top of this file.")
        print("   Unidentified videos will score as 'Unknown Source' (30).\n")
    print("─" * 60)

    results = []
    category_counts = {}

    for doc in documents:
        record = score_document(doc)
        results.append(record)
        cat = record["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

        title_short = record["title"][:52] + "..." if len(record["title"]) > 52 else record["title"]
        print(f"  {record['final_score']:>3}/100  [{record['credibility_label']:<9}]  "
              f"{record['category']:<18}  {title_short}")

    # ── Save output ───────────────────────────────────────────
    output_path = "source_credibility.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n  💾 Saved → {output_path}")

    # ── Summary ───────────────────────────────────────────────
    avg_score = sum(r["final_score"] for r in results) / len(results) if results else 0
    print("\n" + "─" * 60)
    print(f"✅ Done — {len(results)} sources scored | Avg score: {avg_score:.1f}/100")

    print("\n── Category Breakdown ───────────────────────────────────")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        score = BASE_SCORES.get(cat, 30)
        print(f"   {cat:<22} {count:>2} docs  (base score: {score})")

    print("\n── Top Credibility Scores ───────────────────────────────")
    for r in sorted(results, key=lambda x: -x["final_score"])[:5]:
        print(f"   {r['final_score']:>3}  {r['credibility_label']:<9}  {r['title'][:55]}")

    print("\n── Lowest Credibility Scores ────────────────────────────")
    for r in sorted(results, key=lambda x: x["final_score"])[:5]:
        print(f"   {r['final_score']:>3}  {r['credibility_label']:<9}  {r['title'][:55]}")

    # ── Optional detailed report ──────────────────────────────
    if save_report:
        report = {
            "generated_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_sources":    len(results),
            "average_score":    round(avg_score, 2),
            "category_counts":  category_counts,
            "score_distribution": {
                "Very High (90-100)": sum(1 for r in results if r["final_score"] >= 90),
                "High (75-89)":       sum(1 for r in results if 75 <= r["final_score"] < 90),
                "Medium (55-74)":     sum(1 for r in results if 55 <= r["final_score"] < 75),
                "Low (35-54)":        sum(1 for r in results if 35 <= r["final_score"] < 55),
                "Very Low (0-34)":    sum(1 for r in results if r["final_score"] < 35),
            },
            "sources": results,
        }
        report_path = "source_credibility_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  📊 Report → {report_path}")

    print()


if __name__ == "__main__":
    input_path  = sys.argv[1] if len(sys.argv) > 1 else "ingested_dataa_master_keywords.json"
    save_report = "--report" in sys.argv
    run(input_path, save_report)
