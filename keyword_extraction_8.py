"""
keyword_extraction.py  (v8 — phrase blocklist, prompt-leak guard, mistral-ready)
Pipeline: ingested_data.json → Master JSON → IAF Keyword + Phrase Extraction

Steps:
  1. Convert ingested_data.json to Master JSON schema
  2. Filter out off-topic documents  (TF-IDF relevance signals)
  3. Extract IAF/defence keywords (English + Hindi) using TF-IDF whitelist
  4. Detect multi-word IAF defence phrases
  5. LLM (Ollama): generates one-line intelligence summary per document
  6. Save outputs and keyword report

Usage:
    python keyword_extraction.py ingested_data.json
    python keyword_extraction.py ingested_data.json --top 10 --report
    python keyword_extraction.py ingested_data.json --report --no-llm   ← skip LLM
    python keyword_extraction.py ingested_data.json --report --llm-model mistral
"""

import json
import re
import sys
import math
import os
from collections import defaultdict
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════
# OLLAMA LLM — SUMMARY ONLY  (v7)
#
# Design decision: llama3.2 is too small for reliable structured
# keyword validation — it over-rejects, hallucinates, and produces
# inconsistent JSON. Instead we use it for ONE thing it does well:
# writing a concise intelligence summary of the document.
# TF-IDF + domain whitelist own ALL keyword and phrase decisions.
# ═══════════════════════════════════════════════════════════════

def ollama_available(model="llama3.2"):
    """Return True if ollama library is importable and server is reachable."""
    try:
        import ollama
        ollama.list()
        return True
    except Exception:
        return False


def llm_summarize(title: str, content_snippet: str, model: str = "llama3.2") -> str:
    """
    Ask Ollama to write a single intelligence-analyst summary sentence.
    Returns empty string on any failure — never raises.
    """
    import ollama
    prompt = (
        f"You are an Indian Air Force intelligence analyst. "
        f"Write exactly ONE sentence (max 20 words) summarising the key military/defence "
        f"significance of this document. Be specific. No preamble.\n\n"
        f"Title: {title}\n"
        f"Content: {content_snippet[:1200]}"
    )
    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        summary = response["message"]["content"].strip().strip('"\'')
        # Cap at 30 words just in case
        return " ".join(summary.split()[:30])
    except Exception:
        return ""

# ═══════════════════════════════════════════════════════════════
# STEP 1 — CONVERSION
# ═══════════════════════════════════════════════════════════════

DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')

def detect_language(text):
    devanagari = len(DEVANAGARI_RANGE.findall(text))
    total = len(re.findall(r'[a-zA-Z\u0900-\u097F]', text))
    if total == 0: return "unknown"
    ratio = devanagari / total
    if ratio > 0.6:   return "hi"
    elif ratio > 0.2: return "hi-en"
    return "en"

def convert_entry(entry, scrape_date):
    video_id    = entry.get("video_id", "")
    title       = entry.get("video_title", "")
    content     = entry.get("transcript_text", "")
    source_type = entry.get("source_type", "video")
    source_url  = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    lang        = detect_language(content)
    return {
        "source_id":   video_id,
        "source_type": source_type,
        "source_url":  source_url,
        "title":       title,
        "content":     content,
        "timestamp":   "",
        "language":    lang,
        "metadata": {
            "author":           "",
            "publisher":        "YouTube",
            "duration":         "",
            "word_count":       len(content.split()),
            "character_count":  len(content),
            "topic":            "",
            "keywords":         [],
            "phrases":          [],
            "tags":             [],
            "location":         "",
            "scrape_date":      scrape_date,
            "file_format":      "video/mp4",
            "confidence_score": 0.0
        },
        "nlp_features": {
            "tokens":            [],
            "lemmas":            [],
            "entities":          [],
            "sentiment":         "",
            "sentiment_score":   0.0,
            "summary":           "",
            "language_detected": lang,
            "readability_score": 0.0,
            "emotion":           "",
            "categories":        []
        }
    }

def convert_all(raw_data):
    scrape_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    converted = [convert_entry(e, scrape_date) for e in raw_data]
    print(f"  ✔ Converted {len(converted)} records to Master JSON schema")
    return converted


