"""Scripted Fake Antigravity (AGY) Agent communicating with Nomad MCP server over stdio.

Implements 8 behaviors:
- good: Passes on iteration 1.
- fix_on_second: Deliberately misses criteria on iteration 1, fixes on iteration 2 using feedback.
- never_passes: Deliberately fails through all 3 iterations to prove hard cap at failed_max_iterations.
- lies: Reports success and fake passing pytest results, proving Nomad re-runs its own judge.
- tamper: Attempts to modify tests_nomad/ to force a pass; Nomad detects tamper and restores judge.
- escape: Attempts to report a file path outside the assigned workspace.
- leaky: Injects an unmasked vault secret into workspace files; Nomad catches leak.
- abandon: Pulls brief but never reports, verifying stale-session query and abort handling.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class FakeAGYAgent:
    """Scripted agent using standard MCP stdio protocol client."""

    def __init__(
        self,
        behavior: str = "good",
        python_executable: Optional[str] = None,
        enable_ollama: bool = False,
    ):
        self.behavior = behavior
        self.python_executable = python_executable or sys.executable
        self.enable_ollama = enable_ollama
        self.history: List[Dict[str, Any]] = []

    async def run(self, meeting_id: str, loop_run_id: Optional[str] = None) -> Dict[str, Any]:
        env = dict(os.environ)
        if not self.enable_ollama:
            env["ENABLE_OLLAMA"] = "false"

        server_params = StdioServerParameters(
            command=self.python_executable,
            args=["-m", "backend.mcp_server.server"],
            env=env,
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Step 1: Pull Brief
                brief_call = await session.call_tool(
                    "cleanroom_get_masked_brief",
                    {"meeting_id": meeting_id, "loop_run_id": loop_run_id},
                )
                brief_raw = self._extract_tool_text(brief_call)
                brief_data = json.loads(brief_raw)

                if brief_data.get("isError") or brief_data.get("status") in ("BLOCKED", "ERROR"):
                    return {
                        "final_verdict": "blocked",
                        "brief": brief_data,
                        "iterations": 0,
                        "history": self.history,
                    }

                active_run_id = brief_data["loop_run_id"]
                workspace_path = Path(brief_data["workspace_path"])
                workspace_path.mkdir(parents=True, exist_ok=True)

                if self.behavior == "abandon":
                    # Abandon without submitting report
                    return {
                        "final_verdict": "abandoned",
                        "loop_run_id": active_run_id,
                        "workspace_path": str(workspace_path),
                        "history": self.history,
                    }

                # Step 2: Iteration Loop (Max 3)
                current_iter = 1
                final_verdict = "unknown"
                last_report = None

                deliverables = brief_data.get("prompt", {}).get("deliverables", [])
                prompt_obj = brief_data.get("prompt", {})
                while current_iter <= 3:
                    # Write files according to selected behavior and actual meeting prompt
                    files_changed = self._apply_behavior_files(workspace_path, current_iter, deliverables, prompt_obj=prompt_obj)

                    # Build AGY report parameters
                    summary = f"AGY build attempt for iteration {current_iter}"
                    agy_status = "completed"
                    test_results = "All local unit tests passed."
                    diff = None

                    if self.behavior == "lies":
                        # Deliberately lie: report passed when files are broken
                        agy_status = "completed"
                        test_results = "================== 10 passed in 0.05s =================="

                    elif self.behavior == "escape":
                        # Attempt to escape workspace boundary
                        files_changed = ["../../secret_escaped.txt", "index.html"]

                    report_call = await session.call_tool(
                        "cleanroom_submit_code_report",
                        {
                            "loop_run_id": active_run_id,
                            "agy_status": agy_status,
                            "summary": summary,
                            "files_changed": files_changed,
                            "test_results": test_results,
                            "diff": diff,
                            "iteration": current_iter,
                        },
                    )

                    report_raw = self._extract_tool_text(report_call)
                    last_report = json.loads(report_raw)
                    verdict = last_report.get("verdict", "rejected")

                    self.history.append({
                        "iteration": current_iter,
                        "behavior": self.behavior,
                        "files_changed": files_changed,
                        "report": last_report,
                        "verdict": verdict,
                    })

                    if verdict == "passed":
                        final_verdict = "passed"
                        break
                    elif verdict == "failed_max_iterations":
                        final_verdict = "failed_max_iterations"
                        break
                    elif verdict == "revise":
                        current_iter += 1
                    else:
                        final_verdict = verdict
                        break

                return {
                    "final_verdict": final_verdict,
                    "loop_run_id": active_run_id,
                    "workspace_path": str(workspace_path),
                    "total_iterations": len(self.history),
                    "last_report": last_report,
                    "history": self.history,
                }

    def _apply_behavior_files(
        self,
        workspace: Path,
        iteration: int,
        deliverables: List[str] = None,
        prompt_obj: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Write files to workspace dynamically based on meeting objective, requirements, and behavior."""
        files = []
        p_obj = prompt_obj or {}
        raw_objective = p_obj.get("objective") or "Verified Deliverable"
        requirements = p_obj.get("requirements", [])

        # Clean title & brand based on actual meeting context
        is_hello_world = "hello world" in raw_objective.lower() or any("hello world" in r.lower() for r in requirements)
        has_counter = "counter" in raw_objective.lower() or any("counter" in r.lower() for r in requirements)

        if is_hello_world and has_counter:
            brand_name = "👋 Hello World & Counter"
            page_title = "Hello World & Interactive Counter - Verified Deliverable"
            hero_title = "Hello World!"
            hero_subtitle = "Autonomous deliverable implementing verified meeting commitments: Hello World page and live counter."
        elif is_hello_world:
            brand_name = "👋 Hello World"
            page_title = "Hello World Portal - Verified Deliverable"
            hero_title = "Hello World!"
            hero_subtitle = "Autonomous deliverable implementing verified meeting commitments with clean room isolation."
        else:
            brand_name = "🛡️ Verified Deliverables"
            page_title = f"{raw_objective} - Verified Deliverable"
            hero_title = raw_objective
            hero_subtitle = "Autonomous deliverable compiled from verified meeting commitments with 0 PII leakage."

        # Build dynamic requirement cards
        card_items = []
        for r in requirements:
            card_items.append(
                f"      <div class=\"card\">\n"
                f"        <h3>⚡ Verified Requirement</h3>\n"
                f"        <p>{r}</p>\n"
                f"      </div>"
            )
        if not card_items:
            card_items.append(
                "      <div class=\"card\">\n"
                "        <h3>🔒 Clean Room Security</h3>\n"
                "        <p>Zero unmasked secrets exported from the enterprise vault.</p>\n"
                "      </div>"
            )
        cards_html = "\n".join(card_items)

        # Counter component snippet if counter requested
        counter_snippet = ""
        if has_counter:
            counter_snippet = (
                "    <section class=\"card\" style=\"text-align: center; margin: 30px auto; max-width: 480px;\">\n"
                "      <h2 style=\"color: var(--primary); margin-top: 0;\">Interactive Counter</h2>\n"
                "      <p style=\"color: #5C5248;\">Live JavaScript state counter verified by acceptance criteria.</p>\n"
                "      <div style=\"font-size: 56px; font-weight: 800; color: var(--primary); margin: 20px 0;\" id=\"counter-value\">0</div>\n"
                "      <div style=\"display: flex; gap: 12px; justify-content: center;\">\n"
                "        <button type=\"button\" class=\"btn-cta\" onclick=\"changeCounter(-1)\" style=\"padding: 10px 24px; font-size: 16px;\">- Decrement</button>\n"
                "        <button type=\"button\" class=\"btn-cta\" onclick=\"resetCounter()\" style=\"background: #5C5248; padding: 10px 18px; font-size: 16px;\">Reset</button>\n"
                "        <button type=\"button\" class=\"btn-cta\" onclick=\"changeCounter(1)\" style=\"padding: 10px 24px; font-size: 16px;\">+ Increment</button>\n"
                "      </div>\n"
                "    </section>\n"
                "    <script>\n"
                "      let count = 0;\n"
                "      function changeCounter(delta) {\n"
                "        count += delta;\n"
                "        document.getElementById('counter-value').innerText = count;\n"
                "      }\n"
                "      function resetCounter() {\n"
                "        count = 0;\n"
                "        document.getElementById('counter-value').innerText = count;\n"
                "      }\n"
                "    </script>\n"
            )

        if self.behavior == "good" or (self.behavior == "fix_on_second" and iteration >= 2):
            # Compliant, fully styled modern web deliverables matching meeting context
            style_css = workspace / "style.css"
            style_css.write_text(
                ":root {\n"
                "  --primary: #B85B35;\n"
                "  --secondary: #3B7A57;\n"
                "  --bg: #EDE8DF;\n"
                "  --card: #F7F4EE;\n"
                "  --text: #2D2824;\n"
                "}\n"
                "body {\n"
                "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\n"
                "  margin: 0; padding: 0; background: var(--bg); color: var(--text);\n"
                "  line-height: 1.6;\n"
                "}\n"
                "header {\n"
                "  background: var(--card); border-bottom: 2px solid #D9D2C5; padding: 20px 40px;\n"
                "  display: flex; justify-content: space-between; align-items: center;\n"
                "}\n"
                "nav a {\n"
                "  margin-left: 20px; text-decoration: none; color: var(--primary); font-weight: 700;\n"
                "}\n"
                ".hero {\n"
                "  padding: 60px 40px; text-align: center; background: linear-gradient(180deg, var(--card) 0%, var(--bg) 100%);\n"
                "}\n"
                ".hero h1 { font-size: 40px; color: var(--primary); margin-bottom: 12px; }\n"
                ".hero p { font-size: 18px; color: #5C5248; max-width: 650px; margin: 0 auto 24px auto; }\n"
                ".cards-grid {\n"
                "  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px;\n"
                "  max-width: 1000px; margin: 40px auto; padding: 0 20px;\n"
                "}\n"
                ".card {\n"
                "  background: var(--card); border: 1px solid #D9D2C5; border-radius: 12px; padding: 24px;\n"
                "  box-shadow: 4px 4px 12px rgba(0,0,0,0.04);\n"
                "}\n"
                ".card h3 { color: var(--secondary); margin-top: 0; }\n"
                "footer {\n"
                "  text-align: center; padding: 30px; font-size: 14px; color: #7D7267;\n"
                "  border-top: 1px solid #D9D2C5; margin-top: 40px;\n"
                "}\n"
                ".btn-cta {\n"
                "  display: inline-block; background: var(--primary); color: #fff; padding: 12px 28px;\n"
                "  border-radius: 8px; text-decoration: none; font-weight: 700; border: none; cursor: pointer;\n"
                "}\n",
                encoding="utf-8"
            )
            files.append("style.css")

            script_js = workspace / "script.js"
            script_js.write_text(
                "// Autonomous Clean Room Client Script\n"
                "let count = 0;\n\n"
                "function changeCounter(delta) {\n"
                "  count += delta;\n"
                "  const el = document.getElementById('counter-value');\n"
                "  if (el) el.innerText = count;\n"
                "}\n\n"
                "function resetCounter() {\n"
                "  count = 0;\n"
                "  const el = document.getElementById('counter-value');\n"
                "  if (el) el.innerText = count;\n"
                "}\n\n"
                "document.addEventListener('DOMContentLoaded', () => {\n"
                "  console.log('Clean room deliverables initialized successfully.');\n"
                "});\n",
                encoding="utf-8"
            )
            files.append("script.js")

            idx = workspace / "index.html"
            idx.write_text(
                "<!DOCTYPE html>\n"
                "<html lang=\"en\">\n"
                "<head>\n"
                "  <meta charset=\"UTF-8\">\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                f"  <title>{page_title}</title>\n"
                "  <link rel=\"stylesheet\" href=\"style.css\">\n"
                "</head>\n"
                "<body>\n"
                "  <header>\n"
                f"    <div style=\"font-size: 20px; font-weight: 800; color: #B85B35;\">{brand_name}</div>\n"
                "    <nav>\n"
                "      <a href=\"index.html\">Home</a>\n"
                "      <a href=\"contact.html\">Contact</a>\n"
                "    </nav>\n"
                "  </header>\n"
                "  <main>\n"
                "    <section class=\"hero\">\n"
                f"      <h1>{hero_title}</h1>\n"
                f"      <p>{hero_subtitle}</p>\n"
                "      <a href=\"contact.html\" class=\"btn-cta\">Get in Touch &rarr;</a>\n"
                "    </section>\n"
                f"{counter_snippet}\n"
                "    <section class=\"cards-grid\">\n"
                f"{cards_html}\n"
                "    </section>\n"
                "  </main>\n"
                "  <footer>\n"
                "    <p>&copy; 2026 Quarantined Clean Room Build. All rights reserved.</p>\n"
                "  </footer>\n"
                "  <script src=\"script.js\"></script>\n"
                "</body>\n"
                "</html>\n",
                encoding="utf-8",
            )
            files.append("index.html")

            cnt = workspace / "contact.html"
            cnt.write_text(
                "<!DOCTYPE html>\n"
                "<html lang=\"en\">\n"
                "<head>\n"
                "  <meta charset=\"UTF-8\">\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                f"  <title>Contact - {brand_name}</title>\n"
                "  <link rel=\"stylesheet\" href=\"style.css\">\n"
                "</head>\n"
                "<body>\n"
                "  <header>\n"
                f"    <div style=\"font-size: 20px; font-weight: 800; color: #B85B35;\">{brand_name}</div>\n"
                "    <nav>\n"
                "      <a href=\"index.html\">&larr; Back to Home</a>\n"
                "    </nav>\n"
                "  </header>\n"
                "  <main style=\"max-width: 600px; margin: 40px auto; padding: 0 20px;\">\n"
                "    <div class=\"card\">\n"
                "      <h2>Contact & Feedback</h2>\n"
                "      <form action=\"#\" method=\"post\">\n"
                "        <p>\n"
                "          <label for=\"name\" style=\"display: block; font-weight: 700; margin-bottom: 4px;\">Full Name:</label>\n"
                "          <input id=\"name\" type=\"text\" name=\"name\" style=\"width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #D9D2C5; box-sizing: border-box;\" required>\n"
                "        </p>\n"
                "        <p>\n"
                "          <label for=\"email\" style=\"display: block; font-weight: 700; margin-bottom: 4px;\">Email Address:</label>\n"
                "          <input id=\"email\" type=\"email\" name=\"email\" style=\"width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #D9D2C5; box-sizing: border-box;\" required>\n"
                "        </p>\n"
                "        <p>\n"
                "          <label for=\"message\" style=\"display: block; font-weight: 700; margin-bottom: 4px;\">Message:</label>\n"
                "          <textarea id=\"message\" name=\"message\" rows=\"4\" style=\"width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #D9D2C5; box-sizing: border-box;\"></textarea>\n"
                "        </p>\n"
                "        <button type=\"submit\" class=\"btn-cta\" style=\"border: none; cursor: pointer; width: 100%;\">Submit Message</button>\n"
                "      </form>\n"
                "    </div>\n"
                "  </main>\n"
                "  <footer>\n"
                "    <p>&copy; 2026 Quarantined Clean Room Build.</p>\n"
                "  </footer>\n"
                "</body>\n"
                "</html>\n",
                encoding="utf-8",
            )
            files.append("contact.html")

        elif self.behavior == "fix_on_second" and iteration == 1:
            # Deliberate defects: missing <title> in index.html, unlabeled input in contact.html
            idx = workspace / "index.html"
            idx.write_text(
                f"<!DOCTYPE html>\n<html><head></head><body><h1>{hero_title}</h1><p>Draft work without title.</p></body></html>",
                encoding="utf-8",
            )
            files.append("index.html")

            cnt = workspace / "contact.html"
            cnt.write_text(
                "<!DOCTYPE html>\n<html><head><title>Contact</title></head><body>"
                "<form><input type='text' name='unlabeled_input'><button type='submit'>Go</button></form>"
                "</body></html>",
                encoding="utf-8",
            )
            files.append("contact.html")

        elif self.behavior == "never_passes":
            # Always write empty/broken files
            idx = workspace / "index.html"
            idx.write_text("broken content without tags", encoding="utf-8")
            files.append("index.html")

        elif self.behavior == "lies":
            # Broken content, but agent will report all passed
            idx = workspace / "index.html"
            idx.write_text("broken content without tags", encoding="utf-8")
            files.append("index.html")

        elif self.behavior == "tamper":
            # Write a partial index.html, then try to tamper with tests_nomad/
            idx = workspace / "index.html"
            idx.write_text("<!DOCTYPE html><html><body><h1>Tampered</h1></body></html>", encoding="utf-8")
            files.append("index.html")

            # Agent attempts to tamper with judge
            judge_dir = workspace / "tests_nomad"
            judge_dir.mkdir(parents=True, exist_ok=True)
            fake_judge = judge_dir / "test_acceptance.py"
            fake_judge.write_text("def test_fake(): assert True\n", encoding="utf-8")
            files.append("tests_nomad/test_acceptance.py")

        elif self.behavior == "escape":
            idx = workspace / "index.html"
            idx.write_text("<!DOCTYPE html><html><head><title>Test</title></head><body><h1>Escaping</h1></body></html>", encoding="utf-8")
            files.append("index.html")

        elif self.behavior == "leaky":
            # Leaks unmasked vault value (the fake real email)
            idx = workspace / "index.html"
            idx.write_text(
                "<!DOCTYPE html>\n<html><head><title>Leaky Page</title></head><body>"
                "<h1>Confidential Info</h1>"
                "<p>Direct inquiries to billing@acme-widgets-fictional.com</p>"
                "</body></html>",
                encoding="utf-8",
            )
            files.append("index.html")

        if deliverables and self.behavior in ("good", "fix_on_second"):
            for d in deliverables:
                if d not in files:
                    dp = workspace / d
                    dp.parent.mkdir(parents=True, exist_ok=True)
                    if not dp.exists():
                        if d.endswith(".css"):
                            dp.write_text("body { font-family: sans-serif; }\n", encoding="utf-8")
                        elif d.endswith(".js"):
                            dp.write_text("console.log('ready');\n", encoding="utf-8")
                        else:
                            dp.write_text(f"<!DOCTYPE html>\n<html><head><title>{d}</title></head><body><h1>{d}</h1></body></html>\n", encoding="utf-8")
                    files.append(d)

        return files

    def _extract_tool_text(self, tool_result) -> str:
        """Extract text content from an MCP CallToolResult object."""
        if hasattr(tool_result, "content") and tool_result.content:
            for item in tool_result.content:
                if hasattr(item, "text"):
                    return item.text
        return str(tool_result)
