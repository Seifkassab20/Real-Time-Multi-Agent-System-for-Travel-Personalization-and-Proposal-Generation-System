import logging
import os
import sys
import time
from typing import List, Optional, Callable, AsyncGenerator
from backend.core.ASR.src.asr_infrence import transcribe, process_audio_chunk, ASR
from backend.core.ASR.src.llm_engine import LLMEngine
from backend.core.ASR.src.models import PipelineOutput, TranscriptionSegment
from backend.core.ASR.src.preprocess_audio import audio_utils
from backend.core.tracing_config import get_metadata
from langsmith import traceable
from backend.database.models.calls import Calls
from backend.database.repostries.calls_repo import calls_repository  
from backend.database.db import NeonDatabase
from datetime import datetime
import numpy as np
import torch
from collections import deque
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ASR_Pipeline")

class TranscriptionService:
    """
    Service for handling audio transcription and post-correction.
    Designed for real-time streaming audio processing.
    """
    @traceable(run_type="tool", name="transcription_service_initialization")
    def __init__(self, 
                 chunk_duration: float = 2.0,  # seconds
                 overlap_duration: float = 0.5,  # seconds
                 min_confidence: float = 0.3,
                 buffer_size: int = 10):
        initialization_start_time = time.time()
        try:
            logger.info("Initializing Real-Time TranscriptionService...")
            
            # Real-time processing parameters
            self.chunk_duration = chunk_duration
            self.overlap_duration = overlap_duration
            self.min_confidence = min_confidence
            self.sample_rate = 16000
            self.chunk_samples = int(chunk_duration * self.sample_rate)
            self.overlap_samples = int(overlap_duration * self.sample_rate)
            
            # Audio buffer for streaming
            self.audio_buffer = deque(maxlen=buffer_size * self.chunk_samples)
            self.is_processing = False
            
            # Collect environment variables for tracing
            env_vars = {
                "DEVICE": os.getenv("DEVICE", "cpu"),
                "MODEL_NAME": os.getenv("MODEL_NAME", "default"),
                "CORRECTION_MODEL": os.getenv("CORRECTION_MODEL", "default"),
                "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                "CHUNK_LENGTH": str(chunk_duration),
                "OVERLAP": str(overlap_duration),
                "REAL_TIME_MODE": "enabled"
            }
            
            self.correction_engine = LLMEngine()
            self.calls_repo = calls_repository()
            self.audio_processor = audio_utils()
            
            # Initialize call session
            self.current_call_id = None
            self.call_start_time = None
            self.processed_segments = []
            
            initialization_metadata = get_metadata(
                "transcription_service_init",
                environment_variables=env_vars,
                correction_engine_initialized=True,
                service_status="initialized_successfully",
                mode="real_time_streaming"
            )
            
            logger.info(f"TranscriptionService initialization metadata: {initialization_metadata}")
            logger.info("TranscriptionService initialized successfully.")
            
        except Exception as e:
            initialization_time = time.time() - initialization_start_time
            error_metadata = get_metadata(
                "transcription_service_init_error",
                environment_variables=env_vars,
                error_type=type(e).__name__,
                error_message=str(e),
                initialization_time_seconds=round(initialization_time, 3),
                service_status="initialization_failed"
            )
            
            logger.error(f"Failed to initialize TranscriptionService with metadata: {error_metadata}")
            raise

    @traceable(run_type="tool", name="add_call_record")
    async def add_call_record(self, call_data):
        """
        Adds a call record to the database.
        """
        async with NeonDatabase().get_session() as session:
            new_call = await self.calls_repo.create(session, Calls(**call_data))
        logger.info(f"New call record added with ID: {new_call.call_id}")
        return  new_call.call_id

    @traceable(run_type="tool", name="asr_streaming")
    async def stream_audio(self, audio_path: str, on_segment: Optional[Callable[[TranscriptionSegment], None]] = None) -> AsyncGenerator[tuple, None]:
        """
        Stream the audio file in real time by chunking and processing each chunk
        sequentially. Yields (TranscriptionSegment, call_id) for the first segment,
        then (TranscriptionSegment, None) for the rest.
        """
        started_at = datetime.utcnow()
        logger.info(f"Streaming audio file: {audio_path}")

        # Pre-create call record to get call_id
        call_id = await self.add_call_record({
            "call_context": [],
            "started_at": started_at,
            "ended_at": None,
        })

        utils = audio_utils()
        waveform = utils.preprocess_audio(audio_path)
        sr = 16000
        chunks = utils.chunk_audio(torch.tensor(waveform), sr=sr)

        device = torch.device(ASR.device)
        processed_segments: List[TranscriptionSegment] = []

        for i, chunk in enumerate(chunks, start=1):
            try:
                result = process_audio_chunk(
                    chunk=chunk,
                    chunk_index=i,
                    total_chunks=len(chunks),
                    sr=sr,
                    tgt_lang="arb",
                    device=device,
                )

                text = result.get("text", "").strip()
                confidence = result.get("avg_confidence", 0.0)
                if not text or confidence <= 0.3:
                    continue

                try:
                    correction = self.correction_engine.correct_text(text, confidence)
                    corrected_text = correction.get("corrected_text", text)
                    needs_review = correction.get("requires_confirmation", False)
                except Exception as llm_err:
                    logger.warning(f"LLM correction failed for chunk {i}: {llm_err}")
                    corrected_text = text
                    needs_review = True

                segment = TranscriptionSegment(
                    raw_text=text,
                    corrected_text=corrected_text,
                    confidence=confidence,
                    needs_review=needs_review,
                )

                processed_segments.append(segment)
                if on_segment:
                    try:
                        on_segment(segment)
                    except Exception as cb_err:
                        logger.warning(f"Segment callback error: {cb_err}")
                if i == 1:
                    yield segment, call_id
                else:
                    yield segment, None

            except Exception as e:
                logger.error(f"Streaming error on chunk {i}: {e}")
                continue

        # Persist session (update call record)
        ended_at = datetime.utcnow()
        try:
            await self.add_call_record({
                "call_context": [seg.__dict__ for seg in processed_segments],
                "started_at": started_at,
                "ended_at": ended_at,
            })
        except Exception as db_err:
            logger.warning(f"Failed to persist streaming session: {db_err}")