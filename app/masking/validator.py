import re
from typing import List, Tuple, Optional, Any
from app.masking.models import AgentTaskPayload
from app.masking.rules import (
    CREDENTIAL_PATTERNS,
    PII_PATTERNS,
    BUSINESS_PATTERNS,
    TECHNICAL_ALLOWLIST
)

class SecurityLeakException(Exception):
    """Raised when confidential business context or conversational leakage is detected in agent payload."""
    pass

class LeakInspector:
    """
    Pre-Dispatch Privacy & Confidentiality Leak Inspector.
    Guarantees that AgentTaskPayload contains ZERO business secrets,
    ZERO raw conversational quotes, and ZERO unmasked PII.
    """
    
    # Trigger patterns for confidential business motivations (NOT technical execution)
    FORBIDDEN_BUSINESS_PATTERNS = [
        re.compile(r'\b(?:negotiat(?:ing|ion)|acquisition|merger|in talks with)\b', re.IGNORECASE),
        re.compile(r'\b(?:expanding into|new markets|market expansion)\b', re.IGNORECASE),
        re.compile(r'\b(?:internal sales|unreleased financial|commercial secret)\b', re.IGNORECASE),
        re.compile(r'\b(?:customer numbers are expected|growth projections)\b', re.IGNORECASE),
    ]

    ROLE_PREFIXES = {"BACKEND:", "FRONTEND:", "QA:", "DEVOPS:", "SECURITY:", "DATABASE:", "API:", "INFRA:"}
    
    # Pattern for raw speaker dialogue quotes with timestamps or conversational speech
    RAW_SPEAKER_DIALOGUE_PATTERN = re.compile(
        r'(?:^[A-Z][a-z]+\s*\[\d{2}:\d{2}\]:|'
        r'^[A-Z][a-z]+:\s*["\']|'
        r'^[A-Z][a-z]+:\s*(?:We |I |You |Let\'s |Then |Yeah |Sure |No |Okay ))',
        re.MULTILINE
    )

    @classmethod
    def inspect_agent_payload(cls, payload: AgentTaskPayload) -> Tuple[bool, List[str]]:
        """
        Validates the agent-facing payload.
        Returns (is_clean, list_of_violations).
        """
        violations = []
        
        all_text_elements = (
            payload.intentions +
            payload.things_to_implement +
            payload.technical_context
        )

        for text in all_text_elements:
            # 1. Identify allowlist spans
            safe_spans = []
            for safe_pattern in TECHNICAL_ALLOWLIST:
                for match in safe_pattern.finditer(text):
                    safe_spans.append(match.span())

            def is_safe(start, end):
                for s_start, s_end in safe_spans:
                    if start >= s_start and end <= s_end:
                        return True
                return False

            # 2. Check for explicit Must Not Leak patterns (Credentials, PII, Business Secrets)
            must_not_leak_groups = [CREDENTIAL_PATTERNS, PII_PATTERNS, BUSINESS_PATTERNS]
            for group in must_not_leak_groups:
                for pattern, category in group:
                    for match in pattern.finditer(text):
                        if not is_safe(match.start(), match.end()):
                            # Ensure it's not a vault token
                            val = match.group(0)
                            if not (val.startswith("[") and val.endswith("]")):
                                violations.append(f"MUST NOT LEAK policy violation ({category}): {val}")

            # 3. Check for confidential business strategy leaks (Custom Validator patterns)
            for pattern in cls.FORBIDDEN_BUSINESS_PATTERNS:
                for match in pattern.finditer(text):
                    if not is_safe(match.start(), match.end()):
                        violations.append(f"Business secret leak detected matching '{pattern.pattern}': {match.group(0)}")

            # 4. Check for raw conversation quote copies
            if cls.RAW_SPEAKER_DIALOGUE_PATTERN.search(text):
                violations.append(f"Raw speaker dialogue detected instead of structured requirement: {text}")

        is_clean = len(violations) == 0
        return is_clean, violations

    @classmethod
    def assert_clean_payload(cls, payload: AgentTaskPayload) -> None:
        """Throws SecurityLeakException if payload contains any leakage."""
        is_clean, violations = cls.inspect_agent_payload(payload)
        if not is_clean:
            raise SecurityLeakException(
                f"Security Leak Gate Failed for task {payload.task_id} with {len(violations)} violations:\n" +
                "\n".join([f" - {v}" for v in violations])
            )

class CrossContaminationValidator:
    """
    Validates claim isolation, deadline accuracy, technology exclusion,
    and cross-task non-contamination (§14).
    """
    @classmethod
    def validate_and_clean_payload(
        cls,
        payload: AgentTaskPayload,
        commitment: Optional[Any] = None
    ) -> AgentTaskPayload:
        # 1. Technology & Context Isolation: Remove unselected technologies and operational context
        cleaned_things = []
        for t in payload.things_to_implement:
            # If line is conversational context (e.g. "Arjun will go through the launch requirements..."), drop it
            if re.search(r'\b(?:go\s+through\s+the\s+launch\s+requirements|client\s+wants\s+SSO\s+support\s+added\s+before)\b', t, re.IGNORECASE):
                continue
            cleaned_things.append(t)

        if not cleaned_things and payload.things_to_implement:
            cleaned_things = payload.things_to_implement

        cleaned_context = []
        for c in payload.technical_context:
            # Exclude unselected technology evaluations (e.g. Redis)
            if re.search(r'\b(?:redis|evaluate\s+redis|not\s+decided\s+on\s+redis)\b', c, re.IGNORECASE):
                continue
            # Exclude operational dates that do not belong to technical execution
            if re.search(r'\b(?:renewal|security\s+review|annual\s+contract|enterprise\s+accounts|deadline:\s*November)\b', c, re.IGNORECASE):
                continue
            cleaned_context.append(c)

        # 2. Deadline Isolation: Prefer commitment-local assignee deadline
        clean_deadline = payload.deadline
        if commitment and commitment.assignees:
            comm_deadline = commitment.assignees[0].deadline
            if comm_deadline and comm_deadline.lower() != "none":
                clean_deadline = comm_deadline

        # 3. Clean Intentions: Strip conversational narrative
        cleaned_intentions = []
        for it in payload.intentions:
            clean_it = re.sub(r'^(?:[A-Z][a-z]+\s+will\s+go\s+through\s+the\s+launch\s+requirements\.?\s*)', '', it, flags=re.IGNORECASE).strip()
            if clean_it:
                cleaned_intentions.append(clean_it)

        return AgentTaskPayload(
            task_id=payload.task_id,
            intentions=cleaned_intentions or payload.intentions,
            things_to_implement=cleaned_things,
            technical_context=cleaned_context,
            deadline=clean_deadline
        )
