import os
import sys
import json
import csv
import spacy

# ── Load spaCy model ──────────────────────────────────────────────────────────
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("spaCy model not found. Run: python -m spacy download en_core_web_sm")
    sys.exit(1)

# ── Keyword lists ─────────────────────────────────────────────────────────────
technology_keywords = [
    "AI", "Python", "Java", "C++", "Machine Learning",
    "Deep Learning", "TensorFlow", "PyTorch",
    "Blockchain", "Cloud Computing", "Data Science"
]

event_keywords = [
    "conference", "summit", "hackathon",
    "workshop", "seminar", "olympics",
    "election", "launch", "festival"
]


# ── Universal text extractor ──────────────────────────────────────────────────

def extract_text_from_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    filename = os.path.basename(filepath)

    # ── PDF ───────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(filepath)
            items = []
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    items.append({"title": f"{filename} - Page {i+1}", "text": text})
            doc.close()
            if items:
                return items
        except ImportError:
            print("Tip: pip install pymupdf")
        except Exception as e:
            print(f"PDF read failed: {e}")

    # ── DOCX ──────────────────────────────────────────────────────────────────
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(filepath)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            if text:
                return [{"title": filename, "text": text}]
        except ImportError:
            print("Tip: pip install python-docx")
        except Exception as e:
            print(f"DOCX read failed: {e}")

    # ── XLSX / XLS ────────────────────────────────────────────────────────────
    if ext in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True)
            items = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                rows_text = []
                for row in ws.iter_rows(values_only=True):
                    row_str = " ".join(str(c) for c in row if c is not None)
                    if row_str.strip():
                        rows_text.append(row_str)
                if rows_text:
                    items.append({"title": f"{filename} - Sheet: {sheet}", "text": "\n".join(rows_text)})
            if items:
                return items
        except ImportError:
            print("Tip: pip install openpyxl")
        except Exception as e:
            print(f"Excel read failed: {e}")

    # ── PPTX ──────────────────────────────────────────────────────────────────
    if ext == ".pptx":
        try:
            from pptx import Presentation
            prs = Presentation(filepath)
            items = []
            for i, slide in enumerate(prs.slides):
                texts = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
                if texts:
                    items.append({"title": f"{filename} - Slide {i+1}", "text": "\n".join(texts)})
            if items:
                return items
        except ImportError:
            print("Tip: pip install python-pptx")
        except Exception as e:
            print(f"PPTX read failed: {e}")

    # ── Plain text (txt, csv, json, xml, html, md, log, yaml ...) ────────────
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()

        if ext == ".json" or raw.strip().startswith(("{", "[")):
            try:
                data = json.loads(raw)
                items = extract_text_from_json(data, filename)
                if items:
                    return items
            except json.JSONDecodeError:
                pass

        if raw.strip():
            return [{"title": filename, "text": raw}]

    except UnicodeDecodeError:
        pass

    # ── Latin-1 fallback ─────────────────────────────────────────────────────
    try:
        with open(filepath, "r", encoding="latin-1") as f:
            raw = f.read()
        if raw.strip():
            return [{"title": filename, "text": raw}]
    except Exception:
        pass

    # ── Last resort: raw bytes ────────────────────────────────────────────────
    try:
        import re
        with open(filepath, "rb") as f:
            raw_bytes = f.read()
        printable = "".join(chr(b) for b in raw_bytes if 32 <= b < 127 or b in (9, 10, 13))
        chunks = re.findall(r'[A-Za-z0-9 ,.\-:;\'\"!?]{4,}', printable)
        text = " ".join(chunks)
        if text.strip():
            print(f"Warning: Extracting readable text only from '{filename}'.")
            return [{"title": filename, "text": text}]
    except Exception as e:
        print(f"Failed to read file at byte level: {e}")

    print(f"Could not extract any text from: {filename}")
    return []


def extract_text_from_json(data, filename):
    items = []

    def collect_strings(obj):
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            if "transcript_text" in obj:
                return obj["transcript_text"]
            return " ".join(collect_strings(v) for v in obj.values() if v)
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                text = collect_strings(item)
                if text:
                    title = item.get("video_title", f"Entry {i+1}") if isinstance(item, dict) else f"Entry {i+1}"
                    items.append({"title": title, "text": text})
            return ""
        return ""

    if isinstance(data, list):
        collect_strings(data)
    else:
        text = collect_strings(data)
        if text:
            items.append({"title": filename, "text": text})

    return items if items else []


# ── Entity extractor ──────────────────────────────────────────────────────────

def is_non_english(text):
    return any('\u0900' <= c <= '\u097F' for c in text)


def extract_entities(text):
    doc = nlp(text)
    people, organizations, locations, technologies, events = [], [], [], [], []

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            people.append(ent.text)
        elif ent.label_ == "ORG":
            organizations.append(ent.text)
        elif ent.label_ in ["GPE", "LOC"]:
            locations.append(ent.text)

    for tech in technology_keywords:
        if tech.lower() in text.lower():
            technologies.append(tech)

    for event in event_keywords:
        if event.lower() in text.lower():
            events.append(event)

    return {
        "people":        list(set(people)),
        "organizations": list(set(organizations)),
        "locations":     list(set(locations)),
        "technologies":  list(set(technologies)),
        "events":        list(set(events)),
    }


