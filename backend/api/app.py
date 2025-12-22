from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import asyncio
import uuid
import base64
import tempfile
import os
import subprocess
import subprocess
from datetime import datetime
from backend.core.recommendation_engine.recommendation_orchestrator import (
    build_user_profile_from_extraction,
    merge_value,
    MERGE_RULES,
    recommend
)


def convert_webm_to_wav(input_path: str, output_path: str) -> bool:
    """
    Convert WebM/Opus audio to WAV format using ffmpeg.
    Returns True if conversion was successful, False otherwise.
    """
    try:
        # First, check file size
        file_size = os.path.getsize(input_path)
        print(f"[DEBUG] Converting file: {input_path}, size: {file_size} bytes")
        
        if file_size < 100:
            print(f"[DEBUG] File too small, likely invalid: {file_size} bytes")
            return False
        
        result = subprocess.run([
            'ffmpeg', '-y',  # -y to overwrite output file if exists
            '-f', 'webm',    # Explicitly specify input format
            '-i', input_path,
            '-vn',           # No video
            '-ar', '16000',  # Sample rate: 16kHz (required for ASR)
            '-ac', '1',      # Mono channel
            '-acodec', 'pcm_s16le',  # PCM 16-bit little-endian
            '-f', 'wav',
            output_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"[DEBUG] FFmpeg stderr: {result.stderr}")
            # Try alternative approach without explicit format
            print("[DEBUG] Trying alternative conversion...")
            result2 = subprocess.run([
                'ffmpeg', '-y',
                '-i', input_path,
                '-vn',
                '-ar', '16000',
                '-ac', '1',
                '-f', 'wav',
                output_path
            ], capture_output=True, text=True, timeout=30)
            
            if result2.returncode != 0:
                print(f"[DEBUG] FFmpeg alternative also failed: {result2.stderr[-500:] if len(result2.stderr) > 500 else result2.stderr}")
                return False
        
        # Verify output file exists and has content
        if os.path.exists(output_path) and os.path.getsize(output_path) > 44:  # WAV header is 44 bytes
            print(f"[DEBUG] WAV file created: {output_path}, size: {os.path.getsize(output_path)} bytes")
            return True
        return False
    except subprocess.TimeoutExpired:
        print("FFmpeg conversion timed out")
        return False
    except FileNotFoundError:
        print("FFmpeg not found. Please install ffmpeg.")
        return False
    except Exception as e:
        print(f"Conversion error: {e}")
        return False



def convert_webm_to_wav(input_path: str, output_path: str) -> bool:
    """
    Convert WebM audio to WAV format using ffmpeg.
    Returns True if conversion was successful, False otherwise.
    """
    try:
        result = subprocess.run([
            'ffmpeg', '-y',  # -y to overwrite output file if exists
            '-i', input_path,
            '-ar', '16000',  # Sample rate: 16kHz (required for ASR)
            '-ac', '1',      # Mono channel
            '-f', 'wav',
            output_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("FFmpeg conversion timed out")
        return False
    except FileNotFoundError:
        print("FFmpeg not found. Please install ffmpeg.")
        return False
    except Exception as e:
        print(f"Conversion error: {e}")
        return False
from backend.core.ASR.src.pipeline import TranscriptionService
from backend.core.extraction_agent.extraction_agent import ExtractionAgent
from backend.core.extraction_agent.models import TranscriptSegment, Agent_output
from backend.core.profile_agent.profile_agent import ProfileAgent
from backend.database.db import NeonDatabase
from backend.database.models.calls import Calls
from backend.database.repostries.calls_repo import calls_repository
from pydantic import BaseModel
from typing import List, Optional

# Pydantic models for API responses
class QuestionResponse(BaseModel):
    question: str
    fields_filling: List[str]

class ProfileQuestionsResponse(BaseModel):
    call_id: str
    questions: List[QuestionResponse]
    success: bool
    error: Optional[str] = None

app = FastAPI(title="Travel Personalization API")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared state (in memory)
active_connections = {}

# Initialize profile agent
profile_agent = ProfileAgent()
calls_repo = calls_repository()

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Travel Personalization API is running",
        "endpoints": {
            "websocket": "ws://localhost:8000/ws/stream",
            "health": "http://localhost:8000/health",
            "profile_questions": "http://localhost:8000/api/profile/questions/{call_id}"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": str(datetime.utcnow())}

@app.post("/api/profile/questions/{call_id}", response_model=ProfileQuestionsResponse)
async def get_profile_questions(call_id: str):
    """
    Generate profile questions based on the user's existing profile.
    
    This endpoint invokes the ProfileAgent to analyze the user's profile
    and generate relevant questions to fill in missing information.
    
    Args:
        call_id: The unique identifier for the call/session
        
    Returns:
        ProfileQuestionsResponse with generated questions
    """
    try:
        result = await profile_agent.invoke(call_id)
        
        # invoke returns a tuple (json_string, profile_id)
        if isinstance(result, tuple):
            json_response = result[0]
            # Parse the JSON string response
            if isinstance(json_response, str):
                import json
                result_data = json.loads(json_response)
            else:
                result_data = json_response
        elif isinstance(result, str):
            import json
            result_data = json.loads(result)
        else:
            result_data = result
        
        questions = result_data.get("questions", []) if result_data else []
        
        return ProfileQuestionsResponse(
            call_id=call_id,
            questions=[QuestionResponse(**q) for q in questions],
            success=True
        )
    except Exception as e:
        print(f"Profile questions error: {e}")
        return ProfileQuestionsResponse(
            call_id=call_id,
            questions=[],
            success=False,
            error=str(e)
        )

async def safe_send_json(websocket: WebSocket, data: dict) -> bool:
    """Safely send JSON over websocket, return False if connection is closed."""
    try:
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError, Exception) as e:
        # Connection already closed, don't log errors
        return False

@app.websocket("/ws/stream", name="websocket_endpoint")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    asr_service = TranscriptionService()
    extraction_agent = ExtractionAgent()
    
    
    final_profile = {}
    recommendations = []
    segment_count = 0
    client_info = {}
    call_id = str(uuid.uuid4())
    extraction_id = None  # Track extraction_id across segments
    audio_buffer = []
    header_chunk = None  # Store the first chunk which contains WebM header
    ws_connected = True  # Track connection state
    
    # Create a temporary directory for audio files
    temp_dir = tempfile.mkdtemp()
    
    try: 
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle start_call message with client info
            if message.get("type") == "start_call":
                client_info = {
                    "name": message.get("clientName", "Unknown"),
                    "phone": message.get("clientPhone", ""),
                    "call_id": call_id,
                    "started_at": datetime.utcnow().isoformat()
                }
                print(f"Call started with client: {client_info['name']} ({client_info['phone']})")
                # Reset audio state for new call
                audio_buffer = []
                header_chunk = None
                
                # Create call record in database so extraction can reference it
                try:
                    NeonDatabase.init()
                    async with NeonDatabase.get_session() as session:
                        call_record = Calls(
                            call_id=uuid.UUID(call_id),
                            call_context=[],
                            started_at=datetime.utcnow()
                        )
                        await calls_repo.create(session, call_record)
                        print(f"Call record created in database with ID: {call_id}")
                except Exception as e:
                    print(f"Error creating call record: {e}")
                
                ws_connected = await safe_send_json(websocket, {
                    "type": "call_started",
                    "call_id": call_id,
                    "message": f"Call started with {client_info['name']}"
                })
            
            # Handle audio segments from frontend
            elif message.get("type") == "audio_segment":
                audio_data = message.get("data")
                mime_type = message.get("mimeType", "audio/webm;codecs=opus")
                
                if audio_data:
                    # Decode base64 audio data
                    audio_bytes = base64.b64decode(audio_data)
                    
                    # Save WebM file
                    temp_webm_path = os.path.join(temp_dir, f"segment_{segment_count}.webm")
                    temp_wav_path = os.path.join(temp_dir, f"segment_{segment_count}.wav")
                    
                    with open(temp_webm_path, 'wb') as f:
                        f.write(audio_bytes)
                    
                    # Convert WebM to WAV for ASR processing
                    if not convert_webm_to_wav(temp_webm_path, temp_wav_path):
                        print(f"Failed to convert audio segment {segment_count}")
                        ws_connected = await safe_send_json(websocket, {
                            "type": "error",
                            "message": "Audio conversion failed. Please ensure ffmpeg is installed."
                        })
                        # Clean up
                        if os.path.exists(temp_webm_path):
                            os.remove(temp_webm_path)
                        continue
                    
                    # Process the converted WAV audio through ASR
                    try:
                        async for asr_segment, seg_call_id in asr_service.stream_audio(temp_wav_path):
                            segment_count += 1
                            
                            if not await safe_send_json(websocket, {
                                "type": "transcript",
                                "text": asr_segment.corrected_text,
                                "segment": segment_count
                            }):
                                ws_connected = False
                                break

                            # 2. Extract
                            transcript_obj = TranscriptSegment(
                                segment_id=str(uuid.uuid4()),
                                timestamp=datetime.utcnow(),
                                speaker="customer",
                                text=asr_segment.corrected_text
                            )
                            
                            try:
                                extraction_result = await extraction_agent.invoke(
                                    transcript_obj, segment_count, call_id, extraction_id
                                )
                  
                                if isinstance(extraction_result, tuple):
                                    extraction_data = extraction_result[0]
                                    # Capture extraction_id for subsequent segments
                                    if extraction_result[1]:
                                        extraction_id = extraction_result[1]
                                else:
                                    extraction_data = extraction_result
                                
                                # Merge extraction data into final_profile
                                for key, rule in MERGE_RULES.items():
                                    if key in extraction_data:
                                        final_profile[key] = merge_value(
                                            final_profile.get(key), 
                                            extraction_data.get(key), 
                                            rule
                                        )
                                    
                                extraction = Agent_output(**extraction_data)
                                
                                # Notify frontend that extraction is done so it can fetch updated questions
                                if not await safe_send_json(websocket, {
                                    "type": "extraction_done",
                                    "call_id": call_id,
                                    "segment": segment_count,
                                    "message": "Extraction completed successfully"
                                }):
                                    ws_connected = False
                                    break
                                
                                # 3. Generate recommendations if we have enough data
                                try:
                                    # Build user profile from accumulated extraction data
                                    user_profile = build_user_profile_from_extraction(final_profile)
                                    
                                    # Run recommendation engine
                                    plan = recommend(user_profile)
                                    
                                    if plan and plan.get("status") == "OK":
                                        # Format recommendations for frontend
                                        recommendations_payload = {
                                            "type": "recommendations",
                                            "call_id": call_id,
                                            "segment": segment_count,
                                            "hotel": plan.get("hotel"),
                                            "itinerary": plan.get("itinerary"),
                                            "budget_breakdown": plan.get("budget_breakdown")
                                        }
                                        if await safe_send_json(websocket, recommendations_payload):
                                            print(f"Recommendations sent for segment {segment_count}")
                                            print(recommendations_payload)
                                        else:
                                            ws_connected = False
                                            break
                                except Exception as rec_error:
                                    print(f"Recommendation error: {rec_error}")
                                    # Don't fail extraction if recommendations fail
                                    
                            except Exception as e:
                                print(f"Extraction error: {e}")
                                continue
                            
                            # Break outer loop if disconnected
                            if not ws_connected:
                                break
                                
                    except Exception as e:
                        print(f"ASR Error: {e}")
                        ws_connected = await safe_send_json(websocket, {
                            "type": "error",
                            "message": f"Transcription error: {str(e)}"
                        })
                    finally:
                        # Clean up temp files
                        for temp_file in [temp_webm_path, temp_wav_path]:
                            if os.path.exists(temp_file):
                                os.remove(temp_file)
            
            # Handle legacy process_audio message (file path based)
            elif message.get("type") == "process_audio":
                audio_path = message.get("path")
                
                async for asr_segment, seg_call_id in asr_service.stream_audio(audio_path):
                    segment_count += 1
                    
                    if not await safe_send_json(websocket, {
                        "type": "transcript",
                        "text": asr_segment.corrected_text,
                        "segment": segment_count
                    }):
                        ws_connected = False
                        break

                    # 2. Extract
                    transcript_obj = TranscriptSegment(
                        segment_id=str(uuid.uuid4()),
                        timestamp=datetime.utcnow(),
                        speaker="customer",
                        text=asr_segment.corrected_text
                    )
                    
                    try:
                        extraction_result = await extraction_agent.invoke(transcript_obj, segment_count, call_id)
          
                        if isinstance(extraction_result, tuple):
                            extraction_data = extraction_result[0]
                        else:
                            extraction_data = extraction_result
                            
                        extraction = Agent_output(**extraction_data)
                    except Exception as e:
                        print(f"Extraction error: {e}")
                        continue

            elif message.get("type") == "stop":
                print(f"Call ended for client: {client_info.get('name', 'Unknown')}")
                break

    except WebSocketDisconnect:
        print("Client disconnected")
        ws_connected = False
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_connected = False
    finally:
        # Clean up temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        # Only try to close if still connected
        if ws_connected:
            try:
                await websocket.close()
            except Exception:
                pass  # Already closed

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

