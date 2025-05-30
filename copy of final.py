import joblib
import numpy as np
import json
import pandas as pd
import os

# 📌 File Paths (static ones)
FACT_BASE_PATH = "data/fact_base.json"
ILLNESS_INFO_PATH = "data/expanded_illness_info_complete.json"
FOLLOWUP_QUESTIONS_PATH = "data/updated_follow_up_questions_tuned.json"
BREED_CATEGORY_MAP_PATH = "data/breed_category_mapping.json"

# 📌 Initialize Global Variables Safely
knowledge_base = []
illness_info = {}
symptom_followups = {}
breed_category_mapping = {}
boosting_model = None
adaboost_model = None
selected_features = []
df = pd.DataFrame()
all_symptoms = []

# 📌 Load JSON Files Helper
def load_json(file_path):
    with open(file_path, "r") as file:
        return json.load(file)

# 📌 Load Static Databases (these are always needed)
illness_info = load_json(ILLNESS_INFO_PATH)
symptom_followups = load_json(FOLLOWUP_QUESTIONS_PATH)
breed_category_mapping = load_json(BREED_CATEGORY_MAP_PATH)

# 📌 Dynamic Pet Resource Loader
def load_pet_resources(pet_type):
    """Load knowledge base, ML models, dataset and features depending on pet type."""
    if pet_type == "dog":
        kb = load_json("data/dog_knowledge_base.json")["rules"]
        boost_model = joblib.load("new model/new_dog_gradient_model.pkl")
        ada_model = joblib.load("new model/new_dog_adaboost_model.pkl")
        feats = joblib.load("new model/new_dog_adaboost_selected_features.pkl")
        dataset = pd.read_csv("data/dog_augmented.csv")
    else:  # cat
        kb = load_json("data/cat_knowledge_base.json")["rules"]
        boost_model = joblib.load("new model/new_cat_gradient_model.pkl")
        ada_model = joblib.load("new model/new_cat_adaboost_model.pkl")
        feats = joblib.load("new model/new_cat_adaboost_selected_features.pkl")
        dataset = pd.read_csv("data/cat_augmented.csv")

    return kb, boost_model, ada_model, feats, dataset

# Load Knowledge Base (Rules)
def load_knowledge_base():
    return knowledge_base  # Uses the preloaded knowledge base


# 📌 Load Illness Information Database
def load_illness_info():
    """Loads illness information from JSON file."""
    with open(ILLNESS_INFO_PATH, "r") as illness_file:
        return json.load(illness_file)


# 📌 Categorize Pet Age
def categorize_age(age):
    """Convert numeric age to category."""
    try:
        age = int(age)  # Ensure it's an integer
    except ValueError:
        return "Unknown"  # Handle non-integer inputs safely

    if age <= 1:
        return "Puppy"
    elif 1 < age <= 7:
        return "Adult"
    else:
        return "Senior"


# 📌 Get User Input
def get_user_input():
    """Collect user input for pet details and symptoms."""

    print("\n🔹 Select your pet type:")
    pet_type = input("➡ Dog or Cat? ").strip().lower()

    while pet_type not in ["dog", "cat"]:
        print("❌ Invalid input. Please choose 'dog' or 'cat'.")
        pet_type = input("➡ Dog or Cat? ").strip().lower()

    print("\n🔹 Enter pet details:")
    pet_name = input("➡ Pet's Name: ").strip()

    print("\n🔹 Enter pet details:")
    age_years = input("➡ Pet Age (in years): ").strip()
    age_range = categorize_age(age_years)  # Convert numeric age to category
    size = input("➡ Pet Size (Small / Medium / Large): ").strip().capitalize()
    breed = input("➡ Pet Breed (or type 'Any'): ").strip().capitalize()

    symptoms = []
    user_answers = {}  # ✅ Always initialize `user_answers`

    while True:
        print("\n🔹 Enter the primary symptom troubling your pet:")
        main_symptom = input("➡ Symptom: ").strip().lower()
        symptom_details = {"name": main_symptom}

        # ✅ Check if symptom has follow-up questions
        if main_symptom in symptom_followups:
            user_answers[main_symptom] = {}  # ✅ Initialize answers for this symptom

            for question in symptom_followups[main_symptom]["questions"]:
                answer = input(f"➡ {question} ").strip().lower()
                user_answers[main_symptom][
                    question
                ] = answer  # ✅ Store response properly

        symptoms.append(symptom_details)

        # ✅ Ask if there are more symptoms
        if input("➡ More symptoms? (Yes/No): ").strip().lower() != "yes":
            break

    return {
        "pet_type": pet_type,
        "pet": pet_name,
        "pet_info": {
            "age_years": age_years,
            "age_range": age_range,
            "size": size,
            "breed": breed,
        },
        "symptoms": symptoms,
        "user_answers": user_answers,
    }



