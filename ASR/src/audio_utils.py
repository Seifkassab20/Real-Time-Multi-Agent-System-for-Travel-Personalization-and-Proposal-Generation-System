import soundfile as sf
import librosa
import numpy as np
from typing import Generator
import torch
import torchaudio.transforms as T
from dotenv import load_dotenv
import os
load_dotenv()

OVERLAP=float(os.getenv('OVERLAP'))
CHUNK_LENGTH=float(os.getenv('CHUNK_LENGTH'))
TARGET_SR= int(os.getenv('TARGET_SR'))

def audio_chunk_generator(file_path: str) -> Generator[np.ndarray, None, None]:
    """
    generates audio chanks with the chunk length and overlap stated in enviroment variables
    """
    info = sf.info(file_path)
    source_sr = info.samplerate
    chunk_samples = int(CHUNK_LENGTH * source_sr)
    overlap_samples = int(OVERLAP * source_sr)
    # 20*16k = 320k and 2*16k=32k       320k-32k=288k datapoints at each chunk (hop samples)
    hop_samples = chunk_samples - overlap_samples
    
    buffer = np.array([], dtype='float32')
    
    with sf.SoundFile(file_path) as f:
        data = f.read(frames=chunk_samples, dtype='float32')
        buffer = data
        print(buffer)
        resampler = T.Resample(source_sr, TARGET_SR, dtype=torch.float32)
        while len(buffer) > 0:
            # Process current buffer
            to_process = buffer
            # Stereo -> Mono (Hubert uses mono)
            if len(to_process.shape) > 1:
                to_process = to_process.mean(axis=1)
                
            # Resample if needed
            if source_sr != TARGET_SR:
                # Convert numpy -> torch tensor
                tensor_chunk = torch.from_numpy(to_process)
                # Resample
                resampled_tensor = resampler(tensor_chunk)
                # Convert back to numpy
                to_process = resampled_tensor.numpy()
            yield to_process

            if len(buffer) < chunk_samples:
                break 
            # Prepare next buffer (Overlap + New Data)
            overlap_data = buffer[-overlap_samples:]
            new_data = f.read(frames=hop_samples, dtype='float32')
            
            if len(new_data) == 0:
                break
                
            buffer = np.concatenate((overlap_data, new_data))