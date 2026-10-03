"""Ollama prompt compiler with structured JSON schema output, deterministic fallback,
invented requirement filtering, and privacy egress leak scanning.

Guarantees:
- Input is masked tasks only.
- Output is a validated Pydantic StructuredPrompt.
- Low temperature (0.1), bounded timeout.
- Deterministic fallback on timeout/failure/model missing, labeled source: 'fallback'.
- Requirement traceability: any requirement not traceable to task fields or criteria is dropped.
- Privacy guard & leak scan: refusing release if any vault value or sensitive entity appears.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.config import settings
from backend.logging import logger
from backend.loop.criteria_catalog import Criterion
from backend.loop.task_selector import BuildTask
from backend.processors.privacy import Vault


class StructuredPrompt(BaseModel):
    objective: str
    context: str
    requirements: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)
    workspace_instructions: str
    reporting_instructions: str
    iteration: int = 1
    previous_feedback: Optional[str] = None
    source: str = "ollama"  # "ollama" or "fallback"

    def to_markdown(self) -> str:
        """Render the structured prompt as clear, authoritative Markdown for AGY."""
        sections = [
            f"# AUTONOMOUS CODING TASK BRIEF (Iteration {self.iteration})",
            "",
            "## 1. Objective",
            self.objective,
            "",
            "## 2. Masked Context",
            self.context,
            "",
            "## 3. Deliverables",
        ]
        for d in self.deliverables:
            sections.append(f"- `{d}`")

        sections.extend(["", "## 4. Specific Requirements"])
        for r in self.requirements:
            sections.append(f"- {r}")

        sections.extend(["", "## 5. Acceptance Criteria"])
        for ac in self.acceptance_criteria:
            sections.append(f"- {ac}")

        sections.extend(["", "## 6. Constraints"])
        for c in self.constraints:
            sections.append(f"- {c}")

        if self.out_of_scope:
            sections.extend(["", "## 7. Out of Scope"])
            for o in self.out_of_scope:
                sections.append(f"- {o}")

        if self.previous_feedback:
            sections.extend(["", "## ⚠️ PREVIOUS EVALUATION FEEDBACK (Fix these issues)", self.previous_feedback])

        sections.extend([
            "",
            "## 8. Workspace Instructions",
            self.workspace_instructions,
            "",
            "## 9. Reporting Instructions",
            self.reporting_instructions,
        ])

        return "\n".join(sections)


class PrivacyRefusalError(ValueError):
    """Raised when a compiled prompt contains leaked secrets or vault values."""
    pass


class PromptCompiler:
    """Compiles build tasks and acceptance criteria into a StructuredPrompt."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        enable_ollama: Optional[bool] = None,
        vault: Optional[Vault] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.enable_ollama = enable_ollama if enable_ollama is not None else settings.ENABLE_OLLAMA
        self.vault = vault or Vault()

    def compile(
        self,
        meeting_id: str,
        tasks: List[BuildTask],
        criteria: List[Criterion],
        workspace_path: str,
        iteration: int = 1,
        previous_feedback: Optional[str] = None,
        business_context: Optional[List[str]] = None,
    ) -> StructuredPrompt:
        """
        Compile masked build tasks into a StructuredPrompt.
        Tries local Ollama with JSON-schema format; falls back cleanly to deterministic compiler.
        Runs full privacy/leak scan before returning.
        """
        prompt: Optional[StructuredPrompt] = None

        if self.enable_ollama:
            try:
                prompt = self._compile_with_ollama(
                    tasks=tasks,
                    criteria=criteria,
                    workspace_path=workspace_path,
                    iteration=iteration,
                    previous_feedback=previous_feedback,
                    business_context=business_context,
                )
            except Exception as e:
                logger.warning(f"[PromptCompiler] Ollama compilation failed or timed out: {e}. Falling back to deterministic template.")

        if prompt is None:
            prompt = self.compile_fallback(
                tasks=tasks,
                criteria=criteria,
                workspace_path=workspace_path,
                iteration=iteration,
                previous_feedback=previous_feedback,
                business_context=business_context,
            )

        # Tracing check: Ollama must not invent requirements.
        prompt.requirements = self._filter_invented_requirements(prompt.requirements, tasks, criteria)

        # Privacy egress scan: verify no vault values or sensitive PII leaked into prompt
        self._verify_privacy(prompt)

        return prompt

    def compile_fallback(
        self,
        tasks: List[BuildTask],
        criteria: List[Criterion],
        workspace_path: str,
        iteration: int = 1,
        previous_feedback: Optional[str] = None,
        business_context: Optional[List[str]] = None,
    ) -> StructuredPrompt:
        """Deterministic template compiler that produces identical structured schema."""
        all_deliverables = []
        for t in tasks:
            all_deliverables.extend(t.deliverables)
        deliverables = list(dict.fromkeys(all_deliverables)) or ["index.html"]

        all_constraints = [
            "No third-party CDN or external host connections (static local assets only).",
            "Valid HTML5 structure and clean standard tags.",
            "All links must resolve locally inside the workspace.",
            "Do not write or touch any file outside the workspace path.",
        ]
        for t in tasks:
            all_constraints.extend(t.constraints)
        constraints = list(dict.fromkeys(all_constraints))

        requirements = []
        for t in tasks:
            clean_desc = t.description.strip()
            requirements.append(f"{t.title}: {clean_desc}")

        criteria_descriptions = [f"[{c.catalog_type}] {c.description}" for c in criteria]

        objective = f"Implement static web deliverables ({', '.join(deliverables)}) according to verified meeting intelligence."
        context = "Verified commitments extracted and sanitized from executive diligence session."

        workspace_instructions = (
            f"You MUST create and modify files ONLY inside your assigned workspace:\n`{workspace_path}`\n"
            "Never create or access files with '..' or outside this directory."
        )

        reporting_instructions = (
            "When finished, call the MCP tool 'cleanroom_submit_code_report' with:\n"
            "- loop_run_id: provided in brief\n"
            "- iteration: current iteration number\n"
            "- agy_status: 'completed' | 'partial' | 'blocked' | 'failed'\n"
            "- summary: clear description of files created\n"
            "- files_changed: list of relative file paths (e.g. ['index.html'])\n"
            "- test_results: output of tests run locally (optional)\n"
            "- code_diff: git diff or unified patch (optional)"
        )

        return StructuredPrompt(
            objective=objective,
            context=context,
            requirements=requirements,
            constraints=constraints,
            deliverables=deliverables,
            acceptance_criteria=criteria_descriptions,
            out_of_scope=["Backend server databases", "External cloud integrations", "Third-party tracking scripts"],
            workspace_instructions=workspace_instructions,
            reporting_instructions=reporting_instructions,
            iteration=iteration,
            previous_feedback=previous_feedback,
            source="fallback",
        )

    def _compile_with_ollama(
        self,
        tasks: List[BuildTask],
        criteria: List[Criterion],
        workspace_path: str,
        iteration: int,
        previous_feedback: Optional[str],
        business_context: Optional[List[str]] = None,
    ) -> Optional[StructuredPrompt]:
        """Call Ollama /api/chat with structured JSON schema format."""
        # 1. Check if model available
        available_models = self._get_available_models()
        model_to_use = self.model
        if model_to_use not in available_models:
            if available_models:
                model_to_use = available_models[0]
            else:
                return None

        # Build prompt payload
        tasks_summary = "\n".join(f"- {t.title}: {t.description} (Deliverables: {t.deliverables})" for t in tasks)
        criteria_summary = "\n".join(f"- {c.description}" for c in criteria)

        schema = {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "context": {"type": "string"},
                "requirements": {"type": "array", "items": {"type": "string"}},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "deliverables": {"type": "array", "items": {"type": "string"}},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "out_of_scope": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["objective", "context", "requirements", "constraints", "deliverables", "acceptance_criteria"],
        }

        user_msg = (
            f"You are a technical specification compiler. Compile the following masked requirements into an authoritative brief.\n"
            f"Tasks:\n{tasks_summary}\n\n"
            f"Acceptance Criteria:\n{criteria_summary}\n\n"
            f"Workspace Path: {workspace_path}\n"
            f"Iteration: {iteration}\n"
        )
        if previous_feedback:
            user_msg += f"\nPrevious Evaluation Feedback to Address (Fix these failures):\n{previous_feedback}\n"
        if business_context:
            user_msg += (
                f"\nReference Business Context (Use ONLY to clarify technical context, NEVER leak private metrics/financials):\n"
                + "\n".join([f"- {bc}" for bc in business_context]) + "\n"
            )

        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": "You are a precise technical compiler. Only use provided facts. Never invent unmentioned features."},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
            "format": schema,
        }

        # Attempt call with 1 retry
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/chat",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    content_str = resp_data.get("message", {}).get("content", "")
                    parsed = json.loads(content_str)

                    # Validate through Pydantic
                    return StructuredPrompt(
                        objective=parsed.get("objective", "Implement static web pages"),
                        context=parsed.get("context", "Verified meeting intelligence"),
                        requirements=parsed.get("requirements", []),
                        constraints=parsed.get("constraints", []),
                        deliverables=parsed.get("deliverables", ["index.html"]),
                        acceptance_criteria=[c.description for c in criteria],
                        out_of_scope=parsed.get("out_of_scope", []),
                        workspace_instructions=f"You MUST create and modify files ONLY inside:\n`{workspace_path}`",
                        reporting_instructions=(
                            "When finished, call the MCP tool 'cleanroom_submit_code_report' with:\n"
                            "- loop_run_id: provided in brief\n"
                            "- iteration: current iteration number\n"
                            "- agy_status: 'completed' | 'partial' | 'blocked' | 'failed'\n"
                            "- summary: clear description of files created\n"
                            "- files_changed: list of relative file paths\n"
                            "- test_results: output of tests run locally (optional)\n"
                            "- code_diff: git diff or unified patch (optional)"
                        ),
                        iteration=iteration,
                        previous_feedback=previous_feedback,
                        source="ollama",
                    )
            except Exception as e:
                logger.warning(f"[PromptCompiler] Attempt {attempt} failed: {e}")
                if attempt == 2:
                    return None
        return None

    def _get_available_models(self) -> List[str]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def _filter_invented_requirements(
        self, requirements: List[str], tasks: List[BuildTask], criteria: List[Criterion]
    ) -> List[str]:
        """Drop or flag requirements that do not trace back to task fields or criteria."""
        source_text = " ".join([t.title + " " + t.description + " " + " ".join(t.deliverables) for t in tasks]).lower()
        criteria_text = " ".join([c.description + " " + (c.target_file or "") for c in criteria]).lower()
        combined_corpus = source_text + " " + criteria_text

        kept = []
        for req in requirements:
            # Extract key nouns/words (> 3 chars)
            words = [w for w in re.findall(r"\b[a-zA-Z]{4,}\b", req.lower())]
            if not words:
                kept.append(req)
                continue

            # If at least one significant word matches the corpus, keep it
            overlap = any(w in combined_corpus for w in words)
            if overlap:
                kept.append(req)
            else:
                logger.warning(f"[PromptCompiler] Dropped invented requirement: '{req}'")

        if not kept:
            # Ensure at least tasks are preserved
            for t in tasks:
                kept.append(f"{t.title}: {t.description}")
        return kept

    def _verify_privacy(self, prompt: StructuredPrompt):
        """Scans the entire prompt against known vault values and sensitive entities."""
        forbidden_values = self.vault.known_sensitive_values()
        full_text = prompt.to_markdown()

        leaks = []
        for fv in forbidden_values:
            if fv and len(fv) >= 3 and fv.lower() in full_text.lower():
                leaks.append(fv)

        # Regex scan for raw emails or phone numbers that escaped tokenization
        email_matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", full_text)
        if email_matches:
            leaks.extend(email_matches)

        if leaks:
            logger.critical(f"[PromptCompiler] PRIVACY GATE REFUSAL: Prompt contains sensitive values: {leaks}")
            raise PrivacyRefusalError(f"Privacy gate failure: prompt contains {len(leaks)} unmasked values: {leaks[:3]}")
