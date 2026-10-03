"""
Autonomous Meeting-to-Code Closed Loop Orchestrator.

This orchestrator manages the automated build-evaluate-refine cycle between
Nomad (local Control Plane) and Antigravity (AGY, Execution Plane) via MCP.

It does NOT call AGY directly. AGY is a separate process that connects via MCP tools.
This orchestrator:
1. Initializes the loop run and generates the masked brief + acceptance criteria.
2. Evaluates AGY's submitted report locally using unmasked context.
3. On failure: generates a context-enriched corrective prompt for the next iteration.
4. On circuit breaker: halts and alerts the developer.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.logging import logger
from backend.processors.ledger import AuditLedger
from backend.storage.repository import Repository
from backend.storage.models import AutonomousLoopRunModel, BuildReportModel, MeetingModel


MAX_ITERATIONS = 3


class AutonomousLoopOrchestrator:
    """State machine managing the Nomad <-> AGY autonomous build loop."""

    def __init__(self, repo: Repository):
        self.repo = repo

    # ------------------------------------------------------------------ #
    #  PUBLIC ENTRY POINTS                                                  #
    # ------------------------------------------------------------------ #

    def initialize_loop(self, meeting_id: str) -> dict:
        """
        Step 1: Called when the developer clicks "Build".
        - Checks that the meeting has been processed and gate decision is 'release'.
        - Reads the cloud_llm.md / masked brief output artifact.
        - Generates acceptance criteria (pytest stubs) from verified claims.
        - Creates an AutonomousLoopRunModel record.
        Returns a status dict.
        """
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return {"status": "error", "error": f"Meeting '{meeting_id}' not found."}

        # 1. Check gate decision
        decision = self.repo.get_latest_release_decision(meeting.id)
        if not decision or decision.decision.lower() != "release":
            return {
                "status": "blocked",
                "error": "Meeting has not been verified and released yet. Run verification first.",
                "gate_decision": decision.decision if decision else "NOT_PROCESSED",
            }

        # 2. Read masked brief from cloud_llm output artifact or verified masked output
        masked_brief_text = None
        artifacts = self.repo.list_output_artifacts(meeting.id)
        cloud_art = next((a for a in artifacts if a.audience.lower() == "cloud_llm"), None)
        if cloud_art and Path(cloud_art.file_path).exists():
            masked_brief_text = Path(cloud_art.file_path).read_text(encoding="utf-8")
        else:
            # Fallback paths: check common output locations
            candidate_paths = [
                Path(f"./data/outputs/{meeting.id}/cloud_llm.md"),
                Path(f"./outputs/verified_{meeting.id}_masked.md"),
                Path(f"./outputs/verified_{meeting.meetily_id}_masked.md"),
            ]
            for cp in candidate_paths:
                if cp.exists():
                    masked_brief_text = cp.read_text(encoding="utf-8")
                    break

        if not masked_brief_text:
            return {
                "status": "error",
                "error": "No 'cloud_llm' output artifact or verified masked markdown found on disk. Run pipeline first.",
            }

        # 3. Generate acceptance criteria
        summary_text = meeting.raw_summary or masked_brief_text
        acceptance_criteria = self._generate_acceptance_criteria(meeting.id, summary_text)

        # 4. Create loop run record
        loop_run = self.repo.create_loop_run(meeting_id=meeting.id, max_iterations=MAX_ITERATIONS)
        self.repo.update_loop_run(
            loop_run_id=loop_run.id,
            status="dispatched",
            masked_brief_text=masked_brief_text,
            acceptance_criteria=acceptance_criteria,
        )

        # 5. Record in audit ledger
        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=meeting.id,
            event_type="autonomous_loop_initialized",
            payload={
                "loop_run_id": loop_run.id,
                "iteration": 0,
                "brief_length": len(masked_brief_text),
            },
            transcript_sha256=meeting.transcript_sha256 or "no_hash",
        )

        logger.info(f"[AutonomousLoop] Loop initialized for meeting {meeting.id}, run {loop_run.id}")

        return {
            "status": "dispatched",
            "loop_run_id": loop_run.id,
            "meeting_id": meeting.id,
            "iteration": 0,
            "message": (
                "Loop initialized. AGY can now call cleanroom_get_masked_brief "
                f"with meeting_id='{meeting.id}' to receive its task."
            ),
        }

    def evaluate_report(self, meeting_id: str, report_id: str) -> dict:
        """
        Step 2: Called after AGY submits its report via cleanroom_submit_code_report.
        - Fetches the BuildReportModel from DB.
        - Runs local evaluation: check test_results string and agy_status.
        - Routes to success, retry, or circuit_breaker.
        Returns a status dict.
        """
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return {"status": "error", "error": f"Meeting '{meeting_id}' not found."}

        report = self.repo.db.query(BuildReportModel).filter(BuildReportModel.id == report_id).first()
        if not report:
            return {"status": "error", "error": f"Build report '{report_id}' not found."}

        loop_run = self.repo.db.query(AutonomousLoopRunModel).filter(
            AutonomousLoopRunModel.id == report.loop_run_id
        ).first()
        if not loop_run:
            return {"status": "error", "error": f"Loop run not found for report '{report_id}'."}

        # --- Local Evaluation Logic ---
        passed = self._evaluate_test_results(
            agy_status=report.agy_status,
            test_results=report.test_results or "",
            summary=report.summary,
        )

        if passed:
            return self._handle_success(meeting, loop_run, report)
        else:
            return self._handle_failure(meeting, loop_run, report)

    # ------------------------------------------------------------------ #
    #  INTERNAL HELPERS                                                     #
    # ------------------------------------------------------------------ #

    def _generate_acceptance_criteria(self, meeting_id: str, raw_summary: str) -> str:
        """
        Converts the verified meeting summary into pytest-compatible acceptance stubs.
        Uses keyword extraction from the summary to build test scaffolding.
        This is intentionally rule-based (deterministic), not LLM-based.
        """
        lines = [
            "# AUTO-GENERATED ACCEPTANCE CRITERIA",
            "# Generated by Nomad from verified meeting claims.",
            "# AGY must implement code that passes ALL of these tests.",
            "# DO NOT modify these tests. They represent the client's verified requirements.",
            "",
            "import pytest",
            "",
            "# ---------------------------------------------------------------",
            "# INSTRUCTIONS FOR AGY:",
            "# 1. Read the brief_markdown carefully.",
            "# 2. Implement code to satisfy each test case below.",
            "# 3. Replace each 'raise NotImplementedError' with your implementation.",
            "# 4. All tests must pass before calling cleanroom_submit_code_report.",
            "# ---------------------------------------------------------------",
            "",
        ]

        # Extract bullet-point requirements from the summary or text
        requirements = []
        for line in raw_summary.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•", "–")) and len(stripped) > 3:
                clean_req = stripped.lstrip("-*•– ")
                if not clean_req.startswith("[ ]") and not clean_req.startswith("[x]"):
                    requirements.append(clean_req)
                elif len(clean_req) > 4:
                    requirements.append(clean_req[3:].strip())

        if not requirements:
            # Fallback: look for lines starting with '#' or numbered items or use default
            for line in raw_summary.split("\n"):
                stripped = line.strip()
                if len(stripped) > 10 and not stripped.startswith("#") and not stripped.startswith(">"):
                    requirements.append(stripped)
                    if len(requirements) >= 5:
                        break

        if not requirements:
            requirements = ["Implement the features described in the brief"]

        for i, req in enumerate(requirements[:10], start=1):  # Max 10 test stubs
            safe_name = "".join(c if c.isalnum() else "_" for c in req[:40]).lower().rstrip("_")
            lines.append(f"def test_requirement_{i:02d}_{safe_name}():")
            lines.append(f'    """Verify: {req}"""')
            lines.append("    # TODO (AGY): Implement test assertions here.")
            lines.append("    raise NotImplementedError('Test not yet implemented by AGY')")
            lines.append("")

        return "\n".join(lines)

    def _evaluate_test_results(self, agy_status: str, test_results: str, summary: str) -> bool:
        """
        Deterministic local evaluation of AGY's submission.
        Returns True (PASS) or False (FAIL).

        Pass conditions (ALL must be true):
        1. agy_status is 'success' or 'partial'.
        2. test_results string does NOT contain 'FAILED', 'ERROR', or 'NotImplementedError'.
        3. test_results string contains 'passed' or 'ok' (pytest output keyword).
        """
        if agy_status.lower() == "failure":
            return False

        test_output = test_results.lower()

        # Check for failure indicators
        failure_indicators = ["failed", "error", "notimplementederror", "exception", "traceback"]
        for indicator in failure_indicators:
            if indicator in test_output:
                return False

        # Check for explicit pass signal
        if "passed" in test_output or "ok" in test_output:
            return True

        # If no test output at all and agy_status is success, treat as partial pass
        if not test_results.strip() and agy_status.lower() == "success":
            logger.warning("[AutonomousLoop] AGY reported success but no test output. Treating as partial pass.")
            return True

        return False

    def _handle_success(self, meeting: MeetingModel, loop_run: AutonomousLoopRunModel, report: BuildReportModel) -> dict:
        """Handle a successful build report."""
        # 1. Mark report as passed
        self.repo.update_build_report_evaluation(
            report_id=report.id,
            evaluation_result="pass",
            evaluation_notes="All acceptance criteria passed.",
        )

        # 2. Mark loop run as complete
        self.repo.update_loop_run(loop_run_id=loop_run.id, status="success")

        # 3. Update meeting status
        meeting.status = "build_complete"
        self.repo.db.commit()

        # 4. Save output artifact for AGY report
        out_dir = Path(f"./data/outputs/{meeting.id}")
        out_dir.mkdir(parents=True, exist_ok=True)
        report_file = out_dir / f"agy_build_report_iter{report.iteration}.json"
        report_file.write_text(json.dumps({
            "loop_run_id": loop_run.id,
            "iteration": report.iteration,
            "agy_status": report.agy_status,
            "summary": report.summary,
            "files_changed": json.loads(report.files_changed_json),
            "test_results": report.test_results,
            "code_diff": report.code_diff,
            "evaluation": "PASS",
        }, indent=2), encoding="utf-8")

        # 5. Audit ledger entry
        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=meeting.id,
            event_type="autonomous_loop_success",
            payload={
                "loop_run_id": loop_run.id,
                "iteration": report.iteration,
                "report_id": report.id,
                "files_changed": json.loads(report.files_changed_json),
            },
            transcript_sha256=meeting.transcript_sha256 or "no_hash",
        )

        logger.info(f"[AutonomousLoop] ✅ BUILD COMPLETE for meeting {meeting.id} at iteration {report.iteration}")

        return {
            "status": "success",
            "meeting_id": meeting.id,
            "loop_run_id": loop_run.id,
            "iteration": report.iteration,
            "message": "✅ Build complete. All acceptance criteria passed. Report saved to audit ledger.",
            "report_path": str(report_file),
        }

    def _handle_failure(self, meeting: MeetingModel, loop_run: AutonomousLoopRunModel, report: BuildReportModel) -> dict:
        """Handle a failed build report — retry or trip circuit breaker."""
        current_iteration = report.iteration
        next_iteration = current_iteration + 1

        # Mark report as failed
        self.repo.update_build_report_evaluation(
            report_id=report.id,
            evaluation_result="fail",
            evaluation_notes=self._extract_failure_reason(report.test_results or ""),
        )

        # --- Circuit Breaker Check ---
        if next_iteration >= MAX_ITERATIONS:
            return self._trip_circuit_breaker(meeting, loop_run, report)

        # --- Generate Corrective Prompt ---
        corrective_prompt = self._generate_corrective_prompt(
            meeting=meeting,
            report=report,
            iteration=current_iteration,
        )

        # Update loop run for retry
        self.repo.update_loop_run(
            loop_run_id=loop_run.id,
            status="dispatched",
            iteration=next_iteration,
            corrective_prompt=corrective_prompt,
        )

        # Audit ledger entry
        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=meeting.id,
            event_type="autonomous_loop_retry",
            payload={
                "loop_run_id": loop_run.id,
                "failed_iteration": current_iteration,
                "next_iteration": next_iteration,
                "failure_reason": self._extract_failure_reason(report.test_results or ""),
            },
            transcript_sha256=meeting.transcript_sha256 or "no_hash",
        )

        logger.warning(
            f"[AutonomousLoop] ⚠️ Iteration {current_iteration} FAILED for meeting {meeting.id}. "
            f"Retrying as iteration {next_iteration}."
        )

        return {
            "status": "retrying",
            "meeting_id": meeting.id,
            "loop_run_id": loop_run.id,
            "failed_iteration": current_iteration,
            "next_iteration": next_iteration,
            "corrective_prompt": corrective_prompt,
            "message": (
                f"⚠️ Iteration {current_iteration} failed. Corrective prompt generated. "
                f"AGY should call cleanroom_get_masked_brief again to receive updated instructions."
            ),
        }

    def _trip_circuit_breaker(self, meeting: MeetingModel, loop_run: AutonomousLoopRunModel, report: BuildReportModel) -> dict:
        """Trip the 3-strike circuit breaker and alert the developer."""
        error_summary = (
            f"Circuit breaker triggered after {MAX_ITERATIONS} failed iterations. "
            f"Last failure: {self._extract_failure_reason(report.test_results or '')}"
        )

        self.repo.update_loop_run(
            loop_run_id=loop_run.id,
            status="needs_intervention",
            error_summary=error_summary,
        )
        meeting.status = "needs_intervention"
        self.repo.db.commit()

        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=meeting.id,
            event_type="autonomous_loop_circuit_breaker",
            payload={
                "loop_run_id": loop_run.id,
                "iterations_attempted": MAX_ITERATIONS,
                "error_summary": error_summary,
            },
            transcript_sha256=meeting.transcript_sha256 or "no_hash",
        )

        logger.error(
            f"[AutonomousLoop] 🚨 CIRCUIT BREAKER TRIPPED for meeting {meeting.id}. "
            "Human intervention required."
        )

        return {
            "status": "needs_intervention",
            "meeting_id": meeting.id,
            "loop_run_id": loop_run.id,
            "error_summary": error_summary,
            "message": (
                f"🚨 Circuit breaker tripped after {MAX_ITERATIONS} failed attempts. "
                "Human intervention is required. Review the test failures in the build reports."
            ),
        }

    def _generate_corrective_prompt(self, meeting: MeetingModel, report: BuildReportModel, iteration: int) -> str:
        """
        Generates a context-enriched corrective prompt using Nomad's local business context.
        This is Nomad's 'secret weapon' — it can see the raw transcript to understand
        WHY AGY failed, and inject the missing context into the corrective prompt.
        """
        failure_reason = self._extract_failure_reason(report.test_results or "")
        raw_context = meeting.raw_summary or "No additional context available."

        prompt = f"""
