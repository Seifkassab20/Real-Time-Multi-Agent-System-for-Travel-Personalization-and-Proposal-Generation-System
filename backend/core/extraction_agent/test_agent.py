"""
Test script for Extraction Agent
Tests extraction with sample transcripts and measures latency
"""
import asyncio
import json
import time
from datetime import datetime
from extraction_agent.agent import ExtractionAgent
from extraction_agent.models import TranscriptSegment

# Sample test transcripts
TEST_TRANSCRIPTS = [
    {
        "segment_id": "seg_001",
        "timestamp": datetime.now().isoformat(),
        "speaker": "customer",
        "text": "Hi, I'm planning a trip to Paris for next month. I have a budget of around $3000 and I'll be traveling with my wife."
    },
    {
        "segment_id": "seg_002",
        "timestamp": datetime.now().isoformat(),
        "speaker": "customer",
        "text": "We're interested in visiting museums, trying local cuisine, and maybe a day trip to Versailles. We prefer boutique hotels."
    },
    {
        "segment_id": "seg_003",
        "timestamp": datetime.now().isoformat(),
        "speaker": "customer",
        "text": "I'm a bit worried about the language barrier, but we're really excited about this trip!"
    },
    {
        "segment_id": "seg_004",
        "timestamp": datetime.now().isoformat(),
        "speaker": "customer",
        "text": "Can you help us find something for December 15th to 22nd? We're two adults, no kids."
    },
    {
        "segment_id": "seg_005",
        "timestamp": datetime.now().isoformat(),
        "speaker": "agent",
        "text": "Of course! Let me check availability for Paris in mid-December for two guests."
    }
]


async def test_extraction_agent():
    """Test the extraction agent with sample transcripts"""
    print("=" * 60)
    print("EXTRACTION AGENT TEST")
    print("=" * 60)
    
    agent = ExtractionAgent()
    
    results = []
    total_start = time.time()
    
    for i, transcript_data in enumerate(TEST_TRANSCRIPTS, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}/{len(TEST_TRANSCRIPTS)}")
        print(f"{'='*60}")
        
        # Create transcript segment
        segment = TranscriptSegment(**transcript_data)
        
        print(f"📝 Input:")
        print(f"   Segment ID: {segment.segment_id}")
        print(f"   Speaker: {segment.speaker}")
        print(f"   Text: {segment.text}")
        
        # Extract
        start = time.time()
        extraction = await agent._extract(segment)
        latency = (time.time() - start) * 1000
        
        print(f"\n⚡ Latency: {latency:.2f}ms")
        print(f"📊 Extracted Entities:")
        print(json.dumps(extraction.entities, indent=2))
        
        # Store results
        results.append({
            "segment_id": segment.segment_id,
            "speaker": segment.speaker,
            "text": segment.text,
            "entities": extraction.entities,
            "latency_ms": latency
        })
    
    total_time = (time.time() - total_start) * 1000
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total transcripts: {len(TEST_TRANSCRIPTS)}")
    print(f"Total time: {total_time:.2f}ms")
    print(f"Average latency: {total_time/len(TEST_TRANSCRIPTS):.2f}ms")
    
    latencies = [r["latency_ms"] for r in results]
    print(f"Min latency: {min(latencies):.2f}ms")
    print(f"Max latency: {max(latencies):.2f}ms")
    
    # Count extractions
    customer_segments = [r for r in results if r["speaker"] == "customer"]
    total_entities = sum(len(r["entities"]) for r in customer_segments)
    print(f"\nCustomer segments: {len(customer_segments)}")
    print(f"Total entity types extracted: {total_entities}")
    
    # Save results
    output_file = "test_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "test_timestamp": datetime.now().isoformat(),
            "total_transcripts": len(TEST_TRANSCRIPTS),
            "total_time_ms": total_time,
            "average_latency_ms": total_time/len(TEST_TRANSCRIPTS),
            "results": results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to {output_file}")


if __name__ == "__main__":
    asyncio.run(test_extraction_agent())
