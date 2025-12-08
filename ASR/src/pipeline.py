import logging
import os
import time
from typing import List, Optional
from ASR.src.audio_utils import preprocess_and_stream
from ASR.src.asr_engine import SeamlessModel
from ASR.src.asr import ASREngine
from ASR.src.llm_engine import LLMEngine
from ASR.src.pii_guard import PIIGuard 
from ASR.src.security import SecurityManager
from ASR.src.models import PipelineOutput, TranscriptionSegment


logger = logging.getLogger('asr_pipeline')

class TranscriptionService:
    def __init__(self):
        """
        Initialize all processing engines.
        """
        logger.info("Initializing Transcription Service components...")
        self.asr = ASREngine()
        self.corrector = LLMEngine()
        self.security = SecurityManager()
        self.pii = PIIGuard()

    def process_file(self, file_path: str) -> PipelineOutput:
        """
        Orchestrates the ASR -> LLM -> Security pipeline for a given audio file.
        """
        logger.info(f"Starting processing for file: {file_path}")
        start_time = time.time()
        
        segments: List[TranscriptionSegment] = []
        raw_texts: List[str] = []
        corrected_texts: List[str] = []
        
        stream = preprocess_and_stream(file_path)
        
        for i, audio_chunk in enumerate(stream):
            try:

                raw_text, confidence = self.asr.transcribe_chunk(audio_chunk)
                
                if not raw_text.strip():
                    continue

                correction_result = self.corrector.correct_text(raw_text, confidence)
                corrected_text_str = correction_result.get('corrected_text', raw_text)
                needs_confirmation = correction_result.get('requires_confirmation', False)

                # PII Redaction & Encryption
                safe_text, encrypted_blob = self.security.detect_and_redact(corrected_text_str)

                # Confidence Policy Evaluation
                status = self.pii.evaluate_confidence(confidence)
                print(f"Evaluated status: {status}")
                
                if needs_confirmation:
                    status = "review"

                # 5. Build Segment
                segment = TranscriptionSegment(
                    raw_text=raw_text,
                    corrected_text=safe_text,
                    encrypted_data=encrypted_blob, 
                    confidence=confidence,
                    needs_review=(status == "review"),
                    start_time=None, 
                    end_time=None
                )
                
                segments.append(segment)
                raw_texts.append(raw_text)
                corrected_texts.append(safe_text)

            except Exception as e:
                logger.error(f"Error processing chunk {i}: {str(e)}", exc_info=True)
                continue

        total_duration = time.time() - start_time
        logger.info(f"Processing complete. Duration: {total_duration:.2f}s. Segments: {len(segments)}")

        return PipelineOutput(
            full_raw_text=" ".join(raw_texts),
            full_corrected_text=" ".join(corrected_texts),
            segments=segments,
            metadata={
                "duration": total_duration,
                "file_path": file_path,
                "total_chunks": len(segments)
            }
        )