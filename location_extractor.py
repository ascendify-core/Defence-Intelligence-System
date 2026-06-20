"""
location_extractor.py — Geographical Location Extractor
=========================================================
Defence Intelligence Platform | Entity Extraction Team

What this does:
  1. Reads all collected intelligence files
  2. Extracts geographical locations from content:
       - Countries, Cities, States
       - Borders (LOC, LAC, etc.)
       - Military Bases, Airports, Ports
  3. Validates each location using Nominatim (OpenStreetMap / GeoPy)
  4. Adds latitude, longitude, and location type
  5. Saves geo_coordinates.json

Usage:
  Run on all collected files:
      python location_extractor.py

  Run on a specific file:
      python location_extractor.py --input monitored_results.json

  Run on a single piece of text:
      python location_extractor.py --text "Indian Navy conducted exercise near Kochi"

  Skip geocoding (faster, no internet needed):
      python location_extractor.py --no-geo
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# LOCATION VOCABULARY
# Organised by category for defence intelligence
# ═══════════════════════════════════════════════════════════════

COUNTRIES = [
    "India", "Pakistan", "China", "Russia", "USA", "United States",
    "France", "Israel", "Iran", "Afghanistan", "Bangladesh", "Nepal",
    "Sri Lanka", "Maldives", "Myanmar", "Bhutan", "UAE", "Saudi Arabia",
    "UK", "United Kingdom", "Germany", "Japan", "South Korea", "North Korea",
    "Turkey", "Ukraine", "Taiwan",
]

INDIAN_STATES = [
    "Jammu and Kashmir", "Jammu", "Kashmir", "Ladakh", "Punjab", "Haryana",
    "Rajasthan", "Gujarat", "Maharashtra", "Goa", "Karnataka", "Kerala",
    "Tamil Nadu", "Andhra Pradesh", "Telangana", "Odisha", "West Bengal",
    "Assam", "Arunachal Pradesh", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Sikkim", "Tripura", "Uttarakhand", "Uttar Pradesh",
    "Madhya Pradesh", "Chhattisgarh", "Jharkhand", "Bihar", "Delhi",
    "Himachal Pradesh",
]

CITIES = [
    # Indian cities — defence relevant
    "New Delhi", "Delhi", "Mumbai", "Bengaluru", "Bangalore", "Chennai",
    "Hyderabad", "Kolkata", "Pune", "Ahmedabad", "Srinagar", "Jammu",
    "Leh", "Kargil", "Pathankot", "Ambala", "Hindon", "Jodhpur",
    "Jaisalmer", "Bikaner", "Barmer", "Adampur", "Halwara", "Nal",
    "Uttarlai", "Bhuj", "Jamnagar", "Porbandar", "Okha", "Karwar",
    "Kochi", "Visakhapatnam", "Vizag", "Mumbai", "Chennai", "Kolkata",
    "Port Blair", "Guwahati", "Tezpur", "Jorhat", "Dibrugarh",
    "Siliguri", "Bagdogra", "Gorakhpur", "Agra", "Gwalior", "Bhopal",
    "Nagpur", "Pune", "Nashik", "Deolali", "Kalyan", "Dehradun",
    "Chandigarh", "Amritsar", "Ludhiana", "Bathinda", "Fazilka",
    "Ferozepur", "Gurdaspur", "Kathua", "Udhampur", "Ratnuchak",
    "Pahalgam", "Baramulla", "Kupwara", "Poonch", "Rajouri",
    # Pakistani cities
    "Islamabad", "Karachi", "Lahore", "Rawalpindi", "Peshawar",
    "Quetta", "Multan", "Faisalabad", "Sialkot", "Gujranwala",
    # Chinese cities / regions
    "Beijing", "Shanghai", "Xinjiang", "Tibet", "Lhasa", "Aksai Chin",
    "Depsang", "Galwan", "Daulat Beg Oldie", "DBO",
    # Other capitals/cities
    "Kabul", "Dhaka", "Kathmandu", "Colombo", "Naypyidaw", "Thimphu",
    "Moscow", "Washington", "London", "Paris", "Tel Aviv", "Tehran",
    "Ankara", "Taipei", "Seoul", "Tokyo", "Riyadh", "Abu Dhabi", "Dubai",
]

BORDERS_AND_LINES = [
    "Line of Control", "LOC", "LoC", "Line of Actual Control", "LAC",
    "International Border", "IB", "Wagah", "Attari", "Zero Line",
    "Siachen", "Saltoro Ridge", "Sir Creek", "Doklam", "Galwan Valley",
    "Shaksgam Valley", "Aksai Chin", "Arunachal Pradesh", "McMahon Line",
    "Durand Line",
]

MILITARY_BASES = [
    # IAF Bases
    "Pathankot Air Base", "Pathankot",
    "Ambala Air Base", "Ambala",
    "Hindon Air Base", "Hindon",
    "Jodhpur Air Base", "Jodhpur",
    "Jaisalmer Air Base", "Jaisalmer",
    "Adampur Air Base", "Adampur",
    "Halwara Air Base", "Halwara",
    "Srinagar Air Base",
    "Leh Air Base", "Leh",
    "Tezpur Air Base", "Tezpur",
    "Jorhat Air Base", "Jorhat",
    "Bagdogra Air Base", "Bagdogra",
    "Gorakhpur Air Base",
    "Agra Air Base", "Agra",
    "Gwalior Air Base", "Gwalior",
    "Pune Air Base",
    "Bhuj Air Base", "Bhuj",
    "Nal Air Base",
    "Uttarlai Air Base", "Uttarlai",
    "Jamnagar Air Base", "Jamnagar",
    "Kalaikunda Air Base",
    "Hashimara Air Base",
    "Bareilly Air Base",
    # Naval Bases
    "INS Vikramaditya", "INS Vikrant",
    "INS Kadamba", "Karwar Naval Base",
    "INS Kochi", "Kochi Naval Base",
    "INS Visakhapatnam", "Vizag Naval Base", "Visakhapatnam Naval Base",
    "INS Chennai",
    "INS Andaman", "Port Blair Naval Base",
    "INS Rajali", "Arakkonam",
    # Army
    "Nagrota", "Yol", "Joshimath", "Daulat Beg Oldie",
    "Depsang Plains", "Pangong Tso",
]

AIRPORTS = [
    "Indira Gandhi International Airport", "IGI Airport",
    "Chhatrapati Shivaji International Airport", "CSIA",
    "Kempegowda International Airport",
    "Chennai International Airport",
    "Rajiv Gandhi International Airport",
    "Netaji Subhas Chandra Bose Airport",
    "Sardar Vallabhbhai Patel International Airport",
    "Calicut International Airport",
    "Cochin International Airport", "Kochi Airport",
    "Amritsar Airport", "Sri Guru Ram Dass Jee International Airport",
    "Chandigarh Airport",
    "Srinagar Airport",
    "Leh Kushok Bakula Rimpochee Airport", "Leh Airport",
    "Pathankot Airport",
    "Adampur Airport",
    "Halwara Airport",
    "Jodhpur Airport",
    "Jaisalmer Airport",
    "Visakhapatnam Airport",
    "Port Blair Airport",
    "Guwahati Airport", "Lokpriya Gopinath Bordoloi Airport",
    "Karachi Airport", "Islamabad Airport", "Lahore Airport",
    "Beijing Capital Airport", "Shanghai Pudong Airport",
]

PORTS = [
    "Mumbai Port", "Nhava Sheva", "JNPT",
    "Chennai Port", "Ennore Port",
    "Kochi Port", "Cochin Port",
    "Visakhapatnam Port", "Vizag Port",
    "Kolkata Port", "Haldia Port",
    "Paradip Port",
    "Kandla Port", "Mundra Port",
    "New Mangalore Port",
    "Mormugao Port",
    "Tuticorin Port", "V.O.Chidambaranar Port",
    "Port Blair",
    "Karwar Port",
    "Karachi Port",
    "Gwadar Port",
    "Hambantota Port",
    "Colombo Port",
    "Chittagong Port",
]

# ── Combined location dictionary ──────────────────────────────
LOCATION_DB = {}
for loc in COUNTRIES:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "Country"}
for loc in INDIAN_STATES:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "State"}
for loc in CITIES:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "City"}
for loc in BORDERS_AND_LINES:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "Border/Line"}
for loc in MILITARY_BASES:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "Military Base"}
for loc in AIRPORTS:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "Airport"}
for loc in PORTS:
    LOCATION_DB[loc.lower()] = {"name": loc, "type": "Port"}

# ── Country lookup ─────────────────────────────────────────────
CITY_COUNTRY = {
    # Indian
    "new delhi":"India","delhi":"India","mumbai":"India","bengaluru":"India",
    "bangalore":"India","chennai":"India","hyderabad":"India","kolkata":"India",
    "pune":"India","ahmedabad":"India","srinagar":"India","jammu":"India",
    "leh":"India","kargil":"India","pathankot":"India","ambala":"India",
    "hindon":"India","jodhpur":"India","jaisalmer":"India","adampur":"India",
    "halwara":"India","karwar":"India","kochi":"India","visakhapatnam":"India",
    "vizag":"India","port blair":"India","guwahati":"India","tezpur":"India",
    "jorhat":"India","bagdogra":"India","agra":"India","gwalior":"India",
    "siliguri":"India","chandigarh":"India","amritsar":"India","ludhiana":"India",
    "pahalgam":"India","baramulla":"India","kupwara":"India","poonch":"India",
    "rajouri":"India","udhampur":"India","nagrota":"India","bikaner":"India",
    "barmer":"India","bhuj":"India","jamnagar":"India","nagpur":"India",
    "dehradun":"India","gorakhpur":"India","bhopal":"India","nashik":"India",
    "arakkonam":"India","dbo":"India","daulat beg oldie":"India",
    "galwan":"India","pangong":"India","doklam":"India","siachen":"India",
    "aksai chin":"India","arunachal pradesh":"India",
    # Pakistan
    "islamabad":"Pakistan","karachi":"Pakistan","lahore":"Pakistan",
    "rawalpindi":"Pakistan","peshawar":"Pakistan","quetta":"Pakistan",
    "multan":"Pakistan","faisalabad":"Pakistan","sialkot":"Pakistan",
    "gwadar":"Pakistan",
    # China
    "beijing":"China","shanghai":"China","lhasa":"China","xinjiang":"China",
    "tibet":"China",
    # Others
    "kabul":"Afghanistan","dhaka":"Bangladesh","kathmandu":"Nepal",
    "colombo":"Sri Lanka","moscow":"Russia","washington":"USA",
    "london":"UK","paris":"France","tel aviv":"Israel","tehran":"Iran",
    "ankara":"Turkey","taipei":"Taiwan","seoul":"South Korea",
    "tokyo":"Japan","riyadh":"Saudi Arabia","abu dhabi":"UAE","dubai":"UAE",
}


# ═══════════════════════════════════════════════════════════════
# EXTRACTION ENGINE
# ═══════════════════════════════════════════════════════════════

def extract_locations(text):
    """
    Extract all geographical locations from text.
    Returns a list of dicts with name, type, country.
    """
    found    = {}
    text_l   = text.lower()

    # Scan all known locations (longest match first to avoid partial matches)
    all_locs = sorted(LOCATION_DB.keys(), key=len, reverse=True)

    for loc_key in all_locs:
        # Use word-boundary matching
        pattern = r'\b' + re.escape(loc_key) + r'\b'
        if re.search(pattern, text_l):
            info = LOCATION_DB[loc_key]
            name = info["name"]
            ltype = info["type"]

            # Avoid duplicates — skip if a longer version already captured
            already = any(
                name.lower() in k or k in name.lower()
                for k in found
                if k != name.lower()
            )
            if not already:
                country = CITY_COUNTRY.get(loc_key, "")
                if ltype == "Country":
                    country = name
                elif ltype == "State":
                    country = "India"
                elif ltype in ("Military Base", "Airport", "Port", "Border/Line"):
                    country = CITY_COUNTRY.get(loc_key, "India")

                found[name.lower()] = {
                    "location": name,
                    "type":     ltype,
                    "country":  country,
                }

    return list(found.values())


def extract_context(text, location_name, window=80):
    """Extract a short sentence snippet around the location mention."""
    idx = text.lower().find(location_name.lower())
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end   = min(len(text), idx + len(location_name) + window)
    snippet = text[start:end].strip()
    # Clean up partial words at edges
    snippet = re.sub(r'^\S+\s', '', snippet) if start > 0 else snippet
    snippet = re.sub(r'\s\S+$',  '', snippet) if end < len(text) else snippet
    return f"...{snippet}..."


# ═══════════════════════════════════════════════════════════════
# GEOCODING — Nominatim via GeoPy
# ═══════════════════════════════════════════════════════════════

# Manual coordinate cache for common defence locations
# Prevents API calls for well-known places and avoids rate limits
COORD_CACHE = {
    "india":           (20.5937, 78.9629),
    "pakistan":        (30.3753, 69.3451),
    "china":           (35.8617, 104.1954),
    "russia":          (61.5240, 105.3188),
    "usa":             (37.0902, -95.7129),
    "france":          (46.2276, 2.2137),
    "israel":          (31.0461, 34.8516),
    "iran":            (32.4279, 53.6880),
    "new delhi":       (28.6139, 77.2090),
    "delhi":           (28.7041, 77.1025),
    "mumbai":          (19.0760, 72.8777),
    "bengaluru":       (12.9716, 77.5946),
    "bangalore":       (12.9716, 77.5946),
    "chennai":         (13.0827, 80.2707),
    "hyderabad":       (17.3850, 78.4867),
    "kolkata":         (22.5726, 88.3639),
    "pune":            (18.5204, 73.8567),
    "srinagar":        (34.0837, 74.7973),
    "jammu":           (32.7266, 74.8570),
    "leh":             (34.1526, 77.5771),
    "kargil":          (34.5539, 76.1349),
    "pathankot":       (32.2643, 75.6421),
    "ambala":          (30.3782, 76.7767),
    "hindon":          (28.6979, 77.3890),
    "jodhpur":         (26.2389, 73.0243),
    "jaisalmer":       (26.9157, 70.9083),
    "adampur":         (31.4338, 75.7588),
    "halwara":         (30.7450, 75.6470),
    "tezpur":          (26.6528, 92.7926),
    "jorhat":          (26.7509, 94.2037),
    "bagdogra":        (26.6812, 88.3286),
    "agra":            (27.1767, 78.0081),
    "gwalior":         (26.2183, 78.1828),
    "bhuj":            (23.2500, 69.6667),
    "jamnagar":        (22.4707, 70.0577),
    "kochi":           (9.9312, 76.2673),
    "visakhapatnam":   (17.6868, 83.2185),
    "vizag":           (17.6868, 83.2185),
    "port blair":      (11.6234, 92.7265),
    "guwahati":        (26.1445, 91.7362),
    "chandigarh":      (30.7333, 76.7794),
    "amritsar":        (31.6340, 74.8723),
    "pahalgam":        (34.0159, 75.3150),
    "baramulla":       (34.1996, 74.3428),
    "kupwara":         (34.5256, 74.2617),
    "poonch":          (33.7726, 74.0979),
    "rajouri":         (33.3768, 74.3099),
    "udhampur":        (32.9167, 75.1333),
    "islamabad":       (33.7294, 73.0931),
    "karachi":         (24.8607, 67.0011),
    "lahore":          (31.5204, 74.3587),
    "rawalpindi":      (33.6007, 73.0679),
    "beijing":         (39.9042, 116.4074),
    "shanghai":        (31.2304, 121.4737),
    "lhasa":           (29.6520, 91.1721),
    "kabul":           (34.5553, 69.2075),
    "dhaka":           (23.8103, 90.4125),
    "kathmandu":       (27.7172, 85.3240),
    "colombo":         (6.9271, 79.8612),
    "moscow":          (55.7558, 37.6173),
    "washington":      (38.9072, -77.0369),
    "london":          (51.5074, -0.1278),
    "paris":           (48.8566, 2.3522),
    "tel aviv":        (32.0853, 34.7818),
    "tehran":          (35.6892, 51.3890),
    "ankara":          (39.9334, 32.8597),
    "taipei":          (25.0320, 121.5654),
    "seoul":           (37.5665, 126.9780),
    "tokyo":           (35.6762, 139.6503),
    "dubai":           (25.2048, 55.2708),
    "karwar":          (14.8136, 74.1240),
    "gwadar":          (25.1216, 62.3254),
    "siachen":         (35.4220, 76.9580),
    "galwan":          (34.7333, 78.2333),
    "depsang":         (35.3333, 77.9167),
    "aksai chin":      (35.0000, 79.5000),
    "doklam":          (27.2500, 88.9167),
    "loc":             (34.0000, 74.5000),
    "lac":             (34.5000, 78.0000),
    "line of control": (34.0000, 74.5000),
    "line of actual control": (34.5000, 78.0000),
    "wagah":           (31.6048, 74.5655),
    "nagrota":         (32.6500, 75.0000),
    "dbo":             (35.3500, 77.8000),
    "daulat beg oldie":(35.3500, 77.8000),
    "pangong":         (33.7500, 78.9167),
    "arakkonam":       (13.0500, 79.6700),
}

def geocode_location(location_name, use_api=True):
    """
    Get latitude/longitude for a location.
    First checks local cache, then calls Nominatim API if needed.
    Returns (lat, lon, source) or (None, None, "not_found").
    """
    key = location_name.lower().strip()

    # Check local cache first
    if key in COORD_CACHE:
        lat, lon = COORD_CACHE[key]
        return lat, lon, "cache"

    if not use_api:
        return None, None, "not_found"

    # Call Nominatim (OpenStreetMap) via GeoPy
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError

        geolocator = Nominatim(user_agent="defence_intelligence_platform_v1")
        # Add "India" as bias for ambiguous names
        query = location_name
        location = geolocator.geocode(query, timeout=10)
        if location:
            COORD_CACHE[key] = (location.latitude, location.longitude)
            return location.latitude, location.longitude, "nominatim"

        # Retry with India suffix if first attempt fails
        location = geolocator.geocode(f"{location_name}, India", timeout=10)
        if location:
            COORD_CACHE[key] = (location.latitude, location.longitude)
            return location.latitude, location.longitude, "nominatim"

        return None, None, "not_found"

    except Exception as e:
        return None, None, f"error: {str(e)[:40]}"


# ═══════════════════════════════════════════════════════════════
# DOCUMENT PROCESSING
# ═══════════════════════════════════════════════════════════════

def process_document(doc, use_geo=True):
    """Extract locations from a single document and geocode them."""
    title   = doc.get("title", "") or ""
    summary = doc.get("summary", "") or ""
    content = doc.get("content", "") or ""
    url     = doc.get("url", "") or doc.get("source_url", "")
    doc_id  = doc.get("doc_id", "") or doc.get("source_id", "")

    full_text = f"{title}. {summary}. {content}".strip()
    locations = extract_locations(full_text)

    results = []
    for loc in locations:
        lat, lon, geo_src = geocode_location(loc["location"], use_api=use_geo)
        context = extract_context(full_text, loc["location"])

        entry = {
            "doc_id":       doc_id,
            "source_url":   url,
            "title":        title[:100],
            "location":     loc["location"],
            "type":         loc["type"],
            "country":      loc["country"],
            "context":      context[:200],
            "latitude":     lat,
            "longitude":    lon,
            "geo_source":   geo_src,
            "validated":    lat is not None,
        }
        results.append(entry)

        # Rate limit: 1 req/sec for Nominatim fair use
        if geo_src == "nominatim":
            time.sleep(1.1)

    return results


# ═══════════════════════════════════════════════════════════════
# FILE LOADERS
# ═══════════════════════════════════════════════════════════════

def load_file(path):
    """Load any of the pipeline JSON files."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # Handle intelligence_query_results.json structure
        return data.get("results", [data])
    return data if isinstance(data, list) else [data]


