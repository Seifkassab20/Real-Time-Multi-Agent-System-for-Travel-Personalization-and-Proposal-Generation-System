"""
Simple configuration for Extraction Agent
"""
import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    # LLM Settings
    LLM_API_KEY = os.getenv("")
    LLM_MODEL = ""
    LLM_TEMPERATURE = 0
    
    # Event Bus
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    TRANSCRIPT_TOPIC = "transcripts"
    EXTRACTION_TOPIC = "extractions"

config = Config()