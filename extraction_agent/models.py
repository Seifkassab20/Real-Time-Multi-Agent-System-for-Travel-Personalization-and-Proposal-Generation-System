"""
Minimal data models
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


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