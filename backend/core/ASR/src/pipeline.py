import logging
import os
import sys
import time
from typing import List
from backend.core.ASR.src.asr_infrence import transcribe
from backend.core.ASR.src.llm_engine import LLMEngine
from backend.core.ASR.src.models import PipelineOutput, TranscriptionSegment
from backend.core.tracing_config import setup_tracing, get_trace_metadata, is_tracing_enabled, trace_file_operation, trace_cleanup_operation
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
        """
        Initialize the TranscriptionService.
        Loads the LLM correction engine and sets up tracing.
        """
        initialization_start_time = time.time()
        
        try:
            logger.info("Initializing TranscriptionService...")
            
            # Collect environment variables for tracing
            env_vars = {
                "LANGSMITH_TRACING_V2": os.getenv("LANGSMITH_TRACING_V2", "false"),
                "LANGSMITH_PROJECT": os.getenv("LANGSMITH_PROJECT", "asr-pipeline-tracing"),
                "LANGSMITH_API_KEY": "***" if os.getenv("LANGSMITH_API_KEY") else None,
                "DEVICE": os.getenv("DEVICE", "cpu"),
                "MODEL_NAME": os.getenv("MODEL_NAME", "default"),
                "CORRECTION_MODEL": os.getenv("CORRECTION_MODEL", "default"),
                "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                "CHUNK_LENGTH": os.getenv("CHUNK_LENGTH", "20.0"),
                "OVERLAP": os.getenv("OVERLAP", "2.0")
            }
            
            # Set up tracing infrastructure
            tracing_setup_success = setup_tracing()
            if tracing_setup_success:
                logger.info("LangSmith tracing configured successfully")
            else:
                logger.info("LangSmith tracing not configured - continuing without tracing")
            
            # Initialize LLM correction engine
            self.correction_engine = LLMEngine()
            
            # Calculate initialization time
            initialization_time = time.time() - initialization_start_time
            
            # Add comprehensive initialization metadata for tracing
            initialization_metadata = get_trace_metadata(
                "transcription_service_init",
                environment_variables=env_vars,
                tracing_setup_successful=tracing_setup_success,
                correction_engine_initialized=True,
                initialization_time_seconds=round(initialization_time, 3),
                initialization_timestamp=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                service_status="initialized_successfully"
            )
            
            if is_tracing_enabled():
                logger.info(f"TranscriptionService initialization metadata: {initialization_metadata}")
            
            logger.info("TranscriptionService initialized successfully.")
            
        except Exception as e:
            initialization_time = time.time() - initialization_start_time
            
            # Trace initialization failure
            error_metadata = get_trace_metadata(
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
        """
        Process an audio file: Transcribe -> Filter -> Correct.
        
        Args:
            audio_path (str): Path to the audio file.
            
        Returns:
            PipelineOutput: Structured output containing raw text, corrected text, and segments.
        """
        # Get processing start time and file metadata for tracing
        processing_start_time = time.time()
        processing_start_iso = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(processing_start_time))
        
        # Trace file existence check and get comprehensive metadata
        file_operation_result = trace_file_operation(
            audio_path, 
            "audio_file_validation",
            expected_file_type="audio",
            processing_context="asr_pipeline"
        )
        
        if not file_operation_result["file_exists"]:
            error_msg = f"Audio file not found: {audio_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Extract file metadata from tracing result
        file_size_bytes = file_operation_result["file_size_bytes"]
        file_size_mb = file_operation_result["file_size_mb"]
        
        # Log file operation metadata if tracing is enabled
        if is_tracing_enabled():
            logger.info(f"File operation metadata: {file_operation_result}")

        # Calculate audio duration by preprocessing the audio
        try:
            from ASR.src.preprocess_audio import audio_utils
            audio_processor = audio_utils()
            waveform = audio_processor.preprocess_audio(audio_path)
            duration_seconds = len(waveform) / 16000  # Sample rate is 16kHz after preprocessing
        except Exception as e:
            logger.warning(f"Could not calculate audio duration: {e}")
            duration_seconds = None

        logger.info(f"Processing audio file: {audio_path}")

        try:
            # Add comprehensive pipeline metadata for tracing
            pipeline_metadata = get_trace_metadata(
                "asr_pipeline",
                audio_file=audio_path,
                file_size_mb=round(file_size_mb, 2),
                duration_seconds=round(duration_seconds, 2) if duration_seconds else None,
                processing_start_time=processing_start_iso,
                target_language="arb"  # Default target language
            )
            
            # Log metadata if tracing is enabled
            if is_tracing_enabled():
                logger.info(f"Pipeline tracing metadata: {pipeline_metadata}")

            raw_text, chunk_results = transcribe(audio_path)
            logger.debug(f"Raw transcription completed. Length: {len(raw_text)}")
            
            # Update chunk count in metadata now that we have the results
            chunk_count = len(chunk_results) if chunk_results else 0
            
            segments: List[TranscriptionSegment] = []
            corrected_text_parts: List[str] = []
            corrected_segments=[]
            # 2. Process chunks
            for i, chunk in enumerate(chunk_results):
                text = chunk.get('text', '').strip()
                confidence = chunk.get('avg_confidence', 0.0)

                # Filter low confidence chunks
                if confidence <= 0.3:
                    logger.warning(f"Chunk {i} skipped due to low confidence: {confidence:.2f}")
                    continue
                
                if not text:
                    continue

                # 3. LLM Correction
                try:
                    correction_result = self.correction_engine.correct_text(text, confidence)
                    corrected_text = correction_result.get('corrected_text', '')
                    needs_review = correction_result.get('requires_confirmation', False)
                except Exception as e:
                    logger.error(f"Error during LLM correction for chunk {i}: {e}")
                    # Fallback to raw text if correction fails
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



            # Calculate processing duration
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
            
            # Perform final cleanup operations with tracing
            final_cleanup_result = trace_cleanup_operation(
                "general_memory",
                {
                    "cleanup_trigger": "pipeline_completion",
                    "processed_chunks": chunk_count,
                    "processing_duration": processing_duration
                },
                processing_context="asr_pipeline_completion"
            )
            
            if is_tracing_enabled():
                logger.info(f"Final cleanup metadata: {final_cleanup_result}")
            
            logger.info("Audio processing completed successfully.")
            return corrected_segments

        except FileNotFoundError as e:
            # Trace FileNotFoundError with file path details
            error_metadata = get_trace_metadata(
                "file_error",
                error_type="FileNotFoundError",
                file_path=audio_path,
                error_message=str(e)
            )
            logger.error(f"File not found error with metadata: {error_metadata}")
            raise
        except Exception as e:
            # Trace general exceptions with error context and recovery actions
            error_metadata = get_trace_metadata(
                "pipeline_error",
                error_type=type(e).__name__,
                file_path=audio_path,
                error_message=str(e),
                recovery_action="Pipeline execution terminated"
            )
            logger.error(f"Pipeline error with metadata: {error_metadata}")
            raise

