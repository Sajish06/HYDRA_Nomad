from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class Assignee(BaseModel):
    name: str
    role: str  # e.g., BACKEND, FRONTEND, QA, DEVOPS, DESIGN, PRODUCT
    assigned_work: str
    deadline: Optional[str] = None

class VerifiedCommitment(BaseModel):
    task_id: str
    raw_requirement: str
    assignees: List[Assignee] = Field(default_factory=list)
    evidence_context_quotes: List[str] = Field(default_factory=list)

class MeetingHandoff(BaseModel):
    meeting_id: str
    meeting_title: str
    verified_commitments: List[VerifiedCommitment] = Field(default_factory=list)

class SanitizedAssignee(BaseModel):
    name: str
    role: str
    assigned_work: str
    deadline: Optional[str] = None

class SanitizedTask(BaseModel):
    task_id: str
    masked_requirement: str
    assignees: List[SanitizedAssignee] = Field(default_factory=list)
    masked_evidence_quotes: List[str] = Field(default_factory=list)
    entities_masked_count: int = 0

class ProcessingResult(BaseModel):
    meeting_id: str
    meeting_title: str
    total_entities_masked: int = 0
    total_segments_kept: int = 0
    total_segments_dropped: int = 0
    markdown_path: Optional[str] = None
    vault_path: Optional[str] = None
    sanitized_tasks: List[SanitizedTask] = Field(default_factory=list)
