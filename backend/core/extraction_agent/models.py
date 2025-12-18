from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional, Union
from typing import Literal
class TranscriptSegment(BaseModel):
    """Input: 20-second transcript segment"""
    segment_id: str
    timestamp: datetime
    speaker: str
    text: str

class Agent_output(BaseModel):
    budget: Optional[float] = None
    adults: Optional[int] = None
    children: Optional[int] = None
    children_age: Optional[List[int]] = None
    rooms: Optional[int] = None
    city: Optional[Literal["Cairo", "Giza"]] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    activities: Optional[List[str]] = None
    preferences: Optional[List[str]] = None
    keywords: Optional[List[str]] = None