# ═══════════════════════════════════════════════════════════════
# IAF DOMAIN VOCABULARY (English + Hindi)
# ═══════════════════════════════════════════════════════════════

IAF_DOMAIN_TERMS = {
    # Aircraft & platforms
    "rafale","rafales","tejas","sukhoi","mirage","jaguar","mig","hercules",
    "ilyushin","chinook","apache","chetak","dhruv","lca","mrfa","amca",
    "tapas","archer","rustom","ghatak","ucav","awacs","aew","isr","tanker",
    "gripen","typhoon","hornet","growler","flanker","fulcrum","bison","kiran",
    # Missiles & weapons
    "missile","missiles","bvr","astra","python","derby","mica","meteor",
    "brahmos","nirbhay","rudram","spice","hammer","scalp","storm","shadow",
    "payload","warhead","seeker","guidance","infrared","homing",
    "anti","radiation","sead","suppression","jamming","decoy",
    "interceptor","interceptors","downed","planes","wreckage",
    # Air defence systems
    "s400","s300","barak","akash","mrsam","lrsam","qrsam","vshorad",
    "spyder","igla","manpad","sam","patriot","thaad","iaccs","adcc",
    "iads","shield","layer","intercept","engagement","radars","airspace",
    "intercepted","intercepting","threats",
    # Technology
    "electronic","warfare","ecm","eccm","radar","rwr","maws","irst",
    "datalink","encrypted","stealth","signature","rcs","avionics",
    "supercruise","thrust","vectoring","aesa","pesa","sensor","fusion",
    "network","centric","kaveri","shakti","indigenous","tara","tarang",
    # Organisations
    "bel","drdo","hal","dassault","saab","boeing","lockheed","eurofighter",
    # Operations & doctrine
    "sindoor","sindhu","operation","strike","sortie","mission","patrol",
    "precision","standoff","combat","deterrence","retaliation","escalation",
    "capability","capabilities","operational","deployment","deployed",
    "acquisition","squadrons","squadron","lethal",
    # Adversary systems
    "j10","j20","j35","fc31","pl15","pl12","jf17","thunder","f16","f17",
    "hq9","hq19","kj500","pakistani","pakistan",
    # People & roles in IAF context
    "abinandan","marshal","pilots","pilot","commander","chief",
    "airbase","command","integrated",
    # Hindi / Devanagari IAF terms
    "मिसाइल","मिसाइल्स","राडार","रडार","विमान","लड़ाकू","वायुसेना",
    "रक्षा","ऑपरेशन","मिशन","पायलट","एयरक्राफ्ट","फाइटर","ड्रोन",
    "आकाश","ब्रह्मोस","रुद्रम","अस्त्र","बराक","इलेक्ट्रॉनिक",
    "डिफेंस","एयरबेस","स्ट्राइक","सिंदूर","रॉकेट","ट्रेनिंग",
    "सिस्टम","रेंज","इंटरसेप्टर","स्क्वाड्रन","तेजस","किरण",
    "सुखोई","मिराज","इलेक्ट्र","रिकनेसेंस","विंग","मार्क",
    "सिस्टम्स","मिसाइल्स",
}

IAF_PHRASES = [
    "air defence", "air defense", "electronic warfare", "air superiority",
    "air dominance", "operation sindoor", "precision strike", "beyond visual range",
    "surface to air missile", "air to air missile", "air to ground missile",
    "airborne early warning", "stealth fighter", "radar cross section",
    "missile defence", "missile defense", "drone swarm", "network centric warfare",
    "combat air patrol", "integrated air defence", "integrated air defense",
    "active electronically scanned array", "electronic countermeasures",
    "suppression of enemy air defences", "standoff weapon", "stand off weapon",
    "beyond visual range missile", "fly by wire", "thrust vector control",
    "data link", "sensor fusion", "air power", "air strike", "air base",
    "fighter jet", "fighter aircraft", "unmanned aerial vehicle",
    "unmanned combat aerial vehicle", "air force base", "air chief marshal",
    "squadron leader", "wing commander", "air marshal",
    "s400 missile system", "akash missile", "brahmos missile",
    "rudram missile", "astra missile", "rafale fighter",
    "tejas fighter", "indigenous fighter", "make in india defence",
    "वायु रक्षा", "इलेक्ट्रॉनिक युद्ध", "वायु श्रेष्ठता",
    "मिसाइल रक्षा", "ड्रोन हमला", "हवाई हमला", "वायुसेना अभियान",
    "लड़ाकू विमान", "रक्षा प्रणाली", "वायु शक्ति",
]


