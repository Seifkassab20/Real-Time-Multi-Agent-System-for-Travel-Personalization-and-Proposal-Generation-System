# Quick Start Guide: Integrating Your Pipeline with the API

## Overview

This guide shows you how to integrate your existing pipeline code with the new API schema.

## Current State

You have a working pipeline in your notebook/script:
```python
audio → ASR → Extraction → Profile → Recommendations
```

## Goal

Expose this pipeline through a REST + WebSocket API that your frontend can consume.

---

## Step-by-Step Integration

### Step 1: Install Dependencies

Add these to your `requirements.txt`:

```txt
fastapi
uvicorn[standard]
websockets
python-multipart
aiofiles
```

Install:
```bash
pip install -r requirements.txt
```

### Step 2: Create Main FastAPI App

Create `backend/api/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router

app = FastAPI(
    title="Travel Personalization API",
    description="Real-time travel personalization through audio analysis",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

@app.get("/")
async def root():
    return {
        "message": "Travel Personalization API",
        "docs": "/docs",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Step 3: Update Routes to Use Your Pipeline

Modify `backend/api/routes.py` to integrate `PipelineProcessor`:

```python
from backend.api.pipeline_integration import PipelineProcessor

# Initialize once (singleton)
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
                
                # Process through your pipeline
                await pipeline_processor.process_audio_chunk(
                    session_id=session_id,
                    audio_data=audio_data,
                    websocket=websocket
                )
                
                sessions[session_id]["last_activity"] = datetime.utcnow()
                
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

