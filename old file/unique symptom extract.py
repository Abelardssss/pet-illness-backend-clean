import json

# Load the knowledge base JSON with the "rules" key
with open("data/cat_knowledge_base.json", "r") as f:
    data = json.load(f)

# Extract from the 'rules' key
rules = data.get("rules", [])

# Collect unique symptom names
unique_symptoms = set()

for rule in rules:
    for symptom in rule.get("symptoms", []):
        name = symptom.get("name", "").strip()
        if name:
            unique_symptoms.add(name)

# Sort alphabetically
sorted_symptoms = sorted(unique_symptoms)

# Save to JSON
with open("unique_symptoms.json", "w") as out_file:
    json.dump(sorted_symptoms, out_file, indent=2)

print(f"✅ Extracted {len(sorted_symptoms)} unique symptoms to 'unique_symptoms.json'")