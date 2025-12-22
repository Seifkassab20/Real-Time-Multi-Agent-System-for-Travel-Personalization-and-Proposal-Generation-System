from backend.core.recommendation_engine.planner.Planning_Agent import PlanningAgent
from backend.core.recommendation_engine.recommendation.hotel_recommender import recommend_hotels
from backend.core.recommendation_engine.recommendation.activity_recommender import recommend_activities
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
today = datetime.today()

MERGE_RULES = {
    "budget": "ignore",         
    "adults": "overwrite",
    "children": "overwrite",    
    "children_age": "append",
    "rooms": "overwrite",
    "city": "ignore",
    "check_in": "ignore",
    "check_out": "ignore",
    "activities": "append",
    "preferences": "append",
    "keywords": "append"
}

final_profile = {
    "user_id": str(uuid.uuid4()),
    "segment_ids": [],
    "budget": None,
    "adults": None,
    "children": None,
    "children_age": None,
    "rooms": None,
    "city": None,
    "check_in": None,
    "check_out": None,
    "activities": [],
    "preferences": [],
    "keywords": []
}


def merge_value(existing, incoming, rule):
    if incoming is None:
        return existing
    if rule == "ignore":
        return existing if existing is not None else incoming
    if existing is None:
        return incoming
    if rule == "append":
        if isinstance(existing, list):
            return existing + (incoming if isinstance(incoming, list) else [incoming])
        return [existing, incoming]
    if rule == "overwrite":
        return incoming  
    return existing


def build_user_profile_from_extraction(extracted_data):
    """Convert extracted profile to recommendation engine format"""
    days = 7  # default
    if extracted_data.get("check_in") and extracted_data.get("check_out"):
        try:
            check_in = datetime.fromisoformat(extracted_data["check_in"])
            check_out = datetime.fromisoformat(extracted_data["check_out"])
            days = (check_out - check_in).days
        except:
            pass
    
    # Ensure interests is a clean list
    interests = []
    if extracted_data.get("activities"):
        activities = extracted_data.get("activities", [])
        interests.extend(activities if isinstance(activities, list) else [activities])
    if extracted_data.get("preferences"):
        preferences = extracted_data.get("preferences", [])
        interests.extend(preferences if isinstance(preferences, list) else [preferences])
    
    user_profile = {
        "budget": {
            "total": extracted_data.get("budget") or 2000
        },
        "travelers": {
            "adults": extracted_data.get("adults") or 1,
            "children": extracted_data.get("children") or 0,
            "children_age": extracted_data.get("children_age") or []
        },
        "rooms": extracted_data.get("rooms") or 1,
        "dates": {
            "days": days,
            "start_date": extracted_data.get("check_in") or (today + timedelta(days=0)).strftime("%Y-%m-%d"),
            "end_date": extracted_data.get("check_out") or (today + timedelta(days=days)).strftime("%Y-%m-%d")
        },
        "destination": extracted_data.get("city") or "Cairo",
        "interests": interests
    }
    return user_profile



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
        
        return {"hotels": [], "recommendations": []}
    
    def load_activity_recommendations(self):
        """Load activity recommendations from file or return empty structure"""
        try:
            if self.activities_filepath.exists():
                with open(self.activities_filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load activity data from {self.activities_filepath}: {e}")
        
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

