import logging
import os
import sys
import time
from typing import List
from backend.core.ASR.src.asr_infrence import transcribe
from backend.core.ASR.src.llm_engine import LLMEngine
from backend.core.ASR.src.models import PipelineOutput, TranscriptionSegment
from backend.core.ASR.src.preprocess_audio import audio_utils
from backend.core.tracing_config import get_metadata
from langsmith import traceable

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ASR_Pipeline")

class TranscriptionService:
    """
    Service for handling audio transcription and post-correction.
    Designed to be used as a component in a larger real-time system.
    """
    @traceable(run_type="tool", name="transcription_service_initialization")
    def __init__(self):
        initialization_start_time = time.time()
        try:
            logger.info("Initializing TranscriptionService...")
            
            # Collect environment variables for tracing
            env_vars = {
                "DEVICE": os.getenv("DEVICE", "cpu"),
                "MODEL_NAME": os.getenv("MODEL_NAME", "default"),
                "CORRECTION_MODEL": os.getenv("CORRECTION_MODEL", "default"),
                "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                "CHUNK_LENGTH": os.getenv("CHUNK_LENGTH", "20.0"),
                "OVERLAP": os.getenv("OVERLAP", "2.0")
            }
            
            self.correction_engine = LLMEngine()
            initialization_time = time.time() - initialization_start_time
            initialization_metadata = get_metadata(
                "transcription_service_init",
                environment_variables=env_vars,
                correction_engine_initialized=True,
                initialization_time_seconds=round(initialization_time, 3),
                initialization_timestamp=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                service_status="initialized_successfully"
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

    @traceable(run_type="chain", name="asr_pipeline")
    def process_audio(self, audio_path: str) -> PipelineOutput:
        processing_start_time = time.time()
        processing_start_iso = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(processing_start_time))
        
        # Get file size
        file_size_bytes = os.path.getsize(audio_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        logger.info(f"Audio file: {audio_path}, Size: {file_size_mb:.2f} MB")

        try:
            audio_processor = audio_utils()
            waveform = audio_processor.preprocess_audio(audio_path)
            duration_seconds = len(waveform) / 16000  
        except Exception as e:
            logger.warning(f"Could not calculate audio duration: {e}")
            duration_seconds = None

        logger.info(f"Processing audio file: {audio_path}")

        try:
            pipeline_metadata = get_metadata(
                "asr_pipeline",
                audio_file=audio_path,
                file_size_mb=round(file_size_mb, 2),
                duration_seconds=round(duration_seconds, 2) if duration_seconds else None,
                processing_start_time=processing_start_iso,
                target_language="arb"  # Default target language
            )
            
            logger.info(f"Pipeline tracing metadata: {pipeline_metadata}")

            raw_text, chunk_results = transcribe(audio_path)
            logger.debug(f"Raw transcription completed. Length: {len(raw_text)}")
            
            chunk_count = len(chunk_results) if chunk_results else 0
            
            segments: List[TranscriptionSegment] = []
            corrected_text_parts: List[str] = []
            corrected_segments=[]
            # 2. Process chunks
            for i, chunk in enumerate(chunk_results):
                text = chunk.get('text', '').strip()
                confidence = chunk.get('avg_confidence', 0.0)

                if confidence <= 0.3:
                    logger.warning(f"Chunk {i} skipped due to low confidence: {confidence:.2f}")
                    continue
                
                if not text:
                    continue

                try:
                    correction_result = self.correction_engine.correct_text(text, confidence)
                    corrected_text = correction_result.get('corrected_text', '')
                    needs_review = correction_result.get('requires_confirmation', False)
                except Exception as e:
                    logger.error(f"Error during LLM correction for chunk {i}: {e}")
                    corrected_text = text
                    needs_review = True

                # Create segment
                segment = TranscriptionSegment(
                    raw_text=text,
                    corrected_text=corrected_text,
                    confidence=confidence,
                    needs_review=needs_review
                )
                print('SEGMENT ', segment)
                
                if corrected_text:
                    corrected_segments.append(segment)



            processing_end_time = time.time()
            processing_duration = processing_end_time - processing_start_time

            output = PipelineOutput(
                full_raw_text=raw_text,
                full_corrected_text=" ".join([segment.corrected_text for segment in corrected_segments]),
                segments=corrected_segments,
                metadata={
                    "audio_path": audio_path,
                    "chunk_count": chunk_count,
                    "duration_seconds": duration_seconds,
                    "processing_duration": round(processing_duration, 2),
                    "file_size_mb": round(file_size_mb, 2)
                }
            )
            
            logger.info("Audio processing completed successfully.")
            return corrected_segments

        except FileNotFoundError as e:
            error_metadata = get_metadata(
                "file_error",
                error_type="FileNotFoundError",
                file_path=audio_path,
                error_message=str(e)
            )
            logger.error(f"File not found error with metadata: {error_metadata}")
            raise
        except Exception as e:
            error_metadata = get_metadata(
                "pipeline_error",
                error_type=type(e).__name__,
                file_path=audio_path,
                error_message=str(e),
                recovery_action="Pipeline execution terminated"
            )
            logger.error(f"Pipeline error with metadata: {error_metadata}")
            raise
