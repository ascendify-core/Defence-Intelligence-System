"""
convert_to_master.py
Converts scraped YouTube transcript JSON (audio.json format) to the Master.json schema.

Usage:
    python convert_to_master.py                          # uses default input/output
    python convert_to_master.py input.json output.json   # custom paths
"""

import json
import sys
import re
from datetime import datetime, timezone


# ── Language detection (simple heuristic, no external libs needed) ─────────────
DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')

def detect_language(text: str) -> str:
    """Returns 'hi' for Hindi (Devanagari script), 'en' otherwise."""
    devanagari_chars = len(DEVANAGARI_RANGE.findall(text))
    total_alpha = len(re.findall(r'[a-zA-Z\u0900-\u097F]', text))
    if total_alpha == 0:
        return "unknown"
    ratio = devanagari_chars / total_alpha
    if ratio > 0.6:
        return "hi"
    elif ratio > 0.2:
        return "hi-en"   # code-switched / Hinglish
    return "en"


def tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer."""
    return [t for t in re.split(r'\s+', text.strip()) if t]


def extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """
    Frequency-based keyword extraction (no NLTK needed).
    Strips common stopwords and returns top-N words.
    """
    stopwords = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with",
        "is","are","was","were","be","been","being","have","has","had","do",
        "does","did","will","would","could","should","may","might","shall",
        "that","this","these","those","it","its","we","our","they","their",
        "he","his","she","her","you","your","i","me","my","very","so","now",
        "just","also","here","there","then","than","how","what","which","who",
        "from","by","as","if","not","no","more","some","any","all","about",
        # Hindi stopwords (transliterated)
        "yeh","hai","hain","ka","ki","ke","se","mein","ko","ne","ek","aur",
        "nahi","bhi","par","ho","jo","koi","kya","toh","woh","hum","tum",
    }
    words = re.findall(r'\b[a-zA-Z\u0900-\u097F]{3,}\b', text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq, key=lambda w: freq[w], reverse=True)
    return sorted_words[:top_n]


def infer_topic(title: str) -> str:
    """Map video title keywords to a broad topic label."""
    title_lower = title.lower()
    if any(k in title_lower for k in ["navy","airforce","army","operation","defence","military","rafale","drone","missile"]):
        return "Defense & Military"
    if any(k in title_lower for k in ["pakistan","india","china","war","border","sindoor"]):
        return "Geopolitics"
    if any(k in title_lower for k in ["fit","health","wellness","sport"]):
        return "Health & Fitness"
    return "News & Current Affairs"


def convert_entry(entry: dict, scrape_date: str) -> dict:
    video_id    = entry.get("video_id", "")
    title       = entry.get("video_title", "")
    content     = entry.get("transcript_text", "")
    source_type = entry.get("source_type", "video")

    source_url  = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    tokens      = tokenize(content)
    word_count  = len(tokens)
    char_count  = len(content)
    lang        = detect_language(content)
    keywords    = extract_keywords(content)
    topic       = infer_topic(title)

    return {
        "source_id":   video_id,
        "source_type": source_type,
        "source_url":  source_url,
        "title":       title,
        "content":     content,
        "timestamp":   "",          # not available from scraper output
        "language":    lang,

        "metadata": {
            "author":           "",
            "publisher":        "YouTube",
            "duration":         "",
            "word_count":       word_count,
            "character_count":  char_count,
            "topic":            topic,
            "keywords":         keywords,
            "tags":             [],
            "location":         "",
            "scrape_date":      scrape_date,
            "file_format":      "video/mp4",
            "confidence_score": 0.0     # set by ASR pipeline
        },

        "nlp_features": {
            "tokens":            tokens,
            "lemmas":            [],    # requires spaCy / NLP pipeline
            "entities":          [],    # requires NER model
            "sentiment":         "",
            "sentiment_score":   0.0,
            "summary":           "",
            "language_detected": lang,
            "readability_score": 0.0,
            "emotion":           "",
            "categories":        [topic]
        }
    }


def convert(input_path: str, output_path: str) -> None:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]   # single-entry file

    scrape_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    converted   = [convert_entry(entry, scrape_date) for entry in data]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    print(f"✅ Converted {len(converted)} entries → {output_path}")


def convert_folder(folder_path: str, output_path: str) -> None:
    """Process all .json files in a folder into a single master output."""
    import os
    all_entries = []
    scrape_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    json_files = sorted([
        f for f in os.listdir(folder_path)
        if f.endswith(".json") and not f.startswith("master")
    ])

    if not json_files:
        print(f"⚠️  No .json files found in '{folder_path}'")
        return

    for filename in json_files:
        filepath = os.path.join(folder_path, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = [data]
            entries = [convert_entry(e, scrape_date) for e in data]
            all_entries.extend(entries)
            print(f"  ✔ {filename} → {len(entries)} entries")
        except Exception as e:
            print(f"  ✘ {filename} → skipped ({e})")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Total: {len(all_entries)} entries from {len(json_files)} files → {output_path}")


if __name__ == "__main__":
    import os

    arg1 = sys.argv[1] if len(sys.argv) > 1 else "."
    output_file = sys.argv[2] if len(sys.argv) > 2 else "master_output.json"

    # If arg1 is a directory → batch mode; if it's a file → single file mode
    if os.path.isdir(arg1):
        print(f"📂 Batch mode: processing all .json files in '{arg1}'\n")
        convert_folder(arg1, output_file)
    else:
        convert(arg1, output_file)
