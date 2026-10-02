"""Tests for UI assets, static file serving, and demo fixture validation."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_demo_page_serving():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/demo")
    assert resp.status_code == 200
    assert "Meetily Clean Room - Forensic Evidence & Compliance Console" in resp.text
    assert "top-bar" in resp.text
    assert "workspace-container" in resp.text
    assert "caption-bar" in resp.text


@pytest.mark.asyncio
async def test_demo_redirect():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/demo.html")
    assert resp.status_code == 307
    assert resp.headers.get("location") == "/demo"


@pytest.mark.asyncio
async def test_static_css_assets_serving():
    css_files = ["tokens.css", "base.css", "layout.css", "components.css", "motion.css"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for fname in css_files:
            resp = await ac.get(f"/static/css/{fname}")
            assert resp.status_code == 200, f"Failed to serve {fname}"
            assert len(resp.text) > 100


@pytest.mark.asyncio
async def test_static_js_modules_serving():
    js_files = [
        "main.js",
        "api.js",
        "store.js",
        "router.js",
        "director.js",
        "panels/claims.js",
        "panels/masking.js",
        "panels/audiences.js",
        "panels/gate.js",
        "panels/crosscheck.js",
        "panels/review.js",
        "panels/leakscan.js",
        "panels/ledger.js",
        "panels/palette.js",
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for fname in js_files:
            resp = await ac.get(f"/static/js/{fname}")
            assert resp.status_code == 200, f"Failed to serve {fname}"
            assert len(resp.text) > 50


def test_demo_fixture_schema():
    fixture_path = Path("backend/static/fixtures/demo-fixture.json")
    assert fixture_path.exists(), "demo-fixture.json must exist for offline operation"

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate essential keys expected by UI
    required_keys = [
        "status",
        "meeting_id",
        "run_id",
        "gate_decision",
        "verification",
        "conflicts",
        "review_items",
        "ledger",
        "transcript",
        "summary",
        "audience_outputs",
        "masking_diffs",
        "leak_report",
        "deal",
    ]
    for key in required_keys:
        assert key in data, f"Missing required key in fixture: {key}"

    # Validate verification claims
    claims = data["verification"]["claims"]
    assert len(claims) >= 3
    # Check that $50k claim is present and marked contradicted
    c_50k = next((c for c in claims if "$50,000" in c["text"]), None)
    assert c_50k is not None
    assert c_50k["verdict"] == "contradicted"

    # Validate cross-source conflict
    conflicts = data["conflicts"]
    assert len(conflicts) >= 1
    assert any("EBITDA" in c["metric"] for c in conflicts)

    # Validate audience outputs for all 5 audiences
    audiences = ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"]
    for aud in audiences:
        assert aud in data["audience_outputs"]
        assert len(data["audience_outputs"][aud]) > 50
