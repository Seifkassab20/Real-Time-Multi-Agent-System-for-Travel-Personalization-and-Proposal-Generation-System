from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import asyncio
import uuid
import base64
import tempfile
import os
from datetime import datetime

# Import your actual pipeline components from your project structure
# We'll use the logic similar to what's in your main.py
from backend.core.ASR.src.pipeline import TranscriptionService
from backend.core.extraction_agent.extraction_agent import ExtractionAgent
from backend.core.extraction_agent.models import TranscriptSegment, Agent_output
# from backend.core.profile_agent.profile_agent import ProfileAgent
# from backend.core.recommendation_engine.recommendation_orchestrator import (
#     build_user_profile_from_extraction,
#     merge_value,
#     MERGE_RULES,
#     recommend
# )

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

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Travel Personalization API is running",
        "endpoints": {
            "websocket": "ws://localhost:8000/ws/stream",
            "health": "http://localhost:8000/health"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": str(datetime.utcnow())}

@app.websocket("/ws/stream", name="websocket_endpoint")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    asr_service = TranscriptionService()
    extraction_agent = ExtractionAgent()
    # profile_agent = ProfileAgent()
    
    final_profile = {}
    recommendations = []
    segment_count = 0
    client_info = {}
    call_id = str(uuid.uuid4())
    audio_buffer = []
    
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
                
                await websocket.send_json({
                    "type": "call_started",
                    "call_id": call_id,
                    "message": f"Call started with {client_info['name']}"
                })
            
            # Handle audio chunks from frontend
            elif message.get("type") == "audio_chunk":
                audio_data = message.get("data")
                mime_type = message.get("mimeType", "audio/webm;codecs=opus")
                
                if audio_data:
                    # Decode base64 audio data
                    audio_bytes = base64.b64decode(audio_data)
                    audio_buffer.append(audio_bytes)
                    
                    # Process audio when we have enough data (e.g., every 3 chunks = 3 seconds)
                    if len(audio_buffer) >= 3:
                        # Combine audio chunks
                        combined_audio = b''.join(audio_buffer)
                        audio_buffer = []  # Clear buffer
                        
                        # Save to temporary file for processing
                        temp_audio_path = os.path.join(temp_dir, f"chunk_{segment_count}.webm")
                        with open(temp_audio_path, 'wb') as f:
                            f.write(combined_audio)
                        
                        # Process the audio through ASR
                        try:
                            async for asr_segment, seg_call_id in asr_service.stream_audio(temp_audio_path):
                                segment_count += 1
                                
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": asr_segment.corrected_text,
                                    "segment": segment_count
                                })

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
                        except Exception as e:
                            print(f"ASR Error: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Transcription error: {str(e)}"
                            })
                        finally:
                            # Clean up temp file
                            if os.path.exists(temp_audio_path):
                                os.remove(temp_audio_path)
            
            # Handle legacy process_audio message (file path based)
            elif message.get("type") == "process_audio":
                audio_path = message.get("path")
                
                async for asr_segment, seg_call_id in asr_service.stream_audio(audio_path):
                    segment_count += 1
                    
                    await websocket.send_json({
                        "type": "transcript",
                        "text": asr_segment.corrected_text,
                        "segment": segment_count
                    })

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
    except Exception as e:
        print(f"Error: {e}")
        await websocket.close()
    finally:
        # Clean up temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

