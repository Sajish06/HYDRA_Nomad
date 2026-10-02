"""Abstract base interface for external and local AI providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LLMProvider(ABC):
    """Interface for LLM verification and intelligence extraction."""

    @abstractmethod
    async def verify_claims(
        self, masked_transcript: str, masked_summary: str
    ) -> List[Dict[str, Any]]:
        """Given pseudonymized transcript and summary, propose atomic claims and evidence."""
        pass

    @abstractmethod
    async def extract_intelligence(
        self, masked_transcript: str, masked_summary: str
    ) -> Dict[str, Any]:
        """Extract structured M&A intelligence from masked transcript."""
        pass