# Update GET endpoints to use pipeline_processor
@router.get("/sessions/{session_id}/profile", response_model=ProfileResponse)
async def get_profile(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    profile = pipeline_processor.get_session_profile(session_id)
    
    return ProfileResponse(
        session_id=session_id,
        profile=profile,
        last_updated=sessions[session_id]["last_activity"],
        completeness_score=calculate_completeness(profile)
    )

@router.get("/sessions/{session_id}/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(session_id: str, page: int = 1, page_size: int = 10):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    all_recs = pipeline_processor.get_session_recommendations(session_id)
    
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
```

### Step 4: Adapt Pipeline to Accept Audio Bytes

Currently your pipeline uses a file path. Update it to accept audio bytes:

**Option A: Save to temp file**
```python
import tempfile
import base64

async def process_audio_chunk(self, session_id: str, audio_data: str, websocket):
    # Decode base64 audio
    audio_bytes = base64.b64decode(audio_data)
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        temp_file.write(audio_bytes)
        temp_path = temp_file.name
    
    try:
        # Process with your existing pipeline
        async for asr_segment, call_id in self.asr_service.stream_audio(temp_path):
            # ... rest of your pipeline
            pass
    finally:
        # Clean up temp file
        os.unlink(temp_path)
```

**Option B: Modify ASR service to accept bytes directly**
```python
# In backend/core/ASR/src/pipeline.py
async def stream_audio_bytes(self, audio_bytes: bytes):
    """Stream audio from bytes instead of file"""
    # Implement based on your ASR library
    pass
```

### Step 5: Run the Server

```bash
cd /Users/maryamsaad/Documents/Real-Time-Multi-Agent-System-for-Travel-Personalization-and-Proposal-Generation-System

# Run the API server
uvicorn backend.api.main:app --reload --port 8000
```

Visit http://localhost:8000/docs to see the interactive API documentation.

### Step 6: Test with Client

Use the provided client example:

```python
from backend.api.client_example import TravelPersonalizationClient
import asyncio

async def test():
    client = TravelPersonalizationClient()
    
    # Create session
    session = await client.create_session()
    print(f"Session: {session}")
    
    # Connect WebSocket
    await client.connect_websocket()
    
    # Start receiving updates
    async def handle_msg(msg_type, data):
        print(f"{msg_type}: {data}")
    
    receive_task = asyncio.create_task(
        client.receive_updates(handle_msg)
    )
    
    # Send audio
    with open("path/to/audio.wav", "rb") as f:
        audio_bytes = f.read()
        await client.send_audio_chunk(audio_bytes)
    
    # Wait for processing
    await asyncio.sleep(5)
    
    # Get results
    profile = await client.get_profile()
    recs = await client.get_recommendations()
    
    print(f"Profile: {profile}")
    print(f"Recommendations: {recs}")
    
    receive_task.cancel()
    await client.close()

asyncio.run(test())
```

---

## Frontend Integration

### HTML + JavaScript Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>Travel Personalization</title>
</head>
<body>
    <h1>Travel Personalization</h1>
    
    <button id="startBtn">Start Recording</button>
    <button id="stopBtn" disabled>Stop Recording</button>
    
    <div id="transcription"></div>
    <div id="profile"></div>
    <div id="recommendations"></div>
    
    <script>
        let sessionId = null;
        let ws = null;
        let mediaRecorder = null;
        
        // Create session
        async function createSession() {
            const response = await fetch('http://localhost:8000/api/v1/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const data = await response.json();
            sessionId = data.session_id;
            return data.websocket_url;
        }
        
        // Connect WebSocket
        function connectWebSocket(url) {
            ws = new WebSocket(url);
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };
        }
        
        // Handle messages
        function handleMessage(data) {
            switch(data.type) {
                case 'transcription':
                    document.getElementById('transcription').innerHTML += 
                        `<p>${data.text}</p>`;
                    break;
                case 'profile_update':
                    document.getElementById('profile').innerHTML = 
                        `<pre>${JSON.stringify(data.profile, null, 2)}</pre>`;
                    break;
                case 'recommendations':
                    const recsHtml = data.recommendations.map(rec => 
                        `<div>
                            <h3>${rec.title}</h3>
                            <p>${rec.description}</p>
                            <p>Score: ${rec.score}</p>
                        </div>`
                    ).join('');
                    document.getElementById('recommendations').innerHTML = recsHtml;
                    break;
            }
        }
        
        // Start recording
        document.getElementById('startBtn').onclick = async () => {
            // Create session and connect
            const wsUrl = await createSession();
            connectWebSocket(wsUrl);
            
            // Start recording
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            
            mediaRecorder.ondataavailable = async (event) => {
                if (event.data.size > 0) {
                    // Convert to base64 and send
                    const reader = new FileReader();
                    reader.onload = () => {
                        const base64Audio = btoa(reader.result);
                        ws.send(JSON.stringify({
                            type: 'audio_chunk',
                            data: base64Audio,
                            timestamp: new Date().toISOString(),
                            format: 'webm',
                            sample_rate: 48000
                        }));
                    };
                    reader.readAsBinaryString(event.data);
                }
            };
            
            mediaRecorder.start(1000); // Send chunk every second
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;
        };
        
        // Stop recording
        document.getElementById('stopBtn').onclick = () => {
            mediaRecorder.stop();
            ws.close();
            
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').disabled = true;
        };
    </script>
</body>
</html>
```

---

## Troubleshooting

### Issue: WebSocket connection fails
**Solution:** Make sure CORS is enabled and the server is running on the correct port.

### Issue: Audio format not supported
**Solution:** Your ASR service needs to support the audio format sent by the client. Convert if necessary.

### Issue: Pipeline processing is slow
**Solution:** Consider processing audio chunks in parallel or using a queue system.

---

## Next Steps

1. **Test the API** - Use the provided client or Postman
2. **Build Frontend** - Create a React/Vue app that uses the API
3. **Add Database** - Replace in-memory storage with PostgreSQL
4. **Deploy** - Deploy to cloud (AWS, GCP, Azure)
5. **Monitor** - Add logging and monitoring

---

## File Structure

```
backend/
├── api/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app
│   ├── routes.py                  # API endpoints
│   ├── schemas.py                 # Pydantic models
│   ├── pipeline_integration.py    # Pipeline wrapper
│   ├── client_example.py          # Example client
│   └── API_DOCUMENTATION.md       # Full API docs
├── core/
│   ├── ASR/
│   ├── extraction_agent/
│   ├── profile_agent/
│   └── recommendation_engine/
└── ...
```

---

## Questions?

Refer to:
- `API_DOCUMENTATION.md` for full API reference
- `client_example.py` for usage examples
- FastAPI docs at http://localhost:8000/docs
