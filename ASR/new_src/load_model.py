from transformers import AutoProcessor
from transformers import SeamlessM4Tv2ForSpeechToText
from dotenv import load_dotenv
import os
load_dotenv()


device=os.getenv('DEVICE')
model_name=os.getenv('MODEL_NAME')
cache_dir=os.getenv('cache_dir')

class LoadSeamlessModel:
    def __init__(self):
        self.device=device
        self.model_name=model_name
        self.cache_dir=cache_dir

    def _load(self) -> None:
        """Load model with progress."""
        self.processor = AutoProcessor.from_pretrained(self.model_name, cache_dir=self.cache_dir, use_fast=False)
        self.model = SeamlessM4Tv2ForSpeechToText.from_pretrained(self.model_name, cache_dir=self.cache_dir)
        self.model.to(self.device) 
        self.loaded = True
        print("[Seamless] ✓ Model loaded successfully.")
        return self.processor , self.model


