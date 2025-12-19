from pydantic import BaseModel, Field
from typing import Optional, List

class TranscriptionSegment(BaseModel):
    raw_text: str
    corrected_text: str
    confidence: float
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    needs_review: bool = False

class PipelineOutput(BaseModel):
    full_raw_text: str
    full_corrected_text: str
    segments: List[TranscriptionSegment]
    metadata: dict