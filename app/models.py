from enum import Enum
from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field

class Stance(str, Enum):
    QUESTION = "QUESTION"      # "Should we...?"
    PROPOSE  = "PROPOSE"       # "We could / I think we should..."
    SUGGEST  = "SUGGEST"       # advice from a participant ("You need to...")
    REQUEST  = "REQUEST"       # asks someone to do something ("Can you investigate...?")
    ACCEPT   = "ACCEPT"        # agrees to a proposal/request ("Sure, I'll look into it")
    COMMIT   = "COMMIT"        # self-assigns ("I'll handle it")
    DECIDE   = "DECIDE"        # "Let's do X", "We're going with X"
    REJECT   = "REJECT"        # "No, let's not"
    DEFER    = "DEFER"         # "Let's hold off until next semester"
    CANCEL   = "CANCEL"        # "Drop it", "scrap that"
    REVERSE  = "REVERSE"       # "Actually we decided not to..."
    INFORM   = "INFORM"        # mentions topic without taking a position
    OTHER    = "OTHER"

AFFIRM_STRONG = {Stance.DECIDE, Stance.COMMIT, Stance.ACCEPT}
AFFIRM_WEAK   = {Stance.PROPOSE, Stance.SUGGEST, Stance.REQUEST, Stance.QUESTION}
NEGATE        = {Stance.REJECT, Stance.DEFER, Stance.CANCEL, Stance.REVERSE}

class ClaimType(str, Enum):
    DECISION    = "DECISION"
    COMMITMENT  = "COMMITMENT"
    ACTION      = "ACTION"
    DEADLINE    = "DEADLINE"
    REQUIREMENT = "REQUIREMENT"

class Status(str, Enum):
    VERIFIED       = "VERIFIED"
    AMBIGUOUS      = "AMBIGUOUS"
    UNSUPPORTED    = "UNSUPPORTED"
    USER_CONFIRMED = "USER_CONFIRMED"
    USER_REJECTED  = "USER_REJECTED"

class Reason(str, Enum):
    CLEAN_SUPPORT         = "CLEAN_SUPPORT"
    NO_RELEVANT_EVIDENCE  = "NO_RELEVANT_EVIDENCE"
    INFORM_ONLY           = "INFORM_ONLY"
    PROPOSAL_ONLY         = "PROPOSAL_ONLY"
    DEFERRED              = "DEFERRED"
    REJECTED              = "REJECTED"
    CANCELLED             = "CANCELLED"
    REVERSED              = "REVERSED"
    FLIP_FLOP             = "FLIP_FLOP"
    UNGROUNDED_ACTOR      = "UNGROUNDED_ACTOR"
    UNGROUNDED_DEADLINE   = "UNGROUNDED_DEADLINE"
    SLOT_CONFLICT         = "SLOT_CONFLICT"
    UNRESOLVED_REFERENCE  = "UNRESOLVED_REFERENCE"
    LLM_RULE_DISAGREEMENT = "LLM_RULE_DISAGREEMENT"

class Segment(BaseModel):
    idx: int
    speaker: Optional[str] = None
    time: Optional[str] = None
    t_seconds: Optional[float] = None
    text: str

class Participant(BaseModel):
    name: str
    role: Optional[str] = None
    has_authority: bool = False

class Meeting(BaseModel):
    meeting_id: str
    title: Optional[str] = None
    participants: List[Participant] = []
    segments: List[Segment]
    summary_decisions: List[str] = []
    summary_actions: List[str] = []

class Claim(BaseModel):
    claim_id: str
    meeting_id: str
    text: str
    source: Literal["SUMMARY", "TRANSCRIPT"]
    type: ClaimType
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    deadline: Optional[str] = None
    normalized: str

class ClaimDraft(BaseModel):
    type: ClaimType = ClaimType.DECISION
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    deadline: Optional[str] = None
    normalized: str

class SegmentStance(BaseModel):
    idx: int
    relevance: float = Field(ge=0.0, le=1.0)
    stance: Stance
    toward_claim: Literal["SUPPORTS", "CONTRADICTS", "NEUTRAL"]
    resolved_text: Optional[str] = None
    antecedent_idx: Optional[int] = None
    actor_mentioned: Optional[str] = None
    deadline_mentioned: Optional[str] = None
    quote: str

class StanceAnalysisResponse(BaseModel):
    stances: List[SegmentStance] = []

class ExtractedClaimDraft(BaseModel):
    type: ClaimType
    text: str
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    deadline: Optional[str] = None
    normalized: str
    source_idx: List[int] = []

class ExtractedClaimsResponse(BaseModel):
    claims: List[ExtractedClaimDraft] = []

class EvidenceItem(BaseModel):
    idx: int
    speaker: Optional[str] = None
    time: Optional[str] = None
    text: str
    quote: str
    stance: Stance
    relation: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT"]
    resolved_text: Optional[str] = None
    actor_mentioned: Optional[str] = None
    deadline_mentioned: Optional[str] = None
    source: Literal["LLM", "RULES", "BOTH"] = "LLM"

class SlotCheck(BaseModel):
    slot: Literal["actor", "action", "object", "deadline"]
    claim_value: Optional[str] = None
    status: Literal["GROUNDED", "MISSING", "CONFLICT", "NOT_APPLICABLE"]
    evidence_idx: List[int] = []

class Verification(BaseModel):
    claim_id: str
    status: Status
    gate_action: Literal["PROCEED", "HUMAN_REVIEW", "BLOCK"]
    reasons: List[Reason]
    explanation: str
    evidence_chain: List[EvidenceItem]
    slots: List[SlotCheck]
    resolved_claim: Optional[str] = None
    final_state: Literal["NONE", "PROPOSED", "AFFIRMED", "NEGATED"]
    created_at: str

class ConfirmationRequest(BaseModel):
    decision: Literal["CONFIRMED", "REJECTED"]
    note: Optional[str] = None

class HandoffSegment(BaseModel):
    idx: int
    speaker: Optional[str] = None
    time: Optional[str] = None
    text: str

class VerifiedTask(BaseModel):
    task_id: str
    meeting_id: str
    claim_type: ClaimType
    task_text: str
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    deadline: Optional[str] = None
    effective_status: Literal["VERIFIED", "USER_CONFIRMED"]
    verified_at: str
    verification_hash: str
    grounding_segments: List[HandoffSegment]

class MaskedBrief(BaseModel):
    brief_id: str
    task_id: str
    masked_text: str
    entities_masked: int
    segments_kept: int
    segments_dropped: int
