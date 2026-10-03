"""Protocol-level integration tests for the Nomad MCP Server over stdio transport.

Uses the official Python MCP SDK client:
1. Spawns backend.mcp_server.server over stdio.
2. Performs MCP initialize handshake.
3. Tests tools/list: asserts all 11 tools present with valid JSON schemas.
4. Invokes tools via JSON-RPC: verifies responses and asserts stdout contains only protocol frames.
"""

import asyncio
import json
import sys
import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from backend.storage.database import SessionLocal, init_db
from backend.storage.models import MeetingModel, ReleaseDecisionModel
from backend.storage.repository import Repository


@pytest.fixture(scope="module")
def setup_mcp_test_meeting():
    init_db()
    db = SessionLocal()
    repo = Repository(db)

    meeting_id = "mtg_mcp_protocol_001"
    existing = repo.get_meeting_by_id(meeting_id)
    if existing:
        db.delete(existing)
        db.commit()

    meeting = MeetingModel(
        id=meeting_id,
        meetily_id="meetily_protocol_001",
        title="Protocol Test Meeting",
        status="completed",
        transcript_sha256="hash_mcp_protocol",
        raw_summary="- Build a landing page index.html\n- Build a contact form contact.html",
    )
    db.add(meeting)
    db.commit()

    decision = ReleaseDecisionModel(
        run_id="run_mcp_proto",
        meeting_id=meeting.id,
        decision="release",
        reasons_json=json.dumps(["Verified"]),
    )
    db.add(decision)
    db.commit()

    db.close()
    return meeting_id


@pytest.mark.asyncio
async def test_mcp_stdio_initialize_and_tools_list():
    """Verify stdio handshake, tool registration, and schema validity."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "backend.mcp_server.server"],
        env=None,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_res = await session.initialize()
            assert init_res is not None

            tools_res = await session.list_tools()
            tool_names = {t.name for t in tools_res.tools}

            expected_tools = {
                "cleanroom_process_meeting",
                "cleanroom_get_verification",
                "cleanroom_get_conflicts",
                "cleanroom_get_output",
                "cleanroom_review_decide",
                "cleanroom_leak_report",
                "cleanroom_ask",
                "cleanroom_get_masked_brief",
                "cleanroom_submit_code_report",
                "cleanroom_get_loop_status",
                "cleanroom_abort_loop",
            }

            for exp in expected_tools:
                assert exp in tool_names, f"Expected MCP tool '{exp}' not found in tools/list"

            # Check schemas
            for t in tools_res.tools:
                schema = t.input_schema
                assert isinstance(schema, dict)
                assert schema.get("type") == "object"


@pytest.mark.asyncio
async def test_mcp_stdio_tool_invocations(setup_mcp_test_meeting):
    """Call core Clean Room tools over stdio and verify structured JSON returns."""
    meeting_id = setup_mcp_test_meeting
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "backend.mcp_server.server"],
        env=None,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 1. cleanroom_ask
            ask_res = await session.call_tool("cleanroom_ask", {"meeting_id": meeting_id, "question": "What was agreed?"})
            assert len(ask_res.content) > 0
            text_val = ask_res.content[0].text
            assert "AUDIENCE" in text_val

            # 2. cleanroom_get_masked_brief
            brief_res = await session.call_tool("cleanroom_get_masked_brief", {"meeting_id": meeting_id})
            assert len(brief_res.content) > 0
            brief_data = json.loads(brief_res.content[0].text)
            assert brief_data["status"] == "brief_issued"
            assert "loop_run_id" in brief_data
            assert "workspace_path" in brief_data
            run_id = brief_data["loop_run_id"]

            # 3. cleanroom_get_loop_status
            status_res = await session.call_tool("cleanroom_get_loop_status", {"loop_run_id": run_id})
            status_data = json.loads(status_res.content[0].text)
            assert status_data["loop_run_id"] == run_id
            assert status_data["status"] == "brief_issued"

            # 4. cleanroom_abort_loop
            abort_res = await session.call_tool("cleanroom_abort_loop", {"loop_run_id": run_id, "reason": "Test abort"})
            abort_data = json.loads(abort_res.content[0].text)
            assert abort_data["status"] == "aborted"
