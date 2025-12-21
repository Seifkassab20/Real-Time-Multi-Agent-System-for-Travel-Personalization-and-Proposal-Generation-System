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
            return await self.extraction_repo.get_by_id(session, call_id)


    async def invoke(self, call_id: str) -> dict:
        """Generate profile questions based on the user's existing profile."""
        
        # Fetch the user profile from database
        user_profile = await self.get_profile_by_call_id(call_id)
        
        if user_profile:
            # Convert profile to dict for context
            profile_data = {
                "budget": user_profile.get("budget", 0),
                "check_in": str(user_profile.get("check_in", "Unknown")),
                "check_out": str(user_profile.get("check_out", "Unknown")),
                "adults": user_profile.get("adults", 0),
                "children": user_profile.get("children", 0),
                "children_ages": user_profile.get("children_ages", []),
                'rooms': user_profile.get("rooms", 0),
                'city': user_profile.get("city", ""),
                'activities': user_profile.get("activities", []),
                'preferences': user_profile.get("preferences", []),
                'keywords': user_profile.get("keywords", []),
            }
        else:
            profile_data = {}

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Start generating the questions from this user profile:\n{profile_data}"}
        ]

        # Debug: print the profile data being sent
        print("DEBUG - Profile data:", profile_data)

        try:
            # Call the Ollama LLM with higher max_tokens for complex schema output
            response = self.llm.chat_structured(
                messages, 
                profile_agent_response,
                temperature=0.0, 
                max_tokens=2000  # Increased from 500
            )

            # Debug the response structure
            print("DEBUG - Response:", response)
            return response.model_dump_json()
            
        except Exception as e:
            print(f"Error in profile questions generation: {e}")
            return {}