# ═══════════════════════════════════════════════════════════════
# STEP 2 — RELEVANCE FILTER
# ═══════════════════════════════════════════════════════════════

IAF_RELEVANCE_SIGNALS = {
    "iaf","air force","airforce","indian air","squadron","airbase","air base",
    "air defence","air defense","fighter","jet","aircraft","pilot","sortie",
    "mission","operation","strike","intercept","rafale","tejas","sukhoi",
    "mirage","mig","hercules","chinook","apache","awacs","lca","amca","ucav",
    "drone","uav","missile","missiles","radar","s400","akash","barak","mrsam",
    "qrsam","rudram","astra","brahmos","spice","electronic warfare","jamming",
    "sead","iaccs","adcc","iads","drdo","hal","bel","dassault","saab",
    "sindoor","abhinandan","balakot","air marshal","air chief",
}

OFFTOPIC_SIGNALS = {
    "marathon","fitness","fit","running","song","music","comedy","kapil",
    "celebrity","actor","actress","chef","cook","recipe","diet","fashion",
    "lifestyle","motivation","happiness","mental health","yoga","meditation",
    "gym","workout","weight","cricket","football","bollywood","netflix",
    "amazon","movie","film","series","comedy show",
}

def is_iaf_relevant(doc):
    title   = doc.get("title", "").lower()
    content = doc.get("content", "").lower()
    if any(sig in title for sig in OFFTOPIC_SIGNALS):
        return False
    if any(sig in title for sig in IAF_RELEVANCE_SIGNALS):
        return True
    if any(sig in content[:500] for sig in IAF_RELEVANCE_SIGNALS):
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# STEP 3 — KEYWORD + PHRASE EXTRACTION (TF-IDF)
# ═══════════════════════════════════════════════════════════════

STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","are","was","were","be","been","being","have","has","had","do",
    "does","did","will","would","could","should","may","might","shall",
    "that","this","these","those","it","its","we","our","they","their",
    "he","his","she","her","you","your","i","me","my","very","so","now",
    "just","also","here","there","then","than","how","what","which","who",
    "from","by","as","if","not","no","more","some","any","all","about",
    "up","out","into","over","after","before","between","through","during",
    "each","other","both","few","most","such","only","own","same","too",
    "can","said","one","two","three","new","let","even","back","still",
    "well","way","every","never","right","since","without","while","off",
    "down","get","got","going","go","come","comes","came","make","made",
    "take","know","think","look","see","say","give","want","need","use",
    "keep","work","put","set","much","many","another","however","whether",
    "always","actually","really","quite","simply","clearly","effectively",
    "currently","recently","exactly","significantly","certainly","obviously",
    "um","uh","okay","alright","yeah","yes","right","well","like","bit",
    "lot","thing","things","people","person","time","times","place","day",
    "days","year","years","number","part","parts","line","music","song",
    "applause","comment","channel","video","watch","hello","hey","hi",
    "bye","thank","thanks","join","start","talk","hear","show","mean",
    "call","ask","answer","making","taking","giving","trying","subscribe",
    "india","indian","force","system","systems","country","government",
    "national","world","news","report","today","latest","big","high",
    "long","large","small","major","key","main","real","true","important",
    "netflix","youtube","instagram","facebook","twitter","whatsapp",
    "surfaceto","airto","groundto","longrange","shortrange",
    "first","second","third","last","next","half",
    "hai","hain","kya","toh","aur","bhi","tha","thi","kar","karo",
    "karna","karta","karti","karte","raha","rahi","rahe","hoga","hogi",
    "honge","hua","hui","hue","yeh","ka","ki","ke","se","mein","ko","ne",
    "ek","nahi","par","ho","jo","koi","hum","tum","nhi",
    "यह","है","हैं","का","की","के","से","में","को","ने","एक","और",
    "नहीं","भी","पर","हो","जो","कोई","क्या","तो","वह","हम","तुम",
    "एंड","दि","ऑफ","इन","इस","ऑन","आर","वी","हैव","टू","वाज",
    "विद","दैट","दिस","फॉर","बट","नॉट","हैड","बीन","दे","वर","डू",
    "बहुत","मतलब","दोस्त","करेग","हमार","बात","साथ","लिए",
}

