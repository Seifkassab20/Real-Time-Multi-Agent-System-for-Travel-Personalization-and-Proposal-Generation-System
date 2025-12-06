import json
import time
import uuid
from datetime import datetime
import asyncio
import redis.asyncio as redis
from pydantic import BaseModel
from llm import llm_model
from extraction_agent.models import TranscriptSegment, RawExtraction
from extraction_agent.Config import Config

# --- System prompt for extraction ---




class ExtractionAgent:
    def __init__(self):
        self.agent_id = f"extractor_{uuid.uuid4().hex[:6]}"
        self.client = llm_model
        self.redis = None
        self.SYSTEM_PROMPT="""
        You are an extraction agent for a travel booking system.

        Your ONLY job: Extract travel-related entities from customer speech.

        Extract whatever you find:
        - Dates (any mention of time)
        - Numbers (budget, people count, ages)
        - Locations (countries, cities, sites)
        - Activities (things they want to do)
        - Preferences (hotel types, food, pace)
        - Feelings/tone (excited, worried, hesitant)

        Output JSON format:
        {
        "dates": [...],
        "budget": {...},
        "travelers": {...},
        "locations": [...],
        "activities": [...],
        "preferences": [...],
        "keywords": [...],
        "tone": "..."
        }

        Be FAST. Extract whatever is there. Don't overthink it.
        If nothing travel-related, return empty dict: {}

        Response must be valid JSON only.
        """

        print(f"[{self.agent_id}] Extraction Agent ready")

    async def start(self):
        """Start listening to transcript stream"""
        self.redis = redis.from_url(config.REDIS_URL)
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(config.TRANSCRIPT_TOPIC)
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
            try:
                entities = json.loads(response)
            except json.JSONDecodeError:
                print(f"❌ Failed to parse LLM output: {response}")
                entities = {}
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

    def _call_llm(self, text: str) -> str:
        """Call local Ollama model synchronously"""
        response = self.client.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract entities from: \"{text}\""}
            ]

        )
        return response.message.content


    async def _publish(self, extraction: RawExtraction):
        """Publish to Redis event bus"""
        try:
            await self.redis.publish(
                config.EXTRACTION_TOPIC,
                extraction.model_dump_json()
            )
            print(f"  → Published to Profile Agent")
        except Exception as e:
            print(f"❌ Failed to publish extraction: {e}")


# # --- Run agent ---
# async def main():
#     agent = ExtractionAgent()
#     await agent.start()


# if __name__ == "__main__":
#     asyncio.run(main())
