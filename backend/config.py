"""Application configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Clean Room environment settings with strict secrets handling."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Meetily Clean Room"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # Meetily Automation API configuration
    MEETILY_BASE_URL: str = "http://127.0.0.1:8420"
    MEETILY_API_TOKEN: Optional[SecretStr] = None
    MEETILY_TIMEOUT_SECONDS: float = 15.0

    # Database and Storage
    DATABASE_URL: str = "sqlite:///./data/meetily.db"
    DATA_DIR: Path = Field(default_factory=lambda: Path("./data"))

    # Webhook configuration
    WEBHOOK_SECRET: Optional[SecretStr] = None
    WEBHOOK_PUBLIC_URL: Optional[str] = None
    WEBHOOK_SIGNATURE_HEADER: Optional[str] = "X-Meetily-Signature"
    WEBHOOK_SIGNATURE_ALGORITHM: str = "sha256"
    WEBHOOK_SIGNATURE_PREFIX: Optional[str] = None
    WEBHOOK_ALLOW_UNSIGNED: bool = False

    # AI & Privacy switches
    ENABLE_AI: bool = False
    GEMINI_API_KEY: Optional[SecretStr] = None
    GEMINI_MODEL: Optional[str] = "gemini-2.5-flash"
    ENABLE_WEBHOOKS: bool = True

    # Security: Fail closed, do not store or expose unmasked transcripts
    ENABLE_RAW_STORAGE: bool = False
    EXPOSE_RAW_TRANSCRIPTS: bool = False
    PERSIST_TOKEN_MAP: bool = False

    # Closed Loop & Antigravity settings
    ENABLE_OLLAMA: bool = True
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    AGY_WORKSPACE_ROOT: Optional[Path] = None
    MAX_ITERATIONS: int = 3
    NOMAD_VAULT_KEY: Optional[SecretStr] = None
    NOMAD_LEDGER_KEY: Optional[SecretStr] = None

    # Policy and source paths
    AUDIENCE_PROFILES_PATH: Path = Field(default_factory=lambda: Path("./configs/audience_profiles.yaml"))
    DEAL_CONFIG_PATH: Path = Field(default_factory=lambda: Path("./configs/deal.yaml"))
    DOCUMENTS_DIR: Path = Field(default_factory=lambda: Path("./data/demo/documents"))

    def safe_dict(self) -> dict:
        """Return non-sensitive configuration dictionary for telemetry/diagnostics."""
        return {
            "APP_NAME": self.APP_NAME,
            "APP_ENV": self.APP_ENV,
            "DEBUG": self.DEBUG,
            "API_HOST": self.API_HOST,
            "API_PORT": self.API_PORT,
            "MEETILY_BASE_URL": self.MEETILY_BASE_URL,
            "MEETILY_TIMEOUT_SECONDS": self.MEETILY_TIMEOUT_SECONDS,
            "DATABASE_URL": self.DATABASE_URL,
            "DATA_DIR": str(self.DATA_DIR),
            "WEBHOOK_SIGNATURE_HEADER": self.WEBHOOK_SIGNATURE_HEADER,
            "WEBHOOK_SIGNATURE_ALGORITHM": self.WEBHOOK_SIGNATURE_ALGORITHM,
            "WEBHOOK_ALLOW_UNSIGNED": self.WEBHOOK_ALLOW_UNSIGNED,
            "ENABLE_AI": self.ENABLE_AI,
            "GEMINI_MODEL": self.GEMINI_MODEL,
            "ENABLE_RAW_STORAGE": self.ENABLE_RAW_STORAGE,
            "EXPOSE_RAW_TRANSCRIPTS": self.EXPOSE_RAW_TRANSCRIPTS,
            "PERSIST_TOKEN_MAP": self.PERSIST_TOKEN_MAP,
            "ENABLE_OLLAMA": self.ENABLE_OLLAMA,
            "OLLAMA_BASE_URL": self.OLLAMA_BASE_URL,
            "OLLAMA_MODEL": self.OLLAMA_MODEL,
            "MAX_ITERATIONS": self.MAX_ITERATIONS,
            "AGY_WORKSPACE_ROOT": str(self.AGY_WORKSPACE_ROOT) if self.AGY_WORKSPACE_ROOT else None,
            "HAS_MEETILY_TOKEN": self.MEETILY_API_TOKEN is not None,
            "HAS_WEBHOOK_SECRET": self.WEBHOOK_SECRET is not None,
            "HAS_GEMINI_KEY": self.GEMINI_API_KEY is not None,
            "HAS_VAULT_KEY": self.NOMAD_VAULT_KEY is not None,
            "HAS_LEDGER_KEY": self.NOMAD_LEDGER_KEY is not None,
        }


# Singleton instance
settings = Settings()
