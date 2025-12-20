"""
FastAPI Routes for Travel Personalization System
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from datetime import datetime
import uuid
from typing import Dict, Optional
import json

from backend.api.schemas import (
    SessionCreateRequest,
    SessionCreateResponse,
    ProfileResponse,
    RecommendationsResponse,
    TranscriptResponse,
    AnswerQuestionRequest,
    AnswerQuestionResponse,
    SessionStatusResponse,
    HealthResponse,
    MessageType,
    TranscriptionMessage,
    ExtractionMessage,
    ProfileUpdateMessage,
    RecommendationsMessage,
    ProfileQuestionMessage,
    ErrorMessage,
    StatusMessage,
)

# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/api/v1", tags=["travel-personalization"])

# In-memory storage (replace with database in production)
sessions: Dict[str, dict] = {}
profiles: Dict[str, dict] = {}
recommendations_store: Dict[str, list] = {}
transcripts: Dict[str, list] = {}


# ============================================================================
# REST Endpoints
# ============================================================================

@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest):
    """Create a new conversation session"""
    session_id = str(uuid.uuid4())
    
    sessions[session_id] = {
        "session_id": session_id,
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "status": "created",
        "user_id": request.user_id,
        "metadata": request.metadata or {}
    }
    
    profiles[session_id] = {}
    recommendations_store[session_id] = []
    transcripts[session_id] = []
    
    return SessionCreateResponse(
        session_id=session_id,
        created_at=sessions[session_id]["created_at"],
        websocket_url=f"ws://localhost:8000/api/v1/sessions/{session_id}/stream"
    )


@router.get("/sessions/{session_id}/profile", response_model=ProfileResponse)
async def get_profile(session_id: str):
    """Get current user profile for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    profile = profiles.get(session_id, {})
    
    # Calculate completeness (example logic)
    required_fields = ["destinations", "budget", "travel_dates", "preferences"]
    filled_fields = sum(1 for field in required_fields if profile.get(field))
    completeness = filled_fields / len(required_fields) if required_fields else 0.0
    
    return ProfileResponse(
        session_id=session_id,
        profile=profile,
        last_updated=sessions[session_id]["last_activity"],
        completeness_score=completeness
    )


@router.get("/sessions/{session_id}/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    """Get travel recommendations for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    all_recs = recommendations_store.get(session_id, [])
    
    # Pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_recs = all_recs[start_idx:end_idx]
    
    return RecommendationsResponse(
        session_id=session_id,
        recommendations=paginated_recs,
        generated_at=datetime.utcnow(),
        total_count=len(all_recs),
        page=page,
        page_size=page_size
    )


@router.get("/sessions/{session_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(session_id: str):
    """Get conversation transcript for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    segments = transcripts.get(session_id, [])
    
    return TranscriptResponse(
        session_id=session_id,
        segments=segments,
        total_segments=len(segments)
    )


@router.post("/sessions/{session_id}/answers", response_model=AnswerQuestionResponse)
async def answer_question(session_id: str, request: AnswerQuestionRequest):
    """Submit answer to a profile question"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update profile with answer (implement your logic here)
    profile = profiles.get(session_id, {})
    # Example: map question_id to profile field
    # profile[field_name] = request.answer
    
    sessions[session_id]["last_activity"] = datetime.utcnow()
    
    return AnswerQuestionResponse(
        question_id=request.question_id,
        accepted=True,
        updated_profile=profile,
        timestamp=datetime.utcnow()
    )


@router.get("/sessions/{session_id}/status", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """Get session status"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    profile = profiles.get(session_id, {})
    
    # Calculate completeness
    required_fields = ["destinations", "budget", "travel_dates", "preferences"]
    filled_fields = sum(1 for field in required_fields if profile.get(field))
    completeness = filled_fields / len(required_fields) if required_fields else 0.0
    
    return SessionStatusResponse(
        session_id=session_id,
        status=session["status"],
        created_at=session["created_at"],
        last_activity=session["last_activity"],
        segment_count=len(transcripts.get(session_id, [])),
        profile_completeness=completeness
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """API health check"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
        services={
            "asr": "healthy",
            "extraction": "healthy",
            "profile": "healthy",
            "recommendations": "healthy"
        }
    )


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/sessions/{session_id}/stream")
async def websocket_stream(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time audio streaming and processing
    
    This is where you'll integrate your pipeline:
    - Receive audio chunks from client
    - Process through ASR → Extraction → Profile → Recommendations
    - Send back real-time updates
    """
    await websocket.accept()
    
    if session_id not in sessions:
        await websocket.send_json(
            ErrorMessage(
                error_code="SESSION_NOT_FOUND",
                message=f"Session {session_id} not found",
                timestamp=datetime.utcnow()
            ).dict()
        )
        await websocket.close()
        return
    
    try:
        # Send initial status
        await websocket.send_json(
            StatusMessage(
                status="connected",
                message="Ready to receive audio",
                timestamp=datetime.utcnow()
            ).dict()
        )
        
        # TODO: Initialize your pipeline components here
        # asr_service = TranscriptionService()
        # extraction_agent = ExtractionAgent()
        # profile_agent = ProfileAgent()
        
        while True:
            # Receive audio chunk from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == MessageType.AUDIO_CHUNK:
                # TODO: Process audio through your pipeline
                # This is where you'd integrate your existing code
                
                # Example flow:
                # 1. Process audio through ASR
                # asr_result = await asr_service.process(audio_data)
                # await websocket.send_json(TranscriptionMessage(...).dict())
                
                # 2. Extract entities
                # extraction = await extraction_agent.invoke(transcript)
                # await websocket.send_json(ExtractionMessage(...).dict())
                
                # 3. Update profile
                # merge_extraction_into_profile(profile, extraction)
                # await websocket.send_json(ProfileUpdateMessage(...).dict())
                
                # 4. Generate recommendations
                # recs = recommend(profile)
                # await websocket.send_json(RecommendationsMessage(...).dict())
                
                # 5. Ask clarifying questions
                # questions = await profile_agent.invoke(...)
                # await websocket.send_json(ProfileQuestionMessage(...).dict())
                
                # Update session activity
                sessions[session_id]["last_activity"] = datetime.utcnow()
                sessions[session_id]["status"] = "processing"
                
    except WebSocketDisconnect:
        sessions[session_id]["status"] = "disconnected"
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        await websocket.send_json(
            ErrorMessage(
                error_code="PROCESSING_ERROR",
                message=str(e),
                timestamp=datetime.utcnow()
            ).dict()
        )
        await websocket.close()
