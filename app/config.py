import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for the application
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.5:4b"
    MOCK_LLM: int = 0
    EMBED_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    DB_PATH: str = str(BASE_DIR / "data" / "proof.db")
    RETRIEVAL_TOP_K: int = 8
    WINDOW_BEFORE: int = 2
    WINDOW_AFTER: int = 3
    RRF_K: int = 60
    MIN_RELEVANCE: float = 0.35
    MEETILY_URL: str = "http://127.0.0.1:8420"
    MEETILY_TOKEN: str = ""
    MASKER: str = "stub"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
