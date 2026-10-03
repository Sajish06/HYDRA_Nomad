from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

# --- Input Models from Teammate 1 ---
class Assignee(BaseModel):
    name: str
    role: str                       # e.g., "BACKEND", "FRONTEND", "QA"
    assigned_work: str = ""         # Specific deliverable
    deadline: Optional[str] = None  # e.g., "Friday"

class VerifiedCommitment(BaseModel):
    task_id: str                   # e.g., "TASK-001"
    raw_requirement: str = ""      # Grounded requirement statement
    clean_requirement: Optional[str] = None
    assignees: List[Assignee] = []
    evidence_context_quotes: List[str] = [] # Supporting quotes from raw transcript
    supporting_quotes: Optional[List[str]] = None
    deadline: Optional[str] = None

class MeetingHandoff(BaseModel):
    meeting_id: str
    meeting_title: str
    verified_commitments: List[VerifiedCommitment]


# --- Downstream Agent-Facing Models (Zero Leaks, Pure Technical Specs) ---
class AgentTaskPayload(BaseModel):
    """
    The ONLY payload that reaches downstream AI coding agents.
    Contains strictly the minimum necessary technical information.
    Zero business secrets, zero conversational banter.
    """
    task_id: str
    intentions: List[str] = Field(
        description="High-level technical objective."
    )
    things_to_implement: List[str] = Field(
        description="Normalized, structured assignments per discipline without raw dialogue quotes."
    )
    technical_context: List[str] = Field(
        default_factory=list,
        description="Normalized technical prerequisites and constraints."
    )
    deadline: Optional[str] = None
    business_context: List[str] = Field(
        default_factory=list,
        description="Business context kept locally for reference and evaluation, never dispatched to coding agent."
    )


class AgentRoleBrief(BaseModel):
    """Role-specific brief for individual discipline agents (Backend, Frontend, QA)."""
    brief_id: str
    task_id: str
    meeting_id: str
    role: str                       # "BACKEND", "FRONTEND", "QA"
    assignee_name: str
    actionable_deliverables: List[str]
    technical_context: List[str]
    deadline: Optional[str] = None


class PersonWorkPacket(BaseModel):
    """
    Consolidated, privacy-masked work packet assigned to a specific team member.
    Aggregates all deliverables, technical constraints, and deadlines across tasks.
    """
    person_name: str
    role: str
    meeting_id: str
    assigned_deliverables: List[str] = []
    technical_context: List[str] = []
    deadlines: List[str] = []
    markdown_path: Optional[str] = None


# --- Internal Privacy & Audit Models (Stays Strictly Local, Never Sent to Downstream AI) ---
class AuditEntry(BaseModel):
    category: str
    reason: str
    source: Literal["semantic_model", "deterministic_rule"]
    value: str

class InternalAuditRecord(BaseModel):
    task_id: str
    confidential_context_detected: bool = False
    business_context: List[str] = Field(
        default_factory=list,
        description="Non-leaked commercial, strategic, and operational context stored locally for history/evaluation."
    )
    isolated_business_secrets: List[AuditEntry] = Field(
        default_factory=list,
        description="Business secrets (M&A, strategy, expansion) isolated and kept strictly internal with reasoning."
    )
    sanitized_pii_entities: List[AuditEntry] = Field(
        default_factory=list,
        description="PII or secret tokens masked into local vault."
    )
    token_vault_session_id: str


class ProcessingResult(BaseModel):
    meeting_id: str
    meeting_title: str
    agent_payloads: List[AgentTaskPayload]
    role_briefs: List[AgentRoleBrief]
    person_packets: List[PersonWorkPacket] = []
    audit_records: List[InternalAuditRecord]
    markdown_path: Optional[str] = None
    vault_path: Optional[str] = None
    final_prompt_markdown: Optional[str] = None
    final_prompt_json: Optional[Dict[str, Any]] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "agent_payloads_generated": len(self.agent_payloads),
            "role_briefs_generated": len(self.role_briefs),
            "people_assigned": len(self.person_packets),
            "business_secrets_isolated": sum(len(a.isolated_business_secrets) for a in self.audit_records),
            "markdown_output": self.markdown_path,
            "vault_file": self.vault_path
        }

