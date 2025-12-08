import torch
import torchaudio
import numpy as np
from ASR.src.asr_engine import SeamlessModel
from dotenv import load_dotenv
import os
import torch
import torch.nn.functional as F
load_dotenv()
class ASREngine(SeamlessModel):
    def __init__(self, model_name: str = os.getenv("MODEL_NAME", "facebook/seamless-m4t-v2-large"), device= os.getenv("DEVICE") , cache_dir= os.getenv("cache_dir")):
        super().__init__(model_name, cache_dir)
        if device:
            self.device = device
            if self.model:
                self.model.to(self.device)

    
    def compute_confidence(self, scores):
        """
        Computes confidence as 1 - normalized entropy.
        scores: list of tensors or single tensor [seq_len x vocab_size] logits per decoding step
        """
        if scores is None:
            return 0.0
        if isinstance(scores, torch.Tensor):
            if scores.dim() == 0:
                return 0.0  # can't compute
            scores = [scores]
        try:
            entropies = []
            for step_logits in scores:  # each step: [batch, vocab]
                if step_logits.dim() == 0:
                    continue
                probs = F.softmax(step_logits, dim=-1)
                entropy = -(probs * probs.log()).sum(dim=-1)  # sum over vocab
                entropies.append(entropy)
            
            if not entropies:
                return 0.0
            entropies = torch.stack(entropies)  # [seq_len]
            avg_entropy = entropies.mean().item()
            
            # Optional: normalize to [0,1] assuming max entropy = log(vocab_size)
            vocab_size = scores[0].shape[-1]
            normalized_entropy = avg_entropy / np.log(vocab_size)
            confidence = 1.0 - normalized_entropy  # 1 = high confidence, 0 = low
            return confidence
        except Exception as e:
            print(f"[inference] Could not compute entropy: {e}")
            return 0.0


    def transcribe_chunk(self, audio_chunk: np.ndarray, tgt_lang: str = "arb") -> dict:
        """
        Transcribe a preprocessed audio chunk.
        
        Args:
            audio_chunk: Preprocessed audio chunk (16kHz, mono, normalized)
            tgt_lang: Target language code (e.g., 'ara', 'eng', 'fra')
            
        Returns:
            Dict with keys:
                - 'text': Transcribed text
                - 'language': Target language
                - 'duration_sec': Audio duration
                - 'confidence': Average confidence score
        """
        print(f"\n[inference] Starting transcription for chunk (lang={tgt_lang})...")

        # Duration calculation
        duration_sec = len(audio_chunk) / 16000

        # Prepare for inference
        print("[inference] Preparing inputs...")
        inputs = self.processor(
            audio=[audio_chunk],
            sampling_rate=16000,
            return_tensors="pt",
        )

        # Move to device
        device_obj = torch.device(self.device)
        inputs = inputs.to(device_obj)

        # One-shot inference
        print("[inference] Running model (one-shot)...")
        with torch.no_grad():
            output = self.model.generate(
                **inputs, 
                tgt_lang=tgt_lang,
                return_dict_in_generate=True,
                output_scores=True,
                max_new_tokens=256
            )

        # Handle output: could be dict-like or tuple
        if isinstance(output, tuple):
            sequences = output[0]
            scores = output[1] if len(output) > 1 else None
        else:
            sequences = output.sequences
            scores = getattr(output, 'scores', None)

        # Decode
        print(f"[inference] Sequences shape: {sequences.shape}")
        raw_text = self.processor.batch_decode( sequences, skip_special_tokens=True)[0]

        # Calculate confidence
        try:
            confidence = self.compute_confidence(scores)
        except Exception as e:
            print(f"[inference] Warning: Could not calculate confidence: {e}")
            confidence = 0.0

        print(f"[inference] ✓ Complete. Result length: {len(raw_text)} chars, Confidence: {confidence:.4f}")

        return raw_text, confidence 