"""
Minimal data models
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional, Union

class TranscriptSegment(BaseModel):
    """Input: 20-second transcript segment"""
    segment_id: str
    timestamp: datetime
    speaker: str  # "customer" or "agent"
    text: str


class RawExtraction(BaseModel):
    """Output: Raw extracted entities - no processing"""
    extraction_id: str
    segment_id: str
    timestamp: datetime
    raw_text: str  # The transcript text
    entities: dict  # Whatever LLM extracts
    processing_time_ms: float


class Budget(BaseModel):
    amount: Optional[Union[int, float]] = None
    flexibility: Optional[str] = None

class Travelers(BaseModel):
    adults: Optional[int] = None
    children: Optional[int] = None
    num_of_rooms: Optional[int] = None

class TravelPlan(BaseModel):
    dates: Optional[List[str]] = None
    budget: Optional[Budget] = None
    travelers: Optional[Travelers] = None
    locations: Optional[List[str]] = None
    activities: Optional[List[str]] = None
    preferences: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
