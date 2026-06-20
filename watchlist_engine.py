"""
watchlist_engine.py  —  IAF & Indian Defence Watchlist Management Engine
=========================================================================

Allows analysts to define, manage, and monitor custom intelligence topics.

What this does:
  - Create new watchlists with topic, keywords, sources, alert threshold
  - Edit existing watchlists (add/remove keywords, change settings)
  - Delete watchlists
  - View all watchlists and their status
  - Run a watchlist against existing intelligence data
    (reads monitored_results.json + intelligence_output.json if available)

Watchlist Structure:
  {
    "id":             "WL_001",
    "topic":          "Drone Activity",
    "description":    "Track UAV incursions at India borders",
    "keywords":       ["drone", "uav", "surveillance"],
    "sources":        ["pib", "ani", "google_news"],
    "alert_threshold": "MEDIUM",
    "active":         true,
    "created_at":     "2025-06-16T08:00:00Z",
    "updated_at":     "2025-06-16T08:00:00Z",
    "created_by":     "Analyst 1",
    "match_count":    0
  }

Usage:
  python watchlist_engine.py                    # interactive menu
  python watchlist_engine.py --list             # show all watchlists
  python watchlist_engine.py --run              # run all watchlists against data
  python watchlist_engine.py --run --id WL_001 # run one specific watchlist
"""

import os
import re
import sys
import json
import uuid
import argparse
from datetime import datetime, timezone
from collections import defaultdict

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

WATCHLIST_FILE  = "watchlists.json"
MONITORED_FILE  = "monitored_results.json"
INTEL_FILE      = "intelligence_output.json"

AVAILABLE_SOURCES = {
    "pib":         "PIB India (Government — 95/100)",
    "cert_in":     "CERT-In (Cybersecurity Government — 95/100)",
    "ani":         "ANI News (Verified Media — 85/100)",
    "hindu":       "The Hindu (Verified Media — 85/100)",
    "google_news": "Google News (Search Results — 78/100)",
    "youtube":     "YouTube (Platform — 70/100)",
}

ALERT_THRESHOLDS = ["HIGH", "MEDIUM", "LOW"]

