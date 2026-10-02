"""Schemas for meeting data, transcripts, and summaries."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """An individual spoken segment in a meeting transcript."""

    segment_index: int = Field(..., description="0-indexed order of segment")
    speaker: str = Field(default="Speaker", description="Identified speaker label or name")
    start_time: Optional[float] = Field(default=None, description="Start time in seconds")
    end_time: Optional[float] = Field(default=None, description="End time in seconds")
    text: str = Field(..., description="Spoken text in this segment")


class MeetingTranscript(BaseModel):
    """Full transcript of a meeting, with individual segments."""

    meeting_id: str
    segments: List[TranscriptSegment] = Field(default_factory=list)
    raw_text: Optional[str] = None
    sha256_hash: str = Field(..., description="SHA-256 fingerprint of the transcript")


class MeetingSummary(BaseModel):
    """Meeting summary as received from Meetily or AI."""

    meeting_id: str
    summary_text: str
    action_items: List[str] = Field(default_factory=list)
    key_decisions: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class MeetingMetadata(BaseModel):
    """Metadata regarding a meeting."""

    meetily_id: str
    title: str = "Untitled Meeting"
    created_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    has_transcript: bool = False
    has_summary: bool = False
    status: str = "pending"


class MeetingResponse(BaseModel):
    """Public API response representing a meeting."""

    id: str
    meetily_id: str
    title: str
    created_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str
    transcript_hash: Optional[str] = None
    # Raw transcript is only included if EXPOSE_RAW_TRANSCRIPTS is True
    transcript: Optional[MeetingTranscript] = None
    summary: Optional[MeetingSummary] = None