def parse_duration_range(range_str):
    """
    Parses a duration range string like "1-4 days" into a tuple of (1, 4).
    If parsing fails, returns None.
    """
    if not range_str:
        return None
    cleaned = range_str.lower().replace("days", "").replace("day", "").strip()
    parts = cleaned.split("-")
    if len(parts) == 2:
        try:
            lower = float(parts[0].strip())
            upper = float(parts[1].strip())
            return (lower, upper)
        except ValueError:
            return None
    return None


def duration_overlap(user_range_str, expected_range_str):
    """
    Returns True if the numeric intervals from user_range_str and expected_range_str overlap.
    For example, "1-4 days" and "2-4 days" would overlap.
    """
    user_interval = parse_duration_range(user_range_str)
    expected_interval = parse_duration_range(expected_range_str)
    if user_interval and expected_interval:
        return max(user_interval[0], expected_interval[0]) <= min(
            user_interval[1], expected_interval[1]
        )
    return False


# 📌 Ensure all expected features exist in the dataset (missing ones should be filled with 0)
def align_features(feature_vector, expected_features):
    """Align feature vector with expected features to ensure consistency."""
    feature_vector = feature_vector.copy()  # Prevents SettingWithCopyWarning

    # ✅ Add missing features as zeros
    for feature in expected_features:
        if feature not in feature_vector.columns:
            feature_vector.loc[:, feature] = 0

    # ✅ Reorder columns to match training feature order
    return feature_vector[expected_features]


def adjust_confidence_with_followups(
    confidence, symptom_details, illness_name, user_answers
):
    """Modify confidence scores based on user follow-up answers and KB expectations."""

    illness_rule = next(
        (r for r in knowledge_base if r["illness"] == illness_name), None
    )
    if not illness_rule:
        return confidence

    total_multiplier = 1.0

    for symptom in symptom_details:
        symptom_name = symptom["name"].lower().strip()

        if symptom_name in symptom_followups and illness_rule:
            expected_symptoms = {s["name"].lower(): s for s in illness_rule["symptoms"]}
            if symptom_name in expected_symptoms:
                expected_data = expected_symptoms[symptom_name]
                expected_duration = expected_data.get("duration_range", "Any")
                expected_severity = expected_data.get("severity", "Any")
                expected_subtypes = [
                    sub.strip().lower()
                    for sub in expected_data.get("subtype", "Any").split(",")
                    if sub.strip()
                ]

                user_response = user_answers.get(symptom_name, {})
                user_duration = user_response.get(
                    f"How long has your pet had {symptom_name}?", None
                )
                user_severity = user_response.get(
                    f"Is the {symptom_name} Mild, Moderate, or Severe?", None
                )

                user_subtype = None
                if symptom_name in symptom_followups:
                    for question in symptom_followups[symptom_name]["questions"]:
                        answer = user_response.get(question, None)
                        if answer:
                            candidate = answer.lower().strip()
                            if expected_subtypes and candidate in expected_subtypes:
                                user_subtype = candidate
                                break
                if not user_subtype and user_severity:
                    candidate = user_severity.lower().strip()
                    if expected_subtypes and candidate in expected_subtypes:
                        user_subtype = candidate
                user_subtype_clean = user_subtype if user_subtype else None

                impact_values = symptom_followups.get(symptom_name, {}).get(
                    "impact", {}
                )
                severity_impact = (
                    impact_values.get(user_severity.lower(), 1.2)
                    if user_severity
                    else 1.2
                )
                subtype_impact = (
                    impact_values.get(user_subtype_clean, 1.2)
                    if user_subtype_clean
                    else 1.2
                )

                if user_duration and expected_duration.lower() != "any":
                    if duration_overlap(user_duration, expected_duration):
                        duration_impact = impact_values.get(user_duration.lower(), 1.2)
                    else:
                        duration_impact = 0.95
                else:
                    duration_impact = 1.2

                kb_match_bonus = 1.0
                if user_severity and expected_severity.lower() != "any":
                    kb_match_bonus *= (
                        1.02
                        if user_severity.lower() == expected_severity.lower()
                        else 0.95
                    )

                if user_duration and expected_duration.lower() != "any":
                    if duration_overlap(user_duration, expected_duration):
                        kb_match_bonus *= 1.03
                    else:
                        kb_match_bonus *= 0.95

                if user_subtype_clean and expected_subtypes != ["any"]:
                    kb_match_bonus *= (
                        1.08 if user_subtype_clean in expected_subtypes else 0.9
                    )

                total_multiplier *= (
                    severity_impact * subtype_impact * duration_impact * kb_match_bonus
                )

    return round(confidence * total_multiplier, 2)


def compute_max_possible_score(illness_name):
    """Computes the maximum theoretical confidence score for an illness using its symptoms."""
    rule = next((r for r in knowledge_base if r["illness"] == illness_name), None)
    if not rule:
        return 1.0  # Fallback value to avoid division by zero

    return sum(
        symptom["weight"] * 1.2 * symptom.get("priority", 1.0)
        for symptom in rule["symptoms"]
    )


