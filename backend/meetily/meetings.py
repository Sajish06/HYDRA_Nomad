"""High-level meeting synchronization service connecting MeetilyClient and Repository."""

from typing import Tuple

from backend.config import settings
from backend.meetily.client import MeetilyClient
from backend.schemas.meeting import MeetingMetadata, MeetingSummary, MeetingTranscript
from backend.storage.models import MeetingModel
from backend.storage.repository import Repository


class MeetingSyncService:
    """Orchestrates pulling meeting metadata, transcripts, and summaries from Meetily."""

    def __init__(self, client: MeetilyClient, repo: Repository):
        self.client = client
        self.repo = repo

    async def sync_meeting(
        self, meetily_id: str
    ) -> Tuple[MeetingModel, MeetingTranscript, MeetingSummary]:
        """Fetch meeting details, transcript, and summary from Meetily and persist to database."""
        # 1. Fetch metadata
        meta: MeetingMetadata = await self.client.get_meeting(meetily_id)

        # 2. Fetch transcript
        transcript: MeetingTranscript = await self.client.get_transcript(meetily_id)

        # 3. Fetch summary
        summary: MeetingSummary = await self.client.get_summary(meetily_id)

        # 4. Save to repository
        meeting = self.repo.create_or_get_meeting(
            meetily_id=meta.meetily_id,
            title=meta.title,
            duration_seconds=meta.duration_seconds,
        )

        # Raw transcript storage is strictly guarded by ENABLE_RAW_STORAGE setting
        raw_to_store = transcript.raw_text if settings.ENABLE_RAW_STORAGE else None

        self.repo.update_meeting_data(
            meeting_id=meeting.id,
            transcript_sha256=transcript.sha256_hash,
            raw_transcript=raw_to_store,
            raw_summary=summary.summary_text,
            status="synced",
        )

        return meeting, transcript, summary
