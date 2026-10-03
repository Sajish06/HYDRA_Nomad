"""
OAuth Callback and Authentication Flow Handler.
Implements secure OAuth 2.0 state validation and code exchange flow.
"""

from typing import Dict, Any, Optional
import hashlib
import hmac
import time

class OAuthFlowHandler:
    def __init__(self, client_id: str = "nomad-client", client_secret: str = "secret-key"):
        self.client_id = client_id
        self.client_secret = client_secret
        self._pending_states: Dict[str, float] = {}

    def generate_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Generate the authorization redirect URL and track state."""
        self._pending_states[state] = time.time()
        return f"https://auth.example.com/oauth/authorize?client_id={self.client_id}&redirect_uri={redirect_uri}&state={state}&response_type=code"

    def handle_callback(self, code: str, state: str, expected_state: Optional[str] = None) -> Dict[str, Any]:
        """Validate OAuth callback state and exchange authorization code for tokens."""
        if not code:
            return {"success": False, "error": "missing_code"}
        
        if expected_state and state != expected_state:
            return {"success": False, "error": "invalid_state_mismatch"}

        if state not in self._pending_states:
            return {"success": False, "error": "unrecognized_state"}

        # State is valid, remove from pending
        del self._pending_states[state]

        # Return mock token payload
        token_hash = hashlib.sha256(f"{code}:{self.client_secret}".encode()).hexdigest()
        return {
            "success": True,
            "access_token": f"at_{token_hash[:32]}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write"
        }
