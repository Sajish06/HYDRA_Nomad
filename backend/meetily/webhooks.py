"""Webhook signature verification and envelope parsing for Meetily events."""

import hashlib
import hmac
import json
from typing import Any, Dict, Optional, Tuple

from backend.config import settings
from backend.logging import logger
from backend.meetily.errors import MeetilyAuthError, MeetilyInvalidResponse


class WebhookVerifier:
    """Config-driven HMAC verifier for incoming Meetily webhooks."""

    def __init__(
        self,
        secret: Optional[str] = None,
        header_name: Optional[str] = None,
        algorithm: Optional[str] = None,
        prefix: Optional[str] = None,
        allow_unsigned: Optional[bool] = None,
    ):
        self.secret = secret or (settings.WEBHOOK_SECRET.get_secret_value() if settings.WEBHOOK_SECRET else None)
        self.header_name = (header_name or settings.WEBHOOK_SIGNATURE_HEADER or "X-Meetily-Signature").lower()
        self.algorithm = algorithm or settings.WEBHOOK_SIGNATURE_ALGORITHM or "sha256"
        self.prefix = prefix if prefix is not None else settings.WEBHOOK_SIGNATURE_PREFIX
        self.allow_unsigned = (
            allow_unsigned
            if allow_unsigned is not None
            else (settings.APP_ENV == "development" and settings.WEBHOOK_ALLOW_UNSIGNED)
        )

    def verify(self, raw_body: bytes, headers: Dict[str, str]) -> bool:
        """Verify the signature of the incoming webhook payload.

        Returns True if valid. Raises MeetilyAuthError on invalid or missing signature.
        """
        # Lowercase headers dictionary for case-insensitive lookup
        lower_headers = {k.lower(): v for k, v in headers.items()}
        received_sig = lower_headers.get(self.header_name)

        if not received_sig:
            if self.allow_unsigned:
                logger.warning("Accepting unsigned webhook due to WEBHOOK_ALLOW_UNSIGNED=true in development")
                return True
            raise MeetilyAuthError(f"Missing required webhook signature header: {self.header_name}", status_code=401)

        if not self.secret:
            if self.allow_unsigned:
                logger.warning("Accepting webhook without secret configured due to WEBHOOK_ALLOW_UNSIGNED=true")
                return True
            raise MeetilyAuthError("Webhook secret not configured on server", status_code=401)

        # Handle prefix if present (e.g., 'sha256=abcdef...')
        clean_sig = received_sig.strip()
        if self.prefix and clean_sig.startswith(self.prefix):
            clean_sig = clean_sig[len(self.prefix) :]
        elif "=" in clean_sig and not self.prefix:
            # Common pattern prefix=hash (e.g. sha256=...)
            clean_sig = clean_sig.split("=", 1)[1]

        # Compute HMAC
        hash_func = getattr(hashlib, self.algorithm.lower(), hashlib.sha256)
        computed = hmac.new(
            self.secret.encode("utf-8"),
            raw_body,
            hash_func,
        ).hexdigest()

        if not hmac.compare_digest(computed.lower(), clean_sig.lower()):
            raise MeetilyAuthError("Invalid webhook signature", status_code=401)

        return True

    @staticmethod
    def parse_envelope(raw_body: bytes) -> Tuple[str, str, str, Dict[str, Any]]:
        """Parse raw webhook bytes into (event_id, event_type, resource_id, payload_dict)."""
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            raise MeetilyInvalidResponse(f"Webhook body is not valid JSON: {str(e)}") from e

        if not isinstance(payload, dict):
            raise MeetilyInvalidResponse("Webhook payload must be a JSON object")

        # Tolerant extraction of event_id
        event_id = str(
            payload.get("event_id")
            or payload.get("id")
            or payload.get("delivery_id")
            or ""
        )
        if not event_id:
            raise MeetilyInvalidResponse("Missing event_id in webhook envelope")

        # Tolerant extraction of event_type
        event_type = str(
            payload.get("event")
            or payload.get("type")
            or payload.get("event_type")
            or ""
        )
        if not event_type:
            raise MeetilyInvalidResponse("Missing event_type in webhook envelope")

        # Tolerant extraction of resource_id
        resource_id = ""
        resource = payload.get("resource")
        if isinstance(resource, dict):
            resource_id = str(resource.get("id") or resource.get("meeting_id") or "")
        elif isinstance(resource, str):
            resource_id = resource
        else:
            resource_id = str(
                payload.get("resource_id")
                or payload.get("meeting_id")
                or payload.get("data", {}).get("meeting_id", "")
            )

        return event_id, event_type, resource_id, payload