# 1
def forward_chaining(fact_base):
    """Pure symptom-based rule matching using Forward Chaining."""

    user_symptoms = [
        s["name"].lower().strip()
        for s in fact_base["symptoms"]
        if isinstance(s, dict) and "name" in s
    ]

    possible_diagnoses = []

    for rule in load_knowledge_base():
        total_weight = sum(symptom["weight"] for symptom in rule["symptoms"])
        matched_weight = sum(
            symptom["weight"]
            for symptom in rule["symptoms"]
            if symptom["name"].lower().strip() in user_symptoms
        )

        if matched_weight > 0:
            match_ratio = matched_weight / total_weight
            confidence_fc = round(rule["confidence"] * match_ratio, 2)

            possible_diagnoses.append(
                {
                    "illness": rule["illness"],
                    "matched_symptoms": [
                        s["name"].lower().strip()
                        for s in rule["symptoms"]
                        if s["name"].lower().strip() in user_symptoms
                    ],
                    "confidence_fc": confidence_fc,
                }
            )

    return possible_diagnoses


# 📌 Step 2: Gradient Boosting - Illness Ranking Optimization
def gradient_boosting_ranking(possible_diagnoses, fact_base):
    """Uses Gradient Boosting to refine illness ranking based on symptom match and model prediction."""

    user_symptoms = (
        [
            s["name"].lower().strip()
            for s in fact_base["symptoms"]
            if isinstance(s, dict) and "name" in s
        ]
        if isinstance(fact_base["symptoms"], list)
        else []
    )

    pet_info = fact_base["pet_info"]
    user_answers = fact_base["user_answers"]  # Include user responses for follow-ups

    refined_diagnoses = []

    for diagnosis in possible_diagnoses:
        # Create feature vector for ML model (using only symptoms)
        feature_vector = pd.DataFrame(
            [
                [
                    1 if symptom.lower() in user_symptoms else 0
                    for symptom in all_symptoms
                ]
            ],
            columns=all_symptoms,
        )

        feature_vector_selected = align_features(
            feature_vector[selected_features], boosting_model.feature_names_in_
        )

        # Get Gradient Boosting prediction
        raw_predictions = boosting_model.predict_proba(feature_vector_selected)
        illness_index = list(boosting_model.classes_).index(diagnosis["illness"])
        gb_confidence = raw_predictions[0][illness_index]

        # Retrieve illness rule safely
        rule = next(
            (r for r in load_knowledge_base() if r["illness"] == diagnosis["illness"]),
            None,
        )

        # Default multipliers for age, breed, and size
        if rule:
            age_match = (
                1.1
                if rule.get("age_range", "Any").lower()
                == pet_info.get("age_range", "Any").lower()
                else 0.85
            )

            rule_breed = rule.get("breed", "Any").strip().lower()
            pet_breed = pet_info.get("breed", "Any").strip().lower()
            pet_breed_category = breed_category_mapping.get(
                pet_breed.title(), ""
            ).lower()

            if rule_breed == "any":
                breed_match = 1.0
            elif rule_breed == pet_breed:
                breed_match = 1.1
            elif rule_breed == pet_breed_category:
                breed_match = 1.1
            else:
                breed_match = 0.9

            size_match = (
                1.1
                if rule.get("size", "Any").lower()
                == pet_info.get("size", "Any").lower()
                else 0.9
            )
        else:
            age_match = breed_match = size_match = 1.0

        final_confidence_gb = adjust_confidence_with_followups(
            round(gb_confidence * age_match * breed_match * size_match, 2),
            fact_base["symptoms"],
            diagnosis["illness"],
            user_answers,  # Pass user answers for dynamic adjustments
        )

        refined_diagnoses.append(
            {
                "illness": diagnosis["illness"],
                "matched_symptoms": diagnosis["matched_symptoms"],
                "confidence_fc": diagnosis["confidence_fc"],
                "confidence_gb": final_confidence_gb,
            }
        )

    return refined_diagnoses


