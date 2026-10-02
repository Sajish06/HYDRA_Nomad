"""Cryptographic tamper-evident hash-chained audit ledger.

Provides chronological audit trail of all gatekeeper decisions, reviews, and distribution actions.
Note: This ledger is tamper-evident on the host system; it is not a distributed blockchain or notarization service.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.storage.models import LedgerEntryModel
from backend.storage.repository import Repository


class AuditLedger:
    """Manages append-only SHA-256 hash chains for meeting intelligence lifecycle."""

    GENESIS_HASH = "0" * 64

    @staticmethod
    def canonical_json(payload: Dict[str, Any]) -> str:
        """Serialize payload deterministically with sorted keys and no whitespace."""
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def compute_entry_hash(
        cls, prev_hash: str, payload_json_str: str, transcript_sha256: str
    ) -> str:
        """Compute SHA256(prev_hash || canonical_payload || transcript_sha256)."""
        data = f"{prev_hash}|{payload_json_str}|{transcript_sha256}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def record_event(
        cls,
        repo: Repository,
        meeting_id: str,
        event_type: str,
        payload: Dict[str, Any],
        transcript_sha256: str,
    ) -> LedgerEntryModel:
        """Append a new verified entry to the meeting's hash chain."""
        latest = repo.get_latest_ledger_entry(meeting_id)

        index = 0 if not latest else latest.index + 1
        prev_hash = cls.GENESIS_HASH if not latest else latest.entry_hash
        timestamp = datetime.now(timezone.utc).isoformat()

        canon_payload = cls.canonical_json(payload)
        entry_hash = cls.compute_entry_hash(prev_hash, canon_payload, transcript_sha256)

        return repo.append_ledger_entry(
            meeting_id=meeting_id,
            index=index,
            event_type=event_type,
            timestamp=timestamp,
            payload_dict=payload,
            transcript_sha256=transcript_sha256,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )

    @classmethod
    def verify_chain(cls, entries: List[LedgerEntryModel]) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic integrity of the entire ledger chain.

        Returns (is_valid, error_explanation).
        """
        if not entries:
            return True, None

        # Sort strictly by index
        sorted_entries = sorted(entries, key=lambda e: e.index)

        expected_prev_hash = cls.GENESIS_HASH
        for i, entry in enumerate(sorted_entries):
            # Check sequential index
            if entry.index != i:
                return False, f"Broken chain index sequence: expected {i}, found {entry.index}"

            # Check previous hash link
            if entry.prev_hash != expected_prev_hash:
                return (
                    False,
                    f"Hash link mismatch at index {entry.index}: expected prev_hash '{expected_prev_hash}', got '{entry.prev_hash}'",
                )

            # Recompute entry hash
            # Parse and canonicalize payload to prevent formatting discrepancies
            try:
                p_dict = json.loads(entry.payload_json)
                canon_str = cls.canonical_json(p_dict)
            except Exception:
                canon_str = entry.payload_json

            recomputed = cls.compute_entry_hash(
                entry.prev_hash, canon_str, entry.transcript_sha256
            )
            if recomputed.lower() != entry.entry_hash.lower():
                return (
                    False,
                    f"Tampered entry detected at index {entry.index}: recorded hash '{entry.entry_hash}' does not match recomputed hash '{recomputed}'",
                )

            expected_prev_hash = entry.entry_hash

        return True, None
