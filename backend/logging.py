"""Structured, secure logging utility for Meetily Clean Room."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class SafeJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON without exposing sensitive data."""

    # Keywords that may indicate sensitive content
    SENSITIVE_KEYS = {
        "api_key",
        "token",
        "secret",
        "authorization",
        "transcript",
        "raw_text",
        "password",
        "signature",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include additional attributes if present and safe
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            safe_extra = {}
            for k, v in record.extra_data.items():
                if any(s in k.lower() for s in self.SENSITIVE_KEYS):
                    safe_extra[k] = "[REDACTED]"
                else:
                    safe_extra[k] = v
            log_entry["data"] = safe_extra

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Initialize structured logging for the application."""
    root_logger = logging.getLogger("cleanroom")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(SafeJsonFormatter())
        root_logger.addHandler(handler)

    return root_logger


logger = setup_logging()
