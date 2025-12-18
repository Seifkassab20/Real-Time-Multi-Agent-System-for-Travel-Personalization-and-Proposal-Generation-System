import pandas as pd
import re

# ==============================
# Helpers
# ==============================
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

# ==============================
# MAIN RECOMMENDATION AGENT
# ==============================
def recommend_hotels(profile: dict, hotels_df: pd.DataFrame, top_n=5):
    """
    Input:
      - profile (from Profile Agent)
      - hotels_df (real-time scraped data)

    Output:
      - ranked hotel recommendations with explanation
    """

    # --------------------------
    # Profile inputs
    # --------------------------
    total_budget = profile["budget"]["total"]
    num_days = profile["dates"]["days"]
    city = profile["destination"]["city"]

    # Budget logic (planner-compatible)
    HOTEL_BUDGET_RATIO = 0.45
    hotel_budget = total_budget * HOTEL_BUDGET_RATIO

    max_price_per_night = hotel_budget / num_days

    # --------------------------
    # Clean data
    # --------------------------
    df = hotels_df.copy()

    df["price_per_night"] = df["price_per_night_egp"].apply(parse_price)
    df["rating_score"] = df["rating"].apply(extract_rating)
    df = df.drop_duplicates(subset=["name"])
    df = df.dropna(subset=["price_per_night", "rating_score"])

    # --------------------------
    # Filter
    # --------------------------
    df = df[
        (df["city"].str.lower() == city.lower()) &
        (df["price_per_night"] <= max_price_per_night)
    ]

    if df.empty:
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
            "reason": (
                "High rating and fits within your hotel budget"
            )
        })
    return {
        "status": "OK",
        "hotel_budget": hotel_budget,
        "recommendations": recommendations
    }

# ==============================
profile = {
    "budget": {"total": 20000},
    "dates": {"days": 3},
    "destination": {"city": "Cairo"}
}
def print_hotel_recommendations(result: dict):
    if result["status"] != "OK":
        print(f"\n❌ {result.get('message', 'No recommendations available')}")
        return

    print("\n🏨 HOTEL RECOMMENDATIONS")
    print("=" * 50)
    print(f"💰 Total Hotel Budget: {result['hotel_budget']:.0f} EGP")
    print("-" * 50)

    for idx, hotel in enumerate(result["recommendations"], start=1):
        print(f"\n#{idx} {hotel['name']}")
        print(f"📍 City        : {hotel['city']}")
        print(f"⭐ Rating      : {hotel['rating']}")
        print(f"💵 Price/Night : {hotel['price_per_night']} EGP")
        print(f"🧠 Reason      : {hotel['reason']}")
        print(f"🔗 Link        : {hotel['link']}")

    print("\n" + "=" * 50)


hotels_df = pd.read_excel("data/hotels_latest.xlsx")

result = recommend_hotels(profile, hotels_df)
print_hotel_recommendations(result)
