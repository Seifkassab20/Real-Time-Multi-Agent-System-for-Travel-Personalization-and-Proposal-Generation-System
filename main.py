import asyncio
import uuid
from datetime import datetime, timezone
from backend.core.ASR.src.pipeline import TranscriptionService
from backend.core.extraction_agent.extraction_agent import ExtractionAgent
from backend.core.extraction_agent.models import TranscriptSegment, Agent_output
# from backend.core.profile_agent.profile_agent import ProfileAgent
# from backend.core.recommendation_engine.recommendation_orchestrator import (
#     build_user_profile_from_extraction,
#     merge_value,
#     MERGE_RULES,
#     recommend
# )

# ------------------------------------------------------------------
# Initialization
# ------------------------------------------------------------------

audio_path = "/Users/maryamsaad/Documents/ASR/trial.wav"

asr_service = TranscriptionService()
extraction_agent = ExtractionAgent()
# profile_agent = ProfileAgent()
final_profile = {}
recommendations = []

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def merge_extraction_into_profile(profile: dict, extraction: Agent_output):
    for field, rule in MERGE_RULES.items():
        profile[field] = merge_value(
            profile.get(field),
            getattr(extraction, field, None),
            rule
        )

# ------------------------------------------------------------------
# Main Orchestrator
# ------------------------------------------------------------------

async def main():
    segment_count = 0

    async for asr_segment, call_id in asr_service.stream_audio(audio_path):
        segment_count += 1

        print(f"\n{'='*60}")
        print(f"Processing Segment {segment_count}")
        print(f"{'='*60}")
        print(f"[ASR] {asr_segment.corrected_text}")

        # Build transcript segment
        transcript = TranscriptSegment(
            segment_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            speaker="customer",
            text=asr_segment.corrected_text
        )

        # Extract entities
        extraction_result, extraction_id = await extraction_agent.invoke(transcript, segment_count, call_id)
        
        print(f"[EXTRACTION ID] {extraction_id}")
        print(f"[EXTRACTION] {extraction_result}")

        # # Merge into accumulated profile
        # merge_extraction_into_profile(final_profile, extraction)

        # # Build user profile
        # user_profile = build_user_profile_from_extraction(final_profile)
        # print(f"\n[USER PROFILE]")
        # print(user_profile)

        # # Recommend
        # recommendation_result = recommend(user_profile)
        # recommendations.append(recommendation_result)

        # print(f"\n[RECOMMENDATION]")
        # print(recommendation_result)

        #User profile completion
        # questions = await profile_agent.invoke(call_id=call_id)
        # print(f"\n[PROFILE AGENT QUESTIONS]")
        # print(questions)

    print(f"\n{'='*60}")
    print("All segments processed!")
    print(f"{'='*60}")



if __name__ == "__main__":
    asyncio.run(main())
