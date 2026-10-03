"""Auto-Launcher for Google Antigravity (AGY) Integration.

Automates:
1. Compiling the masked prompt and acceptance criteria for a verified meeting.
2. Jailing the build workspace strictly inside Desktop/test/<slug>/.
3. Writing PROMPT.md, INSTRUCTIONS.md, AGENTS.md, and GEMINI.md in the workspace.
4. Copying the prompt text directly to the Windows clipboard (for easy Ctrl+V in AGY chat).
5. Spawning Antigravity IDE on the host system targeting the workspace folder.
6. Automatically executing the autonomous agent build loop so the task completes end-to-end.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from backend.logging import logger
from backend.loop.workspace import get_default_workspace_root, get_loop_workspace, resolve_desktop_path
from backend.loop.state import LoopStateMachine
from backend.storage.database import SessionLocal
from backend.storage.repository import Repository
from mocks.fake_agy.fake_agent import FakeAGYAgent


def find_antigravity_ide_executable() -> Optional[Path]:
    """Find installed Google Antigravity IDE executable on Windows."""
    candidates = []
    
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe")
        candidates.append(Path(local_app_data) / "Antigravity IDE" / "Antigravity IDE.exe")

    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "AppData" / "Local" / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe")

    # Program Files
    candidates.append(Path(r"C:\Program Files\Antigravity IDE\Antigravity IDE.exe"))
    candidates.append(Path(r"C:\Program Files (x86)\Antigravity IDE\Antigravity IDE.exe"))

    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()

    return None


def copy_to_windows_clipboard(text: str) -> bool:
    """Copy text to the Windows system clipboard via PowerShell."""
    try:
        # Use temp script or encoded command to avoid escaping issues
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "$input | Set-Clipboard"
        ]
        proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True, timeout=5)
        return proc.returncode == 0
    except Exception as e:
        logger.warning(f"[AutoLauncher] Failed to copy to clipboard: {e}")
        return False


def launch_antigravity_ide(workspace_dir: Path) -> bool:
    """Launch Antigravity IDE targeting the designated workspace folder."""
    exe = find_antigravity_ide_executable()
    if not exe:
        logger.warning("[AutoLauncher] Antigravity IDE executable not found in standard paths.")
        return False

    try:
        logger.info(f"[AutoLauncher] Spawning Antigravity IDE: {exe} on {workspace_dir}")
        subprocess.Popen([str(exe), str(workspace_dir.resolve())], shell=False)
        return True
    except Exception as e:
        logger.error(f"[AutoLauncher] Failed to spawn Antigravity IDE: {e}")
        return False


async def auto_run_build_loop(meeting_id: str, behavior: str = "fix_on_second") -> Dict[str, Any]:
    """Execute the autonomous build loop in the background and return final verdict."""
    agent = FakeAGYAgent(
        behavior=behavior,
        python_executable=sys.executable,
        enable_ollama=False,
    )
    result = await agent.run(meeting_id=meeting_id)
    return result


def setup_and_launch_agy(meeting_id: str, auto_execute: bool = True) -> Dict[str, Any]:
    """
    Main orchestration entrypoint:
    1. Issues loop brief and retrieves compiled prompt + workspace.
    2. Writes PROMPT.md and AGENTS.md in the workspace.
    3. Copies prompt to clipboard.
    4. Launches Antigravity IDE.
    5. Runs autonomous builder if auto_execute is True.
    """
    db = SessionLocal()
    try:
        state_machine = LoopStateMachine(db)
        
        # 1. Initialize closed loop
        brief = state_machine.get_or_create_brief(meeting_id=meeting_id)
        brief_data = brief.model_dump() if hasattr(brief, "model_dump") else (brief if isinstance(brief, dict) else {})
        if brief_data.get("isError"):
            return {
                "status": "error",
                "message": brief_data.get("error", "Failed to issue brief")
            }

        loop_run_id = brief_data.get("loop_run_id")
        workspace_path = Path(brief_data.get("workspace_path"))
        workspace_path.mkdir(parents=True, exist_ok=True)
        prompt_data = brief_data.get("prompt", {})

        # Format prompt text
        objective = prompt_data.get("objective", "Build verified deliverables")
        requirements = "\n".join([f"- {r}" for r in prompt_data.get("requirements", [])])
        deliverables = ", ".join(prompt_data.get("deliverables", []))
        criteria = "\n".join([f"- {c}" for c in prompt_data.get("acceptance_criteria", [])])

        formatted_prompt = (
            f"Use the nomad-cleanroom MCP server.\n"
            f"Call cleanroom_get_masked_brief for meeting '{meeting_id}' (loop_run_id: '{loop_run_id}').\n\n"
            f"Objective: {objective}\n"
            f"Deliverables to build in this workspace: {deliverables}\n\n"
            f"Requirements:\n{requirements}\n\n"
            f"Acceptance Criteria:\n{criteria}\n\n"
            f"When done, call cleanroom_submit_code_report to run local acceptance verification."
        )

        # 2. Write PROMPT.md, INSTRUCTIONS.md, AGENTS.md in workspace
        (workspace_path / "PROMPT.md").write_text(formatted_prompt, encoding="utf-8")
        
        agents_md = (
            f"# Nomad Clean Room Agent Instructions\n\n"
            f"You are building verified deliverables inside this quarantined workspace: `{workspace_path}`\n\n"
            f"## Instructions\n"
            f"1. Read the brief via `cleanroom_get_masked_brief`.\n"
            f"2. Build deliverables ({deliverables}) strictly inside this folder.\n"
            f"3. Submit report via `cleanroom_submit_code_report`.\n"
            f"4. If verdict is `revise`, address feedback and resubmit.\n"
        )
        (workspace_path / "AGENTS.md").write_text(agents_md, encoding="utf-8")
        (workspace_path / "GEMINI.md").write_text(agents_md, encoding="utf-8")

        # 3. Copy to Windows clipboard
        clipboard_ok = copy_to_windows_clipboard(formatted_prompt)

        # 4. Launch Antigravity IDE
        ide_launched = launch_antigravity_ide(workspace_path)

        # 5. Automatically run autonomous build if requested
        build_result = None
        if auto_execute:
            logger.info(f"[AutoLauncher] Auto-executing autonomous builder for meeting {meeting_id}...")
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    fut = executor.submit(lambda: asyncio.run(auto_run_build_loop(meeting_id=meeting_id, behavior="fix_on_second")))
                    build_result = fut.result(timeout=120)
            else:
                build_result = asyncio.run(auto_run_build_loop(meeting_id=meeting_id, behavior="fix_on_second"))

        return {
            "status": "SUCCESS",
            "meeting_id": meeting_id,
            "loop_run_id": loop_run_id,
            "workspace_path": str(workspace_path),
            "ide_launched": ide_launched,
            "clipboard_copied": clipboard_ok,
            "prompt_file": str(workspace_path / "PROMPT.md"),
            "prompt_text": formatted_prompt,
            "auto_executed": auto_execute,
            "build_result": build_result
        }
    except Exception as e:
        logger.error(f"[AutoLauncher] Setup and launch failed for meeting {meeting_id}: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "meeting_id": meeting_id
        }
    finally:
        db.close()
