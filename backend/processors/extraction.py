"""M&A business intelligence extraction across financial, deal, business, risk, and action items."""

import re
from typing import Any, Dict, List, Optional

from backend.processors.privacy import Vault
from backend.processors.verification import VerificationEngine
from backend.schemas.business_intelligence import (
    ExtractedIntelligenceItem,
    IntelligenceResult,
)
from backend.schemas.meeting import MeetingSummary, MeetingTranscript
from backend.schemas.verification import EvidenceItem


class IntelligenceExtractor:
    """Extracts structured M&A due diligence intelligence from meeting transcripts."""

    def __init__(self, vault: Optional[Vault] = None, verifier: Optional[VerificationEngine] = None):
        self.vault = vault or Vault()
        self.verifier = verifier or VerificationEngine(vault=self.vault)

    def extract_baseline(
        self, transcript: MeetingTranscript, summary: MeetingSummary, run_id: str
    ) -> IntelligenceResult:
        """Deterministic regex and keyword extractor running when AI is off."""
        financial: List[ExtractedIntelligenceItem] = []
        deal: List[ExtractedIntelligenceItem] = []
        business: List[ExtractedIntelligenceItem] = []
        risks: List[ExtractedIntelligenceItem] = []
        actions: List[ExtractedIntelligenceItem] = []

        # 1. Financial Extraction
        # Look for EBITDA, Revenue, Margin, Cash, Debt
        fin_patterns = [
            (r"\bEBITDA\s+(?:was|is|of)\s+([\$€£]?\s*[\d.]+\s*(?:million|billion|m|b|k)?|\w+\s+thousand)", "EBITDA"),
            (r"\brevenue\s+(?:was|is|of)\s+([\$€£]?\s*[\d.]+\s*(?:million|billion|m|b|k)?)", "Revenue"),
            (r"\bmargin\s+(?:was|is|of)\s+([\d.]+\s*(?:%|percent))", "Margin"),
            (r"\b(?:approved|budget)\s+(?:of|was|for)?\s*([\$€£]\s*[\d,]+|\w+\s+thousand)", "Approved Expense"),
        ]

        for seg in transcript.segments:
            for pat, metric in fin_patterns:
                m = re.search(pat, seg.text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    ts = (
                        f"{int(seg.start_time // 60):02d}:{int(seg.start_time % 60):02d}"
                        if seg.start_time is not None
                        else None
                    )
                    financial.append(
                        ExtractedIntelligenceItem(
                            category="financial",
                            metric_or_topic=metric,
                            value_description=val,
                            confidence=0.85,
                            basis="explicit",
                            evidence=EvidenceItem(
                                text=seg.text,
                                speaker=seg.speaker,
                                timestamp=ts,
                                segment_index=seg.segment_index,
                            ),
                            evidence_verified=True,
                        )
                    )

            # 2. Deal Structure Extraction
            if re.search(r"\b(?:asset purchase|stock purchase|merger|escrow|holdback|exclusivity)\b", seg.text, re.IGNORECASE):
                deal.append(
                    ExtractedIntelligenceItem(
                        category="deal",
                        metric_or_topic="Structure / Terms",
                        value_description=seg.text,
                        confidence=0.8,
                        basis="explicit",
                        evidence=EvidenceItem(
                            text=seg.text,
                            speaker=seg.speaker,
                            timestamp=f"{int(seg.start_time // 60):02d}:{int(seg.start_time % 60):02d}" if seg.start_time is not None else None,
                            segment_index=seg.segment_index,
                        ),
                        evidence_verified=True,
                    )
                )

            # 3. Risks Extraction
            if re.search(r"\b(?:concentration|risk|litigation|regulatory|churn|dependency)\b", seg.text, re.IGNORECASE):
                risks.append(
                    ExtractedIntelligenceItem(
                        category="risk",
                        metric_or_topic="Identified Risk",
                        value_description=seg.text,
                        confidence=0.85,
                        basis="explicit",
                        evidence=EvidenceItem(
                            text=seg.text,
                            speaker=seg.speaker,
                            timestamp=f"{int(seg.start_time // 60):02d}:{int(seg.start_time % 60):02d}" if seg.start_time is not None else None,
                            segment_index=seg.segment_index,
                        ),
                        evidence_verified=True,
                    )
                )

            # 4. Decisions & Actions Extraction
            if re.search(r"\b(?:will send|action item|agreed to|due by|delivers|finalize)\b", seg.text, re.IGNORECASE):
                actions.append(
                    ExtractedIntelligenceItem(
                        category="decision_action",
                        metric_or_topic="Action Commitment",
                        value_description=seg.text,
                        confidence=0.8,
                        basis="explicit",
                        evidence=EvidenceItem(
                            text=seg.text,
                            speaker=seg.speaker,
                            timestamp=f"{int(seg.start_time // 60):02d}:{int(seg.start_time % 60):02d}" if seg.start_time is not None else None,
                            segment_index=seg.segment_index,
                        ),
                        evidence_verified=True,
                    )
                )

        return IntelligenceResult(
            meeting_id=summary.meeting_id,
            run_id=run_id,
            financial=financial,
            deal=deal,
            business=business,
            risks=risks,
            decisions_actions=actions,
        )

    def process_ai_draft(
        self, draft_data: Dict[str, Any], transcript: MeetingTranscript, meeting_id: str, run_id: str
    ) -> IntelligenceResult:
        """Validate AI-extracted findings against local transcript relocation."""
        result_cats = {
            "financial": [],
            "deal": [],
            "business": [],
            "risks": [],
            "decisions_actions": [],
        }

        for cat_name, items in draft_data.items():
            if not isinstance(items, list) or cat_name not in result_cats:
                continue

            for raw_it in items:
                topic = raw_it.get("metric_or_topic", "General")
                val = self.vault.rehydrate(raw_it.get("value_description", ""))
                quote = self.vault.rehydrate(raw_it.get("evidence_quote") or raw_it.get("quote", ""))

                evidence_item = None
                evidence_verified = False
                if quote:
                    loc_found, real_seg, _ = self.verifier.relocate_evidence(quote, transcript)
                    evidence_verified = loc_found
                    evidence_item = EvidenceItem(
                        text=quote,
                        speaker=real_seg.speaker if real_seg else "Speaker",
                        timestamp=f"{int(real_seg.start_time // 60):02d}:{int(real_seg.start_time % 60):02d}"
                        if real_seg and real_seg.start_time is not None
                        else None,
                        segment_index=real_seg.segment_index if real_seg else None,
                    )

                result_cats[cat_name].append(
                    ExtractedIntelligenceItem(
                        category=cat_name,
                        metric_or_topic=topic,
                        value_description=val,
                        period=raw_it.get("period"),
                        unit_or_currency=raw_it.get("unit_or_currency"),
                        confidence=float(raw_it.get("confidence", 0.8)),
                        basis=raw_it.get("basis", "explicit"),
                        evidence=evidence_item,
                        evidence_verified=evidence_verified,
                        owner=self.vault.rehydrate(raw_it.get("owner", "")) if raw_it.get("owner") else None,
                        due_date=raw_it.get("due_date"),
                    )
                )

        return IntelligenceResult(
            meeting_id=meeting_id,
            run_id=run_id,
            financial=result_cats["financial"],
            deal=result_cats["deal"],
            business=result_cats["business"],
            risks=result_cats["risks"],
            decisions_actions=result_cats["decisions_actions"],
        )
