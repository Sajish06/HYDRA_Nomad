import re
import uuid
from typing import Protocol, runtime_checkable
from app.models import VerifiedTask, MaskedBrief

@runtime_checkable
class Masker(Protocol):
    def mask(self, task: VerifiedTask) -> MaskedBrief:
        ...
    def unmask(self, brief_id: str, cloud_output: str) -> str:
        ...

class StubMasker:
    """Trivial local masker for demo purposes: masks entities & summarizes to minimum context."""
    def mask(self, task: VerifiedTask) -> MaskedBrief:
        raw_text = task.task_text
        entities_masked = 0
        
        # Mask emails
        masked_text, count_email = re.subn(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL_REDACTED]", raw_text)
        entities_masked += count_email

        # Mask names if actor is present
        if task.actor and task.actor in masked_text:
            masked_text = masked_text.replace(task.actor, "[ASSIGNEE_1]")
            entities_masked += 1

        # Grounding segments kept vs dropped
        kept = len(task.grounding_segments)
        dropped = 0  # In minimal context, only grounding segments are passed

        brief_id = f"brief_{uuid.uuid4().hex[:8]}"

        return MaskedBrief(
            brief_id=brief_id,
            task_id=task.task_id,
            masked_text=masked_text,
            entities_masked=entities_masked,
            segments_kept=kept,
            segments_dropped=dropped
        )

    def unmask(self, brief_id: str, cloud_output: str) -> str:
        # Re-hydrate if needed
        return cloud_output

def get_masker() -> Masker:
    return StubMasker()
