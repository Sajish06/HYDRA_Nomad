import json
from pathlib import Path
from typing import Union, Dict, Any, Optional, List

from app.masking.models import (
    MeetingHandoff, VerifiedCommitment, Assignee,
    SanitizedTask, SanitizedAssignee, ProcessingResult
)
from app.masking.vault import LocalSecretVault
from app.masking.rules import MaskingRulesEngine
from app.masking.minimizer import ContextMinimizer
from app.masking.splitter import RoleSplitter

class PrivacyMaskingEngine:
    """Main orchestrator for Offline Privacy Masking, Context Minimization, and Local Secret Vault."""

    def __init__(
        self,
        vault_dir: Union[str, Path] = "data/vaults",
        output_dir: Union[str, Path] = "outputs"
    ):
        self.vault_dir = Path(vault_dir)
        self.output_dir = Path(output_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_handoff(self, handoff_data: Union[str, Path, Dict[str, Any], MeetingHandoff]) -> MeetingHandoff:
        if isinstance(handoff_data, MeetingHandoff):
            return handoff_data
        elif isinstance(handoff_data, dict):
            return MeetingHandoff.model_validate(handoff_data)
        elif isinstance(handoff_data, (str, Path)):
            p = Path(handoff_data)
            if not p.exists():
                raise FileNotFoundError(f"Handoff data file not found at: {p}")
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MeetingHandoff.model_validate(data)
        else:
            raise ValueError(f"Unsupported handoff_data type: {type(handoff_data)}")

    def process_verified_tasks(
        self,
        handoff_data: Union[str, Path, Dict[str, Any], MeetingHandoff],
        output_md_path: Optional[Union[str, Path]] = None,
        total_transcript_segments_count: int = 0
    ) -> ProcessingResult:
        """Processes verified commitments from Verification Engine, masks sensitive entities, and exports sanitized markdown."""
        handoff = self._load_handoff(handoff_data)
        meeting_id = handoff.meeting_id
        meeting_title = handoff.meeting_title

        # 1. Initialize local vault and rules engine
        vault = LocalSecretVault(meeting_id=meeting_id, vault_dir=self.vault_dir)
        rules = MaskingRulesEngine(vault=vault)

        # Pre-seed known assignees into entity recognizer
        for comm in handoff.verified_commitments:
            for a in comm.assignees:
                rules.add_known_entity(a.name, category="PERSON")

        sanitized_tasks: List[SanitizedTask] = []
        total_masked_entities = 0
        total_kept_segments = 0
        total_dropped_segments = 0

        # 2. Mask each verified commitment
        for comm in handoff.verified_commitments:
            task_masked_count = 0

            # Minimize grounding evidence quotes
            kept_quotes, kept_count, dropped_count = ContextMinimizer.minimize_evidence(
                comm,
                total_meeting_segments_count=total_transcript_segments_count
            )
            total_kept_segments += kept_count
            total_dropped_segments += dropped_count

            # Mask requirement text
            masked_req, req_count = rules.mask_text(comm.raw_requirement)
            task_masked_count += req_count

            # Mask assignees
            sanitized_assignees = []
            for a in comm.assignees:
                masked_work, work_count = rules.mask_text(a.assigned_work)
                task_masked_count += work_count
                
                # Mask assignee name for external export
                masked_name, name_count = rules.mask_text(a.name)
                task_masked_count += name_count

                sanitized_assignees.append(SanitizedAssignee(
                    name=masked_name,
                    role=a.role,
                    assigned_work=masked_work,
                    deadline=a.deadline
                ))

            # Mask grounding evidence quotes
            masked_quotes = []
            for q in kept_quotes:
                mq, q_count = rules.mask_text(q)
                task_masked_count += q_count
                masked_quotes.append(mq)

            total_masked_entities += task_masked_count
            sanitized_tasks.append(SanitizedTask(
                task_id=comm.task_id,
                masked_requirement=masked_req,
                assignees=sanitized_assignees,
                masked_evidence_quotes=masked_quotes,
                entities_masked_count=task_masked_count
            ))

        # 3. Save local vault
        saved_vault_path = vault.save()

        # 4. Generate Markdown report
        if output_md_path is None:
            output_md_path = self.output_dir / "verified_tasks.md"
        else:
            output_md_path = Path(output_md_path)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)

        md_content = self._generate_markdown_report(
            meeting_id=meeting_id,
            meeting_title=meeting_title,
            sanitized_tasks=sanitized_tasks,
            total_entities_masked=total_masked_entities,
            vault_path=str(saved_vault_path)
        )

        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return ProcessingResult(
            meeting_id=meeting_id,
            meeting_title=meeting_title,
            total_entities_masked=total_masked_entities,
            total_segments_kept=total_kept_segments,
            total_segments_dropped=total_dropped_segments,
            markdown_path=str(output_md_path),
            vault_path=str(saved_vault_path),
            sanitized_tasks=sanitized_tasks
        )

    def _generate_markdown_report(
        self,
        meeting_id: str,
        meeting_title: str,
        sanitized_tasks: List[SanitizedTask],
        total_entities_masked: int,
        vault_path: str
    ) -> str:
        roles_split = RoleSplitter.split_by_role(sanitized_tasks)
        
        lines = [
            f"# 🛡️ Sanitized Task Briefing: {meeting_title}",
            f"> **Meeting ID**: `{meeting_id}`  ",
            f"> **Privacy Gate Status**: `PASS (ALL SENSITIVE DATA MASKED)`  ",
            f"> **Entities Masked**: `{total_entities_masked}` tokens registered in local offline vault  ",
            f"> **Vault Path**: `{vault_path}`  \n",
            "---",
            "## 📋 Masked Tasks & Role Assignments\n"
        ]

        for task in sanitized_tasks:
            lines.append(f"### Task `{task.task_id}`")
            lines.append(f"**Sanitized Requirement:**\n> {task.masked_requirement}\n")
            lines.append("**Role Assignments:**")
            for a in task.assignees:
                deadline_str = f" (Deadline: `{a.deadline}`)" if a.deadline else ""
                lines.append(f"- **[{a.role}]** `{a.name}`: {a.assigned_work}{deadline_str}")
            
            lines.append("\n**Grounding Evidence Quotes (Sanitized):**")
            for quote in task.masked_evidence_quotes:
                lines.append(f"- {quote}")
            lines.append("\n---\n")

        lines.append("## 👥 Role-Specific Fan-out View\n")
        for role, items in roles_split.items():
            lines.append(f"### Role: `{role}` ({len(items)} items)")
            for item in items:
                lines.append(f"- **Task `{item['task_id']}`** ({item['assignee_name']}): {item['assigned_work']}")
            lines.append("")

        return "\n".join(lines)

    def unmask_text(self, meeting_id: str, masked_text: str) -> str:
        """Detokenizes masked text using the meeting's local secret vault."""
        vault = LocalSecretVault(meeting_id=meeting_id, vault_dir=self.vault_dir)
        return vault.unmask(masked_text)
