from typing import List, Tuple
from app.masking.vault import EntityVault
from app.masking.rules import mask_text_with_rules

class ContextMinimizer:
    """
    Minimizes context to strictly grounded task rationales and actions.
    Eliminates irrelevant conversation chatter.
    """
    @staticmethod
    def minimize_and_mask_quotes(quotes: List[str], vault: EntityVault) -> Tuple[List[str], int]:
        sanitized_quotes = []
        total_masked = 0

        for quote in quotes:
            # Mask sensitive entities within the grounding quote
            masked_quote, count = mask_text_with_rules(quote, vault)
            sanitized_quotes.append(masked_quote)
            total_masked += count

        return sanitized_quotes, total_masked
