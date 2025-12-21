import pandas as pd
import re
import json
import logging
from pathlib import Path

# ========================================================
# LOGGING SETUP (Structured / MLOps)
# ========================================================
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log.update(record.extra_data)
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)


console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(
    "activity_recommendation_agent.log", encoding="utf-8"
)

formatter = JsonFormatter()
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger = logging.getLogger("activity_recommendation_agent")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

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
        "cafe": 250,
        "museum": 350,
        "park": 100,
        "mall": 0
    }
    return costs.get(category.lower(), 200)


def extract_city_from_address(text):
    if not isinstance(text, str):
        return None

    text = text.lower()

    giza_patterns = [
        "giza", "giza governorate", "6 october", "october city",
        "sheikh zayed", "haram", "dokki", "mohandessin",
        "faisal", "imbaba", "pyramids"
    ]

    cairo_patterns = [
        "cairo", "cairo governorate", "nasr city", "heliopolis",
        "zamalek", "downtown", "maadi", "new cairo",
        "tagamoa", "garden city"
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
def recommend_activities(profile, activities_df, activities_budget_per_day):

    logger.info(
        "Starting activity recommendation",
        extra={
            "extra_data": {
                "agent": "activity_recommendation",
                "cities": profile["destination"]["city"],
                "days": profile["dates"]["days"],
                "daily_budget": activities_budget_per_day
            }
        }
    )

    try:
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

        activities_per_day = preferences.get("activities_per_day", 3)
        activities_per_day = max(1, int(activities_per_day))

        total_activities = activities_per_day * days

        # --------------------------
        # Clean & normalize data
        # --------------------------
        df = activities_df.copy()
        original_rows = len(df)

        df["rating_score"] = df["rating"].apply(extract_rating)
        df["category"] = df["category"].apply(normalize_category)

        df["extracted_city"] = df["address"].apply(extract_city_from_address)
        df = df[df["extracted_city"].isin(["Cairo", "Giza"])]
        df["extracted_city"] = df["extracted_city"].str.lower()

        df = df.dropna(subset=["name", "category"])
        df = df[df["category"].isin(preferred_types)]

        df["estimated_cost"] = df["category"].apply(estimate_activity_cost)

        logger.info(
            "Activity data cleaned",
            extra={
                "extra_data": {
                    "original_rows": original_rows,
                    "remaining_rows": len(df),
                    "preferred_categories": preferred_types
                }
            }
        )

        # --------------------------
        # Location filtering
        # --------------------------
        city_df = df[df["extracted_city"].isin(cities)]

        if city_df.empty:
            logger.warning(
                "No activities found after city filtering",
                extra={"extra_data": {"cities": cities}}
            )
            return {
                "status": "NO_MATCH",
                "message": f"No activities found in {', '.join(c.capitalize() for c in cities)}"
            }

        # --------------------------
        # Cost filtering
        # --------------------------
        city_df = city_df[
            city_df["estimated_cost"] <= activities_budget_per_day
        ]

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
                "reason": f"Highly rated {cat} in {row['extracted_city'].capitalize()}"
            })

            used_categories[cat] += 1

            if len(recommendations) >= total_activities:
                break

        logger.info(
            "Activity recommendations generated",
            extra={
                "extra_data": {
                    "recommendations_count": len(recommendations),
                    "total_activities_needed": total_activities
                }
            }
        )

        return {
            "status": "OK",
            "days": days,
            "activities_per_day": activities_per_day,
            "daily_budget": activities_budget_per_day,
            "recommendations": recommendations
        }

    except Exception:
        logger.error(
            "Activity recommendation failed",
            exc_info=True,
            extra={"extra_data": {"agent": "activity_recommendation"}}
        )
        return {
            "status": "ERROR",
            "message": "Failed to generate activity recommendations"
        }

# ==============================
# SAVE OUTPUT (Artifact)
# ==============================
def save_activities_result_to_json(result: dict, path="data/artifacts/activities_result.json"):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            "Activities recommendation artifact saved",
            extra={"extra_data": {"path": path}}
        )

    except Exception:
        logger.error(
            "Failed to save activities result",
            exc_info=True,
            extra={"extra_data": {"path": path}}
        )

# ==============================
# Example Run
# ==============================
if __name__ == "__main__":
    profile = {
        "budget": {"total": 50000},
        "dates": {"days": 3},
        "destination": {
            "city": ["Cairo", "Giza"]
        },
        "preferences": {
            "activity_types": ["cafes", "museums", "parks", "malls"],
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

    activities_budget_per_day = (
        profile["budget"]["total"] * 0.25
    ) / profile["dates"]["days"]

    result = recommend_activities(profile, activities_df, activities_budget_per_day)
    save_activities_result_to_json(result)