def adaboost_ranking(possible_diagnoses, fact_base):
    """Uses AdaBoost to re-rank illnesses using model predictions and smart score blending."""

    user_symptoms = (
        [
            s["name"].lower().strip()
            for s in fact_base["symptoms"]
            if isinstance(s, dict) and "name" in s
        ]
        if isinstance(fact_base["symptoms"], list)
        else []
    )

    pet_info = fact_base["pet_info"]
    user_answers = fact_base["user_answers"]

    refined_diagnoses = []

    for diagnosis in possible_diagnoses:
        # Step 1: Build full binary symptom vector
        feature_vector = pd.DataFrame(
            [
                [
                    1 if symptom.lower() in user_symptoms else 0
                    for symptom in all_symptoms
                ]
            ],
            columns=all_symptoms,
        )

        # Step 2: Add engineered scores
        fc_score = diagnosis["confidence_fc"]
        gb_score = diagnosis["confidence_gb"]
        match_ratio = len(diagnosis.get("matched_symptoms", [])) / max(
            len(user_symptoms), 1
        )

        feature_vector["FC_Confidence"] = fc_score
        feature_vector["GB_Confidence"] = gb_score
        feature_vector["Symptom_Match_Ratio"] = round(match_ratio, 4)

        # Step 3: Align to trained AdaBoost feature order
        feature_vector_ab = align_features(
            feature_vector, adaboost_model.feature_names_in_
        )

        # Step 4: Predict using AdaBoost
        raw_probs = adaboost_model.predict_proba(feature_vector_ab)
        predicted_label = adaboost_model.predict(feature_vector_ab)[0]
        illness_index = list(adaboost_model.classes_).index(diagnosis["illness"])
        ab_raw = raw_probs[0][illness_index]

        # Step 5: Boost score if AdaBoost also picked this illness
        ab_confidence = ab_raw
        if predicted_label == diagnosis["illness"]:
            ab_confidence += 0.2  # Small bonus if AdaBoost agrees

        # Step 6: Blended final confidence
        final_score = 0.2 * fc_score + 0.5 * gb_score + 0.3 * ab_confidence

        # Step 7: Apply pet info & follow-ups as modifiers
        rule = next(
            (r for r in load_knowledge_base() if r["illness"] == diagnosis["illness"]),
            None,
        )

        # ✅ Replace with this new hard-penalty version:
        penalty = 1.0

        if rule:
            # Age mismatch penalty
            rule_age = rule.get("age_range", "any").lower()
            pet_age = pet_info.get("age_range", "any").lower()
            if rule_age != "any" and rule_age != pet_age:
                penalty *= 0.7  # strong penalty for age mismatch

            # Breed mismatch penalty
            rule_breed = rule.get("breed", "any").strip().lower()
            pet_breed = pet_info.get("breed", "any").strip().lower()
            pet_breed_category = breed_category_mapping.get(
                pet_breed.title(), ""
            ).lower()
            if rule_breed != "any" and rule_breed not in [
                pet_breed,
                pet_breed_category,
            ]:
                penalty *= 0.85  # moderate penalty for breed mismatch

            # Size mismatch penalty
            rule_size = rule.get("size", "any").lower()
            pet_size = pet_info.get("size", "any").lower()
            if rule_size != "any" and rule_size != pet_size:
                penalty *= 0.85  # moderate penalty for size mismatch

        # Apply penalty before follow-up adjustments
        adjusted_score = round(final_score * penalty, 2)

        # Step 8: Apply follow-up refinements
        final_confidence_ab = adjust_confidence_with_followups(
            adjusted_score,
            fact_base["symptoms"],
            diagnosis["illness"],
            user_answers,
        )

        # Normalize each confidence score between 0 and 1
        normalized_fc = round(min(fc_score / 1.0, 1.0), 4)
        normalized_gb = round(min(gb_score / 1.0, 1.0), 4)
        normalized_ab = round(min(final_confidence_ab / 1.0, 1.0), 4)

        refined_diagnoses.append(
            {
                "illness": diagnosis["illness"],
                "matched_symptoms": diagnosis["matched_symptoms"],
                "confidence_fc": normalized_fc,
                "confidence_gb": normalized_gb,
                "confidence_ab": normalized_ab,
            }
        )

    return refined_diagnoses


# 📌 Function to Save Fact Base Results
def save_fact_base(fact_base):
    """Ensures the directory exists and saves the fact base to a JSON file."""
    os.makedirs(os.path.dirname(FACT_BASE_PATH), exist_ok=True)
    with open(FACT_BASE_PATH, "w") as fb_file:
        json.dump(fact_base, fb_file, indent=4)
    print("\n✅ Results saved to fact_base.json!")


def compute_subtype_coverage(illness_rule, user_answers):
    """
    Computes a normalized subtype coverage score for an illness.
    For each symptom that has subtype data in the knowledge base, if the user's answer
    (from any key in user_answers for that symptom) is found in the expected set,
    count it as a full match (1), otherwise 0.
    The coverage score is returned as a percentage.
    """
    matched = 0
    total = 0
    for symptom in illness_rule["symptoms"]:
        symptom_name = symptom["name"].lower().strip()
        if "subtype" in symptom and symptom["subtype"]:
            total += 1
            expected = {
                sub.strip().lower()
                for sub in symptom["subtype"].split(",")
                if sub.strip()
            }
            user_response = user_answers.get(symptom_name, {})
            user_subtype = None
            for key, val in user_response.items():
                candidate = val.lower().strip()
                if candidate in expected:
                    user_subtype = candidate
                    break
            if user_subtype:
                matched += 1
    if total == 0:
        return 0
    return (matched / total) * 100


