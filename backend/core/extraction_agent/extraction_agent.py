import json
import re
from pydantic import ValidationError
from backend.core.llm import llm_cloud_model
from backend.core.prompts.prompt_loader import PromptLoader
from backend.core.extraction_agent.models import TranscriptSegment , Agent_output
from datetime import date
from backend.database.repostries.extraction_repo import ExtractionRepository
from backend.database.models.extractions import Extraction
from backend.database.db import NeonDatabase
from logging import getLogger
logger = getLogger("extraction_agent")

today = date.today().isoformat()
class ExtractionAgent:

    def __init__(self):
        self.llm = llm_cloud_model
        self.extraction_repo = ExtractionRepository()
        self.system_prompt = PromptLoader.load_prompt("extraction_agent_prompt.yaml")
    
    async def invoke(self, segment: TranscriptSegment, segment_number: int, call_id, extraction_id=None):
        # extraction_id: propagate previously created extraction id for updates
        self.system_prompt = self.system_prompt.format(today=today)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Extract travel information from this text: '{segment.text}'"}
        ]

        try:
            # Call the Ollama LLM
            response = self.llm.chat(messages, temperature=0.0, max_tokens=500)
            # Debug the response structure
            logger.info(f"DEBUG - Response: {response}")
            content = response
            if content:
                content = content.strip()
                
                # Remove markdown code blocks if present
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                content = content.strip()
                
                if not content:
                    logger.info("DEBUG - Content is empty after cleanup")
                    return {}, extraction_id
                
                try:
                    result = json.loads(content)
                    validated = Agent_output(**result)
                    validated_dict = validated.model_dump(exclude_none=True)
                    
                    if segment_number == 1:
                        extraction_id = await self.add_db(validated_dict, call_id)
                    else:
                        # Only attempt update when we have a valid extraction_id
                        if extraction_id:
                            await self.update_db(validated_dict, extraction_id)
                        else:
                            logger.info("DEBUG - Skipping update: missing extraction_id for segment > 1")
                    
                    return validated_dict, extraction_id
                except json.JSONDecodeError as e:
                    logger.info(f"DEBUG - Failed to parse content as JSON: {content[:100]}")
                    return {}, extraction_id
                except ValidationError as e:
                    logger.info(f"DEBUG - Validation error: {e}")
                    return {}, extraction_id
            
            logger.info("DEBUG - No content extracted")
            return {}, extraction_id
            
        except Exception as e:
            logger.info(f"Error in extraction: {e}")
            return {}, extraction_id

    async def add_db(self, data: dict, call_id):
        """Add extraction to database. Expects a dict."""
        # Add call_id to the data
        data['call_id'] = call_id
        # Normalize date strings to date objects
        for k in ("check_in", "check_out"):
            v = data.get(k)
            if isinstance(v, str) and v:
                try:
                    data[k] = date.fromisoformat(v)
                except Exception:
                    pass
        # Coerce numeric fields to strings for VARCHAR columns
        for k in ("adults", "children", "rooms", "budget"):
            v = data.get(k)
            if v is not None and not isinstance(v, str):
                try:
                    data[k] = str(v)
                except Exception:
                    pass
        # Convert children_age list to comma-separated string if provided
        if isinstance(data.get("children_age"), list):
            try:
                data["children_age"] = ",".join(str(x) for x in data["children_age"])
            except Exception:
                pass
        async with NeonDatabase().get_session() as session:
            new_extraction = await self.extraction_repo.create(session, data)
            return new_extraction.extraction_id
    
    async def update_db(self, data: dict, extraction_id):
        """Update extraction in database. Expects a dict."""
        # Normalize date strings to date objects
        for k in ("check_in", "check_out"):
            v = data.get(k)
            if isinstance(v, str) and v:
                try:
                    data[k] = date.fromisoformat(v)
                except Exception:
                    pass
        # Coerce numeric fields to strings for VARCHAR columns
        for k in ("adults", "children", "rooms", "budget"):
            v = data.get(k)
            if v is not None and not isinstance(v, str):
                try:
                    data[k] = str(v)
                except Exception:
                    pass
        # Convert children_age list to comma-separated string if provided
        if isinstance(data.get("children_age"), list):
            try:
                data["children_age"] = ",".join(str(x) for x in data["children_age"])
            except Exception:
                pass
        async with NeonDatabase().get_session() as session:
            updated_extraction = await self.extraction_repo.update(session, extraction_id=extraction_id, update_data=data)



