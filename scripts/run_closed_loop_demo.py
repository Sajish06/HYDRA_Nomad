"""Closed-Loop Autonomous Build Demo runner.

Executes the full Nomad <-> AGY closed-loop cycle over stdio MCP:
- Pulls brief
- Runs scripted Fake AGY behavior (or reports)
- Runs isolated local evaluation
- Iterates up to 3 times
- Verifies the cryptographic AuditLedger chain
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure Windows console handles UTF-8 safely
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.loop.workspace import get_default_workspace_root, resolve_desktop_path
from backend.processors.ledger import AuditLedger
from backend.storage.database import SessionLocal, init_db
from backend.storage.models import MeetingModel, ReleaseDecisionModel
from backend.storage.repository import Repository
from mocks.fake_agy.fake_agent import FakeAGYAgent


def setup_demo_meeting(meeting_id: str = "mtg_closed_loop_demo_001") -> str:
    """Initialize a verified, released meeting in Nomad database."""
    init_db()
    db = SessionLocal()
    repo = Repository(db)

    existing = repo.get_meeting_by_id(meeting_id)
    if existing:
        db.delete(existing)
        db.commit()

    raw_summary = (
        "- Build landing page index.html with a heading, about section, 3-item feature list, footer\n"
        "- Build contact page contact.html with a form for name, email, message, labeled inputs, submit button"
    )

    meeting = MeetingModel(
        id=meeting_id,
        meetily_id=f"meetily_{meeting_id}",
        title="Acme Public Web Portal Sprint",
        status="completed",
        transcript_sha256="sha256_demo_closed_loop_portal",
        raw_summary=raw_summary,
    )
    db.add(meeting)
    db.commit()

    decision = ReleaseDecisionModel(
        run_id=f"run_gate_{meeting_id}",
        meeting_id=meeting.id,
        decision="release",
        reasons_json=json.dumps(["Gate passed: All commitments verified"]),
    )
    db.add(decision)
    db.commit()

    db.close()
    return meeting_id


def print_workspace_tree(workspace: Path):
    """Print directory tree of files built in workspace."""
    print("\n[+] Workspace Contents:")
    for root, dirs, files in os.walk(workspace):
        rel_root = Path(root).relative_to(workspace)
        indent = "  " * len(rel_root.parts)
        if rel_root != Path("."):
            print(f"{indent}[DIR] {rel_root.name}/")
        for f in sorted(files):
            file_path = Path(root) / f
            size = file_path.stat().st_size
            print(f"{indent}  * {f} ({size} bytes)")


async def main():
    parser = argparse.ArgumentParser(description="Nomad Closed-Loop Autonomous Build Demo")
    parser.add_argument(
        "--behavior",
        default="fix_on_second",
        choices=["good", "fix_on_second", "never_passes", "lies", "tamper", "escape", "leaky", "abandon"],
        help="Scripted Fake AGY behavior to demonstrate",
    )
    parser.add_argument(
        "--use-real-desktop",
        action="store_true",
        help="Write to the real Desktop\\test workspace instead of a temporary directory",
    )
    parser.add_argument(
        "--meeting-id",
        default="mtg_closed_loop_demo_001",
        help="Meeting ID to use for demo",
    )
    parser.add_argument(
        "--enable-ollama",
        action="store_true",
        help="Attempt live Ollama prompt compilation (falls back cleanly if unavailable)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" [*] NOMAD CLOSED-LOOP AUTONOMOUS AGENT BUILD DEMO")
    print(f" Behavior: {args.behavior}")
    print(f" Use Real Desktop: {args.use_real_desktop}")
    print("=" * 70)

    # 1. Resolve Desktop path
    desktop = resolve_desktop_path()
    default_root = get_default_workspace_root()
    print(f"\n[Environment] Resolved Desktop: {desktop}")
    print(f"[Environment] Workspace Root:   {default_root}")

    # 2. Setup meeting
    meeting_id = setup_demo_meeting(args.meeting_id)
    print(f"[Nomad] Meeting '{meeting_id}' initialized and released for building.")

    # 3. Configure Fake AGY
    agent = FakeAGYAgent(
        behavior=args.behavior,
        python_executable=sys.executable,
        enable_ollama=args.enable_ollama,
    )

    print(f"\n[AGY] Spawning agent with behavior '{args.behavior}' over stdio MCP...")
    result = await agent.run(meeting_id=meeting_id)

    # 4. Display Iteration History
    print("\n" + "=" * 70)
    print(" [SUMMARY] CLOSED-LOOP EXECUTION")
    print("=" * 70)
    print(f"Final Verdict:    {result['final_verdict'].upper()}")
    print(f"Total Iterations: {result.get('total_iterations', 0)}")
    print(f"Loop Run ID:      {result.get('loop_run_id', 'N/A')}")
    print(f"Workspace Path:   {result.get('workspace_path', 'N/A')}")

    for item in result.get("history", []):
        it = item["iteration"]
        verdict = item["verdict"]
        print(f"\n--- Iteration {it} ---")
        print(f"Files Modified: {item['files_changed']}")
        print(f"Verdict:        {verdict.upper()}")
        eval_data = item["report"].get("evaluation", {})
        passed = eval_data.get("passed_count", 0)
        failed = eval_data.get("failed_count", 0)
        print(f"Test Results:   {passed} passed, {failed} failed")
        if item["report"].get("next_prompt"):
            next_p = item["report"]["next_prompt"]
            print(f"Next Prompt:    Objective: {next_p.get('objective', '')[:80]}...")
            print(f"Masked Feedback:\n{next_p.get('previous_feedback', '')[:200]}")

    # 5. Workspace inspection
    workspace_path = Path(result.get("workspace_path", ""))
    if workspace_path.exists():
        print_workspace_tree(workspace_path)

    # 6. Cryptographic AuditLedger Verification
    print("\n" + "=" * 70)
    print(" [LEDGER] AUDIT LEDGER CHAIN VERIFICATION")
    print("=" * 70)
    db = SessionLocal()
    repo = Repository(db)
    entries = repo.list_ledger_entries(meeting_id)
    is_valid, err = AuditLedger.verify_chain(entries)
    print(f"Total Ledger Events: {len(entries)}")
    for e in entries:
        print(f"  [{e.index:02d}] {e.event_type} | Hash: {e.entry_hash[:16]}...")
    status_msg = "VALID (Unbroken Chain)" if is_valid else f"BROKEN: {err}"
    print(f"\nCryptographic Integrity: {status_msg}")
    db.close()

    print("\n[+] Demo completed successfully.\n")


if __name__ == "__main__":
    asyncio.run(main())