def is_garbled(token):
    if re.match(r'^[a-z]+$', token):            return len(token) < 4
    if re.match(r'^[\u0900-\u097F]+$', token):  return len(token) < 4
    return True

def is_iaf_term(token):
    t = token.lower()
    for term in IAF_DOMAIN_TERMS:
        if t == term or t.startswith(term) or term in t:
            return True
    return False

def tokenize(text):
    raw = re.findall(r'\b[a-zA-Z\u0900-\u097F]{3,}\b', text.lower())
    return [t for t in raw if t not in STOPWORDS and not is_garbled(t)]

def extract_phrases(text):
    text_lower = text.lower()
    return [phrase for phrase in IAF_PHRASES if phrase in text_lower]


# Phrases that must never appear in output
# Catches: LLM prompt leakage, hallucinated non-IAF phrases, generic terms
_PHRASE_BLOCKLIST = {
    "defence intelligence analyst",  # LLM prompt leaking into output
    "indian airforce",               # concatenated — not valid
    "indian air force",              # too generic
    "defence deal",                  # commercial, not operational
    "make in india",                 # policy slogan
    "mmrca contract",                # procurement term
    "long-range air defense system", # too generic
    "operation sindhu",              # unverified operation name
    "air force",                     # too generic
    "beyond visual",                 # incomplete phrase
    "prevented from coming",         # narrative fragment
    "fly away",                      # procurement term
    "silent sentinel",               # descriptive, not technical
    "digital command center",        # generic IT term
    "primetime press conference",    # media term
}

def filter_phrases(phrases: list) -> list:
    """Remove blocklisted and low-quality phrases from final phrase list."""
    return [p for p in phrases if p.lower().strip() not in _PHRASE_BLOCKLIST]

def compute_tf(tokens):
    if not tokens: return {}
    freq = defaultdict(int)
    for t in tokens: freq[t] += 1
    total = len(tokens)
    return {w: c / total for w, c in freq.items()}

def compute_idf(all_token_sets, vocab):
    N = len(all_token_sets)
    return {
        word: math.log((N + 1) / (sum(1 for ts in all_token_sets if word in ts) + 1)) + 1
        for word in vocab
    }

def tfidf_keywords(tf, idf, top_n):
    scores = {
        w: tf[w] * idf.get(w, 1.0) * 4.0
        for w in tf if is_iaf_term(w)
    }
    top = sorted(scores, key=lambda w: scores[w], reverse=True)[:top_n]
    return [{"keyword": w, "score": round(scores[w], 6)} for w in top]

def infer_topic(title, keywords, phrases):
    combined = (title + " " + " ".join(keywords) + " " + " ".join(phrases)).lower()
    checks = [
        (["rafale","tejas","sukhoi","mirage","mig","fighter","aircraft","jet",
          "squadron","sortie","pilot","airbase","operation","strike","sindoor",
          "missile","radar","s400","akash","barak","iaccs","electronic warfare",
          "drone","uav","ucav","awacs","tarang","rudram","astra","bvr","kiran",
          "tara","air superiority","air dominance","combat air patrol"],
         "Indian Air Force"),
        (["navy","naval","submarine","carrier","frigate","destroyer","maritime"],
         "Indian Navy"),
        (["army","tank","artillery","infantry","soldier","battalion"],
         "Indian Army"),
        (["pakistan","china","geopolit","bilateral","diplomatic","tension"],
         "Geopolitics"),
        (["drdo","hal","bel","indigenous","make in india","defence technology",
          "kaveri","aesa","sensor fusion"],
         "Defence Technology"),
    ]
    for kw_list, label in checks:
        if any(k in combined for k in kw_list):
            return label
    return "Defense & Military"

