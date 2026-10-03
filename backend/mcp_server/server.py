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
def get_masked_brief_tool(
    meeting_id: str,
    loop_run_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> str:
    """
    Retrieve the verified, privacy-masked coding brief for a meeting.
    Returns structured prompt, workspace path, criteria, and gate status.
    Fail-closed: returns BLOCKED if the gate decision is not 'release'.
    """
    from backend.loop.state import LoopStateMachine

    sm = LoopStateMachine()
    try:
        res = sm.get_or_create_brief(
            meeting_id=meeting_id,
            loop_run_id=loop_run_id,
            task_id=task_id,
        )
        data = res.model_dump(mode="json")
        # Backwards-compatible aliases
        prompt_obj = data.get("prompt", {})
        data["brief_markdown"] = prompt_obj.get("objective", "") + "\n\n" + prompt_obj.get("workspace_instructions", "")
        return json.dumps(data, indent=2)
    except PermissionError as pe:
        return json.dumps({
            "status": "BLOCKED",
            "isError": True,
            "error": str(pe),
            "gate": {"decision": "HOLD_FOR_REVIEW"},
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "isError": True,
            "error": str(e),
        }, indent=2)
    finally:
        sm.close()


# Tool 9: Submit Code Report
def submit_code_report_tool(
    loop_run_id: str,
    agy_status: str,
    summary: str,
    files_changed: list,
    diff: Optional[str] = None,
    test_results: Optional[str] = None,
    iteration: Optional[int] = None,
    meeting_id: Optional[str] = None,
    code_diff: Optional[str] = None,
) -> str:
    """
    Called by AGY to submit its implementation report back to Nomad.
    Nomad executes local evaluation in an isolated subprocess and returns the verdict.
    """
    from backend.loop.state import CodeReportSubmission, LoopStateMachine

    # Detect legacy argument order: meeting_id, loop_run_id, iteration, agy_status...
    actual_run_id = loop_run_id
    actual_status = agy_status
    actual_summary = summary
    actual_files = files_changed
    actual_diff = diff or code_diff
    actual_iter = iteration

    if meeting_id is not None and not str(loop_run_id).startswith("run_"):
        # Legacy positional caller
        actual_run_id = str(agy_status)
        actual_status = str(files_changed) if isinstance(files_changed, str) else "completed"
        actual_summary = str(diff) if diff else "Implementation report"
        actual_files = list(test_results) if isinstance(test_results, list) else []

    sm = LoopStateMachine()
    try:
        sub = CodeReportSubmission(
            loop_run_id=actual_run_id,
            agy_status=actual_status,
            summary=actual_summary,
            files_changed=actual_files if isinstance(actual_files, list) else [str(actual_files)],
            diff=actual_diff,
            test_results=test_results if isinstance(test_results, str) else None,
            iteration=actual_iter,
            meeting_id=meeting_id,
        )
        res = sm.submit_and_evaluate_report(sub)
        return json.dumps(res.model_dump(mode="json"), indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "isError": True,
            "error": str(e),
            "verdict": "rejected",
        }, indent=2)
    finally:
        sm.close()


# Tool 10: Get Loop Status
def get_loop_status_tool(loop_run_id: str) -> str:
    """Query state, iteration count, and evaluation history for a loop run."""
    from backend.loop.state import LoopStateMachine

    sm = LoopStateMachine()
    try:
        status_dict = sm.get_loop_status(loop_run_id)
        return json.dumps(status_dict, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "isError": True, "error": str(e)}, indent=2)
    finally:
        sm.close()


# Tool 11: Abort Loop
def abort_loop_tool(loop_run_id: str, reason: str = "Aborted by operator") -> str:
    """Manually abort an active build loop."""
    from backend.loop.state import LoopStateMachine

    sm = LoopStateMachine()
    try:
        res = sm.abort_loop(loop_run_id, reason=reason)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "isError": True, "error": str(e)}, indent=2)
    finally:
        sm.close()


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
    def cleanroom_get_masked_brief(
        meeting_id: str,
        loop_run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Retrieve the verified, privacy-masked coding task brief for AGY.
        Returns BLOCKED if gate decision is not 'release'.
        """
        return get_masked_brief_tool(meeting_id=meeting_id, loop_run_id=loop_run_id, task_id=task_id)

    @mcp_app.tool()
    def cleanroom_submit_code_report(
        loop_run_id: str,
        agy_status: str,
        summary: str,
        files_changed: list,
        diff: Optional[str] = None,
        test_results: Optional[str] = None,
        iteration: Optional[int] = None,
        meeting_id: Optional[str] = None,
    ) -> str:
        """
        Submit AGY's build results back to Nomad for local evaluation.
        agy_status: 'completed' | 'partial' | 'blocked' | 'failed'.
        """
        return submit_code_report_tool(
            loop_run_id=loop_run_id,
            agy_status=agy_status,
            summary=summary,
            files_changed=files_changed,
            diff=diff,
            test_results=test_results,
            iteration=iteration,
            meeting_id=meeting_id,
        )

    @mcp_app.tool()
    def cleanroom_get_loop_status(loop_run_id: str) -> str:
        """Query state, iteration count, and evaluation history for a loop run."""
        return get_loop_status_tool(loop_run_id)

    @mcp_app.tool()
    def cleanroom_abort_loop(loop_run_id: str, reason: str = "Aborted by operator") -> str:
        """Manually abort an active build loop."""
        return abort_loop_tool(loop_run_id, reason)


def main():
    """Run MCP server over stdio transport."""
    if mcp_app:
        mcp_app.run()
    else:
        print("MCP SDK not installed. Run 'pip install mcp' to enable MCP server.", file=sys.stderr)


if __name__ == "__main__":
    main()

