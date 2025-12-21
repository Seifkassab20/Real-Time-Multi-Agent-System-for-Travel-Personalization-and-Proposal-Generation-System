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
    
    async def invoke(self, segment: TranscriptSegment, segment_number: int, call_id):
        extraction_id = None 
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
                        await self.update_db(validated_dict, extraction_id)
                    
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
        async with NeonDatabase().get_session() as session:
            new_extraction = await self.extraction_repo.create(session, data)
            return new_extraction.extraction_id
    
    async def update_db(self, data: dict, extraction_id):
        """Update extraction in database. Expects a dict."""
        async with NeonDatabase().get_session() as session:
            updated_extraction = await self.extraction_repo.update(session, extraction_id=extraction_id, update_data=data)



