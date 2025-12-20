# Travel Personalization API Documentation

## Overview

This API provides real-time travel personalization through audio conversation analysis. It processes audio streams through a multi-agent pipeline:

1. **ASR (Automatic Speech Recognition)** - Transcribes audio to text
2. **Extraction Agent** - Extracts travel preferences and requirements
3. **Profile Agent** - Builds and maintains user profile
4. **Recommendation Engine** - Generates personalized travel recommendations

## Architecture

### Communication Patterns

- **WebSocket** - Real-time audio streaming and live updates
- **REST API** - Session management and data retrieval

### Data Flow

```
Client Audio → WebSocket → ASR → Extraction → Profile Update → Recommendations
                    ↓           ↓          ↓            ↓              ↓
                 Updates sent back to client in real-time
```

---

## API Endpoints

### Base URL
```
Production: https://api.travel-personalization.com/api/v1
Development: http://localhost:8000/api/v1
```

---

## REST Endpoints

### 1. Create Session

Create a new conversation session.

**Endpoint:** `POST /sessions`

**Request Body:**
```json
{
  "user_id": "optional_user_id",
  "metadata": {
    "source": "web",
    "language": "en"
  }
}
```

**Response:** `201 Created`
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-12-21T01:42:35Z",
  "websocket_url": "ws://localhost:8000/api/v1/sessions/{session_id}/stream"
}
```

---

### 2. Get User Profile

Retrieve the current user profile for a session.

**Endpoint:** `GET /sessions/{session_id}/profile`

**Response:** `200 OK`
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "profile": {
    "destinations": ["Paris", "Rome"],
    "budget": {
      "min": 2000,
      "max": 5000,
      "currency": "USD"
    },
    "travel_dates": {
      "start": "2025-06-01",
      "end": "2025-06-15"
    },
    "preferences": {
      "accommodation_type": "hotel",
      "activities": ["museums", "food_tours"],
      "travel_style": "cultural"
    }
  },
  "last_updated": "2025-12-21T01:45:00Z",
  "completeness_score": 0.75
}
```

---

### 3. Get Recommendations

Retrieve travel recommendations for a session.

**Endpoint:** `GET /sessions/{session_id}/recommendations`

**Query Parameters:**
- `page` (integer, default: 1) - Page number
- `page_size` (integer, default: 10, max: 100) - Items per page

**Response:** `200 OK`
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "recommendations": [
    {
      "id": "rec_1",
      "destination": "Paris",
      "score": 0.95,
      "title": "7-Day Cultural Experience in Paris",
      "description": "Explore the art and culture of Paris with museum tours and culinary experiences",
      "details": {
        "duration_days": 7,
        "highlights": ["Louvre Museum", "Eiffel Tower", "Food Tour"],
        "accommodation": "4-star hotel in Le Marais"
      },
      "price_estimate": {
        "total": 3500,
        "currency": "USD",
        "breakdown": {
          "flights": 800,
          "accommodation": 1400,
          "activities": 800,
          "meals": 500
        }
      },
      "image_url": "https://example.com/paris.jpg"
    }
  ],
  "generated_at": "2025-12-21T01:45:00Z",
  "total_count": 15,
  "page": 1,
  "page_size": 10
}
```

---

### 4. Get Transcript

Retrieve the conversation transcript.

**Endpoint:** `GET /sessions/{session_id}/transcript`

**Response:** `200 OK`
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "segments": [
    {
      "segment_id": "seg_1",
      "timestamp": "2025-12-21T01:42:40Z",
      "speaker": "customer",
      "text": "I want to visit Paris and Rome this summer",
      "extraction": {
        "destinations": ["Paris", "Rome"],
        "travel_dates": {"season": "summer"}
      }
    }
  ],
  "total_segments": 12
}
```

---

### 5. Answer Profile Question

Submit an answer to a profile completion question.

**Endpoint:** `POST /sessions/{session_id}/answers`

**Request Body:**
```json
{
  "question_id": "q_123",
  "answer": "Between $2000 and $5000"
}
```

**Response:** `200 OK`
```json
{
  "question_id": "q_123",
  "accepted": true,
  "updated_profile": {
    "budget": {
      "min": 2000,
      "max": 5000,
      "currency": "USD"
    }
  },
  "timestamp": "2025-12-21T01:46:00Z"
}
```

---

### 6. Get Session Status

Get the current status of a session.

**Endpoint:** `GET /sessions/{session_id}/status`

**Response:** `200 OK`
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "created_at": "2025-12-21T01:42:35Z",
  "last_activity": "2025-12-21T01:45:30Z",
  "segment_count": 12,
  "profile_completeness": 0.75
}
```

---

### 7. Health Check

Check API health status.

**Endpoint:** `GET /health`

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "timestamp": "2025-12-21T01:42:35Z",
  "version": "1.0.0",
  "services": {
    "asr": "healthy",
    "extraction": "healthy",
    "profile": "healthy",
    "recommendations": "healthy"
  }
}
```

---

## WebSocket Endpoint

### Real-Time Audio Streaming

**Endpoint:** `WS /sessions/{session_id}/stream`

### Connection Flow

