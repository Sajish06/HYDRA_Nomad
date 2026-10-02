"""Schemas for audience masking policies and privacy reports."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PolicyAction(str, Enum):
    KEEP = "keep"
    TOKEN = "token"
    CODENAME = "codename"
    RANGE = "range"
    ROLE = "role"
    REDACT = "redact"
    DROP = "drop"


class AudienceProfile(BaseModel):
    """Configuration mapping entity categories to masking actions for an audience."""

    name: str
    description: str
    actions: Dict[str, PolicyAction] = Field(
        default_factory=dict,
        description="Map from entity category (PERSON, EMAIL, AMOUNT, etc.) to action",
    )


class DealConfig(BaseModel):
    """M&A deal-specific metadata used for entity matching and code naming."""

    target_name: str = "Northwind Analytics"
    target_codename: str = "Project Falcon"
    buyer_name: Optional[str] = "Acme Capital"
    known_people: List[str] = Field(default_factory=list)
    known_orgs: List[str] = Field(default_factory=list)
    known_roles: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps person name to corporate role (e.g. 'Jane Doe': 'Chief Financial Officer')",
    )


class MaskingDiffSpan(BaseModel):
    """A modified span comparing original to audience-transformed text."""

    start: int
    end: int
    original: str
    replacement: str
    category: str
    action: str


class MaskingDiffResponse(BaseModel):
    """Diff view between original and masked text for an audience."""

    audience: str
    original_text: str
    masked_text: str
    diff_spans: List[MaskingDiffSpan] = Field(default_factory=list)


class PrivacyCoverageReport(BaseModel):
    """Audit report of entity detection coverage and active detectors."""

    detected_counts: Dict[str, int] = Field(default_factory=dict)
    active_detectors: List[str] = Field(default_factory=list)
    total_tokens_created: int = 0
    notice: str = "Masking provides deterministic risk reduction, not complete anonymization."
