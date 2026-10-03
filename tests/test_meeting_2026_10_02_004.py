import pytest
from app.auth.oauth_handler import OAuthFlowHandler
from app.middleware.rate_limiter import SimpleRateLimiter

def test_oauth_flow_successful_callback():
    handler = OAuthFlowHandler()
    url = handler.generate_authorization_url(redirect_uri="https://app.example.com/callback", state="state_123")
    assert "https://auth.example.com/oauth/authorize" in url
    assert "state=state_123" in url

    res = handler.handle_callback(code="auth_code_xyz", state="state_123", expected_state="state_123")
    assert res["success"] is True
    assert "access_token" in res
    assert res["token_type"] == "Bearer"

def test_oauth_flow_invalid_state():
    handler = OAuthFlowHandler()
    handler.generate_authorization_url(redirect_uri="https://app.example.com/callback", state="state_correct")
    res = handler.handle_callback(code="auth_code_xyz", state="state_wrong", expected_state="state_correct")
    assert res["success"] is False
    assert res["error"] == "invalid_state_mismatch"

def test_rate_limiter_allows_and_blocks():
    limiter = SimpleRateLimiter(max_requests=3, window_seconds=60)
    ip = "192.168.1.100"

    allowed, rem = limiter.is_allowed(ip)
    assert allowed is True
    assert rem == 2

    allowed, rem = limiter.is_allowed(ip)
    assert allowed is True
    assert rem == 1

    allowed, rem = limiter.is_allowed(ip)
    assert allowed is True
    assert rem == 0

    # 4th request should be blocked
    allowed, rem = limiter.is_allowed(ip)
    assert allowed is False
    assert rem == 0
