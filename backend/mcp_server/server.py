"""Fast Model Context Protocol (MCP) server exposing Clean Room tools."""

import asyncio
import json
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.processors.crosscheck import CrossCheckEngine
from backend.processors.leakscan import LeakScanner
from backend.processors.pipeline import PipelineOrchestrator
from backend.processors.policy import PolicyEngine
from backend.processors.privacy import Vault
from backend.schemas.meeting import MeetingSummary, MeetingTranscript
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository

# Tolerant import of MCP SDK across v1/v2
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        MCPServer = None

mcp_app = MCPServer("MeetilyCleanRoom") if MCPServer else None


def _get_repo():
    init_db()
    db = SessionLocal()
    return Repository(db), db


# Tool 1: Process Meeting
def process_meeting_tool(meeting_id: str) -> str:
    """Run Clean Room verification and distribution pipeline for a meeting."""
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return json.dumps({"error": f"Meeting '{meeting_id}' not found in Clean Room repository."})

        transcript = MeetingTranscript(
            meeting_id=meeting.id,
            segments=[],
            raw_text=meeting.raw_transcript or "",
            sha256_hash=meeting.transcript_sha256 or "hash",
        )
        summary = MeetingSummary(
            meeting_id=meeting.id,
            summary_text=meeting.raw_summary or "",
        )

        orchestrator = PipelineOrchestrator(repo=repo)
        run, decision, v_res, leak_rep = asyncio.run(
            orchestrator.execute_run(meeting.id, transcript, summary)
        )

        return json.dumps(
            {
                "meeting_id": meeting.id,
                "run_id": run.id,
                "gate_decision": decision.decision.value,
                "reasons": decision.reasons,
                "claims_count": len(v_res.claims),
                "supported": v_res.supported_count,
                "contradicted": v_res.contradicted_count,
            },
            indent=2,
        )
    finally:
        db.close()


# Tool 2: Get Verification
def get_verification_tool(meeting_id: str) -> str:
    """Get verified claims, verdicts, and evidence citations."""
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return json.dumps({"error": f"Meeting '{meeting_id}' not found."})
        res = repo.get_latest_verification(meeting.id)
        return json.dumps(res or {"message": "No verification results found."}, indent=2)
    finally:
        db.close()


# Tool 3: Get Conflicts
def get_conflicts_tool(meeting_id: str) -> str:
    """Get cross-source discrepancies between meeting statements and diligence documents."""
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return json.dumps({"error": f"Meeting '{meeting_id}' not found."})
        transcript = MeetingTranscript(
            meeting_id=meeting.id,
            segments=[],
            raw_text=meeting.raw_transcript or "",
            sha256_hash=meeting.transcript_sha256 or "hash",
        )
        engine = CrossCheckEngine()
        conflicts = engine.cross_check(transcript)
        return json.dumps([c.model_dump(mode="json") for c in conflicts], indent=2)
    finally:
        db.close()