# ── Output savers ─────────────────────────────────────────────────────────────

def save_results(results, output_path):
    ext = os.path.splitext(output_path)[1].lower()

    # ── JSON ──────────────────────────────────────────────────────────────────
    if ext == ".json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # ── CSV ───────────────────────────────────────────────────────────────────
    elif ext == ".csv":
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "people", "organizations", "locations", "technologies", "events", "note"])
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "title":         r.get("title", ""),
                    "people":        ", ".join(r.get("people", [])),
                    "organizations": ", ".join(r.get("organizations", [])),
                    "locations":     ", ".join(r.get("locations", [])),
                    "technologies":  ", ".join(r.get("technologies", [])),
                    "events":        ", ".join(r.get("events", [])),
                    "note":          r.get("note", ""),
                })

    # ── TXT ───────────────────────────────────────────────────────────────────
    elif ext == ".txt":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("EXTRACTED ENTITIES\n")
            f.write("=" * 60 + "\n")
            for r in results:
                f.write(f"\nTitle         : {r.get('title', '')}\n")
                f.write(f"  People        : {', '.join(r.get('people', [])) or 'None found'}\n")
                f.write(f"  Organizations : {', '.join(r.get('organizations', [])) or 'None found'}\n")
                f.write(f"  Locations     : {', '.join(r.get('locations', [])) or 'None found'}\n")
                f.write(f"  Technologies  : {', '.join(r.get('technologies', [])) or 'None found'}\n")
                f.write(f"  Events        : {', '.join(r.get('events', [])) or 'None found'}\n")
                if r.get("note"):
                    f.write(f"  Note          : {r['note']}\n")

    # ── XML ───────────────────────────────────────────────────────────────────
    elif ext == ".xml":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<results>\n')
            for r in results:
                f.write(f'  <item>\n')
                f.write(f'    <title>{r.get("title", "")}</title>\n')
                f.write(f'    <people>{", ".join(r.get("people", []))}</people>\n')
                f.write(f'    <organizations>{", ".join(r.get("organizations", []))}</organizations>\n')
                f.write(f'    <locations>{", ".join(r.get("locations", []))}</locations>\n')
                f.write(f'    <technologies>{", ".join(r.get("technologies", []))}</technologies>\n')
                f.write(f'    <events>{", ".join(r.get("events", []))}</events>\n')
                if r.get("note"):
                    f.write(f'    <note>{r["note"]}</note>\n')
                f.write(f'  </item>\n')
            f.write('</results>\n')

    # ── Unsupported: save as .txt with warning ────────────────────────────────
    else:
        fallback = output_path + ".txt"
        print(f"Unsupported output format '{ext}'. Saving as plain text: {fallback}")
        save_results(results, fallback)
        return fallback

    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Input file
    filepath = input("Enter the path to your input file: ").strip().strip('"')
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    # Output file
    print("\nWhere do you want to save the results?")
    print("Supported output formats: .txt  .csv  .json  .xml")
    output_path = input("Enter output file path (e.g. results.csv or C:\\Users\\output.txt): ").strip().strip('"')

    print(f"\nProcessing: {filepath}\n")
    items = extract_text_from_file(filepath)

    if not items:
        print("No text could be extracted from this file.")
        sys.exit(1)

    print(f"Found {len(items)} section(s) to process.\n")

    results = []

    for i, item in enumerate(items):
        title = item.get("title", f"Item {i+1}")
        text  = item.get("text", "")

        if not text.strip():
            print(f"[{i+1}] Skipping (empty): {title}")
            continue

        if is_non_english(text):
            print(f"[{i+1}] Skipping (non-English): {title}")
            results.append({
                "title": title,
                "note":  "Skipped - non-English content",
                "people": [], "organizations": [], "locations": [],
                "technologies": [], "events": []
            })
            continue

        entities = extract_entities(text)
        results.append({"title": title, **entities})
        print(f"[{i+1}] Done: {title}")

    # ── Print summary to console ──────────────────────────────────────────────
    print("\n" + "="*60)
    print("EXTRACTED ENTITIES")
    print("="*60)
    for r in results:
        print(f"\nTitle         : {r['title']}")
        print(f"  People        : {r['people']        if r['people']        else 'None found'}")
        print(f"  Organizations : {r['organizations'] if r['organizations'] else 'None found'}")
        print(f"  Locations     : {r['locations']     if r['locations']     else 'None found'}")
        print(f"  Technologies  : {r['technologies']  if r['technologies']  else 'None found'}")
        print(f"  Events        : {r['events']        if r['events']        else 'None found'}")

    # ── Save to user-chosen file ──────────────────────────────────────────────
    saved_to = save_results(results, output_path)
    print(f"\n{'='*60}")
    print(f"Results saved to : {saved_to}")
    print(f"Total processed  : {len(results)}")


if __name__ == "__main__":
    main()