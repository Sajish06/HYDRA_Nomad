"""Abstract document source interface for diligence repositories."""

from abc import ABC, abstractmethod
from typing import List, Tuple


class DocumentSource(ABC):
    """Interface for retrieving external diligence documents (CIM, term sheets, etc.)."""

    @abstractmethod
    def list_documents(self) -> List[str]:
        """Return list of available document identifiers / filenames."""
        pass

    @abstractmethod
    def get_text(self, doc_id: str) -> str:
        """Return full text content of the specified document."""
        pass

    @abstractmethod
    def get_document_lines(self, doc_id: str) -> List[Tuple[int, str]]:
        """Return 1-indexed list of (line_number, line_text) for citation mapping."""
        pass
