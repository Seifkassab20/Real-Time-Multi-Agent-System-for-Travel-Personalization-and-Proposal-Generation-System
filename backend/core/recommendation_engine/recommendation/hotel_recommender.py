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


handler = logging.StreamHandler()
file_handler = logging.FileHandler(
    "hotel_recommendation_agent.log", encoding="utf-8"
)

formatter = JsonFormatter()
handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger = logging.getLogger("hotel_recommendation_agent")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(file_handler)

# ========================================================
# Helpers
# ========================================================
def parse_price(price_str):
    if pd.isna(price_str):
        return None
    match = re.search(r"\d[\d,]*", str(price_str))
    return float(match.group().replace(",", "")) if match else None


def extract_rating(rating_str):
    if pd.isna(rating_str):
        return None
    match = re.search(r"[\d.]+", str(rating_str))
    return float(match.group()) if match else None

# ========================================================
# MAIN RECOMMENDATION AGENT
# ========================================================
def recommend_hotels(profile, hotels_df, max_price_per_night, top_n=15):

    logger.info(
        "Starting hotel recommendation",
        extra={
            "extra_data": {
                "agent": "hotel_recommendation",
                "destination": profile["destination"]["city"],
                "budget_total": profile["budget"]["total"],
                "days": profile["dates"]["days"]
            }
        }
    )

    try:
        # --------------------------
        # Profile inputs
        # --------------------------
        total_budget = profile["budget"]["total"]
        num_days = profile["dates"]["days"]
        city = profile["destination"]["city"]

        # --------------------------
        # Clean data
        # --------------------------
        df = hotels_df.copy()
        original_count = len(df)

        df["price_per_night"] = df["price_per_night_egp"].apply(parse_price)
        df["rating_score"] = df["rating"].apply(extract_rating)

        df = df.drop_duplicates(subset=["name"])
        df = df.dropna(subset=["price_per_night", "rating_score"])

        logger.info(
            "Data cleaned",
            extra={
                "extra_data": {
                    "original_rows": original_count,
                    "remaining_rows": len(df)
                }
            }
        )

        # --------------------------
        # Filter
        # --------------------------
        df = df[
            (df["city"].str.lower() == city.lower()) &
            (df["price_per_night"] <= max_price_per_night)
        ]

        if df.empty:
            logger.warning(
                "No hotels match constraints",
                extra={
                    "extra_data": {
                        "city": city,
                        "max_price_per_night": max_price_per_night
                    }
                }
            )
            return {
                "status": "NO_MATCH",
                "message": "No hotels match your budget in this city."
            }

        # --------------------------
        # Scoring (Explainable)
        # --------------------------
        df["price_score"] = 1 / df["price_per_night"]
        df["final_score"] = (
            df["rating_score"] * 0.7 +
            df["price_score"] * 0.3
        )

        df = df.sort_values("final_score", ascending=False)

        # --------------------------
        # Output
        # --------------------------
        recommendations = []

        for _, row in df.head(top_n).iterrows():
            recommendations.append({
                "name": row["name"],
                "city": row["city"],
                "price_per_night": round(row["price_per_night"], 2),
                "rating": row["rating_score"],
                "link": row["link"],
                "reason": "High rating and fits within your hotel budget"
            })

        hotel_budget = df.head(top_n)["price_per_night"].sum() * num_days

        logger.info(
            "Hotel recommendations generated",
            extra={
                "extra_data": {
                    "recommendations_count": len(recommendations),
                    "estimated_total_cost": round(hotel_budget, 2)
                }
            }
        )

        return {
            "status": "OK",
            "hotel_budget": hotel_budget,
            "max_price_per_night": max_price_per_night,
            "recommendations": recommendations
        }

    except Exception:
        logger.error(
            "Recommendation agent failed",
            exc_info=True,
            extra={"extra_data": {"agent": "hotel_recommendation"}}
        )
        return {
            "status": "ERROR",
            "message": "Failed to generate hotel recommendations"
        }

# ========================================================
# SAVE OUTPUT (Artifact)
# ========================================================
def save_hotel_result_to_json(result: dict, path="data/artifacts/hotel_result.json"):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(
            "Hotel recommendation artifact saved",
            extra={"extra_data": {"path": path}}
        )

    except Exception:
        logger.error(
            "Failed to save hotel result",
            exc_info=True,
            extra={"extra_data": {"path": path}}
        )

# ========================================================
# CLI / TEST RUN
# ========================================================
profile = {
    "budget": {"total": 50000},
    "dates": {"days": 3},
    "destination": {"city": "Cairo"}
}

hotels_df = pd.read_excel(
    "data/hotels_latest.xlsx"
)

max_price_per_night = (
    profile["budget"]["total"] * 0.45
) / profile["dates"]["days"]

result = recommend_hotels(profile, hotels_df, max_price_per_night)
save_hotel_result_to_json(result)
