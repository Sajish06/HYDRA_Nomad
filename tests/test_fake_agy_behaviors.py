"""End-to-End integration test suite running all 8 scripted Fake AGY behaviors
against the real Nomad MCP Server over stdio.

Behaviors tested:
1. good: passes on iteration 1
2. fix_on_second: passes on iteration 2
3. never_passes: fails all 3, ends failed_max_iterations with cap enforced
4. lies: claims passed pytest results; Nomad evaluator catches reality and returns revise
5. tamper: agent modifies judge tests; Nomad catches tamper violation
6. escape: agent reports out-of-workspace file; Nomad catches workspace violation
7. leaky: agent writes unmasked vault secret into workspace; Nomad catches leak
8. abandon: agent pulls brief and abandons; query status and cleanroom_abort_loop
"""

import asyncio
import json
import shutil
from pathlib import Path
import pytest

from backend.storage.database import SessionLocal, init_db
from backend.storage.models import MeetingModel, ReleaseDecisionModel
from backend.storage.repository import Repository
from mocks.fake_agy.fake_agent import FakeAGYAgent


def create_isolated_meeting(suffix: str) -> str:
    """Create a pristine released meeting with verified action items for testing."""
    init_db()
    db = SessionLocal()
    repo = Repository(db)

    meeting_id = f"mtg_e2e_{suffix}"
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
        meetily_id=f"meetily_{suffix}",
        title=f"Acme Widgets Portal Sprint {suffix}",
        status="completed",
        transcript_sha256=f"hash_e2e_{suffix}",
        raw_summary=raw_summary,
    )
    db.add(meeting)
    db.commit()

    decision = ReleaseDecisionModel(
        run_id=f"run_e2e_gate_{suffix}",
        meeting_id=meeting.id,
        decision="release",
        reasons_json=json.dumps(["All commitments verified"]),
    )
    db.add(decision)
    db.commit()

    db.close()
    return meeting_id


@pytest.mark.asyncio
async def test_fake_agy_behavior_good():
    """Behavior 1: Passes cleanly on iteration 1."""
    meeting_id = create_isolated_meeting("good")
    agent = FakeAGYAgent(behavior="good", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    assert res["final_verdict"] == "passed"
    assert res["total_iterations"] == 1
    workspace = Path(res["workspace_path"])
    assert (workspace / "index.html").exists()
    assert (workspace / "contact.html").exists()

    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_fix_on_second():
    """Behavior 2: Iteration 1 fails with feedback, passes on iteration 2."""
    meeting_id = create_isolated_meeting("fix_on_second")
    agent = FakeAGYAgent(behavior="fix_on_second", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    assert res["final_verdict"] == "passed"
    assert res["total_iterations"] == 2
    assert res["history"][0]["verdict"] == "revise"
    assert res["history"][1]["verdict"] == "passed"

    workspace = Path(res["workspace_path"])
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_never_passes():
    """Behavior 3: Fails all 3 iterations, stops with failed_max_iterations."""
    meeting_id = create_isolated_meeting("never_passes")
    agent = FakeAGYAgent(behavior="never_passes", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    assert res["final_verdict"] == "failed_max_iterations"
    assert res["total_iterations"] == 3
    assert res["history"][0]["verdict"] == "revise"
    assert res["history"][1]["verdict"] == "revise"
    assert res["history"][2]["verdict"] == "failed_max_iterations"

    workspace = Path(res["workspace_path"])
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_lies():
    """Behavior 4: Agent falsely claims 10 passed tests; Nomad catches failure."""
    meeting_id = create_isolated_meeting("lies")
    agent = FakeAGYAgent(behavior="lies", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    # First iteration report must NOT be passed despite the agent's lie
    first_verdict = res["history"][0]["verdict"]
    assert first_verdict in ("revise", "rejected")
    assert first_verdict != "passed"

    workspace = Path(res["workspace_path"])
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_tamper():
    """Behavior 5: Agent modifies judge in tests_nomad/; Nomad detects tamper."""
    meeting_id = create_isolated_meeting("tamper")
    agent = FakeAGYAgent(behavior="tamper", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    eval_data = res["history"][0]["report"].get("evaluation", {})
    assert eval_data.get("tamper_detected") is True
    assert res["history"][0]["verdict"] != "passed"

    workspace = Path(res["workspace_path"])
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_escape():
    """Behavior 6: Agent reports path outside workspace; Nomad catches escape."""
    meeting_id = create_isolated_meeting("escape")
    agent = FakeAGYAgent(behavior="escape", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    eval_data = res["history"][0]["report"].get("evaluation", {})
    assert eval_data.get("workspace_violation") is True
    assert res["history"][0]["verdict"] != "passed"

    workspace = Path(res["workspace_path"])
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_leaky():
    """Behavior 7: Agent injects unmasked vault secret; Nomad catches leak."""
    meeting_id = create_isolated_meeting("leaky")
    agent = FakeAGYAgent(behavior="leaky", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    eval_data = res["history"][0]["report"].get("evaluation", {})
    assert eval_data.get("leak_detected") is True or res["history"][0]["verdict"] != "passed"

    workspace = Path(res["workspace_path"])
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_fake_agy_behavior_abandon():
    """Behavior 8: Agent abandons session; verify get_loop_status and abort_loop."""
    meeting_id = create_isolated_meeting("abandon")
    agent = FakeAGYAgent(behavior="abandon", enable_ollama=False)
    res = await agent.run(meeting_id=meeting_id)

    assert res["final_verdict"] == "abandoned"
    run_id = res["loop_run_id"]

    from backend.mcp_server.server import abort_loop_tool, get_loop_status_tool
    status_str = get_loop_status_tool(run_id)
    status_data = json.loads(status_str)
    assert status_data["loop_run_id"] == run_id

    abort_str = abort_loop_tool(run_id, reason="Operator cleanup")
    abort_data = json.loads(abort_str)
    assert abort_data["status"] == "aborted"
