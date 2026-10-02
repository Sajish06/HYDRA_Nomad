"""Audience policy engine applying declarative masking profiles and range conversions."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from backend.config import settings
from backend.processors.privacy import Vault
from backend.schemas.meeting import MeetingSummary
from backend.schemas.policy import (
    AudienceProfile,
    DealConfig,
    MaskingDiffResponse,
    MaskingDiffSpan,
    PolicyAction,
)
from backend.schemas.verification import ClaimItem, EvidenceItem


def amount_to_range(amount_str: str) -> str:
    """Convert exact monetary amounts into generalized ranges for board profile."""
    # Match millions: e.g. $4.2M, 4.2 million, $4,200,000
    cleaned = amount_str.replace(",", "").strip()
    currency = "$"
    if "€" in cleaned or "EUR" in cleaned:
        currency = "€"
    elif "£" in cleaned or "GBP" in cleaned:
        currency = "£"

    # Check millions
    m_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:million|m)\b", cleaned, re.IGNORECASE)
    if m_match:
        val = float(m_match.group(1))
        lower = int(val)
        upper = lower + 1
        return f"{currency}{lower}M-{currency}{upper}M"

    # Check thousands
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:thousand|k)\b", cleaned, re.IGNORECASE)
    if k_match:
        val = float(k_match.group(1))
        lower = int(val // 10) * 10
        upper = lower + 10
        return f"{currency}{lower}k-{currency}{upper}k"

    # Raw numbers: e.g. $15000 or $15,000
    raw_match = re.search(r"(\d+)", cleaned)
    if raw_match:
        val = int(raw_match.group(1))
        if val >= 1_000_000:
            m_val = val / 1_000_000
            lower = int(m_val)
            upper = lower + 1
            return f"{currency}{lower}M-{currency}{upper}M"
        elif val >= 1_000:
            lower = (val // 10_000) * 10_000
            upper = lower + 10_000
            return f"{currency}{lower:,}-{currency}{upper:,}"
        else:
            return f"{currency}0-{currency}1,000"

    return f"{currency}Range"


class PolicyEngine:
    """Applies audience profiles to text, summaries, and claims."""

    def __init__(
        self,
        profiles_path: Optional[Path] = None,
        deal_config: Optional[DealConfig] = None,
    ):
        self.profiles_path = profiles_path or Path(settings.AUDIENCE_PROFILES_PATH)
        self.deal_config = deal_config or self._load_deal_config()
        self.profiles: Dict[str, AudienceProfile] = self._load_profiles()

    def _load_deal_config(self) -> DealConfig:
        path = Path(settings.DEAL_CONFIG_PATH)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return DealConfig(**data)
            except Exception:
                pass
        return DealConfig()

    def _load_profiles(self) -> Dict[str, AudienceProfile]:
        profiles = {}
        if self.profiles_path.exists():
            try:
                with open(self.profiles_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for name, p_data in data.get("profiles", {}).items():
                    profiles[name] = AudienceProfile(
                        name=name,
                        description=p_data.get("description", ""),
                        actions={
                            k: PolicyAction(v) for k, v in p_data.get("actions", {}).items()
                        },
                    )
            except Exception:
                pass

        # Fallbacks if file missing
        if not profiles:
            profiles["deal_team"] = AudienceProfile(
                name="deal_team",
                description="Internal deal team",
                actions={cat: PolicyAction.KEEP for cat in ["PERSON", "AMOUNT", "TARGET_NAME", "EMAIL", "PHONE"]},
            )
            profiles["lender"] = AudienceProfile(
                name="lender",
                description="Lender syndicate",
                actions={"PERSON": PolicyAction.TOKEN, "TARGET_NAME": PolicyAction.CODENAME, "AMOUNT": PolicyAction.KEEP},
            )
            profiles["board"] = AudienceProfile(
                name="board",
                description="Board of Directors",
                actions={"PERSON": PolicyAction.KEEP, "TARGET_NAME": PolicyAction.KEEP, "AMOUNT": PolicyAction.RANGE},
            )
            profiles["outside_counsel"] = AudienceProfile(
                name="outside_counsel",
                description="Outside counsel",
                actions={"PERSON": PolicyAction.TOKEN, "TARGET_NAME": PolicyAction.KEEP, "AMOUNT": PolicyAction.KEEP},
            )
            profiles["cloud_llm"] = AudienceProfile(
                name="cloud_llm",
                description="Cloud AI Boundary",
                actions={"PERSON": PolicyAction.TOKEN, "ORGANIZATION": PolicyAction.TOKEN, "TARGET_NAME": PolicyAction.TOKEN},
            )
        return profiles

    def get_profile(self, audience: str) -> AudienceProfile:
        return self.profiles.get(audience) or self.profiles["deal_team"]

    def mask_text(
        self, text: str, audience: str, vault: Vault
    ) -> Tuple[str, List[MaskingDiffSpan]]:
        """Apply audience profile actions to text and compute detailed diff spans."""
        profile = self.get_profile(audience)
        detected = vault.engine.detect_entities(text)

        # Build replacement map
        replacements: List[Tuple[int, int, str, str, str, str]] = []  # (start, end, orig, repl, cat, action)

        for entity in detected:
            action = profile.actions.get(entity.category, PolicyAction.KEEP)
            # Custom handling for role
            action_str = action.value if isinstance(action, PolicyAction) else str(action)

            replacement = None
            if action_str == "keep":
                continue
            elif action_str == "token":
                replacement = vault._get_or_create_token(entity.text, entity.category)
            elif action_str == "codename" or entity.category == "TARGET_NAME" and action_str == "codename":
                replacement = self.deal_config.target_codename
            elif action_str == "role":
                replacement = self.deal_config.known_roles.get(
                    entity.text, vault._get_or_create_token(entity.text, "PERSON")
                )
            elif action_str == "range" or entity.category == "AMOUNT" and action_str == "range":
                replacement = amount_to_range(entity.text)
            elif action_str == "redact":
                replacement = "[REDACTED]"
            elif action_str == "drop":
                replacement = ""

            if replacement is not None and replacement != entity.text:
                replacements.append((entity.start, entity.end, entity.text, replacement, entity.category, action_str))

        # Sort back to front to apply
        replacements.sort(key=lambda r: r[0], reverse=True)
        chars = list(text)
        diff_spans: List[MaskingDiffSpan] = []

        for start, end, orig, repl, cat, act in replacements:
            chars[start:end] = list(repl)
            diff_spans.append(
                MaskingDiffSpan(
                    start=start,
                    end=start + len(repl),
                    original=orig,
                    replacement=repl,
                    category=cat,
                    action=act,
                )
            )

        diff_spans.reverse()
        masked_text = "".join(chars)
        return masked_text, diff_spans

    def diff(self, text: str, audience: str, vault: Vault) -> MaskingDiffResponse:
        """Generate a structured masking diff response for UI visualization."""
        masked_text, diff_spans = self.mask_text(text, audience, vault)
        return MaskingDiffResponse(
            audience=audience,
            original_text=text,
            masked_text=masked_text,
            diff_spans=diff_spans,
        )

    def apply_to_summary(self, summary: MeetingSummary, audience: str, vault: Vault) -> MeetingSummary:
        """Apply audience masking to summary text and action items."""
        masked_text, _ = self.mask_text(summary.summary_text, audience, vault)

        masked_actions = []
        for action in summary.action_items:
            m_act, _ = self.mask_text(action, audience, vault)
            masked_actions.append(m_act)

        masked_decisions = []
        for dec in summary.key_decisions:
            m_dec, _ = self.mask_text(dec, audience, vault)
            masked_decisions.append(m_dec)

        return MeetingSummary(
            meeting_id=summary.meeting_id,
            summary_text=masked_text,
            action_items=masked_actions,
            key_decisions=masked_decisions,
            created_at=summary.created_at,
        )

    def apply_to_claims(self, claims: List[ClaimItem], audience: str, vault: Vault) -> List[ClaimItem]:
        """Apply audience masking to claims, explanations, and their citations."""
        transformed = []
        for claim in claims:
            masked_text, _ = self.mask_text(claim.text, audience, vault)
            masked_explanation, _ = self.mask_text(claim.explanation, audience, vault)
            masked_owner = None
            if claim.owner:
                masked_owner, _ = self.mask_text(claim.owner, audience, vault)

            masked_evidence = []
            for ev in claim.evidence:
                ev_text, _ = self.mask_text(ev.text, audience, vault)
                ev_speaker, _ = self.mask_text(ev.speaker, audience, vault)
                masked_evidence.append(
                    EvidenceItem(
                        text=ev_text,
                        speaker=ev_speaker,
                        timestamp=ev.timestamp,
                        segment_index=ev.segment_index,
                    )
                )

            transformed.append(
                ClaimItem(
                    id=claim.id,
                    text=masked_text,
                    claim_type=claim.claim_type,
                    verdict=claim.verdict,
                    confidence=claim.confidence,
                    explanation=masked_explanation,
                    evidence=masked_evidence,
                    evidence_verified=claim.evidence_verified,
                    method=claim.method,
                    flags=claim.flags,
                    owner=masked_owner,
                    deadline=claim.deadline,
                    owner_verified=claim.owner_verified,
                    deadline_verified=claim.deadline_verified,
                )
            )
        return transformed
