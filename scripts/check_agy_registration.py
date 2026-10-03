"""Diagnosis and Registration Checker for Nomad Clean Room MCP Server in Google Antigravity (AGY).

Features:
- Locates mcp_config.json and AGY schema folder (defaults to USERPROFILE/.gemini, supports C:\\Users\\Jeyaraman).
- Verifies command and cwd paths.
- Spawns live Nomad MCP server via stdio and queries tools/list.
- Reports schema drift between disk schemas and live MCP server tools.
- Evaluates whether schema files are IDE-generated or hand-written.
- Writes proposed registration and schema files to docs/agy_registration/.
- Safe by default: NEVER writes to ~/.gemini unless --apply is explicitly passed.
- When --apply is passed: prints a unified diff, creates a timestamped backup, and updates the configuration.
"""

import argparse
import asyncio
import difflib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def resolve_gemini_paths(home_override: str = None):
    """Resolve .gemini directory, checking specified override, current user, or Jeyaraman."""
    candidates = []
    if home_override:
        candidates.append(Path(home_override))
    candidates.append(Path(r"C:\Users\Jeyaraman"))
    candidates.append(Path.home())

    for cand in candidates:
        gemini_dir = cand / ".gemini"
        if gemini_dir.exists():
            return gemini_dir, cand

    # Default to current user home
    return Path.home() / ".gemini", Path.home()


