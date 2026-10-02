"""Schema adapter isolating all Meetily Automation API response structures.

Transforms external payload shapes into internal Pydantic models.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from backend.meetily.errors import MeetilyInvalidResponse
from backend.schemas.meeting import (
    MeetingMetadata,
    MeetingSummary,
    MeetingTranscript,
    TranscriptSegment,
)


class MeetilySchemaAdapter:
    """Tolerant parser converting varied Meetily API payloads to Clean Room schemas."""

    @staticmethod
    def compute_sha256(text: str) -> str:
        """Compute SHA-256 fingerprint for text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def parse_meeting_metadata(cls, data: Dict[str, Any]) -> MeetingMetadata:
        """Parse raw meeting response into MeetingMetadata."""
        if not isinstance(data, dict):
            raise MeetilyInvalidResponse("Meeting payload must be a JSON object")

        meetily_id = str(data.get("id") or data.get("meetily_id") or data.get("uuid") or "")
        if not meetily_id:
            raise MeetilyInvalidResponse("Meeting payload missing id/meetily_id")

        title = str(
            data.get("title") or data.get("name") or data.get("subject") or "Untitled Meeting"
        )

        # Parse date if present
        created_at = None
        raw_date = data.get("created_at") or data.get("date") or data.get("timestamp")
        if raw_date:
            try:
                if isinstance(raw_date, (int, float)):
                    created_at = datetime.fromtimestamp(raw_date)
                elif isinstance(raw_date, str):
                    created_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except Exception:
                created_at = None

        # Parse duration
        duration = data.get("duration_seconds") or data.get("duration") or data.get("length")
        duration_seconds = float(duration) if duration is not None else None

        has_transcript = bool(data.get("has_transcript") or data.get("transcript"))
        has_summary = bool(data.get("has_summary") or data.get("summary"))
        status = str(data.get("status") or "completed")

        return MeetingMetadata(
            meetily_id=meetily_id,
            title=title,
            created_at=created_at,
            duration_seconds=duration_seconds,
            has_transcript=has_transcript,
            has_summary=has_summary,
            status=status,
        )

    @classmethod
    def parse_transcript(
        cls, meeting_id: str, data: Union[Dict[str, Any], List[Any], str]
    ) -> MeetingTranscript:
        """Parse transcript payload (segmented or flat) into MeetingTranscript."""
        segments: List[TranscriptSegment] = []
        raw_full_text = ""

        # Case 1: Raw string
        if isinstance(data, str):
            raw_full_text = data.strip()
            segments.append(
                TranscriptSegment(
                    segment_index=0,
                    speaker="Speaker",
                    start_time=None,
                    end_time=None,
                    text=raw_full_text,
                )
            )

        # Case 2: List of segments
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                if isinstance(item, dict):
                    seg_text = str(
                        item.get("text") or item.get("content") or item.get("words") or ""
                    ).strip()
                    speaker = str(
                        item.get("speaker") or item.get("speaker_name") or item.get("speaker_id") or "Speaker"
                    )
                    start = item.get("start_time") if "start_time" in item else item.get("start")
                    end = item.get("end_time") if "end_time" in item else item.get("end")

                    segments.append(
                        TranscriptSegment(
                            segment_index=idx,
                            speaker=speaker,
                            start_time=float(start) if start is not None else None,
                            end_time=float(end) if end is not None else None,
                            text=seg_text,
                        )
                    )
            raw_full_text = " ".join(s.text for s in segments if s.text)

        # Case 3: Dict with segments or text
        elif isinstance(data, dict):
            raw_segments = (
                data.get("segments")
                or data.get("transcript")
                or data.get("items")
                or data.get("utterances")
            )
            if isinstance(raw_segments, list):
                return cls.parse_transcript(meeting_id, raw_segments)
            elif "text" in data or "content" in data:
                return cls.parse_transcript(meeting_id, str(data.get("text") or data.get("content") or ""))
            else:
                raw_full_text = json.dumps(data)
                segments.append(
                    TranscriptSegment(
                        segment_index=0,
                        speaker="Speaker",
                        start_time=None,
                        end_time=None,
                        text=raw_full_text,
                    )
                )

        sha256_hash = cls.compute_sha256(raw_full_text)
        return MeetingTranscript(
            meeting_id=meeting_id,
            segments=segments,
            raw_text=raw_full_text,
            sha256_hash=sha256_hash,
        )

    @classmethod
    def parse_summary(cls, meeting_id: str, data: Union[Dict[str, Any], str]) -> MeetingSummary:
        """Parse summary payload into MeetingSummary."""
        summary_text = ""
        action_items: List[str] = []
        key_decisions: List[str] = []

        if isinstance(data, str):
            summary_text = data.strip()
        elif isinstance(data, dict):
            summary_text = str(
                data.get("summary_text")
                or data.get("summary")
                or data.get("overview")
                or data.get("notes")
                or data.get("content")
                or ""
            ).strip()

            raw_actions = (
                data.get("action_items")
                or data.get("actions")
                or data.get("tasks")
                or data.get("next_steps")
                or []
            )
            if isinstance(raw_actions, list):
                for item in raw_actions:
                    if isinstance(item, str):
                        action_items.append(item.strip())
                    elif isinstance(item, dict):
                        desc = item.get("text") or item.get("task") or item.get("description") or ""
                        owner = item.get("owner")
                        due = item.get("due_date") or item.get("deadline")
                        text_parts = [desc]
                        if owner:
                            text_parts.append(f"(Owner: {owner})")
                        if due:
                            text_parts.append(f"(Due: {due})")
                        action_items.append(" ".join(text_parts))

            raw_decisions = (
                data.get("key_decisions")
                or data.get("decisions")
                or data.get("outcomes")
                or []
            )
            if isinstance(raw_decisions, list):
                for item in raw_decisions:
                    if isinstance(item, str):
                        key_decisions.append(item.strip())
                    elif isinstance(item, dict):
                        key_decisions.append(str(item.get("decision") or item.get("text") or ""))

        return MeetingSummary(
            meeting_id=meeting_id,
            summary_text=summary_text,
            action_items=action_items,
            key_decisions=key_decisions,
            created_at=datetime.now(timezone.utc),
        )
