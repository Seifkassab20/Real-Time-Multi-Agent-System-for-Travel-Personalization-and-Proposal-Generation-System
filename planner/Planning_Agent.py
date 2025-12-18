from typing import Dict
import json
from pathlib import Path

# ==============================
# Helpers
# ==============================
def load_json(path: str) -> Dict:
    if not Path(path).exists():
        raise FileNotFoundError(f"Required artifact not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================
# PLANNING AGENT
# ==============================
class PlanningAgent:
    def __init__(self, profile: dict):
        self.profile = profile
        self.days = profile["dates"]["days"]

    def distribute_budget(self):
        total = self.profile["budget"]["total"]
        days = self.profile["dates"]["days"]

        budget = {
            "hotel_total": total * 0.45,
            "activities_total": total * 0.25,
            "food_total": total * 0.20,
            "transport_total": total * 0.10,
        }

        budget["hotel_per_night"] = budget["hotel_total"] / days
        budget["activities_per_day"] = budget["activities_total"] / days
        budget["food_per_day"] = budget["food_total"] / days

        return budget

    def create_plan(self, hotel_result: Dict, activities_result: Dict) -> Dict:
        activities = activities_result["recommendations"]
        activities_per_day = activities_result["activities_per_day"]

        plan = {}
        activity_index = 0

        for day in range(1, self.days + 1):
            day_key = f"Day {day}"
            plan[day_key] = []

            for _ in range(activities_per_day):
                if activity_index >= len(activities):
                    break

                plan[day_key].append({
                    "type": "activity",
                    **activities[activity_index]
                })
                activity_index += 1

            # Meals
            plan[day_key].insert(1, {
                "type": "meal",
                "name": "Lunch",
                "estimated_cost": 200
            })

            plan[day_key].append({
                "type": "meal",
                "name": "Dinner",
                "estimated_cost": 300
            })

        return {
            "status": "OK",
            "budget_breakdown": self.distribute_budget(),
            "hotel": hotel_result["recommendations"][0],
            "itinerary": plan
        }


# ==============================
# Pretty Printer
# ==============================
def print_itinerary(plan):
    print("\n🗓️    TRIP ITINERARY")
    print("=" * 50)

    for day, items in plan["itinerary"].items():
        print(f"\n{day}")
        print("-" * 30)

        for item in items:
            if item["type"] == "activity":
                print(f"🎯   {item['name']} ({item['category']})")
            elif item["type"] == "meal":
                print(f"🍽️   {item['name']} (~{item['estimated_cost']} EGP)")

    print("\n🏨   Hotel:", plan["hotel"]["name"])


# ==============================
# Run Planner
# ==============================
if __name__ == "__main__":

    profile = {
        "budget": {"total": 5},
        "dates": {"days": 3},
        "destination": {
            "city": ["Cairo", "Giza"]
        },
        "preferences": {
            "activity_types": ["cafes", "museums", "parks", "malls"],
            "activities_per_day": 3
        }
    }

    # ✅ Load agent outputs (ONLY source)
    hotel_result = load_json("data/artifacts/hotel_result.json")
    activities_result = load_json("data/artifacts/activites_result.json")

    planner = PlanningAgent(profile)

    final_plan = planner.create_plan(
        hotel_result=hotel_result,
        activities_result=activities_result
    )

    print_itinerary(final_plan)
