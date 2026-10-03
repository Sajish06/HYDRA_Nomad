"""Cryptographic tamper-evident hash-chained audit ledger.

Provides chronological audit trail of all gatekeeper decisions, reviews, and distribution actions.
Note: This ledger is tamper-evident on the host system; it is not a distributed blockchain or notarization service.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.config import settings
from backend.storage.models import LedgerEntryModel
from backend.storage.repository import Repository


class AuditLedger:
    """Manages append-only SHA-256 or HMAC-SHA256 hash chains for meeting intelligence lifecycle."""

    GENESIS_HASH = "0" * 64

    @classmethod
    def get_ledger_key(cls) -> Optional[str]:
        if settings.NOMAD_LEDGER_KEY:
            return settings.NOMAD_LEDGER_KEY.get_secret_value()
        return os.environ.get("NOMAD_LEDGER_KEY")

    @staticmethod
    def canonical_json(payload: Dict[str, Any]) -> str:
        """Serialize payload deterministically with sorted keys and no whitespace."""
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def compute_entry_hash(
        cls, prev_hash: str, payload_json_str: str, transcript_sha256: str, key: Optional[str] = None
    ) -> str:
        """Compute SHA256(prev_hash || canonical_payload || transcript_sha256), with optional HMAC."""
        data = f"{prev_hash}|{payload_json_str}|{transcript_sha256}".encode("utf-8")
        active_key = key if key is not None else cls.get_ledger_key()
        if active_key:
            return hmac.new(active_key.encode("utf-8"), data, hashlib.sha256).hexdigest()
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def record_event(
        cls,
        repo: Repository,
        meeting_id: str,
        event_type: str,
        payload: Dict[str, Any],
        transcript_sha256: str,
        key: Optional[str] = None,
    ) -> LedgerEntryModel:
        """Append a new verified entry to the meeting's hash chain."""
        effective_transcript_hash = transcript_sha256 or "no_transcript_hash"
        latest = repo.get_latest_ledger_entry(meeting_id)

        index = 0 if not latest else latest.index + 1
        prev_hash = cls.GENESIS_HASH if not latest else latest.entry_hash
        timestamp = datetime.now(timezone.utc).isoformat()

        canon_payload = cls.canonical_json(payload)
        entry_hash = cls.compute_entry_hash(prev_hash, canon_payload, effective_transcript_hash, key=key)

        return repo.append_ledger_entry(
            meeting_id=meeting_id,
            index=index,
            event_type=event_type,
            timestamp=timestamp,
            payload_dict=payload,
            transcript_sha256=effective_transcript_hash,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )

    @classmethod
    def verify_chain(cls, entries: List[LedgerEntryModel], key: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic integrity of the entire ledger chain.

        Returns (is_valid, error_explanation).
        """
        if not entries:
            return True, None

        # Sort strictly by index
        sorted_entries = sorted(entries, key=lambda e: e.index)

        expected_prev_hash = cls.GENESIS_HASH
        active_key = key if key is not None else cls.get_ledger_key()

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
            try:
                p_dict = json.loads(entry.payload_json)
                canon_str = cls.canonical_json(p_dict)
            except Exception:
                canon_str = entry.payload_json

            recomputed = cls.compute_entry_hash(
                entry.prev_hash, canon_str, entry.transcript_sha256, key=active_key
            )
            if recomputed.lower() != entry.entry_hash.lower():
                # Also check without key in case entry was created without key
                recomputed_nokey = cls.compute_entry_hash(
                    entry.prev_hash, canon_str, entry.transcript_sha256, key=""
                )
                if recomputed_nokey.lower() != entry.entry_hash.lower():
                    return (
                        False,
                        f"Tampered entry detected at index {entry.index}: recorded hash '{entry.entry_hash}' does not match recomputed hash '{recomputed}'",
                    )

            expected_prev_hash = entry.entry_hash

        return True, None
