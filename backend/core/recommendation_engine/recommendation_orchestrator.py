import json
from backend.core.recommendation_engine.planner.Planning_Agent import PlanningAgent
from recommendation.hotel_recommender import recommend_hotels
from recommendation.activity_recommender import recommend_activities


class load_kb_artifacts:
    def __init__(self):
        self.activities_filepath = 'backend/core/recommendation_engine/data/data/artifacts/activities_result.json'
        self.hotel_filepath = 'backend/core/recommendation_engine/data/data/artifacts/hotel_result.json'

    def load_hotel_recommendations(self):
        with open(self.hotel_filepath, 'r') as f:
            return json.load(f)
    def load_activity_recommendations(self):
        with open(self.activities_filepath, 'r') as f:
            return json.load(f)
        
        
def create_plan(user_profile):
    planner = PlanningAgent(user_profile)
    budget_distribution = planner.distribute_budget()
    travel_plan = planner.create_plan(hotel_result, activities_result)
    return plan

def recommend(user_profile):
    kb_loader = load_kb_artifacts()
    hotel_result = kb_loader.load_hotel_recommendations()
    activities_result = kb_loader.load_activity_recommendations()

    plan = create_plan(user_profile)
    return plan


def run_recommendation():
    pass