"""
Integration of existing pipeline with WebSocket API

This module shows how to integrate your existing pipeline code
with the WebSocket API for real-time processing.
"""
import asyncio
import uuid
import base64
from datetime import datetime
from typing import Dict, Any

from backend.core.ASR.src.pipeline import TranscriptionService
from backend.core.extraction_agent.extraction_agent import ExtractionAgent
from backend.core.extraction_agent.models import TranscriptSegment, Agent_output
from backend.core.profile_agent.profile_agent import ProfileAgent
from backend.core.recommendation_engine.recommendation_orchestrator import (
    build_user_profile_from_extraction,
    merge_value,
    MERGE_RULES,
    recommend
)

from backend.api.schemas import (
    TranscriptionMessage,
    ExtractionMessage,
    ProfileUpdateMessage,
    RecommendationsMessage,
    ProfileQuestionMessage,
    RecommendationItem,
    SpeakerType,
    ErrorMessage,
)


class PipelineProcessor:
    """
    Processes audio through the complete pipeline and sends updates via WebSocket
    """
    
    def __init__(self):
        self.asr_service = TranscriptionService()
        self.extraction_agent = ExtractionAgent()
        self.profile_agent = ProfileAgent()
        
        # Session-specific storage
        self.session_profiles: Dict[str, dict] = {}
        self.session_recommendations: Dict[str, list] = {}
    
    def merge_extraction_into_profile(self, profile: dict, extraction: Agent_output):
        """Merge extraction results into accumulated profile"""
        for field, rule in MERGE_RULES.items():
            profile[field] = merge_value(
                profile.get(field),
                getattr(extraction, field, None),
                rule
            )
    
    async def process_audio_chunk(
        self,
        session_id: str,
        audio_data: str,  # base64 encoded
        websocket,
        call_id: str = None
    ):
        """
        Process a single audio chunk through the pipeline
        
        Args:
            session_id: Unique session identifier
            audio_data: Base64 encoded audio data
            websocket: WebSocket connection to send updates
            call_id: Optional call identifier
        """
        try:
            # Initialize session profile if needed
            if session_id not in self.session_profiles:
                self.session_profiles[session_id] = {}
                self.session_recommendations[session_id] = []
            
            profile = self.session_profiles[session_id]
            
            # Decode audio data
            # audio_bytes = base64.b64decode(audio_data)
            # TODO: Save to temp file or process directly
            
            # For now, using your existing audio file approach
            # In production, you'd process the audio_bytes directly
            
            # STEP 1: ASR - Transcribe audio
            # Note: You'll need to modify this to accept audio bytes instead of file path
            async for asr_segment, current_call_id in self.asr_service.stream_audio(audio_path):
                segment_id = str(uuid.uuid4())
                timestamp = datetime.utcnow()
                
                # Send transcription update
                transcription_msg = TranscriptionMessage(
                    segment_id=segment_id,
                    text=asr_segment.corrected_text,
                    speaker=SpeakerType.CUSTOMER,
                    timestamp=timestamp,
                    confidence=getattr(asr_segment, 'confidence', None)
                )
                await websocket.send_json(transcription_msg.dict())
                
                # STEP 2: Extract entities
                transcript = TranscriptSegment(
                    segment_id=segment_id,
                    timestamp=timestamp,
                    speaker="customer",
                    text=asr_segment.corrected_text
                )
                
                extraction_result = await self.extraction_agent.invoke(transcript)
                extraction = Agent_output(**extraction_result)
                
                # Send extraction update
                extraction_msg = ExtractionMessage(
                    segment_id=segment_id,
                    extraction=extraction.dict(),
                    timestamp=datetime.utcnow()
                )
                await websocket.send_json(extraction_msg.dict())
                
                # STEP 3: Update profile
                self.merge_extraction_into_profile(profile, extraction)
                user_profile = build_user_profile_from_extraction(profile)
                
                # Send profile update
                profile_msg = ProfileUpdateMessage(
                    profile=user_profile.dict() if hasattr(user_profile, 'dict') else user_profile,
                    timestamp=datetime.utcnow(),
                    changes=extraction.dict()  # What changed in this update
                )
                await websocket.send_json(profile_msg.dict())
                
                # STEP 4: Generate recommendations
                recommendation_result = recommend(user_profile)
                
                # Convert to API format
                recommendations = self._format_recommendations(recommendation_result)
                self.session_recommendations[session_id] = recommendations
                
                # Send recommendations update
                recs_msg = RecommendationsMessage(
                    recommendations=recommendations,
                    timestamp=datetime.utcnow(),
                    total_count=len(recommendations)
                )
                await websocket.send_json(recs_msg.dict())
                
                # STEP 5: Profile completion questions (optional)
                if call_id or current_call_id:
                    questions = await self.profile_agent.invoke(
                        call_id=call_id or current_call_id
                    )
                    
                    # Send questions
                    if questions:
                        for q in questions:
                            question_msg = ProfileQuestionMessage(
                                question_id=str(uuid.uuid4()),
                                question=q.get('question', ''),
                                field=q.get('field', 'unknown'),
                                timestamp=datetime.utcnow(),
                                options=q.get('options')
                            )
                            await websocket.send_json(question_msg.dict())
        
        except Exception as e:
            # Send error message
            error_msg = ErrorMessage(
                error_code="PIPELINE_ERROR",
                message=str(e),
                timestamp=datetime.utcnow(),
                details={"session_id": session_id}
            )
            await websocket.send_json(error_msg.dict())
            raise
    
    def _format_recommendations(self, recommendation_result: Any) -> list[RecommendationItem]:
        """
        Convert recommendation engine output to API format
        
        Adapt this based on your actual recommendation output structure
        """
        recommendations = []
        
        # Example conversion - adjust based on your actual structure
        if isinstance(recommendation_result, list):
            for idx, rec in enumerate(recommendation_result):
                recommendations.append(
                    RecommendationItem(
                        id=f"rec_{idx}",
                        destination=rec.get('destination', 'Unknown'),
                        score=rec.get('score', 0.0),
                        title=rec.get('title', ''),
                        description=rec.get('description', ''),
                        details=rec.get('details', {}),
                        price_estimate=rec.get('price_estimate'),
                        image_url=rec.get('image_url')
                    )
                )
        elif isinstance(recommendation_result, dict):
            # Handle single recommendation
            recommendations.append(
                RecommendationItem(
                    id="rec_0",
                    destination=recommendation_result.get('destination', 'Unknown'),
                    score=recommendation_result.get('score', 0.0),
                    title=recommendation_result.get('title', ''),
                    description=recommendation_result.get('description', ''),
                    details=recommendation_result.get('details', {}),
                    price_estimate=recommendation_result.get('price_estimate'),
                    image_url=recommendation_result.get('image_url')
                )
            )
        
        return recommendations
    
    def get_session_profile(self, session_id: str) -> dict:
        """Get current profile for a session"""
        return self.session_profiles.get(session_id, {})
    
    def get_session_recommendations(self, session_id: str) -> list:
        """Get current recommendations for a session"""
        return self.session_recommendations.get(session_id, [])


# ============================================================================
# Example: Updated WebSocket handler using PipelineProcessor
# ============================================================================

"""
Update your routes.py WebSocket endpoint to use this:

from backend.api.pipeline_integration import PipelineProcessor

# Initialize once
pipeline_processor = PipelineProcessor()

@router.websocket("/sessions/{session_id}/stream")
async def websocket_stream(websocket: WebSocket, session_id: str):
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
        await websocket.send_json(
            StatusMessage(
                status="connected",
                message="Ready to receive audio",
                timestamp=datetime.utcnow()
            ).dict()
        )
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == MessageType.AUDIO_CHUNK:
                audio_data = message.get("data")
                
                # Process through pipeline
                await pipeline_processor.process_audio_chunk(
                    session_id=session_id,
                    audio_data=audio_data,
                    websocket=websocket
                )
                
                sessions[session_id]["last_activity"] = datetime.utcnow()
                sessions[session_id]["status"] = "processing"
                
    except WebSocketDisconnect:
        sessions[session_id]["status"] = "disconnected"
    except Exception as e:
        await websocket.send_json(
            ErrorMessage(
                error_code="PROCESSING_ERROR",
                message=str(e),
                timestamp=datetime.utcnow()
            ).dict()
        )
        await websocket.close()
"""
