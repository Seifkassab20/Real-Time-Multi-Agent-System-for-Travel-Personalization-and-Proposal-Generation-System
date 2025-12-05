# asr_engine.py
from transformers import AutoProcessor, AutoModelForCTC
import torch
import torch.nn.functional as F
import logging
from dotenv import load_dotenv
import os

load_dotenv()

ASR_MODEL = str(os.getenv("MODEL_NAME"))
DEVICE = str(os.getenv("DEVICE")) 
TARGET_SR = int(os.getenv("TARGET_SR"))

logger = logging.getLogger("asr_engine")
logger.setLevel(logging.INFO)

class ASREngine:
    def __init__(self):
        logger.info(f"Loading ASR model: {ASR_MODEL} on device {DEVICE}")
        self.processor = AutoProcessor.from_pretrained(ASR_MODEL)
        self.model = AutoModelForCTC.from_pretrained(ASR_MODEL).to(DEVICE)

    def transcribe_chunk(self, audio_array) -> dict:
        """
        Transcribe an audio chunk and return token-level confidence.
        
        Returns:
        {
            "text": str,              # ASR text
            "asr_confidence": float   # avg token confidence
        }
        """
        try:
            # Tokenize audio
            inputs = self.processor(audio_array, sampling_rate=TARGET_SR, return_tensors="pt", padding=True)

            # Forward pass to get logits
            with torch.no_grad():
                logits = self.model(inputs.input_values.to(DEVICE)).logits
            # --- 1. Decode Text ---
            pred_ids = torch.argmax(logits, dim=-1)
            asr_text = self.processor.batch_decode(pred_ids)[0]

            # --- 2. Calculate Entropy ---
            # Convert logits to probabilities (0.0 to 1.0)
            probs = F.softmax(logits, dim=-1)
            
            # Formula: -sum(p * log(p))
            # We add 1e-9 to prevent log(0) which results in -inf or NaN
            log_probs = torch.log(probs + 1e-9)
            entropy = -torch.sum(probs * log_probs, dim=-1)
            
            # Entropy is currently a list of values (one per time step). 
            # We take the mean to get a single score for the chunk.
            avg_entropy = float(entropy.mean().cpu())

            return asr_text,avg_entropy

        except Exception as e:
            logger.error(f"ASR chunk transcription failed: {e}")
            return  "",  10.0