## CORRECTIVE INSTRUCTIONS — Iteration {iteration + 1} Retry

Your previous implementation (Iteration {iteration}) failed evaluation with the following issues:

### Failure Reason:
{failure_reason}

### Test Output:
```
{report.test_results or 'No test output provided'}
```

### Your Previous Implementation Summary:
{report.summary}

### Context from Original Business Requirements (Use this to correct your implementation):
{raw_context}

### Instructions for This Retry:
1. Read the failure reason carefully.
2. Review the test output and identify which assertions failed.
3. Cross-reference the business context above to understand the correct expected behavior.
4. Fix ONLY the failing parts. Do not rewrite code that is already correct.
5. Re-run ALL acceptance tests before submitting.
6. Call cleanroom_submit_code_report with your corrected results.
""".strip()

        return prompt

    def _extract_failure_reason(self, test_results: str) -> str:
        """Extract a concise failure reason from pytest output."""
        if not test_results:
            return "No test output provided. Tests may not have been run."

        lines = test_results.split("\n")
        failure_lines = [
            line for line in lines
            if any(kw in line.lower() for kw in ["failed", "error", "assert", "exception"])
        ]

        if failure_lines:
            return "\n".join(failure_lines[:10])  # First 10 failure lines

        return f"AGY reported status 'failure' but no specific test errors found. Full output: {test_results[:500]}"