def compare_illnesses(diagnoses, fact_base):
    """Compare top 2 illnesses and explain why one is ranked higher than the other."""
    if len(diagnoses) < 2:
        return  # Need at least two illnesses for comparison

    illness_1, illness_2 = diagnoses[:2]

    print(
        f"\n🔹 **Why {illness_1['illness']} is Ranked Higher than {illness_2['illness']}?**\n"
    )
    print(
        "| Factor                     |",
        illness_1["illness"],
        " | ",
        illness_2["illness"],
        " |",
    )
    print(
        "|----------------------------|-------------------|-----------------------------|"
    )
    print(
        f"| Confidence Score           | **{illness_1['confidence_ab']}**   | {illness_2['confidence_ab']}      |"
    )
    print(
        f"| Weighted Symptom Matches   | {round(illness_1['confidence_fc'], 2)}   | {round(illness_2['confidence_fc'], 2)}  |"
    )
    print(
        f"| ML Score Adjustment        | +{round(illness_1['confidence_ab'] - illness_1['confidence_fc'], 2)} | +{round(illness_2['confidence_ab'] - illness_2['confidence_fc'], 2)} |"
    )

    # Retrieve illness rules from the knowledge base
    illness_1_rule = next(
        (r for r in knowledge_base if r["illness"] == illness_1["illness"]), None
    )
    illness_2_rule = next(
        (r for r in knowledge_base if r["illness"] == illness_2["illness"]), None
    )
    if not illness_1_rule or not illness_2_rule:
        return

    # Compute normalized subtype coverage scores using our helper function.
    coverage_score_1 = compute_subtype_coverage(
        illness_1_rule, fact_base["user_answers"]
    )
    coverage_score_2 = compute_subtype_coverage(
        illness_2_rule, fact_base["user_answers"]
    )

    print(
        f"| Subtype Coverage Score     | {round(coverage_score_1, 2)}%  | {round(coverage_score_2, 2)}%  |"
    )

    # Optionally, compute key differentiating symptoms if needed.
    def get_unique_diffs(illness_rule):
        unique = []
        for symptom in illness_rule["symptoms"]:
            symptom_name = symptom["name"].lower().strip()
            expected = {
                sub.strip()
                for sub in symptom.get("subtype", "").split(",")
                if sub.strip()
            }
            if expected:
                user_response = fact_base["user_answers"].get(symptom_name, {})
                user_answer = None
                for key, val in user_response.items():
                    candidate = val.strip()
                    if candidate.lower() in {s.lower() for s in expected}:
                        user_answer = candidate
                        break
                if not user_answer:
                    unique.append(
                        f"{symptom_name.capitalize()} ({', '.join(expected)})"
                    )
        return unique

    unique_symptoms_1 = get_unique_diffs(illness_1_rule)
    unique_symptoms_2 = get_unique_diffs(illness_2_rule)

    if not unique_symptoms_1:
        unique_symptoms_1 = ["None"]
    if not unique_symptoms_2:
        unique_symptoms_2 = ["None"]

    print(
        f"| Key Differentiating Symptoms | ✅ {', '.join(unique_symptoms_1)} | ❌ {', '.join(unique_symptoms_2)} |"
    )


def build_comparison_output(diagnoses, fact_base):
    """Returns a structured (non-print) version of the comparison between top 2 illnesses."""
    if len(diagnoses) < 2:
        return {}

    illness_1, illness_2 = diagnoses[:2]
    illness_1_rule = next(
        (r for r in knowledge_base if r["illness"] == illness_1["illness"]), None
    )
    illness_2_rule = next(
        (r for r in knowledge_base if r["illness"] == illness_2["illness"]), None
    )
    if not illness_1_rule or not illness_2_rule:
        return {}

    coverage_1 = compute_subtype_coverage(illness_1_rule, fact_base["user_answers"])
    coverage_2 = compute_subtype_coverage(illness_2_rule, fact_base["user_answers"])

    return {
        "top_illness": illness_1["illness"],
        "second_illness": illness_2["illness"],
        "factors": [
            {
                "name": "Confidence Score",
                "top": illness_1["confidence_ab"],
                "second": illness_2["confidence_ab"],
            },
            {
                "name": "Weighted Symptom Matches",
                "top": illness_1["confidence_fc"],
                "second": illness_2["confidence_fc"],
            },
            {
                "name": "ML Score Adjustment",
                "top": round(
                    illness_1["confidence_ab"] - illness_1["confidence_fc"], 2
                ),
                "second": round(
                    illness_2["confidence_ab"] - illness_2["confidence_fc"], 2
                ),
            },
            {
                "name": "Subtype Coverage Score",
                "top": round(coverage_1, 2),
                "second": round(coverage_2, 2),
            },
        ],
        "reason_summary": {
            "why_top_ranked_higher": [
                f"Matched more weighted symptoms ({illness_1['confidence_fc']} vs {illness_2['confidence_fc']})",
                f"Better subtype alignment ({coverage_1}% vs {coverage_2}%)",
                "Machine learning still favored it after adjustments",
                "Fewer critical symptoms were missing",
            ]
        },
    }


