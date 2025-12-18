import logging
import sys
from backend.core.ASR.src.pipeline import TranscriptionService
from backend.core.ASR.src.tracing_config import setup_tracing, is_tracing_enabled
from langsmith import traceable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

@traceable(run_type="chain", name="asr_main")
def main():
    # Set up tracing at application startup
    setup_tracing()
    
    audio_file = '/Users/maryamsaad/Downloads/New Recording 2.mp3'
    
    service = TranscriptionService()
    
    try:
        result = service.process_audio(audio_file)
        
        print("\n--- Final Result ---")
        print(f"Raw: {result.full_raw_text[:100]}...")
        print(f"Corrected: {result.full_corrected_text[:100]}...")
        

        reviews = [s for s in result.segments if s.needs_review]
        if reviews:
            print(f"\nWARNING: {len(reviews)} segments need human review.")
            
    except FileNotFoundError:
        logging.error("Audio file not found.")
    except Exception as e:
        logging.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()