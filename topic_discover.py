import json
from collections import defaultdict

# Define topic keyword sets
TOPIC_KEYWORDS = {
    "Artificial Intelligence": ["AI", "machine learning", "deep learning", "TensorFlow", "PyTorch"],
    "Cybersecurity": ["network", "security", "cyber", "attack", "firewall"],
    "Defence Technology": ["air force", "army", "missile", "drone", "rafale", "s-400"]
}

# Load entity and keyword data
with open("entities_output.json", "r", encoding="utf-8") as f1:
    entities_data = json.load(f1)

with open("keywords_output.json", "r", encoding="utf-8") as f2:
    keywords_data = json.load(f2)

# keywords_output.json is a dict → extract "documents"
documents = keywords_data.get("documents", [])

print("Entities loaded:", len(entities_data))
print("Keywords loaded:", len(documents))
print("First entity record:", entities_data[0] if entities_data else "None")
print("First keyword record:", documents[0] if documents else "None")

topic_counts = defaultdict(int)
classified_docs = []

# Iterate through entities and keywords together
for i in range(len(entities_data)):
    entity_doc = entities_data[i]
    keyword_doc = documents[i] if i < len(documents) else {}

    title = entity_doc.get("video_title", "")
    keywords = keyword_doc.get("keywords", [])

    # Topic classification
    matched_topics = []
    text = " ".join(keywords).lower() + " " + title.lower()
    for topic, kw_list in TOPIC_KEYWORDS.items():
        if any(kw.lower() in text for kw in kw_list):
            topic_counts[topic] += 1
            matched_topics.append(topic)

    # Entities from Team 2 output
    people = entity_doc.get("people", [])
    orgs = entity_doc.get("organizations", [])
    locs = entity_doc.get("locations", [])
    techs = entity_doc.get("technologies", [])
    events = entity_doc.get("events", [])

    classified_docs.append({
        "video_title": title,
        "keywords": keywords,
        "matched_topics": matched_topics if matched_topics else ["Unclassified"],
        "people": list(set(people)),
        "organizations": list(set(orgs)),
        "locations": list(set(locs)),
        "technologies": list(set(techs)),
        "events": list(set(events))
    })

    print(f"[{i+1}] Title: {title} → Topics: {matched_topics if matched_topics else 'Unclassified'}")

# Save topic summary
topic_results = [{"topic": t, "documents": c} for t, c in topic_counts.items()]
with open("topic_results.json", "w", encoding="utf-8") as f:
    json.dump(topic_results, f, indent=2)

# Save detailed per-document output
with open("topic_entities_keywords.json", "w", encoding="utf-8") as f:
    json.dump(classified_docs, f, indent=2)

print("\n" + "="*60)
print("TOPIC DISCOVERY RESULTS")
print("="*60)
for r in topic_results:
    print(f"Topic : {r['topic']} | Documents : {r['documents']}")

print(f"\nResults saved to: topic_results.json and topic_entities_keywords.json")
print(f"Total documents processed: {len(classified_docs)}")
