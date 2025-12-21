from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import asyncio
import uuid
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

@app.websocket("/ws/stream",name="websocket_endpoint")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    asr_service = TranscriptionService()
    extraction_agent = ExtractionAgent()
    # profile_agent = ProfileAgent()
    
    final_profile = {}
    recommendations = []
    segment_count = 0
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "process_audio":
                audio_path = message.get("path")
                
                async for asr_segment, call_id in asr_service.stream_audio(audio_path):
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
                        extraction_result = await extraction_agent.invoke(transcript_obj,segment_count,call_id)
          
                        if isinstance(extraction_result, tuple):
                            extraction_data = extraction_result[0]
                        else:
                            extraction_data = extraction_result
                            
                        extraction = Agent_output(**extraction_data)
                    except Exception as e:
                        print(f"Extraction error: {e}")
                        continue

                    # # 3. Merge Profile
                    # # Helper function inlined or imported
                    # for field, rule in MERGE_RULES.items():
                    #     final_profile[field] = merge_value(
                    #         final_profile.get(field),
                    #         getattr(extraction, field, None),
                    #         rule
                    #     )
                    
                    # user_profile = build_user_profile_from_extraction(final_profile)
                    
                    # await websocket.send_json({
                    #     "type": "profile_update",
                    #     "profile": user_profile
                    # })

                    # # 4. Recommend
                    # rec_result = recommend(user_profile)
                    # recommendations.append(rec_result)
                    
                    # await websocket.send_json({
                    #     "type": "recommendation",
                    #     "data": rec_result
                    # })

            elif message.get("type") == "stop":
                break

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
