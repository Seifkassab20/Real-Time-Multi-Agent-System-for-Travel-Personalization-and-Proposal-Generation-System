import logging
import os
import sys
from typing import List

from ASR.new_src.asr_infrence import transcribe
from ASR.new_src.llm_engine import LLMEngine
from ASR.new_src.models import PipelineOutput, TranscriptionSegment

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
    def __init__(self):
        """
        Initialize the TranscriptionService.
        Loads the LLM correction engine.
        """
        try:
            logger.info("Initializing TranscriptionService...")
            self.correction_engine = LLMEngine()
            logger.info("TranscriptionService initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize TranscriptionService: {e}")
            raise

    def process_audio(self, audio_path: str) -> PipelineOutput:
        """
        Process an audio file: Transcribe -> Filter -> Correct.
        
        Args:
            audio_path (str): Path to the audio file.
            
        Returns:
            PipelineOutput: Structured output containing raw text, corrected text, and segments.
        """
        if not os.path.exists(audio_path):
            error_msg = f"Audio file not found: {audio_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info(f"Processing audio file: {audio_path}")

        try:

            raw_text, chunk_results = transcribe(audio_path)
            logger.debug(f"Raw transcription completed. Length: {len(raw_text)}")
            
            segments: List[TranscriptionSegment] = []
            corrected_text_parts: List[str] = []

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
                segments.append(segment)
                
                if corrected_text:
                    corrected_text_parts.append(corrected_text)

            full_corrected_text = " ".join(corrected_text_parts)

            output = PipelineOutput(
                full_raw_text=raw_text,
                full_corrected_text=full_corrected_text,
                segments=segments,
                metadata={
                    "audio_path": audio_path,
                    "chunk_count": len(chunk_results)
                }
            )
            
            logger.info("Audio processing completed successfully.")
            return output

        except Exception as e:
            logger.error(f"Error processing audio {audio_path}: {e}")
            raise

if __name__ == "__main__":

    default_path = "/Users/maryamsaad/Downloads/New Recording 2.mp3"
    
    file_path = default_path
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        
    if os.path.exists(file_path):
        try:
            service = TranscriptionService()
            result = service.process_audio(file_path)
            print("\n--- Final Corrected Output ---")
            print(result.full_corrected_text)
            print("------------------------------")
        except Exception as e:
            print(f"An error occurred: {e}")
    else:
        print(f"File not found for testing: {file_path}")