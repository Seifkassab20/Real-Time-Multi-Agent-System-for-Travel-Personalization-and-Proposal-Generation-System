"""
Example client code for interacting with the Travel Personalization API

This shows how your frontend would:
1. Create a session
2. Connect to WebSocket
3. Stream audio
4. Receive real-time updates
"""

import asyncio
import aiohttp
import json
import base64
from datetime import datetime


class TravelPersonalizationClient:
    """Client for Travel Personalization API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws")
        self.session_id = None
        self.websocket = None
    
    async def create_session(self, user_id: str = None) -> dict:
        """Create a new session"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/sessions",
                json={"user_id": user_id}
            ) as response:
                data = await response.json()
                self.session_id = data["session_id"]
                return data
    
    async def connect_websocket(self):
        """Connect to WebSocket for real-time streaming"""
        if not self.session_id:
            raise ValueError("Must create session first")
        
        session = aiohttp.ClientSession()
        self.websocket = await session.ws_connect(
            f"{self.ws_url}/api/v1/sessions/{self.session_id}/stream"
        )
        return self.websocket
    
    async def send_audio_chunk(self, audio_bytes: bytes, audio_format: str = "wav"):
        """Send audio chunk to server"""
        if not self.websocket:
            raise ValueError("WebSocket not connected")
        
        # Encode audio as base64
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        message = {
            "type": "audio_chunk",
            "data": audio_b64,
            "timestamp": datetime.utcnow().isoformat(),
            "format": audio_format,
            "sample_rate": 16000
        }
        
        await self.websocket.send_json(message)
    
    async def receive_updates(self, callback):
        """
        Receive real-time updates from server
        
        Args:
            callback: Function to handle each message
                     Should accept (message_type, data) as arguments
        """
        if not self.websocket:
            raise ValueError("WebSocket not connected")
        
        async for msg in self.websocket:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                message_type = data.get("type")
                await callback(message_type, data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f"WebSocket error: {self.websocket.exception()}")
                break
    
    async def get_profile(self) -> dict:
        """Get current user profile"""
        if not self.session_id:
            raise ValueError("No active session")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/sessions/{self.session_id}/profile"
            ) as response:
                return await response.json()
    
    async def get_recommendations(self, page: int = 1, page_size: int = 10) -> dict:
        """Get recommendations"""
        if not self.session_id:
            raise ValueError("No active session")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/sessions/{self.session_id}/recommendations",
                params={"page": page, "page_size": page_size}
            ) as response:
                return await response.json()
    
    async def get_transcript(self) -> dict:
        """Get conversation transcript"""
        if not self.session_id:
            raise ValueError("No active session")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/sessions/{self.session_id}/transcript"
            ) as response:
                return await response.json()
    
    async def answer_question(self, question_id: str, answer: any) -> dict:
        """Answer a profile question"""
        if not self.session_id:
            raise ValueError("No active session")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/sessions/{self.session_id}/answers",
                json={"question_id": question_id, "answer": answer}
            ) as response:
                return await response.json()
    
    async def close(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()


# ============================================================================
# Example Usage
# ============================================================================

async def handle_message(message_type: str, data: dict):
    """Handle incoming messages from server"""
    
    if message_type == "transcription":
        print(f"[TRANSCRIPTION] {data['text']}")
    
    elif message_type == "extraction":
        print(f"[EXTRACTION] {data['extraction']}")
    
    elif message_type == "profile_update":
        print(f"[PROFILE UPDATE] {data['profile']}")
    
    elif message_type == "recommendations":
        print(f"[RECOMMENDATIONS] Found {len(data['recommendations'])} recommendations")
        for rec in data['recommendations']:
            print(f"  - {rec['title']} (score: {rec['score']})")
    
    elif message_type == "profile_question":
        print(f"[QUESTION] {data['question']}")
        # In a real app, you'd prompt the user and send the answer
    
    elif message_type == "error":
        print(f"[ERROR] {data['message']}")
    
    elif message_type == "status":
        print(f"[STATUS] {data['status']}: {data.get('message', '')}")


async def example_streaming_session():
    """Example: Stream audio and receive real-time updates"""
    
    client = TravelPersonalizationClient()
    
    # 1. Create session
    session_data = await client.create_session(user_id="user_123")
    print(f"Created session: {session_data['session_id']}")
    
    # 2. Connect WebSocket
    await client.connect_websocket()
    print("Connected to WebSocket")
    
    # 3. Start receiving updates in background
    receive_task = asyncio.create_task(
        client.receive_updates(handle_message)
    )
    
    # 4. Stream audio chunks
    # In a real app, you'd capture audio from microphone
    audio_file = "/path/to/audio.wav"
    
    # Read audio in chunks and send
    chunk_size = 16000 * 2  # 1 second of 16kHz audio
    with open(audio_file, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            
            await client.send_audio_chunk(chunk)
            await asyncio.sleep(1)  # Simulate real-time streaming
    
    # 5. Wait a bit for final processing
    await asyncio.sleep(5)
    
    # 6. Get final profile and recommendations
    profile = await client.get_profile()
    print(f"\nFinal Profile: {profile}")
    
    recommendations = await client.get_recommendations()
    print(f"\nFinal Recommendations: {recommendations}")
    
    # 7. Cleanup
    receive_task.cancel()
    await client.close()


async def example_rest_only():
    """Example: Use REST API only (no streaming)"""
    
    client = TravelPersonalizationClient()
    
    # Create session
    session_data = await client.create_session()
    print(f"Session: {session_data}")
    
    # Get profile
    profile = await client.get_profile()
    print(f"Profile: {profile}")
    
    # Get recommendations
    recs = await client.get_recommendations(page=1, page_size=5)
    print(f"Recommendations: {recs}")
    
    # Get transcript
    transcript = await client.get_transcript()
    print(f"Transcript: {transcript}")


if __name__ == "__main__":
    # Run streaming example
    asyncio.run(example_streaming_session())
    
    # Or run REST-only example
    # asyncio.run(example_rest_only())
