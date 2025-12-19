
import numpy as np
import torchaudio
import torch
from dotenv import load_dotenv
import os
from langsmith import traceable
from backend.core.tracing_config import get_metadata
load_dotenv()

class audio_utils:
    def __init__(self) -> None:
        self.max_duration_sec=float(os.getenv("CHUNK_LENGTH"))

    def preprocess_audio(self, audio_path: str) -> np.ndarray:
  
        print(f"[audio] Loading: {audio_path}")
        waveform, sr = torchaudio.load(audio_path)
        print(f"[audio] Loaded: {waveform.shape}, sr={sr}Hz")
        if waveform.ndim > 1 and waveform.shape[0] > 1:
            print("[audio] Converting to mono...")
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        if sr != 16000:
            print(f"[audio] Resampling {sr}Hz → 16000Hz...")
            resampler = torchaudio.transforms.Resample(sr, 16000)
            waveform = resampler(waveform)
            sr = 16000

        duration_sec = waveform.shape[-1] / sr
        print(f"[audio] Duration: {duration_sec:.2f}s (max: {self.max_duration_sec}s)")
        print("[audio] Normalizing amplitude...")
        waveform = waveform.squeeze(0)
        waveform = waveform / (waveform.abs().max() + 1e-8)
        print(f"[audio] ✓ Preprocessed: shape={waveform.shape}, range=[{waveform.min():.3f}, {waveform.max():.3f}]")
        return waveform.numpy()

    @traceable(run_type="tool", name="audio_chunking")
    def chunk_audio(self, waveform: torch.Tensor, sr: int = 16000, overlap_sec: float = 2.0):
        """
        Chunk audio waveform into overlapping segments.
        
        Args:
            waveform: Input audio waveform tensor
            sr: Sample rate (default: 16000)
            overlap_sec: Overlap duration in seconds (default: 2.0)
            
        Returns:
            List of audio chunks as numpy arrays
        """
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
        
        # Calculate metadata for tracing
        chunk_count = len(chunks)
        chunk_duration_sec = self.max_duration_sec
        total_duration_sec = total_samples / sr
        
        # Add tracing metadata if tracing is enabled

        metadata = get_metadata(
                component="audio_chunking",
                chunk_count=chunk_count,
                chunk_duration_sec=chunk_duration_sec,
                overlap_sec=overlap_sec,
                total_duration_sec=total_duration_sec,
                sample_rate=sr,
                samples_per_chunk=samples_per_chunk,
                overlap_samples=overlap_samples,
                step_size=step
            )

        
        return chunks