# Predefined topic suggestions with starter keywords
TOPIC_SUGGESTIONS = {
    "1":  {
        "topic": "IAF Aircraft & Operations",
        "description": "Track Indian Air Force aircraft deployments and combat operations",
        "keywords": ["rafale", "tejas", "sukhoi", "iaf", "squadron", "sortie", "airbase", "amca", "mirage", "mig", "awacs"],
        "sources": ["pib", "ani", "google_news"],
        "alert_threshold": "MEDIUM",
    },
    "2":  {
        "topic": "Drone Activity",
        "description": "Monitor UAV incursions and counter-drone operations at Indian borders",
        "keywords": ["drone", "uav", "incursion", "swarm", "counter drone", "anti drone", "unmanned", "heron", "rustom"],
        "sources": ["google_news", "pib", "ani"],
        "alert_threshold": "HIGH",
    },
    "3":  {
        "topic": "Cyber Attacks",
        "description": "Track cyber threats targeting Indian defence and government networks",
        "keywords": ["cyber attack", "hack", "malware", "ransomware", "breach", "cert-in", "apt36", "phishing", "intrusion"],
        "sources": ["cert_in", "google_news", "ani"],
        "alert_threshold": "HIGH",
    },
    "4":  {
        "topic": "Border Security",
        "description": "Monitor LoC and LAC activity, ceasefire violations, and troop movements",
        "keywords": ["loc", "lac", "ceasefire violation", "troop deployment", "infiltration", "ladakh", "border patrol"],
        "sources": ["pib", "ani", "hindu"],
        "alert_threshold": "HIGH",
    },
    "5":  {
        "topic": "Missiles & Strategic Weapons",
        "description": "Track Indian missile tests and strategic weapons development",
        "keywords": ["brahmos", "agni", "astra", "missile test", "nirbhay", "rudram", "drdo", "warhead", "bvr"],
        "sources": ["pib", "ani", "google_news"],
        "alert_threshold": "HIGH",
    },
    "6":  {
        "topic": "Air Defence Systems",
        "description": "Monitor India's air defence deployments and adversary threats",
        "keywords": ["s-400", "akash", "mrsam", "barak", "iaccs", "intercept", "air defence", "sam", "qrsam"],
        "sources": ["pib", "ani", "google_news"],
        "alert_threshold": "MEDIUM",
    },
    "7":  {
        "topic": "Space & Satellite Threats",
        "description": "Track ASAT weapons, GPS jamming, and satellite security threats",
        "keywords": ["asat", "satellite", "gps jamming", "spoofing", "isro", "orbital", "counter space", "space debris"],
        "sources": ["pib", "google_news", "ani"],
        "alert_threshold": "MEDIUM",
    },
    "8":  {
        "topic": "Foreign Interference & Espionage",
        "description": "Monitor foreign intelligence operations and espionage targeting India",
        "keywords": ["espionage", "isi", "spy", "honeytrap", "disinformation", "raw", "foreign agent", "intelligence breach"],
        "sources": ["ani", "hindu", "google_news"],
        "alert_threshold": "HIGH",
    },
    "9":  {
        "topic": "Terrorist Activity",
        "description": "Track terror incidents, NIA operations, and militant activity in India",
        "keywords": ["terrorist", "militant", "ied", "fidayeen", "nia operation", "encounter", "infiltration", "lashkar"],
        "sources": ["ani", "pib", "google_news"],
        "alert_threshold": "HIGH",
    },
    "10": {
        "topic": "AI in Defence",
        "description": "Track AI and autonomous systems development in Indian defence",
        "keywords": ["ai", "artificial intelligence", "autonomous", "machine learning", "neural network", "drdo ai", "defence ai"],
        "sources": ["pib", "google_news", "ani"],
        "alert_threshold": "MEDIUM",
    },
    "11": {
        "topic": "Nuclear & Missile Programs",
        "description": "Monitor India and adversary nuclear posture and ballistic missile activity",
        "keywords": ["nuclear", "ballistic missile", "agni", "prithvi", "deterrence", "warhead", "strategic forces"],
        "sources": ["google_news", "ani", "hindu"],
        "alert_threshold": "HIGH",
    },
    "12": {
        "topic": "Electronic Warfare",
        "description": "Track electronic warfare systems, radar developments, and EW operations",
        "keywords": ["electronic warfare", "ecm", "radar", "aesa", "jamming", "stealth", "ew system", "countermeasure"],
        "sources": ["pib", "google_news", "ani"],
        "alert_threshold": "MEDIUM",
    },
}


# ══════════════════════════════════════════════════════════════
# FILE I/O
# ══════════════════════════════════════════════════════════════

def load_watchlists():
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_watchlists(watchlists):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlists, f, ensure_ascii=False, indent=2)

