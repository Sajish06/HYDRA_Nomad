"""Privacy detection, deterministic tokenization, in-memory Vault, and coverage audit."""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from backend.config import settings
from backend.schemas.policy import DealConfig, PrivacyCoverageReport


def luhn_checksum_valid(card_num: str) -> bool:
    """Validate digits against Luhn algorithm (mod 10)."""
    digits = [int(c) for c in card_num if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled if doubled < 10 else doubled - 9
        else:
            checksum += d
    return checksum % 10 == 0


def shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy for high-entropy string detection."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    for count in {c: data.count(c) for c in set(data)}.values():
        p_x = count / length
        entropy += -p_x * math.log2(p_x)
    return entropy


@dataclass
class DetectedEntity:
    """Span of text detected as a sensitive entity."""

    start: int
    end: int
    category: str
    text: str

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class MaskedText:
    """Result of privacy tokenization."""

    text: str
    spans: List[DetectedEntity]
    token_map: Dict[str, str]  # token -> original value


class PrivacyEngine:
    """Detects sensitive entities and manages tokenization."""

    # Default categories that are safe for external AI processing (amounts, dates, percentages)
    # vs categories that MUST be masked/redacted before cloud.
    CLOUD_SENSITIVE_CATEGORIES = {
        "EMAIL",
        "PHONE",
        "CARD",
        "API_KEY",
        "NATIONAL_ID",
        "PERSON",
        "ORGANIZATION",
        "TARGET_NAME",
    }

    def __init__(self, deal_config: Optional[DealConfig] = None):
        self.deal_config = deal_config or self._load_deal_config()
        self._active_detectors: List[str] = [
            "EMAIL",
            "PHONE",
            "CARD",
            "API_KEY",
            "NATIONAL_ID",
            "PERSON",
            "ORGANIZATION",
            "TARGET_NAME",
            "AMOUNT",
            "PERCENT",
            "DATE",
        ]

    def _load_deal_config(self) -> DealConfig:
        config_path = Path(settings.DEAL_CONFIG_PATH)
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return DealConfig(**data)
            except Exception:
                pass
        return DealConfig()

    def detect_entities(self, text: str) -> List[DetectedEntity]:
        """Run all active detectors on the input text and resolve overlaps deterministically."""
        candidates: List[DetectedEntity] = []

        # 1. Target Name & Codename
        if self.deal_config.target_name:
            for m in re.finditer(re.escape(self.deal_config.target_name), text, re.IGNORECASE):
                candidates.append(DetectedEntity(m.start(), m.end(), "TARGET_NAME", m.group()))

        # 2. Known People (from deal config)
        for person in self.deal_config.known_people:
            for m in re.finditer(r"\b" + re.escape(person) + r"\b", text, re.IGNORECASE):
                candidates.append(DetectedEntity(m.start(), m.end(), "PERSON", m.group()))

        # 3. Known Organizations
        for org in self.deal_config.known_orgs:
            if org.lower() != self.deal_config.target_name.lower():
                for m in re.finditer(r"\b" + re.escape(org) + r"\b", text, re.IGNORECASE):
                    candidates.append(DetectedEntity(m.start(), m.end(), "ORGANIZATION", m.group()))

        # 4. Email detector
        email_re = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        for m in email_re.finditer(text):
            candidates.append(DetectedEntity(m.start(), m.end(), "EMAIL", m.group()))

        # 5. Phone detector
        phone_re = re.compile(
            r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})\b"
        )
        for m in phone_re.finditer(text):
            # Only count as phone if string length >= 10 chars
            clean = re.sub(r"\D", "", m.group())
            if len(clean) >= 10:
                candidates.append(DetectedEntity(m.start(), m.end(), "PHONE", m.group()))

        # 6. Credit Card (with Luhn validation)
        card_re = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
        for m in card_re.finditer(text):
            digits_only = re.sub(r"\D", "", m.group())
            if luhn_checksum_valid(digits_only):
                candidates.append(DetectedEntity(m.start(), m.end(), "CARD", m.group()))

        # 7. API Keys and Tokens
        api_key_re = re.compile(
            r"\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|bearer\s+[a-zA-Z0-9_\-\.]{20,})\b",
            re.IGNORECASE,
        )
        for m in api_key_re.finditer(text):
            candidates.append(DetectedEntity(m.start(), m.end(), "API_KEY", m.group()))

        # 8. National ID (SSN)
        ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
        for m in ssn_re.finditer(text):
            candidates.append(DetectedEntity(m.start(), m.end(), "NATIONAL_ID", m.group()))

        # 9. Amounts / Financial Figures ($4.2M, $15,000, 15k, etc.)
        amount_re = re.compile(
            r"(?:\$|USD\s*|EUR\s*|€|GBP\s*|£)\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|thousand|m|b|k))?\b|"
            r"\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:million|billion|m|b)\b",
            re.IGNORECASE,
        )
        for m in amount_re.finditer(text):
            candidates.append(DetectedEntity(m.start(), m.end(), "AMOUNT", m.group()))

        # 10. Percentages (e.g. 15%, 22.5 percent)
        percent_re = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent\b)", re.IGNORECASE)
        for m in percent_re.finditer(text):
            candidates.append(DetectedEntity(m.start(), m.end(), "PERCENT", m.group()))

        # 11. Dates
        date_re = re.compile(
            r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|"
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
            re.IGNORECASE,
        )
        for m in date_re.finditer(text):
            candidates.append(DetectedEntity(m.start(), m.end(), "DATE", m.group()))

        # Deterministic overlap resolution: longest span wins. If tie, earlier start wins.
        candidates.sort(key=lambda e: (e.start, -e.length))

        resolved: List[DetectedEntity] = []
        for candidate in candidates:
            # Check overlap with already accepted entities
            overlaps = False
            for accepted in resolved:
                if max(candidate.start, accepted.start) < min(candidate.end, accepted.end):
                    overlaps = True
                    break
            if not overlaps:
                resolved.append(candidate)

        # Sort by start offset
        resolved.sort(key=lambda e: e.start)
        return resolved