# ═══════════════════════════════════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════════════════════════════════

OUTPUT_FILE = "geo_coordinates.json"

INPUT_FILES = [
    "monitored_results.json",
    "ingested_dataa_master_keywords.json",
    "intelligence_output.json",
    "intelligence_query_results.json",
    "source_credibility.json",
]

def run(input_path=None, text_input=None, use_geo=True):
    print(f"\n{'═'*62}")
    print(f"  Defence Intelligence — Location Extractor")
    print(f"{'═'*62}")

    all_results  = []
    location_freq = defaultdict(int)

    # ── Mode 1: single text input ────────────────────────────
    if text_input:
        print(f"\n  📝 Analysing text input...")
        doc = {"title": "Manual Input", "summary": text_input,
               "content": "", "url": "", "doc_id": "manual"}
        results = process_document(doc, use_geo=use_geo)
        all_results.extend(results)
        for r in results:
            location_freq[r["location"]] += 1
            validated = "✔" if r["validated"] else "✖"
            print(f"    {validated} {r['location']:<30} [{r['type']:<15}] "
                  f"Country: {r['country']}")
            if r["latitude"]:
                print(f"       Lat: {r['latitude']:.4f}  Lon: {r['longitude']:.4f}  "
                      f"(via {r['geo_source']})")

    # ── Mode 2: specific file ────────────────────────────────
    elif input_path:
        docs = load_file(input_path)
        print(f"\n  📂 Processing: {input_path} ({len(docs)} docs)")
        for i, doc in enumerate(docs, 1):
            results = process_document(doc, use_geo=use_geo)
            all_results.extend(results)
            for r in results:
                location_freq[r["location"]] += 1
            if results:
                locs = ", ".join(r["location"] for r in results[:4])
                print(f"  [{i:03d}] {doc.get('title','')[:50]}")
                print(f"        → {locs}")

    # ── Mode 3: all pipeline files ───────────────────────────
    else:
        for fpath in INPUT_FILES:
            if not os.path.exists(fpath):
                print(f"  ⚠ Not found (skip): {fpath}")
                continue
            docs = load_file(fpath)
            print(f"\n  📂 {fpath} — {len(docs)} documents")
            for i, doc in enumerate(docs, 1):
                results = process_document(doc, use_geo=use_geo)
                all_results.extend(results)
                for r in results:
                    location_freq[r["location"]] += 1
                if results:
                    locs = ", ".join(r["location"] for r in results[:4])
                    title = doc.get("title","")[:50]
                    print(f"  [{i:03d}] {title}")
                    print(f"        → {locs}")

    # ── Deduplicate by location name ──────────────────────────
    seen_keys = set()
    unique_results = []
    for r in all_results:
        key = (r["location"].lower(), r.get("doc_id",""))
        if key not in seen_keys:
            seen_keys.add(key)
            unique_results.append(r)

    # ── Build summary ─────────────────────────────────────────
    by_type = defaultdict(list)
    by_country = defaultdict(list)
    for r in unique_results:
        by_type[r["type"]].append(r["location"])
        if r["country"]:
            by_country[r["country"]].append(r["location"])

    summary = {
        "generated_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_extractions":len(unique_results),
        "unique_locations":  len(location_freq),
        "geocoded":          sum(1 for r in unique_results if r["validated"]),
        "by_type": {
            k: list(dict.fromkeys(v))
            for k, v in sorted(by_type.items())
        },
        "by_country": {
            k: list(dict.fromkeys(v))[:10]
            for k, v in sorted(by_country.items(), key=lambda x: -len(x[1]))
        },
        "top_locations": [
            {"location": loc, "mentions": cnt}
            for loc, cnt in sorted(location_freq.items(),
                                   key=lambda x: -x[1])[:20]
        ],
        "results": unique_results,
    }

    # ── Save ──────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # ── Print summary ─────────────────────────────────────────
    print(f"\n{'─'*62}")
    print(f"  ✅ Done — {len(unique_results)} location extractions")
    print(f"  📍 Unique locations: {len(location_freq)}")
    print(f"  🌐 Geocoded: {summary['geocoded']} locations")
    print(f"  💾 Saved → {OUTPUT_FILE}")

    print(f"\n── Top Locations Mentioned ──────────────────────────────")
    for item in summary["top_locations"][:12]:
        bar = "█" * min(item["mentions"], 10)
        print(f"  {item['location']:<28} {bar} ({item['mentions']})")

    print(f"\n── By Type ──────────────────────────────────────────────")
    for ltype, locs in summary["by_type"].items():
        print(f"  {ltype:<18} {len(locs):>3}  →  {', '.join(locs[:5])}")

    print(f"\n── By Country ───────────────────────────────────────────")
    for country, locs in list(summary["by_country"].items())[:8]:
        print(f"  {country:<16} {len(locs):>3} locations")

    print()
    return summary


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Defence Intelligence Location Extractor")
    parser.add_argument("--input",  type=str,
                        help="Specific JSON file to process")
    parser.add_argument("--text",   type=str,
                        help="Raw text to extract locations from")
    parser.add_argument("--no-geo", action="store_true",
                        help="Skip geocoding (faster, offline mode)")
    args = parser.parse_args()

    use_geo = not args.no_geo
    if not use_geo:
        print("  ℹ  Geocoding disabled (--no-geo). Coordinates from cache only.")

    run(
        input_path  = args.input,
        text_input  = args.text,
        use_geo     = use_geo,
    )


if __name__ == "__main__":
    main()