def display_symptom_matching(diagnosis, user_answers):
    """Breaks down symptom matching into Direct Matches, Subtype Matches, and Follow-up Matches."""
    illness_rule = next(
        (r for r in knowledge_base if r["illness"] == diagnosis["illness"]), None
    )
    if not illness_rule:
        return

    matched_symptoms = set(diagnosis["matched_symptoms"])
    direct_matches = []
    subtype_matches = []
    followup_matches = []

    for symptom in illness_rule["symptoms"]:
        symptom_name = symptom["name"].lower()
        expected_subtypes = [
            s.strip().lower()
            for s in symptom.get("subtype", "").split(",")
            if s.strip()
        ]
        expected_duration = symptom.get("duration_range", "Any")
        expected_severity = symptom.get("severity", "Any")

        # ✅ Only check symptoms the user actually reported
        if symptom_name not in matched_symptoms:
            continue

        if symptom_name in matched_symptoms:
            direct_matches.append(symptom_name.capitalize())

        user_response = user_answers.get(symptom_name, {})
        user_subtype_key = next(
            (
                q
                for q in symptom_followups.get(symptom_name, {}).get("questions", [])
                if any(
                    x in q for x in ["Dry or Wet", "Watery or Bloody", "Mild or Severe"]
                )
            ),
            None,
        )
        user_subtype = (
            user_response.get(user_subtype_key, "").lower().strip()
            if user_subtype_key
            else None
        )

        if user_subtype and expected_subtypes and user_subtype in expected_subtypes:
            subtype_matches.append(f"{symptom_name.capitalize()} ({user_subtype})")

        user_duration = user_response.get(
            f"How long has your pet had {symptom_name}?", ""
        ).lower()
        user_severity = user_response.get(
            f"Is the {symptom_name} Mild, Moderate, or Severe?", ""
        ).lower()

        # ✅ Follow-up: Duration match
        if expected_duration != "Any" and user_duration:
            if user_duration in expected_duration:
                followup_matches.append(
                    f"{symptom_name.capitalize()} (Duration: {user_duration})"
                )

        # ✅ Follow-up: Severity match
        if expected_severity != "Any" and user_severity:
            if user_severity == expected_severity.lower():
                followup_matches.append(
                    f"{symptom_name.capitalize()} (Severity: {user_severity})"
                )

    print("\n📌 **Symptom Matching Breakdown**")
    if direct_matches:
        print(f"   ✅ **Direct Matches:** {', '.join(direct_matches)}")
    if subtype_matches:
        print(f"   ✅ **Subtype Matches:** {', '.join(subtype_matches)}")
    if followup_matches:
        print(f"   ✅ **Follow-up Matches:** {', '.join(followup_matches)}")
    if not (direct_matches or subtype_matches or followup_matches):
        print("   ❌ No symptoms matched.")

def apply_softmax_to_confidences(diagnoses):
    """Applies softmax to the final AdaBoost confidence scores of the diagnoses list."""
    scores = np.array([d["confidence_ab"] for d in diagnoses])
    exp_scores = np.exp(scores)
    softmax_probs = exp_scores / np.sum(exp_scores)

    for i, d in enumerate(diagnoses):
        d["confidence_softmax"] = round(float(softmax_probs[i]), 4)

    return diagnoses


