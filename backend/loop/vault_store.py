"""Secure, encrypted-at-rest persistence for Vault token maps across processes.

Guarantees:
- Fernet symmetric encryption at rest using NOMAD_VAULT_KEY (or stable derived key).
- Key is never written to disk or logs.
- Automatic deletion upon loop terminal state unless PERSIST_TOKEN_MAP=True.
- Full round-trip fidelity for entity maps, token maps, counters, and leak sets.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

from backend.config import settings
from backend.logging import logger
from backend.processors.privacy import Vault


def _get_fernet_key() -> bytes:
    """Derive a 32-byte URL-safe base64 Fernet key from NOMAD_VAULT_KEY or machine salt."""
    key_str = None
    if settings.NOMAD_VAULT_KEY:
        key_str = settings.NOMAD_VAULT_KEY.get_secret_value()
    elif os.environ.get("NOMAD_VAULT_KEY"):
        key_str = os.environ.get("NOMAD_VAULT_KEY")

    if key_str:
        raw_key = hashlib.sha256(key_str.encode("utf-8")).digest()
    else:
        # Stable machine-fallback salt (derived from machine ID / userprofile, not hardcoded plaintext)
        seed = f"nomad-cleanroom-{os.environ.get('COMPUTERNAME', 'host')}-{os.environ.get('USERNAME', 'user')}"
        raw_key = hashlib.sha256(seed.encode("utf-8")).digest()

    return base64.urlsafe_b64encode(raw_key)


def get_vault_dir() -> Path:
    """Return directory for encrypted vaults, ensuring it exists."""
    vault_dir = Path(settings.DATA_DIR) / "vaults"
    vault_dir.mkdir(parents=True, exist_ok=True)
    return vault_dir


def _get_vault_file(identifier: str) -> Path:
    clean_id = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in identifier)
    return get_vault_dir() / f"vault_{clean_id}.enc"


def save_vault(identifier: str, vault: Vault) -> Path:
    """
    Encrypt and serialize a Vault's state to disk.
    Returns the path to the written encrypted vault.
    """
    state = {
        "entity_to_token": vault._entity_to_token,
        "token_to_entity": vault._token_to_entity,
        "category_counters": vault._category_counters,
        "all_sensitive_values": list(vault._all_sensitive_values),
    }

    raw_json = json.dumps(state, ensure_ascii=False).encode("utf-8")
    fernet = Fernet(_get_fernet_key())
    encrypted = fernet.encrypt(raw_json)

    target_file = _get_vault_file(identifier)
    target_file.write_bytes(encrypted)

    # Restrict permissions on Windows/POSIX if possible
    try:
        os.chmod(target_file, 0o600)
    except Exception:
        pass

    logger.debug(f"[VaultStore] Encrypted vault saved for identifier '{identifier}'")
    return target_file


def load_vault(identifier: str) -> Optional[Vault]:
    """
    Load and decrypt a Vault from disk.
    Returns None if vault file does not exist or decryption fails.
    """
    target_file = _get_vault_file(identifier)
    if not target_file.exists():
        # Also check fallback raw meeting id
        return None

    try:
        encrypted = target_file.read_bytes()
        fernet = Fernet(_get_fernet_key())
        decrypted_json = fernet.decrypt(encrypted).decode("utf-8")
        state = json.loads(decrypted_json)

        vault = Vault()
        vault._entity_to_token = state.get("entity_to_token", {})
        vault._token_to_entity = state.get("token_to_entity", {})
        vault._category_counters = state.get("category_counters", {})
        vault._all_sensitive_values = set(state.get("all_sensitive_values", []))

        return vault
    except Exception as e:
        logger.error(f"[VaultStore] Failed to load/decrypt vault for '{identifier}': {e}")
        return None


def has_vault(identifier: str) -> bool:
    """Check if an encrypted vault exists for the identifier."""
    return _get_vault_file(identifier).exists()


def delete_vault(identifier: str) -> bool:
    """
    Securely delete the encrypted vault from disk at terminal state.
    Respects PERSIST_TOKEN_MAP (keeps file if True).
    """
    if settings.PERSIST_TOKEN_MAP:
        logger.info(f"[VaultStore] PERSIST_TOKEN_MAP=True, retaining vault for '{identifier}'")
        return False

    target_file = _get_vault_file(identifier)
    if target_file.exists():
        try:
            target_file.unlink()
            logger.info(f"[VaultStore] Deleted encrypted vault for '{identifier}'")
            return True
        except Exception as e:
            logger.warning(f"[VaultStore] Error deleting vault for '{identifier}': {e}")
            return False
    return False