def extract_entities(text):
    pattern = re.compile(r'\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b')
    noise = {
        "The","A","An","This","That","These","Those","It","We","They","He",
        "She","You","I","But","And","Or","So","If","In","On","At","To",
        "For","Of","With","By","As","From","When","Where","What","How",
        "Why","Which","Who","Now","Just","Also","Here","There",
    }
    seen, entities = set(), []
    for c in pattern.findall(text):
        if c not in noise and c not in seen and len(c) > 3:
            seen.add(c)
            entities.append(c)
    return entities[:20]


# ═══════════════════════════════════════════════════════════════
# STEP 3+4 — EXTRACT + LLM VALIDATE
# ═══════════════════════════════════════════════════════════════

def extract_keywords_and_phrases(documents, top_n, use_llm=True, llm_model="llama3.2"):
    relevant = [doc for doc in documents if is_iaf_relevant(doc)]
    skipped  = [doc for doc in documents if not is_iaf_relevant(doc)]

    print(f"  ✔ {len(relevant)} documents are IAF-relevant")
    print(f"  ✖ {len(skipped)} documents skipped (off-topic)\n")

    if not relevant:
        return [], skipped

    # Check LLM availability once
    if use_llm:
        print(f"  🤖 Checking Ollama ({llm_model})...", end=" ")
        if ollama_available():
            print(f"✔ Connected — LLM validation ENABLED\n")
        else:
            print("✖ Not reachable — falling back to TF-IDF only\n")
            use_llm = False

    # TF-IDF across relevant docs
    all_tokens = [tokenize(doc.get("content", "")) for doc in relevant]
    all_sets   = [set(t) for t in all_tokens]
    vocab      = set(w for tokens in all_tokens for w in tokens)
    idf        = compute_idf(all_sets, vocab)

    enriched = []
    for i, (doc, tokens) in enumerate(zip(relevant, all_tokens)):
        tf             = compute_tf(tokens)
        tfidf_scored   = tfidf_keywords(tf, idf, top_n)
        tfidf_kw_strs  = [k["keyword"] for k in tfidf_scored]
        tfidf_phrases  = filter_phrases(extract_phrases(doc.get("content", "")))

        short = doc["title"][:55] + "..." if len(doc["title"]) > 55 else doc["title"]
        print(f"  [{i+1:02d}/{len(relevant)}] {short}")
        print(f"           TF-IDF Keywords : {', '.join(tfidf_kw_strs[:6]) or 'none'}")
        print(f"           TF-IDF Phrases  : {', '.join(tfidf_phrases[:3]) or 'none'}")

        # ── Keywords & phrases: TF-IDF + whitelist only (deterministic) ─────
        final_keywords = tfidf_kw_strs
        final_phrases  = tfidf_phrases
        final_scored   = [dict(k, source="tfidf") for k in tfidf_scored]

        # ── LLM: summary only ─────────────────────────────────────
        llm_summary = ""
        if use_llm:
            print(f"           🤖 LLM summarising...", end=" ", flush=True)
            llm_summary = llm_summarize(
                title          = doc.get("title", ""),
                content_snippet= doc.get("content", ""),
                model          = llm_model,
            )
            print("done")

        topic    = infer_topic(doc.get("title", ""), final_keywords, final_phrases)
        entities = extract_entities(doc.get("content", ""))

        doc["metadata"]["keywords"]              = final_keywords
        doc["metadata"]["phrases"]               = final_phrases
        doc["metadata"]["topic"]                 = topic
        doc["nlp_features"]["tokens"]            = tokens[:200]
        doc["nlp_features"]["entities"]          = entities
        doc["nlp_features"]["categories"]        = [topic]
        doc["nlp_features"]["language_detected"] = doc.get("language", "")
        doc["nlp_features"]["keyword_scores"]    = final_scored
        doc["nlp_features"]["summary"]           = llm_summary

        enriched.append(doc)
        print(f"           Keywords : {', '.join(final_keywords[:6]) or 'none'}")
        print(f"           Phrases  : {', '.join(final_phrases[:3]) or 'none'}")
        print(f"           Topic    : {topic}")
        if llm_summary:
            print(f"           Summary  : {llm_summary[:100]}")
        print()

    return enriched, skipped