# ✅ Structured Comparison Output for Terminal (Place at end of `run_diagnosis()`)
def run_diagnosis():
    """Executes the diagnosis process using Forward Chaining, Boosting, and AdaBoost models."""

    fact_base = get_user_input()

    # 📌 Load Pet-Specific Resources
    global knowledge_base, boosting_model, adaboost_model, selected_features, df, all_symptoms
    knowledge_base, boosting_model, adaboost_model, selected_features, df = load_pet_resources(fact_base["pet_type"])
    all_symptoms = [col for col in df.columns if col not in ["Illness"]]

    # 📌 Proceed with Diagnosis
    possible_diagnoses = forward_chaining(fact_base)
    if not possible_diagnoses:
        print("\n❌ No matching illnesses found. Try entering different symptoms.")
        return

    refined_diagnoses = gradient_boosting_ranking(possible_diagnoses, fact_base)
    final_diagnoses = adaboost_ranking(refined_diagnoses, fact_base)
    final_diagnoses = apply_softmax_to_confidences(final_diagnoses)

    final_diagnoses.sort(key=lambda x: -x["confidence_softmax"])

    # Visual threshold and top-N
    PROB_THRESHOLD = 0.04
    filtered = [d for d in final_diagnoses if d["confidence_softmax"] >= PROB_THRESHOLD]
    top_results = filtered[:3]

    compare_illnesses(top_results, fact_base)
    fact_base["possible_diagnosis"] = final_diagnoses
    save_fact_base(fact_base)

    illness_info = load_illness_info()

    print("\n📌 **Pet Information Summary:**")
    print(f"🔹 Age: {fact_base['pet_info']['age_years']} years")
    print(f"🔹 Size: {fact_base['pet_info']['size']}")
    print(f"🔹 Breed: {fact_base['pet_info']['breed']}")

    print("\n🩺 **Symptoms Provided:**")
    for symptom in fact_base["symptoms"]:
        print(f"🔹 {symptom['name'].capitalize()}")

    print("\n🩺 **Final Diagnoses (Forward Chaining + Boosting + AdaBoost):**")
    for diagnosis in top_results:
        # ✅ Show evaluation metrics based on confusion matrix
        performance = evaluate_illness_performance(diagnosis["illness"])
        if performance:
            print("\n📊 **Model Evaluation for this Illness (from full dataset):**")
            print(f"   - Precision: {performance['metrics']['Precision']}")
            print(f"   - Recall: {performance['metrics']['Recall']}")
            print(f"   - Specificity: {performance['metrics']['Specificity']}")
            print(f"   - F1 Score: {performance['metrics']['F1 Score']}")
            print("   - Confusion Matrix:")
            print(
                f"     TP: {performance['confusion_matrix']['TP']}, FP: {performance['confusion_matrix']['FP']}"
            )
            print(
                f"     FN: {performance['confusion_matrix']['FN']}, TN: {performance['confusion_matrix']['TN']}"
            )
        print(f"🔹 {diagnosis['illness']} (Probability: {round(diagnosis['confidence_softmax'] * 100, 2)}%)")
        display_symptom_matching(diagnosis, fact_base["user_answers"])

        print(f"\n📌 **ML Confidence Score Adjustments**")
        print(f"   - Forward Chaining Base Confidence: {diagnosis['confidence_fc']}")
        print(
            f"   - Gradient Boosting Adjusted Confidence: {diagnosis['confidence_gb']}"
        )
        print(f"   - AdaBoost Final Confidence: {diagnosis['confidence_ab']}")

        rule = next(
            (r for r in load_knowledge_base() if r["illness"] == diagnosis["illness"]),
            None,
        )

        if rule:
            matched_symptoms = set(diagnosis["matched_symptoms"])
            illness_symptoms = {s["name"].lower() for s in rule["symptoms"]}
            missing_symptoms = illness_symptoms - matched_symptoms

            print(f"   🔹 **Why this illness?**")
            print(
                f"      - Matched Symptoms: {', '.join(diagnosis['matched_symptoms'])}"
            )

            illness_common_symptoms = illness_info.get(diagnosis["illness"], {}).get(
                "common_symptoms", []
            )
            if not illness_common_symptoms:
                illness_common_symptoms = [s["name"] for s in rule["symptoms"]]

            missing_symptoms_display = ", ".join(
                set(illness_common_symptoms) - matched_symptoms
            )
            print(
                f"      - Common Symptoms Not Reported: {missing_symptoms_display if missing_symptoms_display else 'None ✅'}"
            )

            age_range = rule.get("age_range", "Any").lower()
            breed = rule.get("breed", "Any").lower()
            size = rule.get("size", "Any").lower()
            pet_age_range = fact_base["pet_info"].get("age_range", "Any").lower()
            pet_breed = fact_base["pet_info"].get("breed", "Any").lower()
            pet_size = fact_base["pet_info"].get("size", "Any").lower()

            if age_range != "any" and age_range != pet_age_range:
                print(
                    f"      - ⚠️ This illness is usually found in {age_range.capitalize()} dogs, but your pet is {pet_age_range}."
                )

            if breed != "any" and breed != pet_breed:
                print(
                    f"      - ⚠️ This illness is more common in {breed} breeds, but your pet is a {pet_breed}."
                )

            if size != "any" and size != pet_size:
                print(
                    f"      - ⚠️ This illness is more typical in {size} dogs, but your pet is {pet_size}."
                )

        illness_details = illness_info.get(diagnosis["illness"], {})
        description = illness_details.get("description", "No description available.")
        severity = illness_details.get("severity", "Unknown")
        treatment = illness_details.get(
            "treatment", "No treatment guidelines provided."
        )

        print(f"\n   📌 **About {diagnosis['illness']}**")
        print(
            f"      - {illness_details.get('description', 'No description available.')}"
        )
        print(f"      - **Severity:** {illness_details.get('severity', 'Unknown')}")
        print(f"      - **Causes:** {illness_details.get('causes', 'N/A')}")
        print(f"      - **Transmission:** {illness_details.get('transmission', 'N/A')}")
        print(f"      - **Diagnosis:** {illness_details.get('diagnosis', 'N/A')}")
        print(f"      - **What To Do:** {illness_details.get('what_to_do', 'N/A')}")
        print(f"      - **Treatment:** {illness_details.get('treatment', 'N/A')}")
        print(
            f"      - **Recovery Time:** {illness_details.get('recovery_time', 'N/A')}"
        )
        print(
            f"      - **Risk Factors:** {', '.join(illness_details.get('risk_factors', [])) or 'None'}"
        )
        print(f"      - **Prevention:** {illness_details.get('prevention', 'N/A')}")
        print(
            f"      - **Contagious:** {'Yes' if illness_details.get('contagious', False) else 'No'}\n"
        )

    # ✅ Structured Comparison Output (Only once)
    structured_comparison = build_comparison_output(final_diagnoses, fact_base)

    print("\n🔍 Structured Comparison Output (for frontend):")
    for factor in structured_comparison.get("factors", []):
        top_illness = structured_comparison["top_illness"]
        second_illness = structured_comparison["second_illness"]
        print(
            f"| {factor['name']:<26} | {top_illness}: {factor['top']} | {second_illness}: {factor['second']} |"
        )

    print("\n🧠 Reason Summary:")
    for reason in structured_comparison.get("reason_summary", {}).get(
        "why_top_ranked_higher", []
    ):
        print(f"✅ {reason}")

    top_illness_data = next(
        (
            d
            for d in final_diagnoses
            if d["illness"] == structured_comparison["top_illness"]
        ),
        None,
    )
    if top_illness_data:
        illness_info_data = load_illness_info().get(top_illness_data["illness"], {})
        severity = illness_info_data.get("severity", "Unknown")
        treatment = illness_info_data.get(
            "treatment", "No treatment guidelines provided."
        )
        if "severe" in severity.lower():
            print("\n⚠️ Immediate Action Required:")
            print(
                f"{top_illness_data['illness']} is classified as **{severity.upper()}**."
            )
            print(f"👉 {treatment}")

    print("\n🧪 All Illness Probabilities (SoftMax normalized):")
    for d in final_diagnoses:
        print(f"🔹 {d['illness']}: {round(d['confidence_softmax'] * 100, 2)}%")

    print("\n✅ Diagnosis with full illness details included!")


