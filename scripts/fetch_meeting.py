"""Fetch meeting metadata, transcript, and summary from Meetily Pro gateway and store locally."""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.meetily.client import MeetilyClient
from backend.meetily.meetings import MeetingSyncService
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


async def main():
    parser = argparse.ArgumentParser(description="Fetch and sync a meeting from Meetily Pro.")
    parser.add_argument("meeting_id", help="Meetily Meeting ID or UUID")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        repo = Repository(db)
        client = MeetilyClient()
        service = MeetingSyncService(client=client, repo=repo)

        print(f"Fetching meeting {args.meeting_id} from Meetily...")
        meeting, transcript, summary = await service.sync_meeting(args.meeting_id)

        print(f"[OK] Successfully synced meeting: {meeting.title} ({meeting.meetily_id})")
        print(f"     Transcript segments: {len(transcript.segments)}")
        print(f"     Transcript SHA-256: {transcript.sha256_hash}")
        print(f"     Summary length: {len(summary.summary_text)} chars")
        print(f"     Action items found: {len(summary.action_items)}")
    except Exception as e:
        print(f"[ERROR] Failed to sync meeting: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
