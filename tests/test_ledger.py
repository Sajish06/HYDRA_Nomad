"""Tests for cryptographic tamper-evident audit ledger."""

import json
import uuid

import pytest

from backend.processors.ledger import AuditLedger
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


@pytest.fixture
def ledger_db():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


def test_ledger_append_and_verify_success(ledger_db):
    repo = Repository(ledger_db)
    mid = f"m_ledger_test_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "Ledger Test")
    t_hash = "abc123transcriptfingerprint"

    # Append 3 chronological events
    e0 = AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting.id,
        event_type="run_started",
        payload={"stage": "init", "user": "system"},
        transcript_sha256=t_hash,
    )
    e1 = AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting.id,
        event_type="verification_completed",
        payload={"status": "review_required", "claims_count": 5},
        transcript_sha256=t_hash,
    )
    e2 = AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting.id,
        event_type="gate_decision",
        payload={"decision": "hold_for_review", "reasons": ["Number discrepancy"]},
        transcript_sha256=t_hash,
    )

    assert e0.index == 0
    assert e1.index == 1
    assert e2.index == 2
    assert e1.prev_hash == e0.entry_hash
    assert e2.prev_hash == e1.entry_hash

    # Verify entire chain
    entries = repo.list_ledger_entries(meeting.id)
    is_valid, err = AuditLedger.verify_chain(entries)
    assert is_valid is True
    assert err is None


def test_ledger_detects_tampered_payload(ledger_db):
    repo = Repository(ledger_db)
    mid = f"m_tamper_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "Tamper Test")
    t_hash = "fake_sha256"

    e0 = AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting.id,
        event_type="gate_decision",
        payload={"decision": "hold_for_review"},
        transcript_sha256=t_hash,
    )

    # Tamper with the database row directly
    e0.payload_json = json.dumps({"decision": "release"})  # Maliciously altered payload!
    repo.db.commit()

    entries = repo.list_ledger_entries(meeting.id)
    is_valid, err = AuditLedger.verify_chain(entries)

    assert is_valid is False
    assert "Tampered entry detected" in err


def test_ledger_detects_tampered_prev_hash(ledger_db):
    repo = Repository(ledger_db)
    mid = f"m_tamper_hash_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "Tamper Hash Test")
    t_hash = "fake_sha256"

    AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting.id,
        event_type="event_0",
        payload={"data": 0},
        transcript_sha256=t_hash,
    )
    e1 = AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting.id,
        event_type="event_1",
        payload={"data": 1},
        transcript_sha256=t_hash,
    )

    # Corrupt prev_hash link on e1
    e1.prev_hash = "corrupted_hash_string"
    repo.db.commit()

    entries = repo.list_ledger_entries(meeting.id)
    is_valid, err = AuditLedger.verify_chain(entries)

    assert is_valid is False
    assert "Hash link mismatch" in err
