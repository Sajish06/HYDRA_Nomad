"""Test foundation setup, config, logging, and database initialization."""

from backend.config import Settings
from backend.main import app
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


def test_app_imports():
    """Ensure the FastAPI app imports and has expected title."""
    assert app.title == "Meetily Clean Room"


def test_config_safe_dict_no_secrets():
    """Verify secrets are excluded from safe config output."""
    test_settings = Settings(
        MEETILY_API_TOKEN="secret-meetily-token",
        WEBHOOK_SECRET="super-secret-hmac",
        GEMINI_API_KEY="secret-gemini-key",
    )
    safe = test_settings.safe_dict()
    assert "secret-meetily-token" not in str(safe)
    assert "super-secret-hmac" not in str(safe)
    assert "secret-gemini-key" not in str(safe)
    assert safe["HAS_MEETILY_TOKEN"] is True
    assert safe["HAS_WEBHOOK_SECRET"] is True
    assert safe["HAS_GEMINI_KEY"] is True


def test_database_initialization_and_repository():
    """Verify DB models can be initialized and repository functions work."""
    init_db()
    db = SessionLocal()
    try:
        repo = Repository(db)
        meeting = repo.create_or_get_meeting("meet_test_123", title="Test Deal Meeting", duration_seconds=120.0)
        assert meeting.meetily_id == "meet_test_123"
        assert meeting.title == "Test Deal Meeting"
        fetched = repo.get_meeting_by_meetily_id("meet_test_123")
        assert fetched is not None
        assert fetched.id == meeting.id
    finally:
        db.close()
