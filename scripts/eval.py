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

EXPECTATIONS = {
    "mock_meeting_01_verified.json": "VERIFIED",
    "mock_meeting_02_ambiguous.json": "AMBIGUOUS",
    "mock_meeting_03_implicit.json": "VERIFIED",
    "mock_meeting_04_unsupported.json": "UNSUPPORTED",
    "mock_meeting_05_reversal.json": "AMBIGUOUS"
}

def run_eval():
    print("=" * 78)
    print("ReqCopilot Proof -- Acceptance Evaluation Suite")
    print("=" * 78)
    
    mock_dir = BASE_DIR / "data" / "mock"
    fixtures = sorted(mock_dir.glob("*.json"))
    
    adapter = MockAdapter()
    results = []

    for f_path in fixtures:
        fname = f_path.name
        expected = EXPECTATIONS.get(fname, "UNKNOWN")
        
        t0 = time.time()
        meeting = adapter.load(f_path)
        load_meeting_to_db(meeting, source="mock")
        index_meeting(meeting.meeting_id)
        
        claims = extract_claims_from_summary(meeting)
        if not claims:
            results.append((fname, expected, "NO_CLAIMS", "FAIL", "0.00s", []))
            continue

        c = claims[0]
        v = run_verification_pipeline(c)
        lat = time.time() - t0
        
        actual = v.status.value
        passed = (actual == expected)
        verdict = "PASS" if passed else "FAIL"
        
        results.append((fname, expected, actual, verdict, f"{lat:.2f}s", [r.value for r in v.reasons]))

    print(f"\n| {'Fixture':<32} | {'Expected':<12} | {'Actual':<12} | {'Status':<6} | {'Latency':<8} |")
    print(f"|{'-'*34}|{'-'*14}|{'-'*14}|{'-'*8}|{'-'*10}|")
    
    all_pass = True
    for fname, exp, act, verd, lat, reasons in results:
        if verd != "PASS":
            all_pass = False
        print(f"| {fname:<32} | {exp:<12} | {act:<12} | {verd:<6} | {lat:<8} |")

    print("=" * 78)
    if all_pass:
        print("ALL ACCEPTANCE FIXTURES PASSED!")
    else:
        print("SOME FIXTURES FAILED.")
    print("=" * 78)

if __name__ == "__main__":
    run_eval()
