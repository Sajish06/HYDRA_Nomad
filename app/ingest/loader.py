from typing import Optional
from app.models import Meeting
from app.db import get_db

def load_meeting_to_db(meeting: Meeting, source: str = "mock") -> Meeting:
    """Idempotently loads a normalized Meeting object into SQLite and FTS5."""
    with get_db() as conn:
        # Delete previous meeting data if exists
        conn.execute("DELETE FROM segments_fts WHERE meeting_id = ?", (meeting.meeting_id,))
        conn.execute("DELETE FROM segments WHERE meeting_id = ?", (meeting.meeting_id,))
        conn.execute("DELETE FROM participants WHERE meeting_id = ?", (meeting.meeting_id,))
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting.meeting_id,))

        # Insert meeting
        conn.execute(
            "INSERT INTO meetings (id, title, source) VALUES (?, ?, ?)",
            (meeting.meeting_id, meeting.title, source)
        )

        # Insert participants
        for p in meeting.participants:
            conn.execute(
                "INSERT OR REPLACE INTO participants (meeting_id, name, role, has_authority) VALUES (?, ?, ?, ?)",
                (meeting.meeting_id, p.name, p.role, 1 if p.has_authority else 0)
            )

        # Insert segments into both segments table and FTS5
        for s in meeting.segments:
            conn.execute(
                "INSERT INTO segments (meeting_id, idx, speaker, time, t_seconds, text) VALUES (?, ?, ?, ?, ?, ?)",
                (meeting.meeting_id, s.idx, s.speaker, s.time, s.t_seconds, s.text)
            )
            conn.execute(
                "INSERT INTO segments_fts (text, meeting_id, idx) VALUES (?, ?, ?)",
                (s.text, meeting.meeting_id, str(s.idx))
            )

    return meeting
