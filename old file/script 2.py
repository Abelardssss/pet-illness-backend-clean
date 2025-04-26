import pandas as pd
import random
import json

# Load illness-symptom tier structure
with open("old file/dog tiers.json", "r") as f:
    illnesses = json.load(f)["illness"]  # 🔁 extract nested under "illnesses"

# Load prevalence mapping
with open("old file/dog_illness_prevalence.json", "r") as f:
    prevalence_map = json.load(f)

# Define number of test cases by prevalence category
prevalence_to_case_count = {
    "Common": 50,
    "Moderate": 30,
    "Rare": 15
}

# Define probability per tier (simulates real-world frequency)
tier_probabilities = {
    "Tier 0": 1.00,  # Always present
    "Tier 1": 0.95,  # Very likely
    "Tier 2": 0.65,  # Moderately likely
    "Tier 3": 0.25,  # Low likelihood
    "Tier 4": 0.05,  # Rare
    "Tier 5": 0.00   # Always absent (if used)
}

# Extract master symptom list from all illnesses
symptom_set = set()
for tier_data in illnesses.values():
    for tier_symptoms in tier_data.values():
        symptom_set.update(tier_symptoms)
symptom_list = sorted(symptom_set)  # 🔤 Alphabetical

# Generate dataset
data = []

for illness, tiers in illnesses.items():
    # Get how many test cases this illness should generate
    prevalence = prevalence_map.get(illness, "Moderate")
    num_cases = prevalence_to_case_count.get(prevalence, 30)

    for case_num in range(1, num_cases + 1):
        case = {"Test Case ID": f"{illness}_{case_num}", "Illness": illness}

        for symptom in symptom_list:
            present = 0
            for tier_name, symptoms in tiers.items():
                if symptom in symptoms:
                    prob = tier_probabilities.get(tier_name, 0)
                    present = 1 if random.random() < prob else 0
                    break  # Found the tier, no need to continue
            case[symptom] = present

        data.append(case)

# Save to CSV
df = pd.DataFrame(data)
df.to_csv("dog_illness_dataset.csv", index=False)
print("✅ Dataset created: 'dog_illness_dataset.csv'")
