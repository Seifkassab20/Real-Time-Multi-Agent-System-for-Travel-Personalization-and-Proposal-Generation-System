import os
import time
from dotenv import load_dotenv
from transformers import AutoProcessor, SeamlessM4Tv2ForSpeechToText
from langsmith import traceable
from backend.core.tracing_config import get_metadata
load_dotenv()
DEVICE = os.getenv('DEVICE', 'cpu')
MODEL_NAME = os.getenv('MODEL_NAME')
CACHE_DIR = os.getenv('cache_dir')

class LoadSeamlessModel:
    def __init__(self):
        self.device = DEVICE
        self.model_name = MODEL_NAME
        self.cache_dir = CACHE_DIR
        self.processor = None
        self.model = None

    @traceable(run_type="tool", name="seamless_model_loading")
    def load(self): 
        """Load model and processor with tracing."""
        start_time = time.time()
        
        # Load processor and model
        self.processor = AutoProcessor.from_pretrained(
            self.model_name, 
            cache_dir=self.cache_dir, 
            use_fast=False
        )
        self.model = SeamlessM4Tv2ForSpeechToText.from_pretrained(
            self.model_name, 
            cache_dir=self.cache_dir
        )
        self.model.to(self.device)
        
        loading_time = time.time() - start_time
        metadata={
            "model_name": self.model_name,
            "device": self.device,
            "loading_time_seconds": round(loading_time, 3),
            "cache_dir": self.cache_dir
        }
        
        return self.processor, self.model

# Usage
if __name__ == "__main__":
    loader = LoadSeamlessModel()
    processor, model = loader.load()