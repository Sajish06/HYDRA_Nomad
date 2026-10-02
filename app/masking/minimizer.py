from typing import List, Tuple
from app.masking.models import VerifiedCommitment

class ContextMinimizer:
    """Minimizes transcript context by discarding conversational noise and keeping strictly relevant grounding evidence."""

    @staticmethod
    def minimize_evidence(commitment: VerifiedCommitment, total_meeting_segments_count: int = 0) -> Tuple[List[str], int, int]:
        """Filters context quotes to minimal necessary grounding lines. Returns (kept_quotes, kept_count, dropped_count)."""
        kept = []
        for quote in commitment.evidence_context_quotes:
            q_clean = quote.strip()
            if q_clean and len(q_clean) > 5:
                kept.append(q_clean)

        kept_count = len(kept)
        # If total segments count is known from full transcript, calculate dropped
        dropped_count = max(0, total_meeting_segments_count - kept_count) if total_meeting_segments_count > 0 else 0

        return kept, kept_count, dropped_count