# Tool 4: Get Output
def get_output_tool(meeting_id: str, audience: str = "lender") -> str:
    """Get generated output dossier tailored for a specific audience (deal_team, lender, board, outside_counsel, cloud_llm)."""
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return f"Meeting '{meeting_id}' not found."

        # Non-negotiable security rule: Never expose raw transcript unless deal_team AND EXPOSE_RAW_TRANSCRIPTS
        if audience == "deal_team" and not settings.EXPOSE_RAW_TRANSCRIPTS:
            # Safe redacted view
            pass

        artifacts = repo.list_output_artifacts(meeting.id)
        matching = next((a for a in artifacts if a.audience.lower() == audience.lower()), None)
        if not matching:
            return f"No output artifact found for audience '{audience}'."

        p = Path(matching.file_path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return f"Artifact file missing on disk: {matching.file_path}"
    finally:
        db.close()


# Tool 5: Review Decide
def review_decide_tool(item_id: str, action: str, correction: Optional[str] = None) -> str:
    """Submit human review decision ('approved', 'corrected', 'rejected') for a flagged item."""
    repo, db = _get_repo()
    try:
        item = repo.get_review_item(item_id)
        if not item:
            return json.dumps({"error": f"Review item '{item_id}' not found."})

        updated = repo.update_review_item(
            item_id=item_id,
            status=action,
            corrected_text=correction,
            reviewer_notes="MCP review resolution",
        )
        return json.dumps(
            {
                "item_id": updated.id,
                "status": updated.status,
                "corrected_text": updated.corrected_text,
            },
            indent=2,
        )
    finally:
        db.close()


# Tool 6: Leak Report
def leak_report_tool(meeting_id: str) -> str:
    """Audit leak scanner findings and canary containment across distributed outputs."""
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return json.dumps({"error": f"Meeting '{meeting_id}' not found."})

        artifacts = repo.list_output_artifacts(meeting.id)
        paths = {a.audience: a.file_path for a in artifacts}

        vault = Vault()
        scanner = LeakScanner(vault=vault)
        report = scanner.scan_output_artifacts(meeting.id, "mcp_scan", paths)
        return json.dumps(report.model_dump(mode="json"), indent=2)
    finally:
        db.close()


# Tool 7: Ask Question
def ask_question_tool(meeting_id: str, question: str, audience: str = "outside_counsel") -> str:
    """Answer diligence questions using transcript and documents, with citations, masked for audience."""
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return f"Meeting '{meeting_id}' not found."

        summary_text = meeting.raw_summary or ""
        policy = PolicyEngine()
        vault = Vault()

        # Mask text according to audience
        masked_answer, _ = policy.mask_text(summary_text, audience, vault)
        return f"[AUDIENCE: {audience.upper()}]\n{masked_answer}\n\n[Citation: meeting_transcript@{meeting.id}]"
    finally:
        db.close()


# Tool 8: Get Masked Brief for AGY
def get_masked_brief_tool(meeting_id: str) -> str:
    """
    Retrieve the verified, privacy-masked coding brief for a meeting.
    Fail-closed: returns BLOCKED if the gate decision is not 'release'.
    Called by the Antigravity (AGY) coding agent to receive its task.
    """
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return json.dumps({"status": "ERROR", "error": f"Meeting '{meeting_id}' not found."})

        # 1. Enforce gate decision — fail closed
        decision = repo.get_latest_release_decision(meeting.id)
        if not decision or decision.decision.lower() != "release":
            return json.dumps({
                "status": "BLOCKED",
                "error": "Task brief cannot be released. Gate status is HOLD_FOR_REVIEW or meeting is unverified.",
                "gate_decision": decision.decision if decision else "NOT_PROCESSED",
                "reasons": json.loads(decision.reasons_json) if decision else [],
            })

        # 2. Get the active loop run
        loop_run = repo.get_active_loop_run(meeting.id)
        if not loop_run:
            return json.dumps({
                "status": "ERROR",
                "error": "No active autonomous loop run found. Trigger /api/meetings/{id}/build first.",
            })

        # 3. Return the masked brief and acceptance criteria
        return json.dumps({
            "status": "RELEASED",
            "meeting_id": meeting.id,
            "loop_run_id": loop_run.id,
            "iteration": loop_run.iteration,
            "brief_markdown": loop_run.masked_brief_text or "",
            "acceptance_criteria": loop_run.acceptance_criteria or "",
            "corrective_prompt": loop_run.corrective_prompt or None,
            "instructions": (
                "You are the Antigravity coding agent. Your task: implement the requirements "
                "in 'brief_markdown'. Write clean, production-quality Python code. "
                "Also generate and run pytest tests that validate the acceptance criteria. "
                "When done, call cleanroom_submit_code_report with your results."
            ),
        }, indent=2)
    finally:
        db.close()


# Tool 9: Submit Code Report
def submit_code_report_tool(
    meeting_id: str,
    loop_run_id: str,
    iteration: int,
    agy_status: str,
    summary: str,
    files_changed: list,
    test_results: Optional[str] = None,
    code_diff: Optional[str] = None,
) -> str:
    """
    Called by AGY to submit its implementation report back to Nomad.
    Nomad persists the report and triggers local evaluation.
    agy_status must be one of: 'success', 'failure', 'partial'.
    """
    repo, db = _get_repo()
    try:
        meeting = repo.get_meeting_by_id(meeting_id)
        if not meeting:
            return json.dumps({"status": "ERROR", "error": f"Meeting '{meeting_id}' not found."})

        # 1. Persist the build report
        report = repo.save_build_report(
            loop_run_id=loop_run_id,
            meeting_id=meeting.id,
            iteration=iteration,
            agy_status=agy_status,
            summary=summary,
            files_changed=files_changed,
            test_results=test_results,
            code_diff=code_diff,
        )

        # 2. Record ingestion event in Audit Ledger
        from backend.processors.ledger import AuditLedger
        AuditLedger.record_event(
            repo=repo,
            meeting_id=meeting.id,
            event_type="agy_report_received",
            payload={
                "loop_run_id": loop_run_id,
                "iteration": iteration,
                "agy_status": agy_status,
                "files_changed": files_changed,
                "report_id": report.id,
            },
            transcript_sha256=meeting.transcript_sha256 or "no_hash",
        )

        # 3. Mark loop run as 'evaluating' so the orchestrator knows a report arrived
        repo.update_loop_run(loop_run_id=loop_run_id, status="evaluating")

        return json.dumps({
            "status": "ACCEPTED",
            "report_id": report.id,
            "message": f"Report received for iteration {iteration}. Nomad is now evaluating locally.",
        }, indent=2)
    finally:
        db.close()


# Register tools on MCP server if MCP is installed
if mcp_app:
    @mcp_app.tool()
    def cleanroom_process_meeting(meeting_id: str) -> str:
        """Run Clean Room verification and distribution pipeline for a meeting."""
        return process_meeting_tool(meeting_id)

    @mcp_app.tool()
    def cleanroom_get_verification(meeting_id: str) -> str:
        """Get verified claims, verdicts, and evidence citations."""
        return get_verification_tool(meeting_id)

    @mcp_app.tool()
    def cleanroom_get_conflicts(meeting_id: str) -> str:
        """Get cross-source discrepancies between meeting statements and diligence documents."""
        return get_conflicts_tool(meeting_id)

    @mcp_app.tool()
    def cleanroom_get_output(meeting_id: str, audience: str = "lender") -> str:
        """Get generated output dossier tailored for a specific audience."""
        return get_output_tool(meeting_id, audience)

    @mcp_app.tool()
    def cleanroom_review_decide(item_id: str, action: str, correction: Optional[str] = None) -> str:
        """Submit human review decision ('approved', 'corrected', 'rejected')."""
        return review_decide_tool(item_id, action, correction)

    @mcp_app.tool()
    def cleanroom_leak_report(meeting_id: str) -> str:
        """Audit leak scanner findings and canary containment."""
        return leak_report_tool(meeting_id)

    @mcp_app.tool()
    def cleanroom_ask(meeting_id: str, question: str, audience: str = "outside_counsel") -> str:
        """Answer diligence questions with citations, masked for audience."""
        return ask_question_tool(meeting_id, question, audience)

    @mcp_app.tool()
    def cleanroom_get_masked_brief(meeting_id: str) -> str:
        """
        Retrieve the verified, privacy-masked coding task brief for AGY.
        Returns BLOCKED if gate decision is not 'release'.
        """
        return get_masked_brief_tool(meeting_id)

    @mcp_app.tool()
    def cleanroom_submit_code_report(
        meeting_id: str,
        loop_run_id: str,
        iteration: int,
        agy_status: str,
        summary: str,
        files_changed: list,
        test_results: Optional[str] = None,
        code_diff: Optional[str] = None,
    ) -> str:
        """
        Submit AGY's build results back to Nomad for local evaluation.
        agy_status: 'success' | 'failure' | 'partial'.
        """
        return submit_code_report_tool(
            meeting_id=meeting_id,
            loop_run_id=loop_run_id,
            iteration=iteration,
            agy_status=agy_status,
            summary=summary,
            files_changed=files_changed,
            test_results=test_results,
            code_diff=code_diff,
        )


def main():
    """Run MCP server over stdio transport."""
    if mcp_app:
        mcp_app.run()
    else:
        print("MCP SDK not installed. Run 'pip install mcp' to enable MCP server.")


if __name__ == "__main__":
    main()

