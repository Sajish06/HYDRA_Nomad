from pathlib import Path
import json
from typing import Dict, Optional

class EntityVault:
    """
    Local Reversible Secret Vault.
    Stores bidirectional mappings: real_text <-> placeholder token.
    Secrets NEVER leave the local environment.
    """
    def __init__(self, session_id: str, storage_dir: str = "data/vaults"):
        self.session_id = session_id
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.token_to_secret: Dict[str, str] = {}
        self.secret_to_token: Dict[str, str] = {}
        self.category_counts: Dict[str, int] = {}

    def get_or_create_token(self, secret_text: str, category: str = "ENTITY") -> str:
        """Returns existing placeholder token or registers a new one."""
        cleaned_secret = secret_text.strip()
        if not cleaned_secret:
            return secret_text

        # Return existing token if already masked
        if cleaned_secret in self.secret_to_token:
            return self.secret_to_token[cleaned_secret]

        # Allocate new token, e.g., [SENSITIVE_FINANCIAL_1]
        cat_upper = category.upper().replace(" ", "_")
        self.category_counts[cat_upper] = self.category_counts.get(cat_upper, 0) + 1
        count = self.category_counts[cat_upper]
        token = f"[{cat_upper}_{count}]"

        self.token_to_secret[token] = cleaned_secret
        self.secret_to_token[cleaned_secret] = token
        return token

    def unmask_text(self, text: str) -> str:
        """Re-hydrates masked tokens in cloud LLM responses back to their original secret values."""
        unmasked = text
        for token, secret in self.token_to_secret.items():
            unmasked = unmasked.replace(token, secret)
        return unmasked

    def save(self) -> Path:
        """Persists the vault file locally for audit and downstream unmasking."""
        file_path = self.storage_dir / f"vault_{self.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": self.session_id,
                "mappings": self.token_to_secret
            }, f, indent=2)
        return file_path

    @classmethod
    def load(cls, session_id: str, storage_dir: str = "data/vaults") -> "EntityVault":
        vault = cls(session_id, storage_dir)
        file_path = vault.storage_dir / f"vault_{session_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                vault.token_to_secret = data.get("mappings", {})
                vault.secret_to_token = {v: k for k, v in vault.token_to_secret.items()}
        return vault