class Vault:
    """In-memory cryptographic token vault providing reversible pseudonymization."""

    def __init__(self, engine: Optional[PrivacyEngine] = None):
        self.engine = engine or PrivacyEngine()
        self._entity_to_token: Dict[str, str] = {}  # "normalized_text|category" -> token
        self._token_to_entity: Dict[str, str] = {}  # token -> original_text
        self._category_counters: Dict[str, int] = {}
        self._all_sensitive_values: Set[str] = set()

    def _get_or_create_token(self, text: str, category: str) -> str:
        key = f"{text.lower().strip()}|{category}"
        if key in self._entity_to_token:
            return self._entity_to_token[key]

        counter = self._category_counters.get(category, 0) + 1
        self._category_counters[category] = counter
        token = f"[{category}_{counter}]"

        self._entity_to_token[key] = token
        self._token_to_entity[token] = text
        self._all_sensitive_values.add(text.strip())
        return token

    def tokenize(
        self, text: str, categories_to_mask: Optional[Set[str]] = None
    ) -> MaskedText:
        """Tokenize sensitive entities in text into stable session tokens."""
        detected = self.engine.detect_entities(text)
        if categories_to_mask is None:
            categories_to_mask = PrivacyEngine.CLOUD_SENSITIVE_CATEGORIES

        # Track sensitive values for leak detection
        for d in detected:
            if d.category in PrivacyEngine.CLOUD_SENSITIVE_CATEGORIES:
                self._all_sensitive_values.add(d.text.strip())

        spans_to_replace = [d for d in detected if d.category in categories_to_mask]

        # Build replacement string from back to front to preserve offsets
        masked_chars = list(text)
        for entity in reversed(spans_to_replace):
            token = self._get_or_create_token(entity.text, entity.category)
            masked_chars[entity.start : entity.end] = list(token)

        masked_text = "".join(masked_chars)
        return MaskedText(
            text=masked_text,
            spans=spans_to_replace,
            token_map=dict(self._token_to_entity),
        )

    def rehydrate(self, text: str) -> str:
        """Replace tokens with their real original entity values."""
        result = text
        for token, original in self._token_to_entity.items():
            result = result.replace(token, original)
        return result

    def known_sensitive_values(self) -> Set[str]:
        """Return all known sensitive strings captured in the vault (used strictly for leak scanning)."""
        # Also include known people and target from deal config
        res = set(self._all_sensitive_values)
        for p in self.engine.deal_config.known_people:
            res.add(p.strip())
        if self.engine.deal_config.target_name:
            res.add(self.engine.deal_config.target_name.strip())
        return {v for v in res if len(v) >= 3}

    def get_coverage_report(self) -> PrivacyCoverageReport:
        """Generate audit report of entity detection coverage."""
        counts = {}
        for k, v in self._category_counters.items():
            counts[k] = v
        return PrivacyCoverageReport(
            detected_counts=counts,
            active_detectors=list(self.engine._active_detectors),
            total_tokens_created=len(self._token_to_entity),
            notice="Masking provides deterministic risk reduction, not complete anonymization.",
        )
