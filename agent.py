"""
Simplified Extraction Agent - Fast extraction only
"""
import json
import time
import uuid
from datetime import datetime
import asyncio
import redis.asyncio as redis
from openai import OpenAI

from models import TranscriptSegment, RawExtraction
from config import config


# Simple system prompt - just extract entities
SYSTEM_PROMPT = """You are an extraction agent for a travel booking system.

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

Response must be valid JSON only."""


class ExtractionAgent:
    """Fast extraction agent - 20s segments"""
    
    def __init__(self):
        self.agent_id = f"extractor_{uuid.uuid4().hex[:6]}"
        self.client = OpenAI(api_key=config.LLM_API_KEY)
        self.redis = None
        print(f"[{self.agent_id}] Extraction Agent ready")
    
    async def start(self):
        """Start listening to transcript stream"""
        # Connect to Redis
        self.redis = redis.from_url(config.REDIS_URL)
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(config.TRANSCRIPT_TOPIC)
        
        print(f"[{self.agent_id}] Listening for transcripts...")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                await self._process_message(message["data"])
    
    async def _process_message(self, data: bytes):
        """Process incoming transcript"""
        try:
            # Parse transcript
            segment_dict = json.loads(data)
            segment = TranscriptSegment(**segment_dict)
            
            print(f"\n[{self.agent_id}] Got transcript: {segment.segment_id}")
            print(f"  Speaker: {segment.speaker}")
            print(f"  Text: {segment.text[:80]}...")
            
            # Extract entities (async)
            extraction = await self._extract(segment)
            
            # Publish to event bus
            await self._publish(extraction)
            
        except Exception as e:
            print(f"[{self.agent_id}] Error: {e}")
    
    async def _extract(self, segment: TranscriptSegment) -> RawExtraction:
        """
        Fast extraction using LLM
        """
        start = time.time()
        
        # Call LLM
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            self._call_llm,
            segment.text
        )
        
        # Parse JSON
        try:
            entities = json.loads(response)
        except:
            entities = {}
        
        processing_time = (time.time() - start) * 1000
        
        # Create result
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
            print(f"  Found: {list(entities.keys())}")
        
        return extraction
    
    def _call_llm(self, text: str) -> str:
        """Call OpenAI (runs in thread pool)"""
        response = self.client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract entities from: \"{text}\""}
            ],
            temperature=config.LLM_TEMPERATURE,
            max_tokens=500,
            timeout=5,  # 5 second timeout
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    
    async def _publish(self, extraction: RawExtraction):
        """Publish to event bus"""
        await self.redis.publish(
            config.EXTRACTION_TOPIC,
            extraction.model_dump_json()
        )
        print(f"  → Published to Profile Agent")


# Run agent
async def main():
    agent = ExtractionAgent()
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
