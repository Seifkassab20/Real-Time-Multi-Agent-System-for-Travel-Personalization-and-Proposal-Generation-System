from transformers import AutoProcessor
from transformers import SeamlessM4Tv2ForSpeechToText
from dotenv import load_dotenv
import os
import time
from langsmith import traceable, get_current_run_tree
load_dotenv()


device=os.getenv('DEVICE')
model_name=os.getenv('MODEL_NAME')
cache_dir=os.getenv('cache_dir')

class LoadSeamlessModel:
    def __init__(self):
        self.device=device
        self.model_name=model_name
        self.cache_dir=cache_dir

    @traceable(run_type="tool", name="model_loading")
    def _load(self) -> None:
        """Load model with progress."""
        start_time = time.time()
        
        # Load processor and model
        self.processor = AutoProcessor.from_pretrained(self.model_name, cache_dir=self.cache_dir, use_fast=False)
        self.model = SeamlessM4Tv2ForSpeechToText.from_pretrained(self.model_name, cache_dir=self.cache_dir)
        self.model.to(self.device) 
        self.loaded = True
        
        # Calculate loading time
        loading_time = time.time() - start_time
        
        # Add metadata to current trace
        current_run = get_current_run_tree()
        if current_run:
            current_run.extra = current_run.extra or {}
            current_run.extra.update({
                "model_name": self.model_name,
                "cache_directory": self.cache_dir,
                "device": self.device,
                "loading_time_seconds": round(loading_time, 3),
                "processor_loaded": True,
                "model_loaded": True,
                "model_moved_to_device": True
            })
        
        print(f"[Seamless] ✓ Model loaded successfully in {loading_time:.3f}s.")
        return self.processor , self.model


