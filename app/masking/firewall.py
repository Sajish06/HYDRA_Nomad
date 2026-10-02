from typing import Tuple, List
from app.masking.models import AgentTaskPayload, AuditEntry
from app.masking.vault import EntityVault
from app.masking.rules import mask_text_with_rules
from app.masking.validator import LeakInspector

class DeterministicFirewall:
    """
    Layer 2: Deterministic Python / FastAPI Privacy Firewall.
    Runs after Layer 1 (Semantic Decomposition).
    Applies exhaustive regex scrubbing for:
      - Credentials (API keys, AWS keys, JWTs, DB URIs, Passwords)
      - PII (Emails, Phones, SSNs, Credit Cards)
      - Network Infrastructure (IP addresses, Internal hosts)
      - Financial amounts ($ figures, sensitive percentages)
    Enforces the Pre-Dispatch Leak Inspector Gate before allowing any payload to pass.
    """
    @classmethod
    def sanitize_agent_payload(
        cls,
        payload: AgentTaskPayload,
        vault: EntityVault
    ) -> Tuple[AgentTaskPayload, List[AuditEntry]]:
        """
        Scans and sanitizes all fields in AgentTaskPayload.
        Replaces sensitive matches with reversible tokens in EntityVault.
        Returns (sanitized_payload, list_of_audit_entries_masked).
        """
        all_audit_entries: List[AuditEntry] = []

        # 1. Sanitize Intentions
        sanitized_intentions = []
        for text in payload.intentions:
            clean_text, entries = mask_text_with_rules(text, vault)
            sanitized_intentions.append(clean_text)
            all_audit_entries.extend(entries)

        # 2. Sanitize Things to Implement
        sanitized_tasks = []
        for text in payload.things_to_implement:
            clean_text, entries = mask_text_with_rules(text, vault)
            sanitized_tasks.append(clean_text)
            all_audit_entries.extend(entries)

        # 3. Sanitize Technical Context
        sanitized_context = []
        for text in payload.technical_context:
            clean_text, entries = mask_text_with_rules(text, vault)
            sanitized_context.append(clean_text)
            all_audit_entries.extend(entries)

        sanitized_payload = AgentTaskPayload(
            task_id=payload.task_id,
            intentions=sanitized_intentions,
            things_to_implement=sanitized_tasks,
            technical_context=sanitized_context,
            deadline=payload.deadline
        )

        # 4. Enforce Pre-Dispatch Leak Gate
        LeakInspector.assert_clean_payload(sanitized_payload)

        return sanitized_payload, all_audit_entries
