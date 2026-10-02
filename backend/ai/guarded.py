"""Guarded LLM Provider enforcing mandatory privacy checks and egress logging."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.ai.base import LLMProvider
from backend.processors.privacy import Vault, luhn_checksum_valid


class PrivacyGateError(Exception):
    """Raised when unmasked sensitive text is detected prior to an external AI call."""
    pass


class GuardedLLMProvider(LLMProvider):
    """Decorator for LLMProvider that enforces fail-closed privacy gating and egress logging."""

    def __init__(
        self,
        provider: LLMProvider,
        vault: Vault,
        meeting_id: str = "default",
        egress_dir: Optional[Path] = None,
    ):
        self.provider = provider
        self.vault = vault
        self.meeting_id = meeting_id
        self.egress_dir = egress_dir or Path(f"./data/outputs/{meeting_id}")
        self.egress_dir.mkdir(parents=True, exist_ok=True)
        self.egress_log_file = self.egress_dir / "ai_egress.jsonl"

    def _final_privacy_check(self, text: str) -> None:
        """Scan text for any raw sensitive entities or PII before sending to external AI."""
        # 1. Check for unmasked emails
        if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text):
            raise PrivacyGateError("Egress Privacy Check Failed: Unmasked email detected in AI payload.")

        # 2. Check for SSN / National IDs
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
            raise PrivacyGateError("Egress Privacy Check Failed: Unmasked National ID / SSN detected.")

        # 3. Check for API keys
        if re.search(r"\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,})\b", text):
            raise PrivacyGateError("Egress Privacy Check Failed: Unmasked API key detected.")

        # 4. Check for Luhn-valid Credit Cards
        for m in re.finditer(r"\b(?:\d[ -]*?){13,19}\b", text):
            digits = re.sub(r"\D", "", m.group())
            if luhn_checksum_valid(digits):
                raise PrivacyGateError("Egress Privacy Check Failed: Unmasked credit card detected.")

        # 5. Check against known sensitive values captured in the Vault (people, target name)
        sensitive_strings = self.vault.known_sensitive_values()
        for sensitive in sensitive_strings:
            # Word boundary search to prevent substring false-positives
            pattern = r"\b" + re.escape(sensitive) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                raise PrivacyGateError(
                    f"Egress Privacy Check Failed: Raw sensitive value '{sensitive}' detected in AI payload."
                )

    def _record_egress(self, call_type: str, payload_text: str) -> None:
        """Write the masked AI egress event and byte count to audit log."""
        byte_count = len(payload_text.encode("utf-8"))
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meeting_id": self.meeting_id,
            "call_type": call_type,
            "bytes_sent": byte_count,
            "masked_payload_sample": payload_text[:300] + ("..." if len(payload_text) > 300 else ""),
        }
        with open(self.egress_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def verify_claims(
        self, masked_transcript: str, masked_summary: str
    ) -> List[Dict[str, Any]]:
        # Run strict privacy gate
        self._final_privacy_check(masked_transcript)
        self._final_privacy_check(masked_summary)

        combined = f"TRANSCRIPT:\n{masked_transcript}\n\nSUMMARY:\n{masked_summary}"
        self._record_egress("verify_claims", combined)

        return await self.provider.verify_claims(masked_transcript, masked_summary)

    async def extract_intelligence(
        self, masked_transcript: str, masked_summary: str
    ) -> Dict[str, Any]:
        # Run strict privacy gate
        self._final_privacy_check(masked_transcript)
        self._final_privacy_check(masked_summary)

        combined = f"TRANSCRIPT:\n{masked_transcript}\n\nSUMMARY:\n{masked_summary}"
        self._record_egress("extract_intelligence", combined)

        return await self.provider.extract_intelligence(masked_transcript, masked_summary)
