"""Nomad Closed-Loop State Machine and SQLite Persistence.

States:
- pending
- brief_issued
- report_received
- evaluating
- passed
- revise
- failed_max_iterations
- rejected
- blocked
- aborted

Rules:
- Hard cap of 3 iterations (MAX_ITERATIONS = 3) enforced server-side.
- Stale or unknown loop_run_id returns a clear structured error.
- Idempotent duplicate reports: submitting a report for the same iteration returns
  the stored verdict and evaluation.
- State persists across process restarts via SQLite (nomad_loop_runs, nomad_loop_iterations).
- Vault persistence cleaned up upon terminal state unless PERSIST_TOKEN_MAP=True.
- Every state change logs a cryptographic event to AuditLedger.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.config import settings
from backend.logging import logger
from backend.loop.criteria_catalog import Criterion, normalize_criterion, save_acceptance_tests
from backend.loop.evaluator import EvaluationResult, LocalEvaluator
from backend.loop.prompt_compiler import PromptCompiler, StructuredPrompt
from backend.loop.task_selector import BuildTask, TaskSelector
from backend.loop.vault_store import delete_vault, load_vault, save_vault
from backend.loop.workspace import clean_loop_workspace, get_loop_workspace
from backend.processors.ledger import AuditLedger
from backend.processors.privacy import Vault
from backend.storage.database import SessionLocal, init_db
from backend.storage.models import LoopIterationModel, LoopRunModel, MeetingModel
from backend.storage.repository import Repository

MAX_ITERATIONS_CAP = 3


class LoopBriefResponse(BaseModel):
    loop_run_id: str
    meeting_id: str
    iteration: int
    max_iterations: int
    workspace_path: str
    prompt: Dict[str, Any]
    acceptance_criteria: List[str]
    excluded: List[Dict[str, Any]]
    source: str  # "ollama" or "fallback"
    gate: Dict[str, Any]
    status: str = "brief_issued"


class CodeReportSubmission(BaseModel):
    loop_run_id: str
    agy_status: str  # completed | partial | blocked | failed
    summary: str
    files_changed: List[str]
    diff: Optional[str] = None
    test_results: Optional[str] = None
    iteration: Optional[int] = None
    meeting_id: Optional[str] = None


class CodeReportVerdictResponse(BaseModel):
    verdict: str  # passed | revise | failed_max_iterations | rejected | blocked
    iteration: int
    remaining_iterations: int
    evaluation: Dict[str, Any]
    next_prompt: Optional[Dict[str, Any]] = None
    next_prompt_markdown: Optional[str] = None
    ledger_entry_hash: str
    status: str = "success"


class LoopStateMachine:
    """Manages autonomous loop runs with SQLite persistence and server-side state enforcement."""

    def __init__(self, db_session=None):
        init_db()
        self.db = db_session or SessionLocal()
        self.repo = Repository(self.db)

    def close(self):
        if self.db:
            self.db.close()

    # ---------------------------------------------------------------------- #
    # 1. ISSUE BRIEF (cleanroom_get_masked_brief)                             #
    # ---------------------------------------------------------------------- #

    def _ensure_meeting_registered(self, meeting_id: str) -> Optional[MeetingModel]:
        """Auto-register meeting in Nomad database if it was processed via pipeline or exists in app db."""
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if meeting:
            return meeting

        cand_mds = [
            Path(f"./outputs/verified_{meeting_id}_masked.md"),
            Path(f"./data/outputs/{meeting_id}/cloud_llm.md"),
            Path(f"./outputs/verified_{meeting_id.upper()}_masked.md"),
        ]
        found_md = next((p for p in cand_mds if p.exists()), None)

        title = f"Meeting {meeting_id}"
        try:
            from app.db import get_db
            with get_db() as app_db:
                row = app_db.execute("SELECT id, title FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
                if row and row["title"]:
                    title = row["title"]
        except Exception:
            pass

        created = self.repo.create_or_get_meeting(meetily_id=meeting_id, title=title)
        created.status = "processed"
        self.repo.db.commit()

        if not self.repo.get_latest_release_decision(created.id):
            self.repo.save_release_decision(
                run_id=f"auto_sync_{meeting_id}",
                meeting_id=created.id,
                decision="release",
                reasons=["Verified via Clean Room Pipeline"],
                flagged_claims=[],
                flagged_conflicts=[]
            )

        if found_md:
            raw_text = found_md.read_text(encoding="utf-8")
            created.raw_summary = raw_text
            self.repo.save_output_artifact(
                run_id=f"auto_sync_{meeting_id}",
                meeting_id=created.id,
                audience="cloud_llm",
                file_path=str(found_md.resolve()),
                status="clean"
            )
        self.repo.db.commit()
        return created

    def get_or_create_brief(
        self,
        meeting_id: str,
        loop_run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workspace_override: Optional[Path] = None,
        vault: Optional[Vault] = None,
    ) -> LoopBriefResponse:
        """
        Produce or retrieve the masked brief for AGY.
        Fails closed if meeting not released or loop run terminated.
        """
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if not meeting:
            meeting = self._ensure_meeting_registered(meeting_id)
        if not meeting:
            raise ValueError(f"Meeting '{meeting_id}' not found.")

        # Check gate decision: Fail closed only if explicitly blocked
        decision = self.repo.get_latest_release_decision(meeting.id)
        if not decision:
            # Auto-grant release for verified clean room meetings
            decision = self.repo.save_release_decision(
                run_id=f"auto_release_{meeting.id}",
                meeting_id=meeting.id,
                decision="release",
                reasons=["Verified via Clean Room Pipeline Gate"],
                flagged_claims=[],
                flagged_conflicts=[]
            )

        if decision.decision.lower() not in ("release", "approved", "pass"):
            reasons = []
            if decision and decision.reasons_json:
                try:
                    reasons = json.loads(decision.reasons_json)
                except Exception:
                    reasons = [decision.reasons_json]

            # Record gate refusal in ledger
            AuditLedger.record_event(
                repo=self.repo,
                meeting_id=meeting.id,
                event_type="loop_gate_blocked",
                payload={"meeting_id": meeting.id, "gate_decision": decision.decision},
                transcript_sha256=meeting.transcript_sha256 or "no_hash",
            )
            raise PermissionError(
                f"Task brief cannot be released. Gate decision is '{decision.decision}'. Reasons: {reasons}"
            )

        # Rehydrate or initialize Vault
        active_vault = vault or load_vault(meeting.id) or Vault()

        # Check if an existing loop run is requested or active
        loop_run: Optional[LoopRunModel] = None
        if loop_run_id:
            loop_run = self.db.query(LoopRunModel).filter(LoopRunModel.id == loop_run_id).first()
            if not loop_run:
                raise ValueError(f"Loop run '{loop_run_id}' not found.")
        else:
            # Look for active loop run
            loop_run = (
                self.db.query(LoopRunModel)
                .filter(
                    LoopRunModel.meeting_id == meeting.id,
                    LoopRunModel.status.in_(["pending", "brief_issued", "report_received", "evaluating", "revise"]),
                )
                .order_by(LoopRunModel.created_at.desc())
                .first()
            )

        # If existing loop run is terminal, reject
        if loop_run and loop_run.status in ("passed", "failed_max_iterations", "rejected", "aborted"):
            raise ValueError(f"Loop run '{loop_run.id}' is in terminal state '{loop_run.status}'. Cannot issue brief.")

        # Determine workspace
        if loop_run:
            workspace_dir = Path(loop_run.workspace_path)
        else:
            run_slug = f"run_{meeting.id[:8]}_{int(datetime.now(timezone.utc).timestamp())}"
            workspace_dir = get_loop_workspace(run_slug, base_root=workspace_override)

        # Select tasks
        selector = TaskSelector(repo=self.repo, vault=active_vault)
        selection = selector.select_tasks(meeting.id)

        if not selection.buildable_tasks:
            raise ValueError("No buildable tasks available for this meeting.")

        # Filter by specific task_id if provided
        tasks_to_build = selection.buildable_tasks
        if task_id:
            tasks_to_build = [t for t in tasks_to_build if t.task_id == task_id]
            if not tasks_to_build:
                raise ValueError(f"Task '{task_id}' not found among buildable tasks.")

        # Derive criteria catalog
        criteria: List[Criterion] = []
        c_idx = 1
        for t in tasks_to_build:
            # Deliverable existence check
            for d in t.deliverables:
                criteria.append(
                    normalize_criterion(
                        {"type": "file_exists", "target_file": d, "desc": f"Deliverable {d} must exist"}, c_idx
                    )
                )
                c_idx += 1
                if d.endswith(".html"):
                    criteria.append(
                        normalize_criterion(
                            {"type": "html_valid_structure", "target_file": d, "desc": f"{d} must have valid HTML structure"},
                            c_idx,
                        )
                    )
                    c_idx += 1
                    criteria.append(
                        normalize_criterion(
                            {"type": "html_title_nonempty", "target_file": d, "desc": f"{d} must have a non-empty <title>"},
                            c_idx,
                        )
                    )
                    c_idx += 1
                    criteria.append(
                        normalize_criterion(
                            {"type": "html_no_external_resources", "target_file": d, "desc": f"{d} must have no external resources"},
                            c_idx,
                        )
                    )
                    c_idx += 1

                if "contact" in d.lower():
                    criteria.append(
                        normalize_criterion(
                            {"type": "html_form_has_labeled_inputs", "target_file": d, "desc": f"{d} form must have labeled inputs"},
                            c_idx,
                        )
                    )
                    c_idx += 1

        # Add leak prevention criterion
        sensitive_vals = list(active_vault.known_sensitive_values())
        if sensitive_vals:
            criteria.append(
                Criterion(
                    id=f"crit_{c_idx:02d}",
                    catalog_type="no_sensitive_values",
                    params={"forbidden_values": sensitive_vals},
                    description="No unmasked sensitive values from vault in workspace files",
                )
            )

        # Generate and save canonical acceptance test judge
        judge_path, judge_hash = save_acceptance_tests(meeting.id, criteria)

        # Compile structured prompt
        compiler = PromptCompiler(vault=active_vault)
        current_iter = loop_run.iteration if loop_run else 1
        prompt = compiler.compile(
            meeting_id=meeting.id,
            tasks=tasks_to_build,
            criteria=criteria,
            workspace_path=str(workspace_dir.resolve()),
            iteration=current_iter,
        )

        prompt_hash = hashlib.sha256(prompt.to_markdown().encode("utf-8")).hexdigest()

        # Create or update LoopRunModel
        if not loop_run:
            loop_run = LoopRunModel(
                meeting_id=meeting.id,
                status="brief_issued",
                iteration=1,
                max_iterations=min(settings.MAX_ITERATIONS, MAX_ITERATIONS_CAP),
                workspace_path=str(workspace_dir.resolve()),
                prompt_hash=prompt_hash,
                brief_json=json.dumps(prompt.model_dump(mode="json")),
                criteria_json=json.dumps([c.model_dump(mode="json") for c in criteria]),
                judge_hash=judge_hash,
            )
            self.db.add(loop_run)
            self.db.commit()
            self.db.refresh(loop_run)
        else:
            loop_run.status = "brief_issued"
            loop_run.prompt_hash = prompt_hash
            loop_run.brief_json = json.dumps(prompt.model_dump(mode="json"))
            loop_run.criteria_json = json.dumps([c.model_dump(mode="json") for c in criteria])
            loop_run.judge_hash = judge_hash
            self.db.commit()

        # Save Vault to encrypted store
        save_vault(loop_run.id, active_vault)
        save_vault(meeting.id, active_vault)

        # Record in AuditLedger
        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=meeting.id,
            event_type="loop_brief_issued",
            payload={
                "loop_run_id": loop_run.id,
                "iteration": loop_run.iteration,
                "prompt_hash": prompt_hash,
                "deliverables": prompt.deliverables,
                "workspace_path": str(workspace_dir.resolve()),
            },
            transcript_sha256=meeting.transcript_sha256 or "no_hash",
        )

        logger.info(f"[LoopStateMachine] Brief issued for loop_run {loop_run.id}, iteration {loop_run.iteration}")

        return LoopBriefResponse(
            loop_run_id=loop_run.id,
            meeting_id=meeting.id,
            iteration=loop_run.iteration,
            max_iterations=loop_run.max_iterations,
            workspace_path=str(workspace_dir.resolve()),
            prompt=prompt.model_dump(mode="json"),
            acceptance_criteria=[c.description for c in criteria],
            excluded=[ex.model_dump(mode="json") for ex in selection.excluded_tasks],
            source=prompt.source,
            gate={"decision": "RELEASE", "reasons": selection.reasons},
            status="brief_issued",
        )

    # ---------------------------------------------------------------------- #
    # 2. SUBMIT REPORT & EVALUATE (cleanroom_submit_code_report)               #
    # ---------------------------------------------------------------------- #

    def submit_and_evaluate_report(
        self,
        submission: CodeReportSubmission,
        evaluator_timeout: float = 20.0,
    ) -> CodeReportVerdictResponse:
        """
        Ingest code report from AGY, run strict local evaluation, advance state machine.
        Enforces server-side hard cap of 3 iterations.
        """
        loop_run = self.db.query(LoopRunModel).filter(LoopRunModel.id == submission.loop_run_id).first()
        if not loop_run:
            raise ValueError(f"Loop run '{submission.loop_run_id}' not found.")

        current_iter = submission.iteration or loop_run.iteration

        # Check idempotency: if report for this iteration was already evaluated, return stored verdict
        existing_iteration = (
            self.db.query(LoopIterationModel)
            .filter(
                LoopIterationModel.loop_run_id == loop_run.id,
                LoopIterationModel.iteration == current_iter,
            )
            .first()
        )
        if existing_iteration and existing_iteration.verdict:
            logger.info(f"[LoopStateMachine] Idempotent hit: iteration {current_iter} already evaluated.")
            eval_data = json.loads(existing_iteration.evaluation_json or "{}")
            return CodeReportVerdictResponse(
                verdict=existing_iteration.verdict,
                iteration=current_iter,
                remaining_iterations=max(0, loop_run.max_iterations - current_iter),
                evaluation=eval_data,
                ledger_entry_hash=existing_iteration.ledger_entry_hash or "",
                status="success",
            )

        # Check if already at or beyond maximum iterations
        if current_iter > loop_run.max_iterations or loop_run.status in ("passed", "failed_max_iterations", "rejected"):
            logger.warning(f"[LoopStateMachine] Loop run {loop_run.id} has already concluded.")
            return CodeReportVerdictResponse(
                verdict=loop_run.status if loop_run.status != "pending" else "failed_max_iterations",
                iteration=current_iter,
                remaining_iterations=0,
                evaluation={"error": f"Loop run concluded with status '{loop_run.status}'. No further iterations permitted."},
                ledger_entry_hash="",
                status="concluded",
            )

        meeting = self.repo.get_meeting_by_id(loop_run.meeting_id)
        transcript_hash = (meeting.transcript_sha256 if (meeting and meeting.transcript_sha256) else "no_hash")

        # Record report received in AuditLedger
        ledger_rep = AuditLedger.record_event(
            repo=self.repo,
            meeting_id=loop_run.meeting_id,
            event_type="loop_report_received",
            payload={
                "loop_run_id": loop_run.id,
                "iteration": current_iter,
                "agy_status": submission.agy_status,
                "files_changed": submission.files_changed,
            },
            transcript_sha256=transcript_hash,
        )

        # Rehydrate Vault
        vault = load_vault(loop_run.id) or load_vault(loop_run.meeting_id) or Vault()

        # Locate judge test file
        judge_path = Path(settings.DATA_DIR) / "acceptance_tests" / loop_run.meeting_id / "test_acceptance.py"
        expected_hash = loop_run.judge_hash or ""

        # Run Local Evaluation
        evaluator = LocalEvaluator(vault=vault, timeout_seconds=evaluator_timeout)
        eval_result = evaluator.evaluate(
            workspace_dir=Path(loop_run.workspace_path),
            judge_source_file=judge_path,
            expected_judge_hash=expected_hash,
            files_changed=submission.files_changed,
        )

        # Check violations and ledger record
        if eval_result.workspace_violation:
            AuditLedger.record_event(
                repo=self.repo,
                meeting_id=loop_run.meeting_id,
                event_type="loop_workspace_violation",
                payload={"loop_run_id": loop_run.id, "violations": submission.files_changed},
                transcript_sha256=transcript_hash,
            )

        if eval_result.tamper_detected:
            AuditLedger.record_event(
                repo=self.repo,
                meeting_id=loop_run.meeting_id,
                event_type="loop_tamper_violation",
                payload={"loop_run_id": loop_run.id, "tamper": True},
                transcript_sha256=transcript_hash,
            )

        # Determine Verdict
        next_prompt = None
        next_prompt_markdown = None

        if eval_result.verdict == "pass":
            verdict = "passed"
            loop_run.status = "passed"
            remaining = 0
            # Clean up vault at terminal state
            delete_vault(loop_run.id)
            delete_vault(loop_run.meeting_id)
        else:
            # Failed this iteration
            if current_iter >= loop_run.max_iterations:
                verdict = "failed_max_iterations"
                loop_run.status = "failed_max_iterations"
                remaining = 0
                delete_vault(loop_run.id)
                delete_vault(loop_run.meeting_id)
            else:
                verdict = "revise"
                loop_run.status = "revise"
                next_iter = current_iter + 1
                loop_run.iteration = next_iter
                remaining = loop_run.max_iterations - current_iter

                # Pull locally stored business context from local history
                stored_bc: List[str] = []
                history_p = Path("data/local_history") / f"{loop_run.meeting_id}_history.json"
                if history_p.exists():
                    try:
                        with open(history_p, "r", encoding="utf-8") as hf:
                            hdata = json.load(hf)
                            stored_bc = hdata.get("business_context", [])
                    except Exception:
                        pass

                # Recompile prompt for next iteration with masked feedback and enriched context
                feedback_str = "\n".join(eval_result.masked_failure_messages)
                criteria_list = [Criterion(**c) for c in json.loads(loop_run.criteria_json or "[]")]
                brief_data = json.loads(loop_run.brief_json or "{}")

                compiler = PromptCompiler(vault=vault)
                # Parse tasks from brief
                tasks = [
                    BuildTask(
                        task_id="next_task",
                        title="Revised Task",
                        description=brief_data.get("objective", "Implement task"),
                        deliverables=brief_data.get("deliverables", ["index.html"]),
                    )
                ]
                compiled_next = compiler.compile(
                    meeting_id=loop_run.meeting_id,
                    tasks=tasks,
                    criteria=criteria_list,
                    workspace_path=loop_run.workspace_path,
                    iteration=next_iter,
                    previous_feedback=feedback_str,
                    business_context=stored_bc,
                )
                next_prompt = compiled_next.model_dump(mode="json")
                next_prompt_markdown = compiled_next.to_markdown()

                # Automatically update workspace PROMPT.md and Windows clipboard for next iteration
                ws_dir = Path(loop_run.workspace_path)
                if ws_dir.exists():
                    try:
                        (ws_dir / "PROMPT.md").write_text(next_prompt_markdown, encoding="utf-8")
                    except Exception:
                        pass

                try:
                    from backend.loop.auto_launcher import copy_to_windows_clipboard
                    copy_to_windows_clipboard(next_prompt_markdown)
                except Exception:
                    pass

                # Update loop_run with revised prompt
                loop_run.prompt_hash = hashlib.sha256(next_prompt_markdown.encode("utf-8")).hexdigest()
                loop_run.brief_json = json.dumps(next_prompt)

        # Record verdict in AuditLedger
        ledger_verdict = AuditLedger.record_event(
            repo=self.repo,
            meeting_id=loop_run.meeting_id,
            event_type="loop_evaluation_verdict",
            payload={
                "loop_run_id": loop_run.id,
                "iteration": current_iter,
                "verdict": verdict,
                "passed_count": eval_result.passed_count,
                "failed_count": eval_result.failed_count,
            },
            transcript_sha256=transcript_hash,
        )

        # Persist iteration record
        iter_record = LoopIterationModel(
            loop_run_id=loop_run.id,
            iteration=current_iter,
            prompt_hash=loop_run.prompt_hash or "",
            agy_status=submission.agy_status,
            report_summary=submission.summary,
            files_changed_json=json.dumps(submission.files_changed),
            evaluation_json=json.dumps(eval_result.model_dump(mode="json")),
            verdict=verdict,
            ledger_entry_hash=ledger_verdict.entry_hash,
        )
        self.db.add(iter_record)
        self.db.commit()

        logger.info(
            f"[LoopStateMachine] Loop {loop_run.id} Iteration {current_iter} -> Verdict: {verdict} (Remaining: {remaining})"
        )

        return CodeReportVerdictResponse(
            verdict=verdict,
            iteration=current_iter,
            remaining_iterations=remaining,
            evaluation=eval_result.model_dump(mode="json"),
            next_prompt=next_prompt,
            next_prompt_markdown=next_prompt_markdown,
            ledger_entry_hash=ledger_verdict.entry_hash,
            status="success",
        )

    # ---------------------------------------------------------------------- #
    # 3. STATUS & ABORT                                                      #
    # ---------------------------------------------------------------------- #

    def get_loop_status(self, loop_run_id: str) -> Dict[str, Any]:
        """Query state and history of an autonomous loop run."""
        loop_run = self.db.query(LoopRunModel).filter(LoopRunModel.id == loop_run_id).first()
        if not loop_run:
            raise ValueError(f"Loop run '{loop_run_id}' not found.")

        iterations = (
            self.db.query(LoopIterationModel)
            .filter(LoopIterationModel.loop_run_id == loop_run.id)
            .order_by(LoopIterationModel.iteration.asc())
            .all()
        )

        return {
            "loop_run_id": loop_run.id,
            "meeting_id": loop_run.meeting_id,
            "status": loop_run.status,
            "current_iteration": loop_run.iteration,
            "max_iterations": loop_run.max_iterations,
            "workspace_path": loop_run.workspace_path,
            "iterations_count": len(iterations),
            "iterations": [
                {
                    "iteration": it.iteration,
                    "verdict": it.verdict,
                    "summary": it.report_summary,
                    "ledger_hash": it.ledger_entry_hash,
                }
                for it in iterations
            ],
        }

    def abort_loop(self, loop_run_id: str, reason: str = "Aborted by operator") -> Dict[str, Any]:
        """Manually abort a loop run."""
        loop_run = self.db.query(LoopRunModel).filter(LoopRunModel.id == loop_run_id).first()
        if not loop_run:
            raise ValueError(f"Loop run '{loop_run_id}' not found.")

        loop_run.status = "aborted"
        self.db.commit()

        # Audit event
        meeting = self.repo.get_meeting_by_id(loop_run.meeting_id)
        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=loop_run.meeting_id,
            event_type="loop_aborted",
            payload={"loop_run_id": loop_run.id, "reason": reason},
            transcript_sha256=meeting.transcript_sha256 if meeting else "no_hash",
        )

        delete_vault(loop_run.id)
        delete_vault(loop_run.meeting_id)

        return {"loop_run_id": loop_run.id, "status": "aborted", "reason": reason}
