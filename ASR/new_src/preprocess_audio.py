
import numpy as np
import torchaudio
import torch
from dotenv import load_dotenv
import os
load_dotenv()

class audio_utils:
    def __init__(self) -> None:
        self.max_duration_sec=float(os.getenv("CHUNK_LENGTH"))

    def preprocess_audio(self, audio_path: str) -> np.ndarray:
  
        print(f"[audio] Loading: {audio_path}")
        # Step 1: Load
        waveform, sr = torchaudio.load(audio_path)
        print(f"[audio] Loaded: {waveform.shape}, sr={sr}Hz")

        # Step 2: Convert to mono
        if waveform.ndim > 1 and waveform.shape[0] > 1:
            print("[audio] Converting to mono...")
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        # Step 3: Resample to 16 kHz (strict requirement per paper)
        if sr != 16000:
            print(f"[audio] Resampling {sr}Hz → 16000Hz...")
            resampler = torchaudio.transforms.Resample(sr, 16000)
            waveform = resampler(waveform)
            sr = 16000

        # Step 4: Check duration (enforce one-shot, no chunking)
        duration_sec = waveform.shape[-1] / sr
        print(f"[audio] Duration: {duration_sec:.2f}s (max: {self.max_duration_sec}s)")

        # Removed the ValueError to allow chunking of long audio

        # Step 5: Normalize amplitude
        print("[audio] Normalizing amplitude...")
        waveform = waveform.squeeze(0)  # Remove channel dim
        waveform = waveform / (waveform.abs().max() + 1e-8)  # Avoid division by zero

        print(f"[audio] ✓ Preprocessed: shape={waveform.shape}, range=[{waveform.min():.3f}, {waveform.max():.3f}]")

        return waveform.numpy()

    def chunk_audio(self, waveform: torch.Tensor, sr: int = 16000, overlap_sec: float = 2.0):

        samples_per_chunk = int(self.max_duration_sec * sr)
        overlap_samples = int(overlap_sec * sr)
        step = samples_per_chunk - overlap_samples
        
        if step <= 0:
            step = samples_per_chunk

        total_samples = waveform.shape[-1]
        
        chunks = []
        for start in range(0, total_samples, step):
            end = min(start + samples_per_chunk, total_samples)
            chunk = waveform[start:end]
            chunks.append(chunk.numpy())
            
            if end == total_samples:
                break
        
        return chunks
