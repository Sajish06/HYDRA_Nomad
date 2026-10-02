"""Schemas for release gating, human review, leak scanning, and ledger."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GateDecisionType(str, Enum):
    RELEASE = "release"
    HOLD_FOR_REVIEW = "hold_for_review"
    BLOCK = "block"


class CrossSourceConflict(BaseModel):
    """Discrepancy between meeting statements and external documents."""

    id: str
    metric: str
    period: Optional[str] = None
    transcript_value: str
    transcript_citation: str
    doc_name: str
    doc_value: str
    doc_citation: str
    severity: str = "high"
    explanation: str


class ReleaseDecision(BaseModel):
    """Gate decision determining whether meeting outputs can be distributed."""

    id: str
    meeting_id: str
    run_id: str
    decision: GateDecisionType
    reasons: List[str] = Field(default_factory=list)
    flagged_claim_ids: List[str] = Field(default_factory=list)
    flagged_conflict_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overridden: bool = False
    approved_by: Optional[str] = None


class ReviewItemStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ReviewDecisionRequest(BaseModel):
    """User input when resolving a review item."""

    action: ReviewItemStatus
    corrected_text: Optional[str] = None
    reviewer_notes: Optional[str] = None


class ReviewItem(BaseModel):
    """Actionable review item presented to human reviewers."""

    id: str
    meeting_id: str
    run_id: str
    item_type: str = "claim"  # 'claim' or 'conflict'
    reference_id: str  # claim_id or conflict_id
    original_text: str
    issue_type: str
    suggested_fix: Optional[str] = None
    status: ReviewItemStatus = ReviewItemStatus.PENDING
    decision_action: Optional[str] = None
    corrected_text: Optional[str] = None
    reviewer_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None


class LeakFinding(BaseModel):
    """A specific leak identified in generated output."""

    sensitive_value: str
    category: str
    location_index: int
    rule_violated: str


class AudienceLeakReport(BaseModel):
    """Leak scan outcome for a single audience output artifact."""

    audience: str
    status: str = "pass"  # 'pass' or 'fail'
    findings: List[LeakFinding] = Field(default_factory=list)
    canary_found: bool = False
    quarantined: bool = False


class OverallLeakReport(BaseModel):
    """Consolidated leak scan report for all generated outputs."""

    meeting_id: str
    run_id: str
    all_passed: bool
    audience_reports: List[AudienceLeakReport] = Field(default_factory=list)


class LedgerEntrySchema(BaseModel):
    """Cryptographic tamper-evident audit ledger record."""

    index: int
    entry_id: str
    meeting_id: str
    event_type: str
    timestamp: str
    payload: Dict[str, Any]
    transcript_sha256: str
    prev_hash: str
    entry_hash: str