def load_intelligence_records():
    records = []
    for fname in [MONITORED_FILE, INTEL_FILE]:
        if os.path.exists(fname):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for d in data:
                    url   = d.get("source", {}).get("url", d.get("url", "")) if isinstance(d.get("source"), dict) else d.get("url", "")
                    title = d.get("source", {}).get("title", d.get("title", "")) if isinstance(d.get("source"), dict) else d.get("title", "")
                    cred  = d.get("credibility", {})
                    score = cred.get("final_score", 50) if isinstance(cred, dict) else (cred if isinstance(cred, int) else 50)
                    alert = cred.get("alert_level", d.get("alert_level", "MEDIUM")) if isinstance(cred, dict) else d.get("alert_level", "MEDIUM")
                    records.append({
                        "doc_id":       d.get("doc_id", ""),
                        "title":        title,
                        "url":          url,
                        "topic":        d.get("topic", ""),
                        "summary":      d.get("summary", ""),
                        "keywords":     d.get("keywords", []),
                        "credibility":  score,
                        "alert_level":  alert,
                        "collected_at": d.get("collected_at", ""),
                        "source_key":   d.get("source_key", ""),
                    })
            except Exception:
                pass
    # Deduplicate
    seen, out = set(), []
    for r in records:
        did = r.get("doc_id", "")
        if did and did not in seen:
            seen.add(did)
            out.append(r)
    return out


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_id(watchlists):
    nums = []
    for w in watchlists:
        m = re.match(r"WL_(\d+)", w.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    next_num = max(nums) + 1 if nums else 1
    return f"WL_{next_num:03d}"

def find_watchlist(watchlists, wl_id):
    wl_id = wl_id.strip()
    # Accept plain number: "4" → "WL_004"
    if wl_id.isdigit():
        wl_id = f"WL_{int(wl_id):03d}"
    for i, w in enumerate(watchlists):
        if w["id"].upper() == wl_id.upper():
            return i, w
    return None, None

def alert_icon(level):
    return "🔴" if level == "HIGH" else "🟡" if level == "MEDIUM" else "🟢"

def print_bar(char="═", width=64):
    print(char * width)

def print_section(title):
    print_bar()
    print(f"  {title}")
    print_bar("─")

def input_stripped(prompt):
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled.")
        return ""


# ══════════════════════════════════════════════════════════════
# WATCHLIST MATCHING ENGINE
# ══════════════════════════════════════════════════════════════

def match_record(record, watchlist):
    """
    Check if a record matches a watchlist.
    Returns (matched: bool, matched_keywords: list)
    """
    text = (
        record.get("title", "") + " " +
        record.get("summary", "") + " " +
        " ".join(record.get("keywords", []))
    ).lower()

    matched_kw = []
    for kw in watchlist.get("keywords", []):
        if kw.lower() in text:
            matched_kw.append(kw)

    # Source filter — if watchlist specifies sources, only match those
    wl_sources = watchlist.get("sources", [])
    source_key = record.get("source_key", "")
    if wl_sources and source_key and source_key not in wl_sources:
        return False, []

    # Alert threshold filter
    threshold  = watchlist.get("alert_threshold", "LOW")
    rec_alert  = record.get("alert_level", "LOW")
    alert_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    if alert_rank.get(rec_alert, 0) < alert_rank.get(threshold, 0):
        return False, []

    return len(matched_kw) > 0, matched_kw


def run_watchlist(watchlist, records):
    """Run one watchlist against all records. Returns list of matches."""
    matches = []
    for rec in records:
        matched, kws = match_record(rec, watchlist)
        if matched:
            matches.append({
                "doc_id":          rec.get("doc_id", ""),
                "title":           rec.get("title", "")[:80],
                "url":             rec.get("url", ""),
                "alert_level":     rec.get("alert_level", ""),
                "credibility":     rec.get("credibility", 0),
                "collected_at":    rec.get("collected_at", ""),
                "matched_keywords":kws,
            })
    # Sort by credibility descending
    matches.sort(key=lambda x: x["credibility"], reverse=True)
    return matches


# ══════════════════════════════════════════════════════════════
# DISPLAY
# ══════════════════════════════════════════════════════════════

def display_watchlist_card(w, index=None):
    status = "✅ ACTIVE" if w.get("active", True) else "⏸  PAUSED"
    prefix = f"  [{index}] " if index is not None else "  "
    print(f"{prefix}{w['id']}  |  {status}")
    print(f"      Topic       : {w['topic']}")
    print(f"      Description : {w.get('description','—')[:60]}")
    print(f"      Keywords    : {', '.join(w.get('keywords',[])[:6])}" +
          (f" ... +{len(w['keywords'])-6} more" if len(w.get('keywords',[])) > 6 else ""))
    print(f"      Sources     : {', '.join(w.get('sources', ['all']))}")
    print(f"      Alert Level : {alert_icon(w.get('alert_threshold','MEDIUM'))} {w.get('alert_threshold','MEDIUM')}")
    print(f"      Created     : {w.get('created_at','')[:10]}  |  By: {w.get('created_by','Analyst')}")
    print(f"      Matches     : {w.get('match_count', 0)} records found last run")

def display_all_watchlists(watchlists):
    if not watchlists:
        print("\n  No watchlists found. Create one first.")
        return
    print_section(f"ALL WATCHLISTS  ({len(watchlists)} total)")
    active  = sum(1 for w in watchlists if w.get("active", True))
    paused  = len(watchlists) - active
    print(f"  Active: {active}   Paused: {paused}")
    print_bar("─")
    for i, w in enumerate(watchlists, 1):
        display_watchlist_card(w, index=i)
        print()
    print_bar()


# ══════════════════════════════════════════════════════════════
# CREATE WATCHLIST
# ══════════════════════════════════════════════════════════════

def create_watchlist(watchlists):
    print_section("CREATE NEW WATCHLIST")

    print("\n  Choose a starting point:")
    print("  [0] Start from scratch (enter everything manually)")
    for k, v in TOPIC_SUGGESTIONS.items():
        print(f"  [{k}] {v['topic']}")

    choice = input_stripped("\n  Enter number (0-12): ")

    if choice in TOPIC_SUGGESTIONS:
        suggestion = TOPIC_SUGGESTIONS[choice]
        print(f"\n  Using template: {suggestion['topic']}")
        print(f"  You can edit any field. Press Enter to keep the suggested value.\n")
        pre = suggestion
    else:
        pre = {"topic": "", "description": "", "keywords": [], "sources": list(AVAILABLE_SOURCES.keys())[:3], "alert_threshold": "MEDIUM"}

    # ── Topic ─────────────────────────────────────────────────
    topic = input_stripped(f"  Topic name [{pre['topic']}]: ")
    if not topic:
        topic = pre["topic"]
    if not topic:
        print("  ✖ Topic name is required.")
        return

    # ── Description ───────────────────────────────────────────
    desc = input_stripped(f"  Description [{pre['description']}]: ")
    if not desc:
        desc = pre["description"]

    # ── Keywords ──────────────────────────────────────────────
    print(f"\n  Current keywords: {', '.join(pre['keywords'])}")
    kw_input = input_stripped("  Add/replace keywords (comma-separated, or Enter to keep): ")
    if kw_input:
        keywords = [k.strip().lower() for k in kw_input.split(",") if k.strip()]
    else:
        keywords = pre["keywords"]
    if not keywords:
        print("  ✖ At least one keyword is required.")
        return

    # ── Sources ───────────────────────────────────────────────
    print(f"\n  Available sources:")
    for k, v in AVAILABLE_SOURCES.items():
        print(f"    [{k}] {v}")
    print(f"  Current selection: {', '.join(pre['sources'])}")
    src_input = input_stripped("  Enter source keys (comma-separated, or Enter to keep): ")
    if src_input:
        sources = [s.strip() for s in src_input.split(",") if s.strip() in AVAILABLE_SOURCES]
        if not sources:
            print("  ⚠  No valid sources — using default.")
            sources = pre["sources"]
    else:
        sources = pre["sources"]

    # ── Alert Threshold ───────────────────────────────────────
    print(f"\n  Alert threshold — only match records AT or ABOVE this level.")
    print(f"  Options: HIGH | MEDIUM | LOW")
    thresh_input = input_stripped(f"  Threshold [{pre['alert_threshold']}]: ").upper()
    if thresh_input not in ALERT_THRESHOLDS:
        thresh_input = pre["alert_threshold"]

    # ── Analyst name ──────────────────────────────────────────
    analyst = input_stripped("  Your name / Analyst ID [Analyst]: ")
    if not analyst:
        analyst = "Analyst"

    # ── Build watchlist object ─────────────────────────────────
    wl_id = generate_id(watchlists)
    ts    = now_utc()
    new_wl = {
        "id":               wl_id,
        "topic":            topic,
        "description":      desc,
        "keywords":         keywords,
        "sources":          sources,
        "alert_threshold":  thresh_input,
        "active":           True,
        "created_at":       ts,
        "updated_at":       ts,
        "created_by":       analyst,
        "match_count":      0,
        "last_run":         None,
    }

    watchlists.append(new_wl)
    save_watchlists(watchlists)

    print(f"\n  ✅ Watchlist created successfully!")
    print_bar("─")
    display_watchlist_card(new_wl)
    print_bar()


# ══════════════════════════════════════════════════════════════
# EDIT WATCHLIST
# ══════════════════════════════════════════════════════════════

def edit_watchlist(watchlists):
    if not watchlists:
        print("\n  No watchlists to edit.")
        return

    display_all_watchlists(watchlists)
    wl_id = input_stripped("  Enter Watchlist ID or number to edit (e.g. WL_001 or 1): ").upper()
    idx, wl = find_watchlist(watchlists, wl_id)
    if wl is None:
        print(f"  ✖ Watchlist '{wl_id}' not found.")
        return

    print(f"\n  Editing: {wl['id']} — {wl['topic']}")
    print("  Press Enter on any field to keep current value.\n")

    while True:
        print("  What would you like to edit?")
        print("  [1] Topic name")
        print("  [2] Description")
        print("  [3] Add keywords")
        print("  [4] Remove keywords")
        print("  [5] Replace ALL keywords")
        print("  [6] Sources")
        print("  [7] Alert threshold")
        print("  [8] Pause / Resume watchlist")
        print("  [9] Done editing")

        choice = input_stripped("\n  Choice: ")

        if choice == "1":
            val = input_stripped(f"  Topic name [{wl['topic']}]: ")
            if val: wl["topic"] = val

        elif choice == "2":
            val = input_stripped(f"  Description [{wl['description']}]: ")
            if val: wl["description"] = val

        elif choice == "3":
            val = input_stripped("  Keywords to ADD (comma-separated): ")
            if val:
                new_kws = [k.strip().lower() for k in val.split(",") if k.strip()]
                added   = [k for k in new_kws if k not in wl["keywords"]]
                wl["keywords"].extend(added)
                print(f"  ✅ Added: {', '.join(added)}" if added else "  ℹ  All keywords already exist.")

        elif choice == "4":
            print(f"  Current keywords: {', '.join(wl['keywords'])}")
            val = input_stripped("  Keywords to REMOVE (comma-separated): ")
            if val:
                rem = [k.strip().lower() for k in val.split(",") if k.strip()]
                removed = [k for k in rem if k in wl["keywords"]]
                wl["keywords"] = [k for k in wl["keywords"] if k not in rem]
                print(f"  ✅ Removed: {', '.join(removed)}" if removed else "  ℹ  None of those keywords found.")

        elif choice == "5":
            val = input_stripped("  New keywords (comma-separated, replaces ALL existing): ")
            if val:
                wl["keywords"] = [k.strip().lower() for k in val.split(",") if k.strip()]
                print(f"  ✅ Keywords replaced. New list: {', '.join(wl['keywords'])}")

        elif choice == "6":
            print("  Available sources:")
            for k, v in AVAILABLE_SOURCES.items():
                print(f"    [{k}] {v}")
            print(f"  Current: {', '.join(wl['sources'])}")
            val = input_stripped("  New sources (comma-separated): ")
            if val:
                new_src = [s.strip() for s in val.split(",") if s.strip() in AVAILABLE_SOURCES]
                if new_src:
                    wl["sources"] = new_src
                    print(f"  ✅ Sources updated: {', '.join(wl['sources'])}")
                else:
                    print("  ✖ No valid sources entered.")

        elif choice == "7":
            print("  Options: HIGH | MEDIUM | LOW")
            val = input_stripped(f"  Threshold [{wl['alert_threshold']}]: ").upper()
            if val in ALERT_THRESHOLDS:
                wl["alert_threshold"] = val
                print(f"  ✅ Threshold set to {val}")

        elif choice == "8":
            wl["active"] = not wl.get("active", True)
            status = "ACTIVE" if wl["active"] else "PAUSED"
            print(f"  ✅ Watchlist is now {status}")

        elif choice == "9" or choice == "":
            break
        else:
            print("  ✖ Invalid choice.")

        wl["updated_at"] = now_utc()
        watchlists[idx] = wl
        save_watchlists(watchlists)
        print(f"  💾 Saved.\n")

    print(f"\n  ✅ Watchlist {wl['id']} updated.")
    print_bar("─")
    display_watchlist_card(wl)
    print_bar()


# ══════════════════════════════════════════════════════════════
# DELETE WATCHLIST
# ══════════════════════════════════════════════════════════════

def delete_watchlist(watchlists):
    if not watchlists:
        print("\n  No watchlists to delete.")
        return

    display_all_watchlists(watchlists)
    wl_id = input_stripped("  Enter Watchlist ID or number to delete (e.g. WL_001 or 1): ").upper()
    idx, wl = find_watchlist(watchlists, wl_id)
    if wl is None:
        print(f"  ✖ Watchlist '{wl_id}' not found.")
        return

    print(f"\n  ⚠  You are about to delete:")
    print(f"     {wl['id']} — {wl['topic']}")
    confirm = input_stripped("  Type DELETE to confirm: ")
    if confirm.strip().upper() == "DELETE":
        watchlists.pop(idx)
        save_watchlists(watchlists)
        print(f"  ✅ Watchlist {wl_id} deleted.")
    else:
        print("  ℹ  Delete cancelled.")


# ══════════════════════════════════════════════════════════════
# RUN WATCHLISTS
# ══════════════════════════════════════════════════════════════

def run_watchlists(watchlists, run_id=None):
    print_section("RUNNING WATCHLISTS AGAINST INTELLIGENCE DATA")

    records = load_intelligence_records()
    if not records:
        print(f"\n  ℹ  No intelligence data found.")
        print(f"     Run monitoring_engine.py or intelligence_fusion_engine.py first.")
        print(f"     The watchlist structure and keywords are saved and ready.")
        print_bar()
        return

    print(f"  Loaded {len(records)} intelligence records.\n")

    to_run = []
    if run_id:
        _, wl = find_watchlist(watchlists, run_id)
        if wl:
            to_run = [wl]
        else:
            print(f"  ✖ Watchlist '{run_id}' not found.")
            return
    else:
        to_run = [w for w in watchlists if w.get("active", True)]

    if not to_run:
        print("  ℹ  No active watchlists to run.")
        return

    total_matches = 0

    for wl in to_run:
        matches = run_watchlist(wl, records)
        wl["match_count"] = len(matches)
        wl["last_run"]    = now_utc()

        # Update in main list
        idx, _ = find_watchlist(watchlists, wl["id"])
        if idx is not None:
            watchlists[idx] = wl

        icon = alert_icon(wl.get("alert_threshold", "MEDIUM"))
        print(f"  {icon} {wl['id']}  —  {wl['topic']}")
        print(f"     {len(matches)} matches found")

        if matches:
            for m in matches[:5]:
                al = alert_icon(m["alert_level"])
                kw = ", ".join(m["matched_keywords"][:3])
                print(f"     {al} [{m['credibility']:>3}/100]  {m['title'][:55]}")
                print(f"          ↳ matched: {kw}")
            if len(matches) > 5:
                print(f"     ... and {len(matches)-5} more matches")
        print()
        total_matches += len(matches)

    save_watchlists(watchlists)
    print_bar("─")
    print(f"  ✅ Run complete  |  {len(to_run)} watchlist(s)  |  {total_matches} total matches")
    print_bar()


# ══════════════════════════════════════════════════════════════
# VIEW WATCHLIST DETAIL
# ══════════════════════════════════════════════════════════════

def view_watchlist(watchlists):
    if not watchlists:
        print("\n  No watchlists found.")
        return
    display_all_watchlists(watchlists)
    wl_id = input_stripped("  Enter Watchlist ID or number for detail (e.g. WL_001 or 1): ").upper()
    if not wl_id:
        return
    _, wl = find_watchlist(watchlists, wl_id)
    if wl is None:
        print(f"  ✖ '{wl_id}' not found.")
        return

    print_section(f"WATCHLIST DETAIL — {wl['id']}")
    print(f"  ID           : {wl['id']}")
    print(f"  Topic        : {wl['topic']}")
    print(f"  Description  : {wl.get('description','—')}")
    print(f"  Status       : {'✅ ACTIVE' if wl.get('active',True) else '⏸  PAUSED'}")
    print(f"  Alert Level  : {alert_icon(wl.get('alert_threshold','MEDIUM'))} {wl.get('alert_threshold','MEDIUM')}")
    print(f"  Created      : {wl.get('created_at','')[:10]}  by {wl.get('created_by','Analyst')}")
    print(f"  Last Updated : {wl.get('updated_at','')[:10]}")
    print(f"  Last Run     : {wl.get('last_run') or 'Never'}")
    print(f"  Match Count  : {wl.get('match_count',0)}")
    print(f"\n  KEYWORDS ({len(wl.get('keywords',[]))}):")
    for i, kw in enumerate(wl.get("keywords", []), 1):
        print(f"    {i:>2}. {kw}")
    print(f"\n  SOURCES ({len(wl.get('sources',[]))}):")
    for src in wl.get("sources", []):
        print(f"    • {AVAILABLE_SOURCES.get(src, src)}")
    print_bar()


# ══════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════

def print_menu(watchlists):
    active = sum(1 for w in watchlists if w.get("active", True))
    print_bar()
    print(f"  IAF & Indian Defence — Watchlist Management Engine")
    print(f"  Watchlists: {len(watchlists)} total  |  {active} active")
    print_bar("─")
    print("  [1] Create new watchlist")
    print("  [2] View all watchlists")
    print("  [3] View watchlist detail")
    print("  [4] Edit watchlist")
    print("  [5] Delete watchlist")
    print("  [6] Run all watchlists against intelligence data")
    print("  [7] Run one specific watchlist")
    print("  [0] Exit")
    print_bar("─")

def main():
    parser = argparse.ArgumentParser(description="Watchlist Management Engine")
    parser.add_argument("--list",  action="store_true", help="List all watchlists and exit")
    parser.add_argument("--run",   action="store_true", help="Run all active watchlists and exit")
    parser.add_argument("--id",    type=str,            help="Watchlist ID to run (use with --run)")
    args = parser.parse_args()

    watchlists = load_watchlists()

    if args.list:
        display_all_watchlists(watchlists)
        return

    if args.run:
        run_watchlists(watchlists, run_id=args.id)
        return

    # Interactive mode
    while True:
        print_menu(watchlists)
        choice = input_stripped("  Choice: ")

        if choice == "1":
            create_watchlist(watchlists)
        elif choice == "2":
            display_all_watchlists(watchlists)
        elif choice == "3":
            view_watchlist(watchlists)
        elif choice == "4":
            edit_watchlist(watchlists)
        elif choice == "5":
            delete_watchlist(watchlists)
        elif choice == "6":
            run_watchlists(watchlists)
        elif choice == "7":
            display_all_watchlists(watchlists)
            wl_id = input_stripped("  Enter Watchlist ID or number to run (e.g. WL_002 or 2): ")
            run_watchlists(watchlists, run_id=wl_id)
        elif choice == "0" or choice.lower() in ("exit", "quit", "q"):
            print("\n  Goodbye.\n")
            break
        else:
            print("  ✖ Invalid choice.\n")
        print()

if __name__ == "__main__":
    main()
