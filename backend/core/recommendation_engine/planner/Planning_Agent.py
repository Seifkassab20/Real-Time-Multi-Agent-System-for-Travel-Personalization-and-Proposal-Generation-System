from typing import Dict
import json
from pathlib import Path
import logging
import sys
import traceback

# ==============================
# LOGGING CONFIG (MLOps Style)
# ==============================
logger = logging.getLogger("planning_agent")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(stage)s | %(message)s'
)


handler.setFormatter(formatter)
logger.addHandler(handler)


def log(stage: str, level: str, message: str, **extra):
    if level == "info":
        logger.info(message, extra={"stage": stage, **extra})
    elif level == "warning":
        logger.warning(message, extra={"stage": stage, **extra})
    elif level == "error":
        logger.error(message, extra={"stage": stage, **extra})



# ==============================
# Helpers
# ==============================
def load_json(path: str) -> Dict:
    try:
        if not Path(path).exists():
            raise FileNotFoundError(f"Required artifact not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        log(
            stage="artifact_load",
            level="info",
            message="Artifact loaded successfully",
            path=path
        )
        return data

    except Exception as e:
        log(
            stage="artifact_load",
            level="error",
            message="Failed to load artifact",
            path=path,
            exception=traceback.format_exc()
        )
        raise


# ==============================
# PLANNING AGENT
# ==============================
class PlanningAgent:
    def __init__(self, profile: dict):
        self.profile = profile
        self.days = profile["dates"]["days"]

        log(
            stage="agent_init",
            level="info",
            message="PlanningAgent initialized",
            days=self.days
        )

    def distribute_budget(self):
        try:
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

            log(
                stage="budget_distribution",
                level="info",
                message="Budget distributed successfully",
                total_budget=total
            )

            return budget

        except Exception:
            log(
                stage="budget_distribution",
                level="error",
                message="Failed to distribute budget",
                exception=traceback.format_exc()
            )
            raise

    def create_plan(self, hotel_result: Dict, activities_result: Dict) -> Dict:
        try:
            activities = activities_result.get("recommendations", [])
            activities_per_day = activities_result.get("activities_per_day")

            if activities_per_day is None:
                log(
                    stage="plan_creation",
                    level="warning",
                    message="activities_per_day missing, defaulting to 2"
                )
                activities_per_day = 2

            budget = self.distribute_budget()

            lunch_cost = budget["food_per_day"] * 0.6
            dinner_cost = budget["food_per_day"] * 0.4

            plan = {}
            activity_index = 0

            for day in range(1, self.days + 1):
                day_key = f"Day {day}"
                plan[day_key] = []

                for _ in range(activities_per_day):
                    if activity_index >= len(activities):
                        break

                    activity = activities[activity_index]

                    if "price" not in activity:
                        log(
                            stage="activity_validation",
                            level="warning",
                            message="Activity missing price",
                            activity_name=activity.get("name")
                        )

                    plan[day_key].append({
                        "type": "activity",
                        **activity
                    })

                    activity_index += 1

                # Meals
                plan[day_key].insert(1, {
                    "type": "meal",
                    "name": "Lunch",
                    "estimated_cost": round(lunch_cost, 2)
                })

                plan[day_key].append({
                    "type": "meal",
                    "name": "Dinner",
                    "estimated_cost": round(dinner_cost, 2)
                })

            hotels = hotel_result.get("recommendations", [])
            if not hotels:
                log(
                    stage="hotel_selection",
                    level="error",
                    message="No hotel recommendations available"
                )
                raise ValueError("Hotel recommendations are empty")

            log(
                stage="plan_creation",
                level="info",
                message="Plan created successfully",
                days=self.days
            )

            return {
                "status": "OK",
                "budget_breakdown": budget,
                "hotel": hotels[0],
                "itinerary": plan
            }

        except Exception:
            log(
                stage="plan_creation",
                level="error",
                message="Failed to create plan",
                exception=traceback.format_exc()
            )
            raise


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
                print(f"🎯   {item.get('name')} ({item.get('category')})")
            elif item["type"] == "meal":
                print(f"🍽️   {item['name']} (~{item['estimated_cost']} EGP)")

    print("\n🏨   Hotel:", plan["hotel"].get("name"))


# ==============================
# Run Planner
# ==============================
if __name__ == "__main__":
    try:
        profile = {
            "budget": {"total": 30000},
            "dates": {"days": 3},
            "destination": {
                "city": ["Cairo", "Giza"]
            },
            "preferences": {
                "activity_types": ["cafes", "museums", "parks", "malls"],
                "activities_per_day": 3
            }
        }

        hotel_result = load_json("data/artifacts/hotel_result.json")
        activities_result = load_json("data/artifacts/activities_result.json")

        planner = PlanningAgent(profile)
        final_plan = planner.create_plan(
            hotel_result=hotel_result,
            activities_result=activities_result
        )

        print_itinerary(final_plan)

        log(
            stage="pipeline_complete",
            level="info",
            message="Planning pipeline finished successfully"
        )

    except Exception:
        log(
            stage="pipeline_failure",
            level="error",
            message="Planning pipeline crashed",
            exception=traceback.format_exc()
        )
