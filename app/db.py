import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from app.config import settings

_db_initialized = False

def get_db_path() -> str:
    path = Path(settings.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)

@contextmanager
def get_db():
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    get_db_path()
    conn = sqlite3.connect(get_db_path())
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS meetings(
          id TEXT PRIMARY KEY,
          title TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          source TEXT
        );
        CREATE TABLE IF NOT EXISTS participants(
          meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
          name TEXT,
          role TEXT,
          has_authority INTEGER DEFAULT 0,
          PRIMARY KEY(meeting_id, name)
        );
        CREATE TABLE IF NOT EXISTS segments(
          meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
          idx INTEGER,
          speaker TEXT,
          time TEXT,
          t_seconds REAL,
          text TEXT,
          PRIMARY KEY(meeting_id, idx)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
          text,
          meeting_id UNINDEXED,
          idx UNINDEXED,
          tokenize='porter unicode61'
        );
        CREATE TABLE IF NOT EXISTS claims(
          id TEXT PRIMARY KEY,
          meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
          text TEXT,
          normalized TEXT,
          source TEXT,
          type TEXT,
          actor TEXT,
          action TEXT,
          object TEXT,
          deadline TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS evidence(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          claim_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
          meeting_id TEXT,
          segment_idx INTEGER,
          stance TEXT,
          relation TEXT,
          quote TEXT,
          resolved_text TEXT,
          source TEXT,
          relevance REAL
        );
        CREATE TABLE IF NOT EXISTS verification(
          claim_id TEXT PRIMARY KEY REFERENCES claims(id) ON DELETE CASCADE,
          status TEXT,
          gate_action TEXT,
          reasons TEXT,
          explanation TEXT,
          final_state TEXT,
          resolved_claim TEXT,
          slots TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS confirmations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          claim_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
          decision TEXT,
          note TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pipeline_trace(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          claim_id TEXT,
          stage TEXT,
          payload TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS handoff_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          claim_id TEXT,
          status_at_handoff TEXT,
          verification_hash TEXT,
          recipient TEXT,
          masked_brief_id TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
    finally:
        conn.close()

def log_trace(claim_id: str, stage: str, payload: Any):
    try:
        with get_db() as conn:
            payload_str = json.dumps(payload, default=str) if not isinstance(payload, str) else payload
            conn.execute(
                "INSERT INTO pipeline_trace (claim_id, stage, payload) VALUES (?, ?, ?)",
                (claim_id, stage, payload_str)
            )
    except Exception:
        pass
