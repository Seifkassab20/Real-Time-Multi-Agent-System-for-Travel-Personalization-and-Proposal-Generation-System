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
    header_chunk = None  # Store the first chunk which contains WebM header
    
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
                
                await websocket.send_json({
                    "type": "call_started",
                    "call_id": call_id,
                    "message": f"Call started with {client_info['name']}"
                })
            
            # Handle complete 20-second audio segments from frontend
            elif message.get("type") == "audio_segment":
                audio_data = message.get("data")
                duration = message.get("duration", 20)
                
                if audio_data:
                    print(f"Received {duration}s audio segment")
                    
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
                        await websocket.send_json({
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
                        # Clean up temp files
                        for temp_file in [temp_webm_path, temp_wav_path]:
                            if os.path.exists(temp_file):
                                os.remove(temp_file)
            
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