1. **Connect** to WebSocket
2. **Receive** status message confirming connection
3. **Send** audio chunks
4. **Receive** real-time updates (transcription, extraction, profile, recommendations)
5. **Close** connection when done

### Message Types

#### Client → Server

##### Audio Chunk
```json
{
  "type": "audio_chunk",
  "data": "base64_encoded_audio_data",
  "timestamp": "2025-12-21T01:42:35Z",
  "format": "wav",
  "sample_rate": 16000
}
```

#### Server → Client

##### Status Message
```json
{
  "type": "status",
  "status": "connected",
  "message": "Ready to receive audio",
  "timestamp": "2025-12-21T01:42:35Z"
}
```

##### Transcription
```json
{
  "type": "transcription",
  "segment_id": "seg_1",
  "text": "I want to visit Paris",
  "speaker": "customer",
  "timestamp": "2025-12-21T01:42:36Z",
  "confidence": 0.95
}
```

##### Extraction
```json
{
  "type": "extraction",
  "segment_id": "seg_1",
  "extraction": {
    "destinations": ["Paris"],
    "budget": null,
    "travel_dates": null,
    "preferences": {}
  },
  "timestamp": "2025-12-21T01:42:37Z"
}
```

##### Profile Update
```json
{
  "type": "profile_update",
  "profile": {
    "destinations": ["Paris"],
    "budget": null,
    "travel_dates": null,
    "preferences": {}
  },
  "timestamp": "2025-12-21T01:42:38Z",
  "changes": {
    "destinations": ["Paris"]
  }
}
```

##### Recommendations
```json
{
  "type": "recommendations",
  "recommendations": [
    {
      "id": "rec_1",
      "destination": "Paris",
      "score": 0.95,
      "title": "7-Day Paris Experience",
      "description": "...",
      "details": {},
      "price_estimate": {},
      "image_url": "..."
    }
  ],
  "timestamp": "2025-12-21T01:42:39Z",
  "total_count": 5
}
```

##### Profile Question
```json
{
  "type": "profile_question",
  "question_id": "q_1",
  "question": "What's your preferred budget range?",
  "field": "budget",
  "timestamp": "2025-12-21T01:42:40Z",
  "options": ["$1000-$2000", "$2000-$5000", "$5000+"]
}
```

##### Error
```json
{
  "type": "error",
  "error_code": "PROCESSING_ERROR",
  "message": "Failed to process audio segment",
  "timestamp": "2025-12-21T01:42:40Z",
  "details": {
    "segment_id": "seg_1"
  }
}
```

---

## Error Codes

| Code | Description |
|------|-------------|
| `SESSION_NOT_FOUND` | Session ID does not exist |
| `PROCESSING_ERROR` | Error during pipeline processing |
| `INVALID_AUDIO_FORMAT` | Unsupported audio format |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `AUTHENTICATION_FAILED` | Invalid credentials |

---

## Rate Limits

- **REST API:** 100 requests per minute per session
- **WebSocket:** 1 connection per session, max 10 audio chunks per second

---

## Authentication

(To be implemented)

```
Authorization: Bearer <token>
```

---

## Example Usage

### JavaScript/TypeScript (Frontend)

```javascript
// Create session
const response = await fetch('http://localhost:8000/api/v1/sessions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ user_id: 'user_123' })
});
const { session_id, websocket_url } = await response.json();

// Connect WebSocket
const ws = new WebSocket(websocket_url);

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'transcription':
      console.log('Transcription:', data.text);
      break;
    case 'recommendations':
      console.log('Recommendations:', data.recommendations);
      break;
    // ... handle other message types
  }
};

// Send audio chunk
function sendAudioChunk(audioBlob) {
  const reader = new FileReader();
  reader.onload = () => {
    const base64Audio = btoa(reader.result);
    ws.send(JSON.stringify({
      type: 'audio_chunk',
      data: base64Audio,
      timestamp: new Date().toISOString(),
      format: 'wav',
      sample_rate: 16000
    }));
  };
  reader.readAsBinaryString(audioBlob);
}
```

### Python (Backend/Testing)

```python
import asyncio
import aiohttp

async def test_api():
    # Create session
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8000/api/v1/sessions') as resp:
            data = await resp.json()
            session_id = data['session_id']
    
    # Connect WebSocket
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            f'ws://localhost:8000/api/v1/sessions/{session_id}/stream'
        ) as ws:
            # Receive messages
            async for msg in ws:
                data = msg.json()
                print(f"Received: {data['type']}")

asyncio.run(test_api())
```

---

## Development Setup

1. Install dependencies:
```bash
pip install fastapi uvicorn websockets aiohttp pydantic
```

2. Run the server:
```bash
uvicorn backend.api.main:app --reload --port 8000
```

3. Access API docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Next Steps for Production

1. **Database Integration** - Replace in-memory storage with PostgreSQL/MongoDB
2. **Authentication** - Implement JWT-based auth
3. **Rate Limiting** - Add Redis-based rate limiting
4. **Monitoring** - Add logging, metrics, and tracing
5. **Scaling** - Deploy with load balancer and multiple workers
6. **Audio Storage** - Store audio files in S3/cloud storage
7. **Caching** - Cache recommendations and profiles