async def get_live_mcp_tools(python_exe: str, cwd: Path):
    """Spawn the live Nomad MCP server and retrieve tool definitions."""
    server_params = StdioServerParameters(
        command=python_exe,
        args=["-m", "backend.mcp_server.server"],
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        cwd=str(cwd),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()
            return response.tools


def generate_proposed_mcp_config(python_exe: Path, project_root: Path) -> dict:
    """Generate canonical MCP server configuration dictionary."""
    return {
        "mcpServers": {
            "nomad-cleanroom": {
                "command": str(python_exe),
                "args": ["-m", "backend.mcp_server.server"],
                "cwd": str(project_root),
                "env": {
                    "PYTHONUNBUFFERED": "1",
                    "AGY_WORKSPACE_ROOT": str(PROJECT_ROOT.parent / "test") if (PROJECT_ROOT.parent / "test").exists() else "auto"
                }
            }
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Check and manage Nomad MCP registration for Antigravity")
    parser.add_argument("--home-dir", type=str, help="Override home directory to inspect (e.g. C:\\Users\\Jeyaraman)")
    parser.add_argument("--apply", action="store_true", help="Apply proposed configuration and schemas with backup")
    args = parser.parse_args()

    print("=" * 70)
    print(" [*] NOMAD MCP REGISTRATION & DRIFT DIAGNOSIS FOR ANTIGRAVITY")
    print("=" * 70)

    gemini_dir, resolved_home = resolve_gemini_paths(args.home_dir)
    mcp_config_path = gemini_dir / "config" / "mcp_config.json"
    schema_dir = gemini_dir / "antigravity-ide" / "mcp" / "nomad-cleanroom"
    docs_output_dir = PROJECT_ROOT / "docs" / "agy_registration"
    docs_schema_dir = docs_output_dir / "schemas"
    docs_schema_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Paths] Inspecting Home:      {resolved_home}")
    print(f"[Paths] Gemini Dir:           {gemini_dir}")
    print(f"[Paths] MCP Config Path:      {mcp_config_path}")
    print(f"[Paths] IDE Schema Dir:       {schema_dir}")
    print(f"[Paths] Proposed Output Dir:  {docs_output_dir}\n")

    # 1. Inspect existing mcp_config.json
    existing_config = {}
    config_exists = mcp_config_path.exists()
    if config_exists:
        try:
            content = mcp_config_path.read_text(encoding="utf-8").strip()
            if content:
                existing_config = json.loads(content)
                print(f"[+] Found existing mcp_config.json ({len(content)} bytes)")
            else:
                print("[!] mcp_config.json exists but is EMPTY.")
        except Exception as e:
            print(f"[-] Error reading mcp_config.json: {e}")
    else:
        print("[-] mcp_config.json DOES NOT EXIST.")

    server_entry = existing_config.get("mcpServers", {}).get("nomad-cleanroom", {})
    if server_entry:
        cmd = server_entry.get("command", "")
        cwd = server_entry.get("cwd", "")
        print(f"[Config] nomad-cleanroom registered:")
        print(f"  command: {cmd} (Exists: {Path(cmd).exists() if cmd else False})")
        print(f"  cwd:     {cwd} (Exists: {Path(cwd).exists() if cwd else False})")
    else:
        print("[!] nomad-cleanroom is NOT registered in mcp_config.json.")

    # 2. Find best python executable
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    python_exe = venv_python if venv_python.exists() else Path(sys.executable)
    print(f"[Python] Target Python executable: {python_exe} (Exists: {python_exe.exists()})")

    # 3. Query Live MCP Server Tools
    print("\n[*] Spawning live Nomad MCP server to query tools/list...")
    try:
        live_tools = asyncio.run(get_live_mcp_tools(str(python_exe), PROJECT_ROOT))
        live_tool_names = sorted([t.name for t in live_tools])
        print(f"[+] Server started successfully. Found {len(live_tools)} live tools:")
        for name in live_tool_names:
            print(f"    - {name}")
    except Exception as e:
        print(f"[-] FAILED to spawn live MCP server: {e}")
        live_tools = []
        live_tool_names = []

    # 4. Inspect Disk Schemas and Detect Drift
    disk_schemas = {}
    if schema_dir.exists():
        for sf in schema_dir.glob("*.json"):
            try:
                disk_schemas[sf.stem] = json.loads(sf.read_text(encoding="utf-8"))
            except Exception:
                pass
        print(f"\n[+] Found {len(disk_schemas)} schema JSON files on disk in {schema_dir}")
    else:
        print(f"\n[!] IDE schema directory {schema_dir} does not exist.")

    drift_report = []
    # Missing on disk
    for t in live_tools:
        if t.name not in disk_schemas:
            drift_report.append(f"MISSING ON DISK: Tool '{t.name}' is live in MCP server but has no schema JSON in {schema_dir.name}")
        else:
            # Compare schemas
            disk_input = disk_schemas[t.name].get("inputSchema", {})
            raw_live = getattr(t, "input_schema", getattr(t, "inputSchema", {}))
            live_input = raw_live if isinstance(raw_live, dict) else (raw_live.model_dump() if hasattr(raw_live, "model_dump") else {})
            if disk_input != live_input:
                drift_report.append(f"SCHEMA DRIFT: Tool '{t.name}' parameters differ between live server and disk schema.")

    # Extra on disk
    for d_name in disk_schemas:
        if d_name not in live_tool_names:
            drift_report.append(f"EXTRA ON DISK: Schema '{d_name}.json' exists on disk but is not provided by live MCP server.")

    print("\n--- Drift Assessment ---")
    if not drift_report:
        print("[+] Zero drift! Live MCP tools and disk schemas are perfectly aligned.")
    else:
        for item in drift_report:
            print(f"  [!] {item}")

    # 5. Schema Origin Analysis
    print("\n--- Schema Origin Analysis ---")
    if not disk_schemas:
        print("Conclusion: No schema files exist on disk. In Google Antigravity / AGY, tool schemas are either")
        print("dynamically fetched at runtime via MCP stdio tools/list, or cached when an MCP server is first")
        print("registered. Hand-written schema files are not strictly required for standard stdio MCP servers.")
    else:
        # Check metadata
        is_ide_generated = any("$schema" in s or "generated" in str(s).lower() for s in disk_schemas.values())
        print(f"Conclusion: Existing schema files appear to be {'IDE-generated' if is_ide_generated else 'hand-written/exported'}.")

    # 6. Generate proposed configuration and schemas in docs/agy_registration/
    proposed_cfg = generate_proposed_mcp_config(python_exe, PROJECT_ROOT)
    proposed_cfg_path = docs_output_dir / "mcp_config.json"
    proposed_cfg_text = json.dumps(proposed_cfg, indent=2) + "\n"
    proposed_cfg_path.write_text(proposed_cfg_text, encoding="utf-8")
    print(f"\n[+] Wrote proposed mcp_config.json to: {proposed_cfg_path}")

    # Write tool schemas
    for t in live_tools:
        schema = getattr(t, "input_schema", getattr(t, "inputSchema", {}))
        schema_obj = {
            "name": t.name,
            "description": t.description,
            "inputSchema": schema if isinstance(schema, dict) else (schema.model_dump() if hasattr(schema, "model_dump") else {}),
        }
        (docs_schema_dir / f"{t.name}.json").write_text(json.dumps(schema_obj, indent=2) + "\n", encoding="utf-8")
    print(f"[+] Wrote {len(live_tools)} tool schema definitions to: {docs_schema_dir}")

    # 7. Handle --apply
    if args.apply:
        print("\n" + "=" * 70)
        print(" [*] APPLYING CONFIGURATION TO USER PROFILE")
        print("=" * 70)

        # Diff preview
        old_text = mcp_config_path.read_text(encoding="utf-8") if config_exists else ""
        merged_cfg = existing_config.copy()
        if "mcpServers" not in merged_cfg:
            merged_cfg["mcpServers"] = {}
        merged_cfg["mcpServers"]["nomad-cleanroom"] = proposed_cfg["mcpServers"]["nomad-cleanroom"]
        new_text = json.dumps(merged_cfg, indent=2) + "\n"

        print("--- Unified Diff for mcp_config.json ---")
        diff = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(mcp_config_path),
            tofile="proposed_mcp_config.json"
        ))
        if diff:
            sys.stdout.writelines(diff)
        else:
            print("(No changes needed for mcp_config.json)")

        # Create timestamped backup
        backup_dir = gemini_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if config_exists and old_text:
            backup_file = backup_dir / f"mcp_config_{ts}.json.bak"
            backup_file.write_text(old_text, encoding="utf-8")
            print(f"[+] Created backup: {backup_file}")

        # Write config
        mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_config_path.write_text(new_text, encoding="utf-8")
        print(f"[+] Updated: {mcp_config_path}")

        # Copy schemas to schema_dir
        schema_dir.mkdir(parents=True, exist_ok=True)
        for sf in docs_schema_dir.glob("*.json"):
            shutil.copy2(sf, schema_dir / sf.name)
        print(f"[+] Copied {len(list(docs_schema_dir.glob('*.json')))} schemas to {schema_dir}")
        print("[+] Application completed successfully.")
    else:
        print("\n[NOTE] Safe mode: No changes were made to the user's home directory.")
        print("To apply this configuration, re-run with --apply.")


if __name__ == "__main__":
    main()
