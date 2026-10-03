"""Nomad Local Evaluator: subprocess-based acceptance testing, scrubbed environment,
tamper detection, workspace bounds checking, leak scanning, and feedback re-masking.

Guarantees:
- Judge isolation: acceptance test suite is stored outside the workspace and copied
  into <workspace>/tests_nomad/ at evaluation time (overwriting any modified files).
- Subprocess execution: tests run via pytest in an isolated subprocess with bounded timeout.
- Scrubbed environment: all API keys, tokens, and sensitive env vars removed from subprocess.
- Tamper detection: compares hash of any existing test file before overwrite.
- Workspace guard: validates that all reported files are inside the allowed workspace directory.
- Leak detection: checks all files in workspace for unmasked sensitive values from the vault.
- Feedback re-masking: all test failure outputs and error messages are passed through the
  vault to ensure no unmasked value ever reaches AGY.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.logging import logger
from backend.loop.workspace import is_path_inside_workspace, validate_workspace_files
from backend.processors.privacy import Vault


class CriterionEvaluation(BaseModel):
    criterion_id: str
    status: str  # "passed" | "failed"
    message: Optional[str] = None


class EvaluationResult(BaseModel):
    verdict: str  # "pass" | "fail"
    passed_count: int = 0
    failed_count: int = 0
    total_count: int = 0
    criterion_results: List[CriterionEvaluation] = Field(default_factory=list)
    masked_failure_messages: List[str] = Field(default_factory=list)
    tamper_detected: bool = False
    workspace_violation: bool = False
    leak_detected: bool = False
    judge_hash: str = ""
    raw_output: str = ""


class LocalEvaluator:
    """Evaluates AGY submissions strictly and locally."""

    SENSITIVE_ENV_VARS = {
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MEETILY_TOKEN",
        "MEETILY_API_TOKEN",
        "WEBHOOK_SECRET",
        "NOMAD_VAULT_KEY",
        "NOMAD_LEDGER_KEY",
        "SECRET_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    }

    def __init__(self, vault: Optional[Vault] = None, timeout_seconds: float = 20.0):
        self.vault = vault or Vault()
        self.timeout_seconds = timeout_seconds

    def evaluate(
        self,
        workspace_dir: Path,
        judge_source_file: Path,
        expected_judge_hash: str,
        files_changed: Optional[List[str]] = None,
        rehydrate_evaluation_copy: bool = False,
    ) -> EvaluationResult:
        """
        Run the complete evaluation workflow:
        1. Workspace path guard on reported files.
        2. Leak scan across all files in workspace.
        3. Copy fresh acceptance judge to <workspace>/tests_nomad/ and check tamper.
        4. Run pytest in clean subprocess.
        5. Re-mask all output before returning result.
        """
        workspace = workspace_dir.resolve()
        files_changed = files_changed or []

        # 1. Workspace boundary validation
        valid_paths, violations = validate_workspace_files(files_changed, workspace)
        workspace_violation = not valid_paths

        # Also inspect workspace for directory traversal / escape attempts
        for p in files_changed:
            if ".." in str(p) or Path(p).is_absolute() and not is_path_inside_workspace(p, workspace):
                workspace_violation = True
                violations.append(str(p))

        # 2. Leak scan on workspace files
        leak_detected, leaked_items = self._scan_workspace_for_leaks(workspace)

        # 3. Judge deployment and tamper detection
        tests_nomad_dir = workspace / "tests_nomad"
        tests_nomad_dir.mkdir(parents=True, exist_ok=True)
        deployed_judge_file = tests_nomad_dir / "test_acceptance.py"

        tamper_detected = False
        if deployed_judge_file.exists():
            existing_content = deployed_judge_file.read_bytes().replace(b"\r\n", b"\n")
            existing_hash = hashlib.sha256(existing_content).hexdigest()
            if existing_hash != expected_judge_hash:
                tamper_detected = True
                logger.warning(
                    f"[Evaluator] Judge file was tampered with! Expected hash {expected_judge_hash[:12]}, found {existing_hash[:12]}. Restoring judge."
                )

        # Always overwrite with canonical judge from Nomad data directory
        shutil.copy2(judge_source_file, deployed_judge_file)

        # If rehydration is requested, create an evaluation copy in a temporary subdirectory
        eval_run_dir = workspace
        if rehydrate_evaluation_copy:
            eval_run_dir = self._create_rehydrated_eval_copy(workspace)

        # 4. Execute test runner in isolated subprocess
        exec_success, raw_stdout, raw_stderr = self._run_pytest_subprocess(eval_run_dir, deployed_judge_file)

        # 5. Clean up temporary rehydrated copy if one was made
        if rehydrate_evaluation_copy and eval_run_dir != workspace and eval_run_dir.exists():
            shutil.rmtree(eval_run_dir, ignore_errors=True)

        # 6. Parse and re-mask output
        combined_output = f"{raw_stdout}\n{raw_stderr}".strip()
        masked_output = self._remask_text(combined_output)

        criterion_results, passed_count, failed_count, failure_msgs = self._parse_pytest_output(combined_output)

        # Re-mask failure messages
        masked_failure_messages = [self._remask_text(m) for m in failure_msgs]

        # Fail if violations or leaks were found
        overall_pass = (
            exec_success
            and not workspace_violation
            and not leak_detected
            and not tamper_detected
            and failed_count == 0
            and passed_count > 0
        )

        if workspace_violation:
            masked_failure_messages.append(f"Workspace violation: file paths outside workspace: {violations}")
        if leak_detected:
            masked_failure_messages.append(f"Security violation: unmasked sensitive data detected in workspace files: {leaked_items}")
        if tamper_detected:
            masked_failure_messages.append("Tamper violation: judge tests in tests_nomad/ were modified or deleted by agent.")

        verdict = "pass" if overall_pass else "fail"

        return EvaluationResult(
            verdict=verdict,
            passed_count=passed_count,
            failed_count=failed_count + (1 if (workspace_violation or leak_detected or tamper_detected) else 0),
            total_count=passed_count + failed_count,
            criterion_results=criterion_results,
            masked_failure_messages=masked_failure_messages,
            tamper_detected=tamper_detected,
            workspace_violation=workspace_violation,
            leak_detected=leak_detected,
            judge_hash=expected_judge_hash,
            raw_output=masked_output,
        )

    def _scan_workspace_for_leaks(self, workspace: Path) -> tuple[bool, List[str]]:
        """Check all deliverable files in workspace against sensitive values."""
        sensitive_values = self.vault.known_sensitive_values()
        if not sensitive_values:
            return False, []

        leaks = []
        for file_path in workspace.rglob("*"):
            if not file_path.is_file():
                continue
            if "tests_nomad" in file_path.parts:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                for s in sensitive_values:
                    if s and len(s) >= 4 and s in content:
                        leaks.append(f"{file_path.name}: {s}")
            except Exception:
                pass

        return (len(leaks) > 0), leaks

    def _create_rehydrated_eval_copy(self, workspace: Path) -> Path:
        """Create a sandbox copy with rehydrated vault tokens for evaluating unmasked invariants."""
        eval_copy_dir = workspace / ".eval_sandbox"
        if eval_copy_dir.exists():
            shutil.rmtree(eval_copy_dir, ignore_errors=True)

        shutil.copytree(workspace, eval_copy_dir, ignore=shutil.ignore_patterns(".eval_sandbox", "tests_nomad"))

        for file_path in eval_copy_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix in (".html", ".css", ".js", ".json", ".txt"):
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                    rehydrated = self.vault.rehydrate(text)
                    file_path.write_text(rehydrated, encoding="utf-8")
                except Exception:
                    pass

        return eval_copy_dir

    def _run_pytest_subprocess(self, run_dir: Path, judge_file: Path) -> tuple[bool, str, str]:
        """Run pytest in a scrubbed environment subprocess."""
        # Clean environment
        scrubbed_env = dict(os.environ)
        for var in self.SENSITIVE_ENV_VARS:
            scrubbed_env.pop(var, None)

        scrubbed_env["NOMAD_WORKSPACE_DIR"] = str(run_dir.resolve())
        scrubbed_env["PYTHONDONTWRITEBYTECODE"] = "1"

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(judge_file.resolve()),
            "-v",
            "--tb=short",
            "-o",
            "pythonpath=.",
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(run_dir.resolve()),
                env=scrubbed_env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            success = proc.returncode == 0
            return success, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"[Evaluator] Test execution timed out after {self.timeout_seconds}s")
            return False, "", f"Execution timed out after {self.timeout_seconds} seconds."
        except Exception as e:
            logger.error(f"[Evaluator] Subprocess execution failed: {e}")
            return False, "", str(e)

    def _parse_pytest_output(self, output: str) -> tuple[List[CriterionEvaluation], int, int, List[str]]:
        """Parse pytest verbose output to extract per-test results and failure messages."""
        criterion_results = []
        passed = 0
        failed = 0
        failure_messages = []

        for line in output.splitlines():
            line_str = line.strip()
            if "::test_" in line_str:
                parts = line_str.split("::")
                test_spec = parts[-1]
                test_name = test_spec.split()[0]
                if "PASSED" in line_str:
                    passed += 1
                    criterion_results.append(CriterionEvaluation(criterion_id=test_name, status="passed"))
                elif "FAILED" in line_str:
                    failed += 1
                    criterion_results.append(CriterionEvaluation(criterion_id=test_name, status="failed"))

            elif line_str.startswith("E   ") or "AssertionError:" in line_str or "FAILED" in line_str:
                if len(line_str) > 4:
                    clean_msg = line_str.lstrip("E ").strip()
                    if clean_msg and clean_msg not in failure_messages:
                        failure_messages.append(clean_msg)

        return criterion_results, passed, failed, failure_messages

    def _remask_text(self, text: str) -> str:
        """
        Re-mask any unmasked sensitive values that might appear in compiler/test output.
        Uses the vault to replace real values with tokens.
        """
        if not text:
            return ""

        # Check all known sensitive values in vault
        masked = text
        for token, original in self.vault._token_to_entity.items():
            if original and len(original) >= 3 and original in masked:
                masked = masked.replace(original, token)

        return masked
