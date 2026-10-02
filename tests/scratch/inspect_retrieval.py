import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import settings
settings.MOCK_LLM = 1

from app.models import Meeting, Segment, Participant, Claim, ClaimType
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.retrieval.hybrid import retrieve_candidates
from app.pipeline import run_verification_pipeline
from tests.test_user_benchmark import BENCHMARK_DATA

for m_data in BENCHMARK_DATA:
    meeting = Meeting(
        meeting_id=m_data['meeting_id'],
        title=m_data['title'],
        participants=[Participant(name=p, has_authority=True) for p in m_data['participants']],
        segments=[Segment(**s) for s in m_data['segments']]
    )
    load_meeting_to_db(meeting, source='benchmark')
    index_meeting(meeting.meeting_id)

    print(f"\n=================== {meeting.meeting_id} ===================")
    for c_info in m_data['claims']:
        claim = Claim(
            claim_id=f"{m_data['meeting_id']}_claim",
            meeting_id=m_data['meeting_id'],
            text=c_info['text'],
            source='SUMMARY',
            type=c_info['type'],
            actor=c_info.get('actor'),
            action=c_info.get('action'),
            object=c_info.get('object'),
            normalized=c_info['text']
        )
        cands = retrieve_candidates(meeting.meeting_id, claim)
        cand_indices = [c['idx'] for c in cands]
        v = run_verification_pipeline(claim)
        exp = c_info['expected'].value
        act = v.status.value
        is_ok = "PASS" if exp == act else "FAIL"
        print(f"[{is_ok}] Claim: {claim.text:<50} | Exp: {exp:<11} | Act: {act:<11} | Reasons: {[r.value for r in v.reasons]}")
        if is_ok == "FAIL":
            print(f"   -> Cands: {cand_indices}")
            print(f"   -> Ev: {[(e.idx, e.speaker, e.stance.value, e.relation) for e in v.evidence_chain]}")
            print(f"   -> Expl: {v.explanation}")
