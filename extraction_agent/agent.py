import json
import time
import uuid
import re
from datetime import datetime
import asyncio
import redis.asyncio as redis
from pydantic import BaseModel
from llm import llm_model
from extraction_agent.models import TranscriptSegment, RawExtraction, TravelPlan
from extraction_agent.Config import Config


# --- System prompt for extraction ---


class ExtractionAgent:
    def __init__(self):
        self.agent_id = f"extractor_{uuid.uuid4().hex[:6]}"
        self.client = llm_model
        self.redis = None
        self.config = Config()
        self.SYSTEM_PROMPT = """
            You are an extraction agent for a travel booking system.

            Your job: Extract travel-related entities from customer speech and convert activities into clear, searchable sentences.

            ACTIVITIES PARSING (CRITICAL):
            - Convert all activity mentions into complete, natural English sentences
            - Make sentences specific and context-rich for semantic search
            - Include relevant details (location, preferences, constraints)
            - Use action verbs and descriptive language
            - Focus on Egyptian tourism activities and experiences

            Examples for Egyptian tourism:
            Input: "want to see the pyramids and maybe the sphinx"
            Output examples activities: [
            "Visit and explore the Great Pyramids of Giza",
            "See the ancient Sphinx monument and learn its history"
            ]

            Input: "interested in diving in the Red Sea, coral reefs"
            Output examples activities: [
            "Experience scuba diving in the Red Sea coral reefs",
            "Explore underwater marine life and colorful coral formations"
            ]

            Input: "want to visit temples, maybe Luxor and Karnak"
            Output examples activities: [
            "Tour the ancient temples of Luxor and Karnak",
            "Explore pharaonic monuments and hieroglyphic inscriptions"
            ]

            Input: "desert safari, camel riding, maybe camping"
            Output examples activities: [
            "Experience a desert safari adventure in the Egyptian Sahara",
            "Go camel riding through sand dunes and desert landscapes",
            "Enjoy overnight camping under the stars in the desert"
            ]

            Input: "cruise down the Nile, see the valley of the kings"
            Output examples activities: [
            "Take a scenic Nile River cruise through ancient Egypt",
            "Visit the Valley of the Kings royal burial tombs"
            ]

            Extract other entities:
            - Dates (any mention of dates or timeframes avoid jargon)
            - Numbers (budget, people count, ages)
            - Locations (countries, cities, sites)
            - Preferences (hotel types, food, pace)
            - Feelings/tone (excited, worried, hesitant)

            Output JSON format:
            {
            "dates": ["December 2024", "winter holiday", "10 days"],
            "budget": {"amount": 3000,"flexibility": "moderate"},
            "travelers": {"adults": 2, "children": 1,"num_of_rooms":2},
            "locations": ["Cairo", "Giza"],
            "activities": [
                "Visit and explore the Great Pyramids of Giza",
                "Take a scenic Nile River cruise ",
                "Tour the egyptian national musem,
                "Shop for traditional Egyptian souvenirs at Khan el-Khalili bazaar"
            ],
            "preferences": ["family-friendly hotels", "cultural experiences", "moderate pace", "guided tours"],
            "keywords": Examples["ancient history", "adventure", "photography"],
            "tone": "excited and curious about Egyptian culture"
            }

            RULES:
            - Activities MUST be full sentences 
            - Make activities semantically rich for RAG retrieval
            - Include context from surrounding conversation when possible
            - If nothing travel-related, return empty dict: {}
            - Response MUST be valid RFC 8259 JSON ONLY (no markdown)
            - DO NOT include comments of any kind (no //, no /* */)
            - DO NOT include trailing commas
            - Use standard double quotes for keys and strings

            Be FAST but PRECISE on activities.
            """        
        print(f"[{self.agent_id}] Extraction Agent ready")

    async def start(self):
        """Start listening to transcript stream"""
        self.redis = redis.from_url(self.config.REDIS_URL)
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.config.TRANSCRIPT_TOPIC)
        print(f"[{self.agent_id}] Listening for transcripts...")

        # Async loop to fetch messages
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and "data" in message:
                await self._process_message(message["data"])
            await asyncio.sleep(0.01)

    async def _process_message(self, data: bytes):
        """Process incoming transcript"""
        try:
            segment_dict = json.loads(data)
            segment = TranscriptSegment(**segment_dict)

            print(f"\n[{self.agent_id}] Got transcript: {segment.segment_id}")
            print(f"  Speaker: {segment.speaker}")
            print(f"  Text: {segment.text[:80]}...")

            extraction = await self._extract(segment)
            await self._publish(extraction)

        except Exception as e:
            print(f"[{self.agent_id}] Error processing message: {e}")

    async def _extract(self, segment: TranscriptSegment) -> RawExtraction:
        """Fast extraction using LLM"""
        start = time.time()
        loop = asyncio.get_event_loop()

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, self._call_llm, segment.text),
                timeout=10
            )
            # _call_llm returns a dict of entities (or empty dict on failure)
            entities = response if isinstance(response, dict) else {}
        except asyncio.TimeoutError:
            print("❌ LLM call timed out")
            entities = {}

        processing_time = (time.time() - start) * 1000

        extraction = RawExtraction(
            extraction_id=f"ext_{uuid.uuid4().hex[:8]}",
            segment_id=segment.segment_id,
            timestamp=datetime.now(),
            raw_text=segment.text,
            entities=entities,
            processing_time_ms=processing_time
        )

        print(f"  ✓ Extracted in {processing_time:.0f}ms")
        if entities:
            print(f"  Found keys: {list(entities.keys())}")

        return extraction

    def _call_llm(self, text: str) -> dict:
        """Call local LLM model and parse output as TravelPlan"""
        response_obj = self.client.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract entities from: \"{text}\""}
            ]
        )
        # Extract the assistant message content as string
        content = None
        # Ollama Python client may return a dict or a ChatResponse object
        if isinstance(response_obj, str):
            content = response_obj
        else:
            # Try dict-style access
            try:
                content = response_obj.get("message", {}).get("content")  # type: ignore[attr-defined]
            except Exception:
                content = None
            # Try attribute access (ChatResponse.message.content)
            if not content:
                message_obj = getattr(response_obj, "message", None)
                if message_obj is not None:
                    content = getattr(message_obj, "content", None)

        if not content or not isinstance(content, str):
            print("❌ Empty or invalid LLM response content")
            return {}

        content = content.strip()
        # Strip Markdown code fences if present
        if content.startswith("```") and content.endswith("```"):
            # Remove the first line (``` or ```json) and the last fence
            lines = content.splitlines()
            if len(lines) >= 2:
                content = "\n".join(lines[1:-1]).strip()

        # Sanitize common LLM JSON issues: comments and trailing commas
        def _strip_json_comments(s: str) -> str:
            # Remove //... comments
            s = re.sub(r"(^|[^:])//.*$", r"\1", s, flags=re.MULTILINE)
            # Remove /* ... */ comments
            s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
            return s

        def _remove_trailing_commas(s: str) -> str:
            # Remove trailing commas before } or ]
            return re.sub(r",\s*(\}|\])", r"\1", s)

        sanitized = _remove_trailing_commas(_strip_json_comments(content))

        # Ensure we have JSON output
        try:
            data = json.loads(sanitized)
        except json.JSONDecodeError:
            # As a last resort, try original content without sanitation to aid debugging
            print(f"❌ Failed to parse LLM output as JSON: {content}")
            data = {}

        # Validate and parse using Pydantic model
        try:
            travel_plan = TravelPlan(**data)
            return travel_plan.dict(exclude_none=True)  
        except Exception as e:
            print(f"❌ TravelPlan validation error: {e}")
            # Return raw dict if it is a dict; otherwise empty
            return data if isinstance(data, dict) else {}


    async def _publish(self, extraction: RawExtraction):
        """Publish to Redis event bus"""
        try:
            await self.redis.publish(
                self.config.EXTRACTION_TOPIC,
                extraction.model_dump_json()
            )
            print(f"  → Published to Profile Agent")
        except Exception as e:
            print(f"❌ Failed to publish extraction: {e}")


