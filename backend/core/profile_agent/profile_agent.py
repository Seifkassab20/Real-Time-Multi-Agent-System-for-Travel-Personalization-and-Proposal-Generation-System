import sys
import os
from dotenv import load_dotenv
load_dotenv()
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
if project_root not in sys.path:
    sys.path.append(project_root)

sys.path.append(os.path.join(current_dir, "../../../"))

from uuid import UUID

from backend.core.llm import OllamaCloudLLM
from backend.core.prompts.prompt_loader import PromptLoader
from backend.core.profile_agent.models import profile_agent_response
from backend.database.db import NeonDatabase
from backend.database.models.customer_profile import CustomerProfileDB
from backend.database.repostries.customer_profile_repo import CustomerProfileRepository
from backend.database.repostries.extraction_repo import ExtractionRepository
from backend.database.models.customer_profile import CustomerProfileDB



class ProfileAgent:
    def __init__(self):
        self.llm = OllamaCloudLLM()
        self.system_prompt = PromptLoader.load_prompt("profile_agent_prompt.yaml")
        self.profile_repo = CustomerProfileRepository()
        self.extraction_repo = ExtractionRepository()

    async def get_profile_by_call_id(self, call_id: str) -> CustomerProfileDB | None:
        """Retrieve a customer profile from the database using call_id."""
        NeonDatabase.init()
        
        async with NeonDatabase.get_session() as session:
            # Profiles are linked via extraction_id, which in this system is set to call_id
            return await self.profile_repo.get_by_call_id(session, call_id)


    async def invoke(self, call_id: str) -> dict:
        """Generate profile questions based on the user's existing profile.
        Args:
            call_id: The extraction/call id for the session.
        Returns:
            tuple: A tuple of (json_response, profile_id).
        """
        # Fetch the user profile from database
        user_profile = await self.get_profile_by_call_id(call_id)

        if user_profile:
            # Convert profile to dict for context
            profile_data = {
                "budget": getattr(user_profile, "budget", 0),
                "check_in": str(getattr(user_profile, "check_in", "Unknown")),
                "check_out": str(getattr(user_profile, "check_out", "Unknown")),
                "adults": getattr(user_profile, "adults", 0),
                "children": getattr(user_profile, "children", 0),
                "children_ages": getattr(user_profile, "children_ages", []),
                'rooms': getattr(user_profile, "rooms", 0),
                'city': getattr(user_profile, "city", ""),
                'activities': getattr(user_profile, "activities", []),
                'preferences': getattr(user_profile, "preferences", []),
                'keywords': getattr(user_profile, "keywords", []),
            }
        else:
            profile_data = {}

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Start generating the questions from this user profile:\n{profile_data}"}
        ]

        print("DEBUG - Profile data:", profile_data)

        try:
            response = self.llm.chat_structured(
                messages,
                profile_agent_response,
                temperature=0.0,
                max_tokens=2000
            )
            print("DEBUG - Response:", response)

            # Create-if-missing: if no profile exists, insert regardless of segment
            if not user_profile:
                created_profile = await self.add_db(response, call_id)
                return response.model_dump_json(), str(created_profile.profile_id)

            # Profile exists; return questions with existing profile_id
            return response.model_dump_json(), str(user_profile.profile_id)
        except Exception as e:
            print(f"Error in profile questions generation: {e}")
            return None, None


    async def add_db(self, data: dict, call_id):
        """Add customer profile to database. Expects a dict."""
        # Only persist supported DB fields; ignore LLM-only keys like 'questions'
        raw: dict
        if hasattr(data, "model_dump"):
            raw = data.model_dump(exclude_none=True)
        elif hasattr(data, "dict"):
            raw = data.dict(exclude_none=True)
        else:
            raw = dict(data) if isinstance(data, dict) else {}

        allowed_keys = {
            "check_in", "check_out", "budget", "adults", "children",
            "children_ages", "specific_sites", "interests",
            "accommodation_preference", "tour_style",
        }
        payload = {k: raw[k] for k in allowed_keys if k in raw}

        # Normalize types
        from datetime import date as _date
        for k in ("check_in", "check_out"):
            v = payload.get(k)
            if isinstance(v, str) and v:
                try:
                    payload[k] = _date.fromisoformat(v)
                except Exception:
                    pass
        for k in ("budget", "adults", "children"):
            v = payload.get(k)
            if isinstance(v, str):
                try:
                    payload[k] = int(v)
                except Exception:
                    pass

        payload['extraction_id'] = call_id
        async with NeonDatabase().get_session() as session:
            new_profile = await self.profile_repo.create(session, CustomerProfileDB(**payload))
            return new_profile

    async def update_db(self, data: dict, profile_id):
        """Update customer profile in database. Expects a dict and profile_id."""
        raw: dict
        if hasattr(data, "model_dump"):
            raw = data.model_dump(exclude_none=True)
        elif hasattr(data, "dict"):
            raw = data.dict(exclude_none=True)
        else:
            raw = dict(data) if isinstance(data, dict) else {}

        allowed_keys = {
            "check_in", "check_out", "budget", "adults", "children",
            "children_ages", "specific_sites", "interests",
            "accommodation_preference", "tour_style",
        }
        update_data = {k: raw[k] for k in allowed_keys if k in raw}

        # Normalize types
        from datetime import date as _date
        for k in ("check_in", "check_out"):
            v = update_data.get(k)
            if isinstance(v, str) and v:
                try:
                    update_data[k] = _date.fromisoformat(v)
                except Exception:
                    pass
        for k in ("budget", "adults", "children"):
            v = update_data.get(k)
            if isinstance(v, str):
                try:
                    update_data[k] = int(v)
                except Exception:
                    pass
                    
        # Skip DB update if there's nothing to persist
        if not update_data:
            return None
        async with NeonDatabase().get_session() as session:
            await self.profile_repo.update(session, profile_id=profile_id, update_data=update_data)
