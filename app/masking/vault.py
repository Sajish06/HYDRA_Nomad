import json
from pathlib import Path
from typing import Dict, Any, Optional

class LocalSecretVault:
    """Local reversible secret vault: keeps sensitive data offline and maps tokens back to originals."""

    def __init__(self, meeting_id: str, vault_dir: Path):
        self.meeting_id = meeting_id
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        
        self.vault_path = self.vault_dir / f"vault_{self.meeting_id}.json"
        
        # Token to secret mapping: {"[PERSON_1]": "Ravi", "[METRIC_1]": "$8 million"}
        self.token_to_secret: Dict[str, str] = {}
        # Secret to token mapping for consistent tokenization: {"ravi": "[PERSON_1]"}
        self.secret_to_token: Dict[str, str] = {}
        # Category counters: {"PERSON": 1, "METRIC": 1}
        self.counters: Dict[str, int] = {}
        
        self._load()

    def _load(self) -> None:
        if self.vault_path.exists():
            try:
                with open(self.vault_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.token_to_secret = data.get("mappings", {})
                    for token, secret in self.token_to_secret.items():
                        self.secret_to_token[secret.lower()] = token
                    self.counters = data.get("counters", {})
            except Exception:
                pass

    def save(self) -> Path:
        data = {
            "meeting_id": self.meeting_id,
            "mappings": self.token_to_secret,
            "counters": self.counters
        }
        with open(self.vault_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return self.vault_path

    def register(self, secret: str, category: str = "ENTITY") -> str:
        """Registers a secret and returns its reversible token."""
        secret_clean = secret.strip()
        if not secret_clean:
            return secret

        key = secret_clean.lower()
        if key in self.secret_to_token:
            return self.secret_to_token[key]

        cat = category.upper()
        idx = self.counters.get(cat, 0) + 1
        self.counters[cat] = idx
        token = f"[{cat}_{idx}]"

        self.token_to_secret[token] = secret_clean
        self.secret_to_token[key] = token
        return token

    def unmask(self, text: str) -> str:
        """Detokenizes text by replacing all registered tokens with original secrets."""
        if not text:
            return text
        result = text
        for token, secret in self.token_to_secret.items():
            result = result.replace(token, secret)
        return result
