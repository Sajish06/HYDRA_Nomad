import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.adapters.mock_adapter import MockAdapter
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.pipeline import run_verification_pipeline

def warm_cache():
    print(f"Warming LLM cache for ReqCopilot Proof (Model: {settings.OLLAMA_MODEL})...")
    mock_dir = BASE_DIR / "data" / "mock"
    fixtures = sorted(mock_dir.glob("*.json"))
    
    adapter = MockAdapter()
    total_claims = 0

    for f_path in fixtures:
        print(f"\nProcessing {f_path.name}...")
        t0 = time.time()
        meeting = adapter.load(f_path)
        load_meeting_to_db(meeting, source="mock")
        index_meeting(meeting.meeting_id)
        
        claims = extract_claims_from_summary(meeting)
        print(f"   Extracted {len(claims)} claim(s)")
        
        for c in claims:
            v = run_verification_pipeline(c)
            print(f"   Claim: \"{c.text}\" -> Status: {v.status.value} (Action: {v.gate_action})")
            total_claims += 1

        print(f"   Done in {time.time() - t0:.2f}s")

    print(f"\nCache warming complete! Processed {len(fixtures)} fixtures and {total_claims} claims.")

if __name__ == "__main__":
    warm_cache()
