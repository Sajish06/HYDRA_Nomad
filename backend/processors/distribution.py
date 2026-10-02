"""Distribution engine fanning out audience-tailored intelligence outputs."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

from backend.processors.policy import PolicyEngine
from backend.processors.privacy import Vault
from backend.schemas.meeting import MeetingSummary
from backend.schemas.verification import ClaimItem


class BaseSink(ABC):
    """Destination sink interface for delivering distributed outputs."""

    @abstractmethod
    async def deliver(self, audience: str, markdown_content: str, json_data: dict) -> str:
        """Deliver audience output artifact. Returns URI or path."""
        pass


class LocalFileSink(BaseSink):
    """Writes distribution artifacts to local disk."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def deliver(self, audience: str, markdown_content: str, json_data: dict) -> str:
        md_file = self.output_dir / f"{audience}.md"
        json_file = self.output_dir / f"{audience}.json"

        md_file.write_text(markdown_content, encoding="utf-8")
        json_file.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

        return str(md_file)


class DistributionEngine:
    """Coordinates policy transformation and fan-out of audience-specific artifacts."""

    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        vault: Optional[Vault] = None,
        output_base_dir: Optional[Path] = None,
    ):
        self.policy = policy_engine or PolicyEngine()
        self.vault = vault or Vault()
        self.output_base_dir = output_base_dir or Path("./data/outputs")

    def format_audience_markdown(
        self,
        audience: str,
        masked_summary: MeetingSummary,
        masked_claims: List[ClaimItem],
    ) -> str:
        """Render a formatted markdown dossier tailored for the audience."""
        lines = [
            "# M&A Due Diligence Intelligence Dossier",
            f"**Audience Classification**: `{audience.upper()}`",
            "**Status**: VERIFIED & GATED RELEASE",
            "",
            "## Executive Summary",
            masked_summary.summary_text,
            "",
            "## Key Action Items & Decisions",
        ]

        if masked_summary.action_items:
            for item in masked_summary.action_items:
                lines.append(f"- [ ] {item}")
        else:
            lines.append("_No action items recorded._")

        lines.extend(["", "## Verified Claims & Citations"])
        for c in masked_claims:
            badge = "🟢" if c.verdict.value == "supported" else "🟡" if c.verdict.value == "partially_supported" else "🔴"
            lines.append(f"### {badge} Claim: {c.text}")
            lines.append(f"- **Verdict**: `{c.verdict.value}` (Confidence: {c.confidence:.0%})")
            if c.explanation:
                lines.append(f"- **Analysis**: {c.explanation}")
            if c.evidence:
                lines.append("- **Evidence Citations**:")
                for ev in c.evidence:
                    ts = f" @ {ev.timestamp}" if ev.timestamp else ""
                    lines.append(f"  > \"{ev.text}\" — *{ev.speaker}{ts}*")
            lines.append("")

        return "\n".join(lines)

    async def distribute(
        self,
        meeting_id: str,
        summary: MeetingSummary,
        claims: List[ClaimItem],
        audiences: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Apply audience policies and emit files for all requested audiences. Returns {audience: file_path}."""
        if audiences is None:
            audiences = ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"]

        meeting_out_dir = self.output_base_dir / meeting_id
        sink = LocalFileSink(meeting_out_dir)
        produced: Dict[str, str] = {}

        for aud in audiences:
            # 1. Transform summary and claims according to audience policy
            m_summary = self.policy.apply_to_summary(summary, aud, self.vault)
            m_claims = self.policy.apply_to_claims(claims, aud, self.vault)

            # 2. Render markdown content
            md_content = self.format_audience_markdown(aud, m_summary, m_claims)

            # 3. Create JSON payload with citations
            json_payload = {
                "meeting_id": meeting_id,
                "audience": aud,
                "summary": m_summary.model_dump(mode="json"),
                "claims": [c.model_dump(mode="json") for c in m_claims],
            }

            # 4. Deliver via sink
            path = await sink.deliver(aud, md_content, json_payload)
            produced[aud] = path

        return produced
