"""Schemas for M&A business intelligence extraction."""

from typing import List, Optional

from pydantic import BaseModel, Field

from backend.schemas.verification import EvidenceItem


class ExtractedIntelligenceItem(BaseModel):
    """An individual piece of intelligence extracted from meeting text."""

    category: str = Field(
        ...,
        description="M&A category: 'financial', 'deal', 'business', 'risk', or 'decision_action'",
    )
    metric_or_topic: str = Field(..., description="Specific metric, risk name, or topic")
    value_description: str = Field(..., description="Exact extracted value or description")
    period: Optional[str] = Field(default=None, description="Time period if applicable (e.g. FY23, Q3)")
    unit_or_currency: Optional[str] = Field(default=None, description="e.g. USD, EUR, %, ratio")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    basis: str = Field(default="explicit", description="'explicit' or 'inferred'")
    evidence: Optional[EvidenceItem] = None
    evidence_verified: bool = False
    # Specific fields for actions/decisions
    owner: Optional[str] = None
    due_date: Optional[str] = None


class IntelligenceResult(BaseModel):
    """Complete M&A intelligence extraction for a meeting."""

    meeting_id: str
    run_id: str
    financial: List[ExtractedIntelligenceItem] = Field(default_factory=list)
    deal: List[ExtractedIntelligenceItem] = Field(default_factory=list)
    business: List[ExtractedIntelligenceItem] = Field(default_factory=list)
    risks: List[ExtractedIntelligenceItem] = Field(default_factory=list)
    decisions_actions: List[ExtractedIntelligenceItem] = Field(default_factory=list)
