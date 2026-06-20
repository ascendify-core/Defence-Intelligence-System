import json
import os


# ==================================================
# CONFIDENCE ENGINE CLASS
# ==================================================

# ==================================================
# CONFIDENCE ENGINE CLASS
# ==================================================

# ==================================================
# CONFIDENCE ENGINE CLASS
# ==================================================

class ConfidenceEngine:
    """Calculates confidence scores for intelligence reports"""
    
    def calculate_correlation(self, reports):
        """Calculate correlation score based on report similarity"""
        if len(reports) <= 1:
            return 0.0
        return min(len(reports) * 10, 100) / 100
    
    def calculate_signal_strength(self, reports):
        """Calculate signal strength based on number of reports"""
        return min(len(reports) * 15, 100)
    
    def calculate_confidence(self, credibility_score, correlation_score, signal_strength, source_count):
        """Calculate final confidence score"""
        weights = {
            'credibility': 0.5,
            'correlation': 0.2,
            'signal': 0.3
        }
        confidence = (
            credibility_score * weights['credibility'] +
            correlation_score * weights['correlation'] +
            signal_strength * weights['signal']
        )
        return round(confidence, 2)


# ==================================================
# MAIN PROGRAM
# ==================================================

import json


print("\nLoading credibility data...")

with open(
    "source_credibility.json",
    "r",
    encoding="utf-8"
) as file:

    credibility_data = json.load(file)

from urllib.parse import parse_qs, urlparse

engine = ConfidenceEngine()

# ==================================================
# HELPER: EXTRACT VIDEO ID FROM YOUTUBE URL
# ==================================================

def extract_video_id(link):
    parsed = urlparse(link.strip())
    if parsed.netloc in ("www.youtube.com", "youtube.com"):
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip("/")
    if parsed.scheme == "" and len(link.strip()) == 11:
        return link.strip()
    return None

# ==================================================
# USER INPUT URL
# ==================================================

source_url = input(
    "\nEnter source URL: "
).strip()

# ==================================================
# FILTER REPORTS BY URL
# ==================================================

filtered_data = []
video_id = extract_video_id(source_url)

for item in credibility_data:
    item_url = item.get("source_url", "")
    item_source_id = item.get("source_id", "")

    if source_url.lower() == item_url.lower():
        filtered_data.append(item)
    elif video_id and item_source_id == video_id:
        filtered_data.append(item)
    elif source_url.lower() in item_url.lower():
        filtered_data.append(item)

# ==================================================
# NO MATCH FOUND
# ==================================================

if len(filtered_data) == 0:

    print(
        f"\nNo reports found for URL '{source_url}'"
    )

    exit()

# ==================================================
# AUTOMATIC SOURCE COUNT
# ==================================================

source_count = len(filtered_data)

# ==================================================
# AUTOMATIC REPORT EXTRACTION
# ==================================================

reports = [
    item["title"]
    for item in filtered_data
]

# ==================================================
# AUTOMATIC CREDIBILITY SCORE
# ==================================================

credibility_score = round(
    sum(
        item["final_score"]
        for item in filtered_data
    ) / len(filtered_data),
    2
)

# ==================================================
# CALCULATE SCORES
# ==================================================

correlation_score = (
    engine.calculate_correlation(
        reports
    )
)

signal_strength = (
    engine.calculate_signal_strength(
        reports
    )
)

confidence_score = (
    engine.calculate_confidence(
        credibility_score,
        correlation_score,
        signal_strength,
        source_count
    )
)

# ==================================================
# CONFIDENCE LEVEL
# ==================================================

if confidence_score >= 90:
    confidence_level = "VERY HIGH"

elif confidence_score >= 75:
    confidence_level = "HIGH"

elif confidence_score >= 60:
    confidence_level = "MEDIUM"

else:
    confidence_level = "LOW"

# ==================================================
# OUTPUT
# ==================================================

result = {
    "source_url": source_url,
    "matched_reports": source_count,
    "credibility_score": credibility_score,
    "correlation_score": correlation_score,
    "signal_strength": signal_strength,
    "confidence_score": confidence_score,
    "confidence_level": confidence_level
}

with open(
    "confidence_report.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        result,
        file,
        indent=4,
        ensure_ascii=False
    )

print("\n===== INTELLIGENCE CONFIDENCE REPORT =====")

print(
    json.dumps(
        result,
        indent=4
    )
)

print(
    "\nReport saved as confidence_report.json"
)