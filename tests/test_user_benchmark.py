import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import pytest
from app.config import settings
settings.MOCK_LLM = 1

from app.models import Meeting, Segment, Participant, Claim, ClaimType, Status
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.pipeline import run_verification_pipeline
from app.claims.from_summary import extract_claims_from_summary

BENCHMARK_DATA = [
    {
        "meeting_id": "MTG_001",
        "title": "Project Planning",
        "participants": ["Alice", "Bob", "Carol"],
        "segments": [
            {"idx": 0, "speaker": "Alice", "time": "10:02", "text": "Let's decide on the backend framework today."},
            {"idx": 1, "speaker": "Alice", "time": "10:04", "text": "I think FastAPI would be a good choice for the backend."},
            {"idx": 2, "speaker": "Bob", "time": "10:05", "text": "I agree. FastAPI should work well for what we're building."},
            {"idx": 3, "speaker": "Carol", "time": "10:07", "text": "For the database, I think we should keep everything local."},
            {"idx": 4, "speaker": "Alice", "time": "10:08", "text": "Yes, let's use SQLite for the local database."},
            {"idx": 5, "speaker": "Alice", "time": "10:11", "text": "Bob, can you investigate whether FAISS will work for our semantic search?"},
            {"idx": 6, "speaker": "Bob", "time": "10:12", "text": "Sure, I'll look into it."},
            {"idx": 7, "speaker": "Carol", "time": "10:15", "text": "Should we also build a mobile application?"},
            {"idx": 8, "speaker": "Alice", "time": "10:16", "text": "Maybe, but I don't think we should decide that today."},
            {"idx": 9, "speaker": "Bob", "time": "10:19", "text": "We should definitely have real-time notifications."},
            {"idx": 10, "speaker": "Alice", "time": "10:20", "text": "Let's leave that for a future version."}
        ],
        "claims": [
            {"text": "Use FastAPI as the backend framework.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Use SQLite as the local database.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Bob will investigate whether FAISS is suitable for semantic search.", "type": ClaimType.COMMITMENT, "actor": "Bob", "action": "investigate", "object": "FAISS", "expected": Status.VERIFIED},
            {"text": "Build a mobile application.", "type": ClaimType.DECISION, "expected": Status.AMBIGUOUS},
            {"text": "Real-time notifications are required now.", "type": ClaimType.REQUIREMENT, "expected": Status.UNSUPPORTED}
        ]
    },
    {
        "meeting_id": "MTG_002",
        "title": "Backend Architecture",
        "participants": ["Alice", "Bob", "Carol", "David"],
        "segments": [
            {"idx": 0, "speaker": "Alice", "time": "14:01", "text": "Let's finalize the backend architecture."},
            {"idx": 1, "speaker": "Bob", "time": "14:03", "text": "I think we should continue with FastAPI."},
            {"idx": 2, "speaker": "Alice", "time": "14:04", "text": "Agreed. FastAPI stays."},
            {"idx": 3, "speaker": "Carol", "time": "14:06", "text": "For embeddings we should use SentenceTransformers."},
            {"idx": 4, "speaker": "David", "time": "14:07", "text": "And all-MiniLM-L6-v2 would be a good model."},
            {"idx": 5, "speaker": "Alice", "time": "14:08", "text": "Okay, let's use all-MiniLM-L6-v2."},
            {"idx": 6, "speaker": "Alice", "time": "14:11", "text": "Bob, can you integrate the embedding pipeline?"},
            {"idx": 7, "speaker": "Bob", "time": "14:12", "text": "Yes, I'll take care of the embedding pipeline."},
            {"idx": 8, "speaker": "David", "time": "14:15", "text": "Bob is also going to handle the database, right?"},
            {"idx": 9, "speaker": "Bob", "time": "14:16", "text": "No, I only agreed to handle the embedding pipeline."},
            {"idx": 10, "speaker": "Alice", "time": "14:17", "text": "Right. Nobody has been assigned the database yet."},
            {"idx": 11, "speaker": "Carol", "time": "14:20", "text": "Should we use Pinecone instead of a local vector store?"},
            {"idx": 12, "speaker": "Alice", "time": "14:21", "text": "We haven't decided that yet."}
        ],
        "claims": [
            {"text": "Continue using FastAPI.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Use SentenceTransformers for embeddings.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "Use all-MiniLM-L6-v2.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Bob will integrate the embedding pipeline.", "type": ClaimType.COMMITMENT, "actor": "Bob", "action": "integrate", "object": "embedding pipeline", "expected": Status.VERIFIED},
            {"text": "Bob will handle the database.", "type": ClaimType.COMMITMENT, "actor": "Bob", "action": "handle", "object": "database", "expected": Status.AMBIGUOUS},
            {"text": "Pinecone will be used.", "type": ClaimType.DECISION, "expected": Status.AMBIGUOUS}
        ]
    },
    {
        "meeting_id": "MTG_003",
        "title": "Security Review",
        "participants": ["Alice", "Bob", "Eve"],
        "segments": [
            {"idx": 0, "speaker": "Eve", "time": "11:01", "text": "We need to finalize how authentication tokens are stored."},
            {"idx": 1, "speaker": "Eve", "time": "11:03", "text": "Authentication tokens must never be stored in plaintext."},
            {"idx": 2, "speaker": "Alice", "time": "11:04", "text": "Agreed. Tokens need secure server-side storage."},
            {"idx": 3, "speaker": "Bob", "time": "11:07", "text": "Should we use Redis for session storage?"},
            {"idx": 4, "speaker": "Eve", "time": "11:08", "text": "Redis could work, but I want to review the security configuration first."},
            {"idx": 5, "speaker": "Alice", "time": "11:11", "text": "Administrators must use multi-factor authentication."},
            {"idx": 6, "speaker": "Eve", "time": "11:12", "text": "Yes, MFA for administrators is mandatory."},
            {"idx": 7, "speaker": "Bob", "time": "11:15", "text": "I'll investigate the Redis security configuration."},
            {"idx": 8, "speaker": "Eve", "time": "11:18", "text": "We should encrypt every field in the database."},
            {"idx": 9, "speaker": "Alice", "time": "11:19", "text": "I'm not sure we need that for every field. Let's decide which fields actually require encryption."},
            {"idx": 10, "speaker": "Bob", "time": "11:23", "text": "We need a penetration test before production."},
            {"idx": 11, "speaker": "Alice", "time": "11:24", "text": "Agreed. A security assessment is required before production."}
        ],
        "claims": [
            {"text": "Authentication tokens must not be stored in plaintext.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "Tokens need secure server-side storage.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "Redis is the selected session store.", "type": ClaimType.DECISION, "expected": Status.AMBIGUOUS},
            {"text": "Administrators must use multi-factor authentication.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "Bob will investigate the Redis security configuration.", "type": ClaimType.COMMITMENT, "actor": "Bob", "action": "investigate", "object": "Redis security configuration", "expected": Status.VERIFIED},
            {"text": "Every database field must be encrypted.", "type": ClaimType.REQUIREMENT, "expected": Status.AMBIGUOUS},
            {"text": "A security assessment is required before production.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED}
        ]
    },
    {
        "meeting_id": "MTG_004",
        "title": "Client Requirements",
        "participants": ["Client", "Alice", "Bob"],
        "segments": [
            {"idx": 0, "speaker": "Client", "time": "15:01", "text": "The application must support card payments."},
            {"idx": 1, "speaker": "Alice", "time": "15:02", "text": "Okay, card payments will be part of the payment requirement."},
            {"idx": 2, "speaker": "Client", "time": "15:04", "text": "Three-D Secure authentication is mandatory."},
            {"idx": 3, "speaker": "Bob", "time": "15:05", "text": "We'll include 3DS support."},
            {"idx": 4, "speaker": "Client", "time": "15:08", "text": "We had a very bad experience with our previous payment vendor."},
            {"idx": 5, "speaker": "Client", "time": "15:09", "text": "Please don't mention that vendor in anything that goes outside this team."},
            {"idx": 6, "speaker": "Alice", "time": "15:11", "text": "Understood. External documentation only needs the technical payment requirements."},
            {"idx": 7, "speaker": "Bob", "time": "15:14", "text": "Should we support cryptocurrency payments too?"},
            {"idx": 8, "speaker": "Client", "time": "15:15", "text": "We haven't decided whether cryptocurrency is required."},
            {"idx": 9, "speaker": "Bob", "time": "15:18", "text": "I'll document the payment requirements."},
            {"idx": 10, "speaker": "Alice", "time": "15:20", "text": "The payment provider itself hasn't been finalized."}
        ],
        "claims": [
            {"text": "Card payments are required.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "3DS authentication is mandatory.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "The previous vendor should not be disclosed externally.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Previous vendor experience is a technical requirement.", "type": ClaimType.REQUIREMENT, "expected": Status.UNSUPPORTED},
            {"text": "Cryptocurrency payments are required.", "type": ClaimType.REQUIREMENT, "expected": Status.AMBIGUOUS},
            {"text": "Bob will document the payment requirements.", "type": ClaimType.COMMITMENT, "actor": "Bob", "action": "document", "object": "payment requirements", "expected": Status.VERIFIED},
            {"text": "The payment provider is finalized.", "type": ClaimType.DECISION, "expected": Status.UNSUPPORTED}
        ]
    },
    {
        "meeting_id": "MTG_005",
        "title": "Final Architecture Review",
        "participants": ["Alice", "Bob", "Carol"],
        "segments": [
            {"idx": 0, "speaker": "Alice", "time": "09:01", "text": "Let's review the architecture decisions from the previous meetings."},
            {"idx": 1, "speaker": "Bob", "time": "09:03", "text": "We're keeping FastAPI as the backend framework."},
            {"idx": 2, "speaker": "Alice", "time": "09:04", "text": "Agreed."},
            {"idx": 3, "speaker": "Carol", "time": "09:07", "text": "FAISS is still our vector store for the local prototype."},
            {"idx": 4, "speaker": "Alice", "time": "09:08", "text": "Yes, keep FAISS for the prototype."},
            {"idx": 5, "speaker": "Bob", "time": "09:11", "text": "For production, we might move to another vector database."},
            {"idx": 6, "speaker": "Alice", "time": "09:12", "text": "Nothing is decided for production yet."},
            {"idx": 7, "speaker": "Carol", "time": "09:15", "text": "The administrator MFA requirement from the security meeting still applies."},
            {"idx": 8, "speaker": "Alice", "time": "09:16", "text": "Yes, MFA remains mandatory."},
            {"idx": 9, "speaker": "Bob", "time": "09:19", "text": "Should we add biometric authentication?"},
            {"idx": 10, "speaker": "Alice", "time": "09:20", "text": "Let's leave that for a future version."},
            {"idx": 11, "speaker": "Bob", "time": "09:23", "text": "I'll prepare the final architecture document."},
            {"idx": 12, "speaker": "Carol", "time": "09:25", "text": "We should deploy the system to AWS next week."},
            {"idx": 13, "speaker": "Alice", "time": "09:26", "text": "Deployment infrastructure hasn't been approved yet."}
        ],
        "claims": [
            {"text": "Keep FastAPI as the backend framework.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Keep FAISS for the local prototype.", "type": ClaimType.DECISION, "expected": Status.VERIFIED},
            {"text": "Production vector database is selected.", "type": ClaimType.DECISION, "expected": Status.AMBIGUOUS},
            {"text": "Administrator MFA remains mandatory.", "type": ClaimType.REQUIREMENT, "expected": Status.VERIFIED},
            {"text": "Biometric authentication is required.", "type": ClaimType.REQUIREMENT, "expected": Status.AMBIGUOUS},
            {"text": "Bob will prepare the final architecture document.", "type": ClaimType.COMMITMENT, "actor": "Bob", "action": "prepare", "object": "final architecture document", "expected": Status.VERIFIED},
            {"text": "AWS deployment next week is approved.", "type": ClaimType.DECISION, "expected": Status.UNSUPPORTED}
        ]
    }
]

def test_user_benchmark_suite():
    total_claims = 0
    passed_claims = 0
    results_table = []

    for m_data in BENCHMARK_DATA:
        meeting = Meeting(
            meeting_id=m_data["meeting_id"],
            title=m_data["title"],
            participants=[Participant(name=p, has_authority=True) for p in m_data["participants"]],
            segments=[Segment(**s) for s in m_data["segments"]]
        )
        load_meeting_to_db(meeting, source="benchmark")
        index_meeting(meeting.meeting_id)

        for c_idx, c_info in enumerate(m_data["claims"]):
            claim = Claim(
                claim_id=f"{m_data['meeting_id']}_c{c_idx+1}",
                meeting_id=m_data["meeting_id"],
                text=c_info["text"],
                source="SUMMARY",
                type=c_info["type"],
                actor=c_info.get("actor"),
                action=c_info.get("action"),
                object=c_info.get("object"),
                normalized=c_info["text"]
            )
            v = run_verification_pipeline(claim)
            actual = v.status
            expected = c_info["expected"]
            is_pass = (actual == expected)
            total_claims += 1
            if is_pass:
                passed_claims += 1
            
            results_table.append({
                "meeting": m_data["meeting_id"],
                "claim": claim.text,
                "type": claim.type.value,
                "expected": expected.value,
                "actual": actual.value,
                "pass": is_pass,
                "reasons": [r.value for r in v.reasons],
                "explanation": v.explanation,
                "evidence": [(e.idx, e.speaker, e.stance.value, e.relation) for e in v.evidence_chain]
            })

    print(f"\nBenchmark Results: {passed_claims}/{total_claims} ({passed_claims/total_claims*100:.1f}%) Passed")
    for r in results_table:
        status_sym = "[PASS]" if r["pass"] else "[FAIL]"
        print(f"{status_sym} [{r['meeting']}] {r['claim']:<45} | Exp: {r['expected']:<11} | Act: {r['actual']:<11} | Reasons: {r['reasons']}")
        if not r["pass"]:
            print(f"   -> Evidence: {r['evidence']}")
            print(f"   -> Explanation: {r['explanation']}")

    with open("data/outputs/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results_table, f, indent=2)

    assert passed_claims == total_claims

if __name__ == "__main__":
    test_user_benchmark_suite()
