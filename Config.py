"""
Simple configuration for Extraction Agent
"""
import os

class Config:
    # LLM Settings
    LLM_API_KEY = os.getenv("OPENAI_API_KEY")
    LLM_MODEL = "gpt-4-turbo"
    LLM_TEMPERATURE = 0.3
    
    # Event Bus
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    TRANSCRIPT_TOPIC = "transcripts"
    EXTRACTION_TOPIC = "extractions"

config = Config()