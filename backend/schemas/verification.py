"""Schemas for claim verification and evidence tracking."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


class OverallVerificationStatus(str, Enum):
    VERIFIED = "verified"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


class EvidenceItem(BaseModel):
    """An exact quote and speaker location in the transcript."""

    text: str
    speaker: str
    timestamp: Optional[str] = None
    segment_index: Optional[int] = None


class ClaimItem(BaseModel):
    """An atomic claim or action item extracted from the meeting summary."""

    id: str = Field(..., description="Unique claim identifier within the verification run")
    text: str = Field(..., description="The atomic claim or action item statement")
    claim_type: str = Field(default="claim", description="'claim' or 'action_item'")
    verdict: Verdict = Field(default=Verdict.UNVERIFIABLE)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    explanation: str = Field(default="")
    evidence: List[EvidenceItem] = Field(default_factory=list)
    evidence_verified: bool = Field(
        default=False,
        description="True if the evidence quote was physically relocated in the local transcript",
    )
    method: str = Field(default="baseline", description="'ai' or 'baseline'")
    flags: List[str] = Field(default_factory=list)
    # Action item specifics
    owner: Optional[str] = None
    deadline: Optional[str] = None
    owner_verified: bool = True
    deadline_verified: bool = True


class OmissionItem(BaseModel):
    """An important topic, figure, or action item in the transcript missing from the summary."""

    text: str
    category: str = "general"
    evidence: Optional[EvidenceItem] = None


class VerificationResult(BaseModel):
    """Complete verification output for a meeting summary."""

    meeting_id: str
    run_id: str
    overall_status: OverallVerificationStatus
    claims: List[ClaimItem] = Field(default_factory=list)
    omissions: List[OmissionItem] = Field(default_factory=list)
    supported_count: int = 0
    partially_supported_count: int = 0
    contradicted_count: int = 0
    unverifiable_count: int = 0
    review_reasons: List[str] = Field(default_factory=list)
    method: str = "baseline"
