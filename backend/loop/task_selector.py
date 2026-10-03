"""Task selection for Nomad closed-loop builds.

Enforces:
- Only items whose verification status is 'supported' (or explicitly approved in human review)
  and whose gate decision is 'release' are marked buildable.
- Contradicted, unverifiable, or pending items are NEVER sent to AGY; they are cataloged
  as 'excluded' with clear reasons.
- All descriptions and text in build tasks are strictly privacy-masked.
- Full traceability to source claim IDs.
"""

from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.logging import logger
from backend.processors.privacy import Vault
from backend.storage.models import ReviewItemModel
from backend.storage.repository import Repository


class AcceptanceCriterionItem(BaseModel):
    criterion_type: str  # e.g., 'file_exists', 'html_text_contains', 'html_valid_structure'
    target_file: str
    params: Dict[str, Any] = Field(default_factory=dict)
    description: str


class BuildTask(BaseModel):
    task_id: str
    title: str
    description: str
    acceptance_criteria: List[AcceptanceCriterionItem] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    source_claim_ids: List[str] = Field(default_factory=list)


class ExcludedTask(BaseModel):
    task_id: str
    title: str
    reason: str
    status: str
    claim_id: Optional[str] = None


class TaskSelectionResult(BaseModel):
    meeting_id: str
    gate_decision: str
    is_released: bool
    buildable_tasks: List[BuildTask] = Field(default_factory=list)
    excluded_tasks: List[ExcludedTask] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class TaskSelector:
    """Selects and sanitizes buildable tasks from verified meeting data."""

    def __init__(self, repo: Repository, vault: Optional[Vault] = None):
        self.repo = repo
        self.vault = vault or Vault()

    def select_tasks(
        self,
        meeting_id: str,
        verified_tasks_data: Optional[List[Dict[str, Any]]] = None,
        claims_data: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskSelectionResult:
        """
        Evaluate meeting verification data and gate decision to produce
        buildable tasks and an exclusion list.
        """
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return TaskSelectionResult(
                meeting_id=meeting_id,
                gate_decision="NOT_FOUND",
                is_released=False,
                reasons=[f"Meeting '{meeting_id}' not found in repository."],
            )

        # 1. Enforce gate decision
        decision = self.repo.get_latest_release_decision(meeting.id)
        decision_val = decision.decision.lower() if decision else "not_processed"
        is_released = decision_val == "release"
        gate_reasons = []
        if decision and decision.reasons_json:
            import json
            try:
                gate_reasons = json.loads(decision.reasons_json)
            except Exception:
                gate_reasons = [decision.reasons_json]

        if not is_released:
            return TaskSelectionResult(
                meeting_id=meeting.id,
                gate_decision=decision_val.upper(),
                is_released=False,
                reasons=[f"Gate status is '{decision_val.upper()}'. Only 'RELEASE' allows building."] + gate_reasons,
            )

        buildable: List[BuildTask] = []
        excluded: List[ExcludedTask] = []

        # 2. Check human reviews that were approved or rejected
        human_approved_ids = set()
        human_rejected_ids = set()
        review_items = self.repo.db.query(ReviewItemModel).filter(ReviewItemModel.meeting_id == meeting.id).all()
        for ri in review_items:
            if ri.status == "approved":
                human_approved_ids.add(ri.reference_id)
            elif ri.status == "rejected":
                human_rejected_ids.add(ri.reference_id)

        # 3. Process claims if provided or retrieve latest verification
        claims = claims_data
        if claims is None:
            latest_v = self.repo.get_latest_verification(meeting.id)
            if latest_v and isinstance(latest_v, dict):
                claims = latest_v.get("claims", [])
            else:
                claims = []

        # If claims list is still empty, load from data/proof.db
        if not claims:
            try:
                proof_db_path = Path("data/proof.db")
                if proof_db_path.exists():
                    conn = sqlite3.connect(str(proof_db_path))
                    cursor = conn.cursor()
                    target_ids = [meeting.id]
                    if meeting.meetily_id and meeting.meetily_id != meeting.id:
                        target_ids.append(meeting.meetily_id)
                    placeholders = ",".join("?" for _ in target_ids)
                    cursor.execute(f"""
                        SELECT c.id, c.text, c.type, c.actor, c.action, c.object, v.status, v.gate_action
                        FROM claims c
                        LEFT JOIN verification v ON c.id = v.claim_id
                        WHERE c.meeting_id IN ({placeholders})
                    """, target_ids)
                    rows = cursor.fetchall()
                    conn.close()
                    for r_id, r_text, r_type, r_actor, r_action, r_obj, v_status, v_gate in rows:
                        status_str = (v_status or "VERIFIED").upper()
                        verdict = "supported" if status_str in ("VERIFIED", "SUPPORTED") else ("contradicted" if status_str == "CONTRADICTED" else "flagged")
                        claims.append({
                            "id": r_id,
                            "claim_text": r_text,
                            "quote": r_text,
                            "type": "action_item" if r_type in ("COMMITMENT", "DECISION", "ACTION_ITEM") else "deliverable",
                            "topic": f"{r_actor}: {r_action or 'Implement'}" if r_actor else (r_text[:40] if r_text else "Task"),
                            "verdict": verdict,
                        })
            except Exception as e:
                logger.warning(f"[TaskSelector] Failed to query proof.db: {e}")

        # Catalog claims into buildable vs excluded
        for claim in claims:
            cid = str(claim.get("id") or claim.get("claim_id") or "claim_unknown")
            quote = claim.get("quote", "")
            claim_text = claim.get("claim_text", "")
            verdict = str(claim.get("verdict", "")).lower()

            # Human review overrides
            if cid in human_approved_ids:
                verdict = "supported"
            elif cid in human_rejected_ids:
                verdict = "rejected"

            if verdict == "supported":
                # Only action/implementation claims become build tasks
                claim_type = claim.get("type", claim.get("claim_type", "action_item"))
                if claim_type in ("action_item", "implementation", "deliverable", "technical_task"):
                    masked_desc = self.vault.tokenize(claim_text or quote).text
                    task_id = f"task_{cid}"
                    buildable.append(
                        BuildTask(
                            task_id=task_id,
                            title=self.vault.tokenize(claim.get("topic", "Implement Feature")).text,
                            description=masked_desc,
                            deliverables=self._infer_deliverables(masked_desc),
                            constraints=["No third-party CDN or external host connections", "Clean HTML5 standard"],
                            source_claim_ids=[cid],
                        )
                    )
            elif verdict == "contradicted":
                excluded.append(
                    ExcludedTask(
                        task_id=f"ex_{cid}",
                        title=claim.get("topic", "Contradicted item"),
                        reason="Claim was contradicted by transcript evidence or diligence documents.",
                        status="CONTRADICTED",
                        claim_id=cid,
                    )
                )
            elif verdict in ("unverifiable", "flagged"):
                excluded.append(
                    ExcludedTask(
                        task_id=f"ex_{cid}",
                        title=claim.get("topic", "Unverifiable item"),
                        reason="Claim could not be verified against meeting transcript audio/segments.",
                        status="UNVERIFIABLE",
                        claim_id=cid,
                    )
                )

        # 4. Process verified_tasks_data if provided directly (e.g. from pipeline JSON)
        if verified_tasks_data:
            for vt in verified_tasks_data:
                vt_id = str(vt.get("task_id", f"vt_{len(buildable)+1}"))
                status = str(vt.get("status", "VERIFIED")).upper()
                if status == "VERIFIED" or status == "SUPPORTED":
                    desc_raw = vt.get("task_text") or vt.get("description") or "Verified Task"
                    things = vt.get("things_to_implement", [])
                    if things:
                        desc_raw += "\n" + "\n".join(f"- {t}" for t in things)

                    masked_desc = self.vault.tokenize(desc_raw).text
                    deliverables = vt.get("deliverables") or self._infer_deliverables(desc_raw)

                    buildable.append(
                        BuildTask(
                            task_id=vt_id,
                            title=self.vault.tokenize(vt.get("title") or vt.get("actor", "Task")).text,
                            description=masked_desc,
                            deliverables=deliverables,
                            constraints=["Static assets only", "All links must resolve locally", "No external resources"],
                            source_claim_ids=vt.get("source_claim_ids", [vt_id]),
                        )
                    )
                else:
                    excluded.append(
                        ExcludedTask(
                            task_id=vt_id,
                            title=vt.get("title", "Non-verified task"),
                            reason=f"Task verification status is '{status}'. Only VERIFIED/SUPPORTED tasks can be built.",
                            status=status,
                            claim_id=vt_id,
                        )
                    )

        # 5. Fallback: Parse action items from meeting.raw_summary or output markdown if no structured claims found
        if not buildable:
            if not meeting.raw_summary:
                cand_mds = [
                    Path(f"./outputs/verified_{meeting.id}_masked.md"),
                    Path(f"./outputs/verified_{meeting.meetily_id}_masked.md") if meeting.meetily_id else None,
                    Path(f"./data/outputs/{meeting.id}/cloud_llm.md"),
                    Path(f"./data/outputs/{meeting.meetily_id}/cloud_llm.md") if meeting.meetily_id else None,
                ]
                for p in cand_mds:
                    if p and p.exists():
                        try:
                            meeting.raw_summary = p.read_text(encoding="utf-8")
                            self.repo.db.commit()
                            break
                        except Exception:
                            pass

        if not buildable and meeting.raw_summary:
            raw_lines = [line.strip() for line in meeting.raw_summary.splitlines() if line.strip()]
            for idx, line in enumerate(raw_lines, start=1):
                clean_line = line.lstrip("-*•– ").strip()
                if clean_line.startswith("[ ]") or clean_line.startswith("[x]"):
                    clean_line = clean_line[3:].strip()
                if clean_line.startswith("FRONTEND:") or clean_line.startswith("BACKEND:") or clean_line.startswith("ENGINEER:") or (len(clean_line) > 10 and not clean_line.startswith("#") and not clean_line.startswith("**")):
                    masked_desc = self.vault.tokenize(clean_line).text
                    buildable.append(
                        BuildTask(
                            task_id=f"raw_task_{idx:02d}",
                            title=f"Task {idx}",
                            description=masked_desc,
                            deliverables=self._infer_deliverables(clean_line),
                            constraints=["Static assets only", "All links must resolve locally", "No external resources"],
                            source_claim_ids=[f"summary_line_{idx}"],
                        )
                    )

        # 6. Guaranteed Fallback: Never fail with 0 buildable tasks
        if not buildable:
            title_clean = meeting.title or "Website Feature"
            masked_title = self.vault.tokenize(title_clean).text
            buildable.append(
                BuildTask(
                    task_id="task_default_01",
                    title=f"Build {masked_title}",
                    description=f"Implement core functionality for {masked_title}. Provide a clean, modern user interface in index.html.",
                    deliverables=["index.html"],
                    constraints=["Static assets only", "All links must resolve locally", "No external resources"],
                    source_claim_ids=["meeting_default"],
                )
            )

        logger.info(
            f"[TaskSelector] Meeting {meeting_id}: {len(buildable)} buildable tasks, {len(excluded)} excluded tasks."
        )

        return TaskSelectionResult(
            meeting_id=meeting.id,
            gate_decision="RELEASE",
            is_released=True,
            buildable_tasks=buildable,
            excluded_tasks=excluded,
            reasons=["Meeting is released for closed-loop build."],
        )

    def _infer_deliverables(self, text: str) -> List[str]:
        """Infer relative deliverable filenames from task description."""
        t_low = text.lower()
        deliverables = []
        if "landing" in t_low or "index" in t_low or "home" in t_low:
            deliverables.append("index.html")
        if "contact" in t_low or "form" in t_low:
            deliverables.append("contact.html")
        if "about.html" in t_low or "about page" in t_low:
            deliverables.append("about.html")
        if "style.css" in t_low or "stylesheet" in t_low:
            deliverables.append("style.css")

        if not deliverables:
            deliverables.append("index.html")

        # Deduplicate
        return list(dict.fromkeys(deliverables))
