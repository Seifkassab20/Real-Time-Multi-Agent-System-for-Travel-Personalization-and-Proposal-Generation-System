from transformers import pipeline
import logging
from dotenv import load_dotenv
import os
load_dotenv()

ASR_MODEL=os.getenv('MODEL_NAME')
DEVICE=os.getenv("DEVICE")
TARGET_SR=int(os.getenv("TARGET_SR"))
logger = logging.getLogger('metrics')

class ASREngine:
    def __init__(self):
        logger.info(f"Loading ASR model: {ASR_MODEL} on {DEVICE}")
        self.pipe = pipeline(
            "automatic-speech-recognition", 
            model=ASR_MODEL ,
            device=DEVICE
        )

    def transcribe_chunk(self, audio_array) -> dict:
        """
        Returns dict with 'text' and optional metadata.
        """
        try:
            # HF pipelines accept dicts for raw audio
            payload = {
                "raw": audio_array,
                "sampling_rate": TARGET_SR
            }
            # Enable return_timestamps="word" if model supports it for better granularity
            output = self.pipe(payload)
            text = output.get("text", "") if isinstance(output, dict) else str(output)
            return {"text": text, "confidence":1.0} # Placeholder confidence
        except Exception as e:
            logger.error(f"ASR Error: {e}")
            return {"text": "", "confidence": 0.0}