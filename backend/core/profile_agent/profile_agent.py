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
from backend.database.models.extractions import Extraction
from backend.database.repostries.extraction_repo import ExtractionRepository



class ProfileAgent:
    def __init__(self):
        self.llm = OllamaCloudLLM()
        self.system_prompt = PromptLoader.load_prompt("profile_agent_prompt.yaml")
        self.extraction_repo = ExtractionRepository()

    async def get_extraction_by_call_id(self, call_id: str) -> Extraction | None:
        """Retrieve extraction data from the database using call_id."""
        NeonDatabase.init()
        
        async with NeonDatabase.get_session() as session:
            # Convert string call_id to UUID
            try:
                call_id_uuid = UUID(call_id)
            except ValueError:
                print(f"Invalid call_id format: {call_id}")
                return None
            return await self.extraction_repo.get_by_call_id(session, call_id_uuid)


    async def invoke(self, call_id: str) -> tuple:
        """Generate profile questions based on the user's existing extraction data.
        Args:
            call_id: The extraction/call id for the session.
        Returns:
            tuple: A tuple of (json_response, extraction_id).
        """
        # Fetch extraction data from database
        extraction_data = await self.get_extraction_by_call_id(call_id)

        if extraction_data:
            # Convert extraction to dict for context
            profile_data = {
                "budget": getattr(extraction_data, "budget", None),
                "check_in": str(getattr(extraction_data, "check_in", "")) if getattr(extraction_data, "check_in", None) else None,
                "check_out": str(getattr(extraction_data, "check_out", "")) if getattr(extraction_data, "check_out", None) else None,
                "adults": getattr(extraction_data, "adults", None),
                "children": getattr(extraction_data, "children", None),
                "children_ages": getattr(extraction_data, "children_age", None),
                "rooms": getattr(extraction_data, "rooms", None),
                "city": getattr(extraction_data, "city", None),
                "activities": getattr(extraction_data, "activities", None),
                "preferences": getattr(extraction_data, "preferences", None),
                "keywords": getattr(extraction_data, "keywords", None),
            }
            # Remove None values for cleaner output
            profile_data = {k: v for k, v in profile_data.items() if v is not None}
            extraction_id = str(extraction_data.extraction_id)
        else:
            profile_data = {}
            extraction_id = None

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

            # Return the questions and extraction_id (no database write needed)
            return response.model_dump_json(), extraction_id
        except Exception as e:
            print(f"Error in profile questions generation: {e}")
            return None, None
