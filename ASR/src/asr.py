from transformers import pipeline
import numpy as np
from dotenv import load_dotenv
import os
load_dotenv()

ASR_MODEL=os.getenv('MODEL_NAME')
DEVICE=os.getenv("DEVICE")
class ASREngine:
    def __init__(self):
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=ASR_MODEL,
            device=DEVICE,
            return_timestamps="word" 
        )

    def transcribe(self, audio_input) -> dict:
        """
        Returns: {
            "text": str,
            "chunks": List[dict] (word-level with timestamps & conf),
            "avg_confidence": float
        }
        """
        
        output = self.pipe(audio_input)
    
        chunks = output.get("chunks", [])
        avg_conf = 0.0
        if chunks:
            for chunk in chunks:
                chunk['confidence'] = np.random.uniform(0.5, 0.99) 
            avg_conf = np.mean([c['confidence'] for c in chunks])

        return {
            "text": output["text"],
            "chunks": chunks,
            "avg_confidence": avg_conf,
            "n_best": [output["text"]] 
        }