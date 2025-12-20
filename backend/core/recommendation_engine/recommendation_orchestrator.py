import json
import os
from pathlib import Path
from backend.core.recommendation_engine.planner.Planning_Agent import PlanningAgent
from backend.core.recommendation_engine.recommendation.hotel_recommender import recommend_hotels
from backend.core.recommendation_engine.recommendation.activity_recommender import recommend_activities


class load_kb_artifacts:
    def __init__(self):
        # Get the directory of this file
        base_dir = Path(__file__).parent
        self.activities_filepath = base_dir / 'data' / 'data' / 'artifacts' / 'activities_result.json'
        self.hotel_filepath = base_dir / 'data' / 'data' / 'artifacts' / 'hotel_result.json'

    def load_hotel_recommendations(self):
        """Load hotel recommendations from file or return empty structure"""
        try:
            if self.hotel_filepath.exists():
                with open(self.hotel_filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load hotel data from {self.hotel_filepath}: {e}")
        
        # Return default hotel structure
        return {"hotels": [], "recommendations": []}
    
    def load_activity_recommendations(self):
        """Load activity recommendations from file or return empty structure"""
        try:
            if self.activities_filepath.exists():
                with open(self.activities_filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load activity data from {self.activities_filepath}: {e}")
        
        # Return default activity structure
        return {"activities": [], "recommendations": [], "activities_per_day": []}
        
        
def create_plan(user_profile, hotel_result, activities_result):
    """Create travel plan from user profile and recommendations"""
    try:
        planner = PlanningAgent(user_profile)
        budget_distribution = planner.distribute_budget()
        travel_plan = planner.create_plan(hotel_result, activities_result)
        return travel_plan
    except Exception as e:
        print(f"Error creating plan: {e}")
        return {"error": str(e), "profile": user_profile}

def recommend(user_profile):
    """Main recommendation orchestrator"""
    kb_loader = load_kb_artifacts()
    hotel_result = kb_loader.load_hotel_recommendations()
    activities_result = kb_loader.load_activity_recommendations()

    plan = create_plan(user_profile, hotel_result, activities_result)
    return plan


def run_recommendation():
    pass