# ═══════════════════════════════════════════════════════════════
# REPORT BUILDER
# ═══════════════════════════════════════════════════════════════

def build_report(enriched, skipped):
    kw_freq     = defaultdict(int)
    phrase_freq = defaultdict(int)
    doc_summaries = []

    for doc in enriched:
        kws     = doc["metadata"].get("keywords", [])
        phrases = doc["metadata"].get("phrases", [])
        for kw in kws:     kw_freq[kw]     += 1
        for ph in phrases: phrase_freq[ph] += 1
        doc_summaries.append({
            "source_id":      doc.get("source_id", ""),
            "title":          doc.get("title", ""),
            "topic":          doc["metadata"]["topic"],
            "keywords":       kws,
            "phrases":        phrases,
            "keyword_scores": doc["nlp_features"].get("keyword_scores", []),
            "entities":       doc["nlp_features"].get("entities", [])[:10],
            "llm_summary":    doc["nlp_features"].get("summary", ""),
        })

    top_kw  = sorted(kw_freq.items(),     key=lambda x: x[1], reverse=True)[:30]
    top_ph  = sorted(phrase_freq.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        "generated_at":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_documents":     len(enriched) + len(skipped),
        "iaf_relevant":        len(enriched),
        "skipped_offtopic":    len(skipped),
        "skipped_titles":      [d.get("title", "") for d in skipped],
        "corpus_top_keywords": [{"keyword": k, "doc_frequency": v} for k, v in top_kw],
        "corpus_top_phrases":  [{"phrase":  p, "doc_frequency": v} for p, v in top_ph],
        "documents":           doc_summaries,
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    input_path  = sys.argv[1] if len(sys.argv) > 1 else "ingested_data.json"
    top_n       = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 10
    save_report = "--report" in sys.argv
    use_llm     = "--no-llm" not in sys.argv
    llm_model   = sys.argv[sys.argv.index("--llm-model") + 1] if "--llm-model" in sys.argv else "llama3.2"

    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    print(f"\n📂 Input   : {input_path}")
    print(f"🤖 LLM     : {'ollama/' + llm_model if use_llm else 'disabled (--no-llm)'}")
    print("─" * 60)

    # Step 1 — Convert
    with open(input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    print(f"\n[Step 1] Converting {len(raw_data)} records to Master JSON schema...")
    master_docs = convert_all(raw_data)

    master_path = input_path.replace(".json", "_master.json")
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master_docs, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved → {master_path}")

    # Step 2+3+4 — Filter, extract, validate
    print(f"\n[Step 2] Filtering & extracting IAF keywords and phrases...\n")
    enriched, skipped = extract_keywords_and_phrases(
        master_docs, top_n, use_llm=use_llm, llm_model=llm_model
    )

    keywords_path = input_path.replace(".json", "_master_keywords.json")
    with open(keywords_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved → {keywords_path}")

    # Step 5 — Report
    report = build_report(enriched, skipped)

    if save_report:
        report_path = input_path.replace(".json", "_keyword_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  📊 Report → {report_path}")

    # Summary
    print("\n" + "─" * 60)
    print(f"✅ Done — {len(enriched)} IAF-relevant docs | {len(skipped)} skipped")

    print("\n── Corpus Top IAF Keywords ──────────────────────────────")
    for item in report["corpus_top_keywords"][:15]:
        print(f"   {item['keyword']:<25} (in {item['doc_frequency']} docs)")

    print("\n── Corpus Top IAF Phrases ───────────────────────────────")
    for item in report["corpus_top_phrases"][:10]:
        print(f"   {item['phrase']:<35} (in {item['doc_frequency']} docs)")

    if skipped:
        print("\n── Skipped (off-topic) ──────────────────────────────────")
        for d in skipped:
            print(f"   ✖ {d.get('title','')[:60]}")
    print()

if __name__ == "__main__":
    main()
