"""
API Schemas for Real-Time Travel Personalization System
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class MessageType(str, Enum):
    """WebSocket message types"""
    AUDIO_CHUNK = "audio_chunk"
    TRANSCRIPTION = "transcription"
    EXTRACTION = "extraction"
    PROFILE_UPDATE = "profile_update"
    RECOMMENDATIONS = "recommendations"
    PROFILE_QUESTION = "profile_question"
    ERROR = "error"
    STATUS = "status"


class SpeakerType(str, Enum):
    """Speaker identification"""
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


# ============================================================================
# WebSocket Messages - Client to Server
# ============================================================================

class AudioChunkMessage(BaseModel):
    """Audio chunk sent from client"""
    type: Literal[MessageType.AUDIO_CHUNK] = MessageType.AUDIO_CHUNK
    data: str = Field(..., description="Base64 encoded audio data")
    timestamp: datetime
    format: str = Field(default="wav", description="Audio format (wav, mp3, etc.)")
    sample_rate: Optional[int] = Field(default=16000, description="Audio sample rate")


# ============================================================================
# WebSocket Messages - Server to Client
# ============================================================================

class TranscriptionMessage(BaseModel):
    """Transcription result"""
    type: Literal[MessageType.TRANSCRIPTION] = MessageType.TRANSCRIPTION
    segment_id: str
    text: str
    speaker: SpeakerType = SpeakerType.CUSTOMER
    timestamp: datetime
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class ExtractionMessage(BaseModel):
    """Extracted entities from transcript"""
    type: Literal[MessageType.EXTRACTION] = MessageType.EXTRACTION
    segment_id: str
    extraction: Dict[str, Any] = Field(..., description="Extracted fields from Agent_output")
    timestamp: datetime


class ProfileUpdateMessage(BaseModel):
    """Updated user profile"""
    type: Literal[MessageType.PROFILE_UPDATE] = MessageType.PROFILE_UPDATE
    profile: Dict[str, Any] = Field(..., description="Current accumulated user profile")
    timestamp: datetime
    changes: Optional[Dict[str, Any]] = Field(None, description="What changed in this update")


class RecommendationItem(BaseModel):
    """Single recommendation"""
    id: str
    destination: str
    score: float = Field(..., ge=0.0, le=1.0)
    title: str
    description: str
    details: Dict[str, Any]
    price_estimate: Optional[Dict[str, float]] = None
    image_url: Optional[str] = None


class RecommendationsMessage(BaseModel):
    """Travel recommendations"""
    type: Literal[MessageType.RECOMMENDATIONS] = MessageType.RECOMMENDATIONS
    recommendations: List[RecommendationItem]
    timestamp: datetime
    total_count: int


class ProfileQuestionMessage(BaseModel):
    """Question to complete user profile"""
    type: Literal[MessageType.PROFILE_QUESTION] = MessageType.PROFILE_QUESTION
    question_id: str
    question: str
    field: str = Field(..., description="Profile field this question relates to")
    timestamp: datetime
    options: Optional[List[str]] = Field(None, description="Multiple choice options if applicable")


class ErrorMessage(BaseModel):
    """Error notification"""
    type: Literal[MessageType.ERROR] = MessageType.ERROR
    error_code: str
    message: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


class StatusMessage(BaseModel):
    """Status update"""
    type: Literal[MessageType.STATUS] = MessageType.STATUS
    status: str = Field(..., description="processing, idle, completed, etc.")
    message: Optional[str] = None
    timestamp: datetime


# ============================================================================
# REST API - Request/Response Models
# ============================================================================

class SessionCreateRequest(BaseModel):
    """Request to create a new session"""
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionCreateResponse(BaseModel):
    """Response after creating session"""
    session_id: str
    created_at: datetime
    websocket_url: str = Field(..., description="WebSocket URL to connect to")


class ProfileResponse(BaseModel):
    """User profile response"""
    session_id: str
    profile: Dict[str, Any]
    last_updated: datetime
    completeness_score: Optional[float] = Field(None, ge=0.0, le=1.0, 
                                                  description="How complete the profile is")


class RecommendationsResponse(BaseModel):
    """Recommendations response"""
    session_id: str
    recommendations: List[RecommendationItem]
    generated_at: datetime
    total_count: int
    page: int = 1
    page_size: int = 10


class TranscriptSegment(BaseModel):
    """Single transcript segment"""
    segment_id: str
    timestamp: datetime
    speaker: SpeakerType
    text: str
    extraction: Optional[Dict[str, Any]] = None


class TranscriptResponse(BaseModel):
    """Conversation transcript"""
    session_id: str
    segments: List[TranscriptSegment]
    total_segments: int


class AnswerQuestionRequest(BaseModel):
    """Answer to a profile question"""
    question_id: str
    answer: Any = Field(..., description="Answer value (string, number, list, etc.)")


class AnswerQuestionResponse(BaseModel):
    """Response after answering question"""
    question_id: str
    accepted: bool
    updated_profile: Dict[str, Any]
    timestamp: datetime


class SessionStatusResponse(BaseModel):
    """Session status"""
    session_id: str
    status: str
    created_at: datetime
    last_activity: datetime
    segment_count: int
    profile_completeness: float = Field(..., ge=0.0, le=1.0)


# ============================================================================
# Health & Metadata
# ============================================================================

class HealthResponse(BaseModel):
    """API health check"""
    status: str = "healthy"
    timestamp: datetime
    version: str
    services: Dict[str, str] = Field(..., description="Status of each service component")


class APIMetadata(BaseModel):
    """API metadata"""
    version: str
    name: str = "Travel Personalization API"
    description: str
    endpoints: Dict[str, List[str]]
