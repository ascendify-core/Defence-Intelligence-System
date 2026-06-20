import json
from collections import Counter

# =====================================================
# LOAD FILES
# =====================================================

with open("topic_results.json", "r", encoding="utf-8") as f:
    topic_data = json.load(f)

with open("keywords_output_iaf_focused.json", "r", encoding="utf-8") as f:
    keyword_data = json.load(f)

with open("extracted_entities.json", "r", encoding="utf-8") as f:
    entity_data = json.load(f)

# =====================================================
# KEYWORD COUNTS BY TOPIC
# =====================================================

topic_keyword_counts = Counter()

for doc in keyword_data:
    topic = doc.get("topic", "Unknown")
    topic_keyword_counts[topic] += len(doc.get("keywords", []))

# =====================================================
# ENTITY COUNTS
# =====================================================

total_entities = 0

for doc in entity_data:

    total_entities += len(doc.get("people", []))
    total_entities += len(doc.get("organizations", []))
    total_entities += len(doc.get("locations", []))
    total_entities += len(doc.get("technologies", []))
    total_entities += len(doc.get("events", []))

# =====================================================
# TREND ANALYSIS
# =====================================================

trend_results = []

total_documents = sum(
    item["documents"]
    for item in topic_data
)

max_mentions = max(
    item["documents"]
    for item in topic_data
)

max_keywords = max(
    topic_keyword_counts.values()
) if topic_keyword_counts else 1

for item in topic_data:

    topic_name = item["topic"]
    current_mentions = item["documents"]

    # -----------------------------------------
    # Simulated Historical Trend
    # -----------------------------------------

    mentions_history = [
        max(1, current_mentions // 4),
        max(1, current_mentions // 2),
        current_mentions
    ]

    # -----------------------------------------
    # Trend Detection
    # -----------------------------------------

    if mentions_history[2] > mentions_history[1] > mentions_history[0]:
        trend = "Increasing"

    elif mentions_history[2] < mentions_history[1] < mentions_history[0]:
        trend = "Decreasing"

    else:
        trend = "Stable"

    # -----------------------------------------
    # Growth Rate
    # -----------------------------------------

    previous = mentions_history[1]

    growth_rate = round(
        ((current_mentions - previous) / previous) * 100,
        2
    )

    # -----------------------------------------
    # Confidence Score
    # -----------------------------------------

    mention_score = (
        current_mentions / max_mentions
    )

    keyword_score = (
        topic_keyword_counts.get(topic_name, 0)
        / max_keywords
    )

    confidence = round(
        (mention_score * 0.7) +
        (keyword_score * 0.3),
        2
    )

    trend_results.append({
        "topic": topic_name,
        "mentions": mentions_history,
        "current_mentions": current_mentions,
        "trend": trend,
        "growth_rate": growth_rate,
        "confidence": confidence
    })

# =====================================================
# SORT BY CONFIDENCE
# =====================================================

trend_results.sort(
    key=lambda x: x["confidence"],
    reverse=True
)

# =====================================================
# SAVE OUTPUT
# =====================================================

with open(
    "trend_results.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        trend_results,
        f,
        indent=4
    )

print("Trend Analysis Completed")
print("Output saved to trend_results.json")