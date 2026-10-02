"""Tests for Meetily webhook receiver, HMAC verification, and deduplication."""

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.main import app
from backend.storage.database import init_db


@pytest.fixture
def test_secret():
    return "test-webhook-secret-key-12345"


def sign_payload(body: bytes, secret: str) -> str:
    """Generate valid HMAC-SHA256 signature for test payload."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_valid_signature_accepted(test_secret, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", type("Secret", (), {"get_secret_value": lambda self: test_secret})())
    monkeypatch.setattr(settings, "WEBHOOK_SIGNATURE_HEADER", "X-Meetily-Signature")
    monkeypatch.setattr(settings, "WEBHOOK_ALLOW_UNSIGNED", False)

    init_db()
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": event_id,
        "event": "summary.completed",
        "resource": {"id": "m_test_webhook_1"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_body, test_secret)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Meetily-Signature": sig,
            },
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_webhook_invalid_signature_401(test_secret, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", type("Secret", (), {"get_secret_value": lambda self: test_secret})())
    monkeypatch.setattr(settings, "WEBHOOK_SIGNATURE_HEADER", "X-Meetily-Signature")
    monkeypatch.setattr(settings, "WEBHOOK_ALLOW_UNSIGNED", False)

    payload = {"event_id": "evt_invalid_sig", "event": "summary.completed", "resource": {"id": "m1"}}
    raw_body = json.dumps(payload).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Meetily-Signature": "wrong-signature-hex",
            },
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_missing_signature_401(test_secret, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", type("Secret", (), {"get_secret_value": lambda self: test_secret})())
    monkeypatch.setattr(settings, "WEBHOOK_SIGNATURE_HEADER", "X-Meetily-Signature")
    monkeypatch.setattr(settings, "WEBHOOK_ALLOW_UNSIGNED", False)

    payload = {"event_id": "evt_missing_sig", "event": "summary.completed", "resource": {"id": "m1"}}
    raw_body = json.dumps(payload).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_deduplication(test_secret, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", type("Secret", (), {"get_secret_value": lambda self: test_secret})())
    monkeypatch.setattr(settings, "WEBHOOK_SIGNATURE_HEADER", "X-Meetily-Signature")

    init_db()
    event_id = f"evt_dup_{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": event_id,
        "event": "summary.completed",
        "resource": {"id": "m_dup_1"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_body, test_secret)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First call -> 202
        r1 = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={"X-Meetily-Signature": sig},
        )
        assert r1.status_code == 202

        # Second call with identical event_id -> 200 duplicate
        r2 = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={"X-Meetily-Signature": sig},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_webhook_unsupported_event_type_ignored(test_secret, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", type("Secret", (), {"get_secret_value": lambda self: test_secret})())

    event_id = f"evt_ignored_{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": event_id,
        "event": "recording.stopped",
        "resource": {"id": "m_rec_1"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_body, test_secret)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={"X-Meetily-Signature": sig},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_missing_resource_id_422(test_secret, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", type("Secret", (), {"get_secret_value": lambda self: test_secret})())

    payload = {"event_id": "evt_no_res", "event": "summary.completed", "resource": {}}
    raw_body = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_body, test_secret)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
            headers={"X-Meetily-Signature": sig},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unsigned_accepted_only_in_dev_with_flag(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "WEBHOOK_ALLOW_UNSIGNED", True)

    event_id = f"evt_dev_{uuid.uuid4().hex[:8]}"
    payload = {"event_id": event_id, "event": "summary.completed", "resource": {"id": "m_dev_1"}}
    raw_body = json.dumps(payload).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/webhooks/meetily",
            content=raw_body,
        )
    assert resp.status_code == 202
