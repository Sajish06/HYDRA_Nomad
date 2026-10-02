"""Local filesystem implementation of DocumentSource."""

from pathlib import Path
from typing import List, Optional, Tuple

from backend.config import settings
from backend.sources.base import DocumentSource


class LocalFolderSource(DocumentSource):
    """Reads diligence documents from a local folder."""

    def __init__(self, directory_path: Optional[Path] = None):
        self.directory_path = directory_path or Path(settings.DOCUMENTS_DIR)
        self.directory_path.mkdir(parents=True, exist_ok=True)

    def list_documents(self) -> List[str]:
        """List all markdown and text files in directory."""
        if not self.directory_path.exists():
            return []
        files = []
        for p in self.directory_path.glob("*"):
            if p.is_file() and p.suffix.lower() in (".md", ".txt", ".json"):
                files.append(p.name)
        return sorted(files)

    def get_text(self, doc_id: str) -> str:
        """Read and return complete document content."""
        target = self.directory_path / doc_id
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Diligence document not found: {doc_id}")
        return target.read_text(encoding="utf-8")

    def get_document_lines(self, doc_id: str) -> List[Tuple[int, str]]:
        """Return 1-indexed (line_number, line_text) for exact citation generation."""
        content = self.get_text(doc_id)
        lines = content.splitlines()
        return [(idx + 1, line) for idx, line in enumerate(lines)]