def build_structured_output(fact_base, final_diagnoses):
    """Builds a frontend-consumable summary without affecting console prints."""
    output = {
        "pet_info": fact_base["pet_info"],
        "symptoms": [s["name"] for s in fact_base["symptoms"]],
        "top_diagnoses": [],
        "comparison": build_comparison_output(final_diagnoses, fact_base),
    }

    illness_details_db = load_illness_info()

    for diagnosis in final_diagnoses[:5]:
        rule = next(
            (r for r in knowledge_base if r["illness"] == diagnosis["illness"]), {}
        )
        illness_details = illness_details_db.get(diagnosis["illness"], {})

        output["top_diagnoses"].append(
            {
                "illness": diagnosis["illness"],
                "confidence_fc": diagnosis["confidence_fc"],
                "confidence_gb": diagnosis["confidence_gb"],
                "confidence_ab": diagnosis["confidence_ab"],
                "matched_symptoms": diagnosis["matched_symptoms"],
                "missing_symptoms": list(
                    set([s["name"].lower() for s in rule.get("symptoms", [])])
                    - set(diagnosis["matched_symptoms"])
                ),
                "severity": illness_details.get("severity", "Unknown"),
                "description": illness_details.get(
                    "description", "No description available."
                ),
                "treatment": illness_details.get(
                    "treatment", "No treatment available."
                ),
            }
        )

    return output


from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score


def evaluate_illness_performance(target_illness):
    """
    Evaluates the 2x2 confusion matrix and classification metrics
    for the given illness based on your full labeled dataset.
    """
    # Load your true vs predicted results
    eval_path = "data/true_vs_predicted.csv"
    if not os.path.exists(eval_path):
        print("⚠️ Evaluation file not found.")
        return None

    df_eval = pd.read_csv(eval_path)

    # Binary classification: target illness vs all others
    y_true = df_eval["Illness"].apply(lambda x: 1 if x == target_illness else 0)
    y_pred = df_eval["Predicted"].apply(lambda x: 1 if x == target_illness else 0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    specificity = tn / (tn + fp) if (tn + fp) != 0 else 0

    return {
        "illness": target_illness,
        "confusion_matrix": {
            "TP": int(tp),
            "FP": int(fp),
            "FN": int(fn),
            "TN": int(tn),
        },
        "metrics": {
            "Precision": round(precision, 4),
            "Recall": round(recall, 4),
            "Specificity": round(specificity, 4),
            "F1 Score": round(f1, 4),
        },
    }


# 📌 Run the system
if __name__ == "__main__":
    run_diagnosis()
