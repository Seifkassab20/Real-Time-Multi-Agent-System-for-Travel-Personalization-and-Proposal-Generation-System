import pandas as pd
import re

# ==============================
# Helpers
# ==============================
def extract_rating(rating_str):
    if pd.isna(rating_str):
        return None
    match = re.search(r"[\d.]+", str(rating_str))
    return float(match.group()) if match else None


def estimate_activity_cost(category):
    """
    Heuristic cost estimation (EGP)
    """
    costs = {
        "cafe": 150,
        "museum": 100,
        "park": 50,
        "mall": 0
    }
    return costs.get(category.lower(), 100)


def extract_city_from_address(text):
    if not isinstance(text, str):
        return None

    text = text.lower()

    # GIZA patterns (very important)
    giza_patterns = [
        "giza",
        "giza governorate",
        "6 october",
        "october city",
        "sheikh zayed",
        "haram",
        "dokki",
        "mohandessin",
        "faisal",
        "imbaba",
        "pyramids"
    ]

    # CAIRO patterns
    cairo_patterns = [
        "cairo",
        "cairo governorate",
        "nasr city",
        "heliopolis",
        "zamalek",
        "downtown",
        "maadi",
        "new cairo",
        "tagamoa",
        "garden city"
    ]

    for p in giza_patterns:
        if p in text:
            return "Giza"

    for p in cairo_patterns:
        if p in text:
            return "Cairo"

    return None


def normalize_category(cat):
    mapping = {
        "cafes": "cafe",
        "cafe": "cafe",
        "museums": "museum",
        "museum": "museum",
        "parks": "park",
        "park": "park",
        "malls": "mall",
        "mall": "mall"
    }
    return mapping.get(cat.lower(), cat.lower())

# =============================
# MAIN ACTIVITY RECOMMENDER
# =============================
def recommend_activities(profile: dict, activities_df: pd.DataFrame):
    """
    Rule-based, explainable activity recommender
    """

    # --------------------------
    # Profile inputs
    # --------------------------
    cities = profile["destination"]["city"]
    cities = [c.lower() for c in cities] if isinstance(cities, list) else [cities.lower()]

    days = profile["dates"]["days"]

    preferences = profile.get("preferences", {})

    preferred_types = preferences.get(
        "activity_types", ["cafe", "mall", "museum", "park"]
    )
    preferred_types = [normalize_category(t) for t in preferred_types]

    # ✅ NEW: activities per day (numeric, explicit)
    activities_per_day = preferences.get("activities_per_day", 3)
    activities_per_day = max(1, int(activities_per_day))

    total_activities = activities_per_day * days

    # --------------------------
    # Clean & normalize data
    # --------------------------
    df = activities_df.copy()

    df["rating_score"] = df["rating"].apply(extract_rating)
    df["category"] = df["category"].apply(normalize_category)

    df["extracted_city"] = df["address"].apply(extract_city_from_address)
    df = df[df["extracted_city"].isin(["Cairo", "Giza"])]
    df["extracted_city"] = df["extracted_city"].str.lower()

    df = df.dropna(subset=["name", "category"])
    df = df[df["category"].isin(preferred_types)]

    # --------------------------
    # Location filtering
    # --------------------------
    city_df = df[df["extracted_city"].isin(cities)]

    if city_df.empty:
        return {
            "status": "NO_MATCH",
            "message": f"No activities found in {', '.join(c.capitalize() for c in cities)}"
        }

    # --------------------------
    # Cost estimation
    # --------------------------
    city_df["estimated_cost"] = city_df["category"].apply(
        estimate_activity_cost
    )

    # --------------------------
    # Scoring
    # --------------------------
    city_df["rating_score"] = city_df["rating_score"].fillna(3.5)

    city_df["final_score"] = (
        city_df["rating_score"] * 0.8 +
        (1 / (city_df["estimated_cost"] + 1)) * 0.2
    )

    city_df = city_df.sort_values("final_score", ascending=False)

    # --------------------------
    # Balanced category selection
    # --------------------------
    recommendations = []
    used_categories = {c: 0 for c in preferred_types}
    max_per_category = total_activities // len(preferred_types) + 1

    for _, row in city_df.iterrows():
        cat = row["category"]

        if used_categories[cat] >= max_per_category:
            continue

        recommendations.append({
            "name": row["name"],
            "category": row["category"],
            "city": row["extracted_city"].capitalize(),
            "rating": row["rating_score"],
            "estimated_cost": row["estimated_cost"],
            "link": row.get("link"),
            "reason": f"Highly rated {cat} in {row['extracted_city'].capitalize()}"
        })

        used_categories[cat] += 1

        if len(recommendations) >= total_activities:
            break

    return {
        "status": "OK",
        "days": days,
        "activities_per_day": activities_per_day,
        "activities_count": len(recommendations),
        "recommendations": recommendations
    }

# ==============================
# Pretty Printer
# ==============================
def print_activity_recommendations(result):
    if result["status"] != "OK":
        print(f"\n❌ {result.get('message', 'No activities found')}")
        return

    print("\n🎯 ACTIVITY RECOMMENDATIONS")
    print("=" * 50)

    for idx, act in enumerate(result["recommendations"], start=1):
        print(f"\n#{idx} {act['name']}")
        print(f"🏷️ Type   : {act['category']}")
        print(f"📍 City   : {act['city']}")
        print(f"⭐ Rating : {act['rating']}")
        print(f"💰 Cost  : ~{act['estimated_cost']} EGP")
        print(f"🧠 Reason: {act['reason']}")


    print("\n" + "=" * 50)


# ==============================
# Example Run
# ==============================
if __name__ == "__main__":
    city = ["Giza", "Cairo"]
    profile = {
        "budget": {"total": 50000},
        "dates": {"days": 3},
        "destination": {
            "city": ["Cairo", "Giza"]
        },
        "preferences": {
            "activity_types": ["cafes", "museums", "parks" , "malls"],
            "activities_per_day": 3
        }
    }


    museums_df = pd.read_excel("data/museums.xlsx")
    cafes_df = pd.read_excel("data/cafes.xlsx")
    parks_df = pd.read_excel("data/parks.xlsx")
    malls_df = pd.read_excel("data/malls.xlsx")

    activities_df = pd.concat(
        [museums_df, cafes_df, parks_df, malls_df],
        ignore_index=True
    )
    result = recommend_activities(profile, activities_df)

    print_activity_recommendations(result)
