"""Repository pattern for database operations in Meetily Clean Room."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.storage.models import (
    IntelligenceRowModel,
    LedgerEntryModel,
    MeetingModel,
    OutputArtifactModel,
    ProcessingRunModel,
    ReleaseDecisionModel,
    ReviewItemModel,
    VerificationResultRowModel,
    WebhookEventModel,
)


class Repository:
    """Synchronous repository functions designed to be executed in thread pools."""

    def __init__(self, db: Session):
        self.db = db

    # --- Meetings ---
    def get_meeting_by_id(self, meeting_id: str) -> Optional[MeetingModel]:
        return self.db.query(MeetingModel).filter(
            (MeetingModel.id == meeting_id) | (MeetingModel.meetily_id == meeting_id)
        ).first()

    def get_meeting_by_meetily_id(self, meetily_id: str) -> Optional[MeetingModel]:
        return self.db.query(MeetingModel).filter(MeetingModel.meetily_id == meetily_id).first()

    def create_or_get_meeting(
        self, meetily_id: str, title: str = "Untitled Meeting", duration_seconds: Optional[float] = None
    ) -> MeetingModel:
        meeting = self.get_meeting_by_meetily_id(meetily_id)
        if meeting:
            if title and title != "Untitled Meeting":
                meeting.title = title
            if duration_seconds is not None:
                meeting.duration_seconds = duration_seconds
            self.db.commit()
            self.db.refresh(meeting)
            return meeting

        meeting = MeetingModel(
            meetily_id=meetily_id,
            title=title,
            duration_seconds=duration_seconds,
            status="created",
        )
        self.db.add(meeting)
        self.db.commit()
        self.db.refresh(meeting)
        return meeting

    def list_meetings(self) -> List[MeetingModel]:
        return self.db.query(MeetingModel).order_by(MeetingModel.created_at.desc()).all()

    def update_meeting_data(
        self,
        meeting_id: str,
        transcript_sha256: Optional[str] = None,
        raw_transcript: Optional[str] = None,
        raw_summary: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[MeetingModel]:
        meeting = self.get_meeting_by_id(meeting_id)
        if not meeting:
            return None
        if transcript_sha256:
            meeting.transcript_sha256 = transcript_sha256
        if raw_transcript is not None:
            meeting.raw_transcript = raw_transcript
        if raw_summary is not None:
            meeting.raw_summary = raw_summary
        if status:
            meeting.status = status
        self.db.commit()
        self.db.refresh(meeting)
        return meeting

    # --- Processing Runs ---
    def create_processing_run(self, meeting_id: str) -> ProcessingRunModel:
        run = ProcessingRunModel(
            meeting_id=meeting_id,
            status="running",
            current_stage="init",
            timings_json=json.dumps({"init": datetime.now(timezone.utc).isoformat()}),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def update_run_stage(
        self,
        run_id: str,
        stage: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[ProcessingRunModel]:
        run = self.db.query(ProcessingRunModel).filter(ProcessingRunModel.id == run_id).first()
        if not run:
            return None
        run.current_stage = stage
        run.status = status
        if error_message:
            run.error_message = error_message
        if status in ("completed", "failed", "hold"):
            run.completed_at = datetime.now(timezone.utc)

        timings = {}
        if run.timings_json:
            try:
                timings = json.loads(run.timings_json)
            except Exception:
                pass
        timings[stage] = datetime.now(timezone.utc).isoformat()
        run.timings_json = json.dumps(timings)

        self.db.commit()
        self.db.refresh(run)
        return run

    def get_latest_run(self, meeting_id: str) -> Optional[ProcessingRunModel]:
        return (
            self.db.query(ProcessingRunModel)
            .filter(ProcessingRunModel.meeting_id == meeting_id)
            .order_by(ProcessingRunModel.started_at.desc())
            .first()
        )

    # --- Verification Results ---
    def save_verification_result(
        self, run_id: str, meeting_id: str, overall_status: str, result_dict: Dict[str, Any]
    ) -> VerificationResultRowModel:
        row = VerificationResultRowModel(
            run_id=run_id,
            meeting_id=meeting_id,
            overall_status=overall_status,
            result_json=json.dumps(result_dict),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_latest_verification(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        row = (
            self.db.query(VerificationResultRowModel)
            .filter(VerificationResultRowModel.meeting_id == meeting_id)
            .order_by(VerificationResultRowModel.created_at.desc())
            .first()
        )
        if not row:
            return None
        return json.loads(row.result_json)

    # --- Intelligence Results ---
    def save_intelligence_result(
        self, run_id: str, meeting_id: str, intelligence_dict: Dict[str, Any]
    ) -> IntelligenceRowModel:
        row = IntelligenceRowModel(
            run_id=run_id,
            meeting_id=meeting_id,
            data_json=json.dumps(intelligence_dict),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_latest_intelligence(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        row = (
            self.db.query(IntelligenceRowModel)
            .filter(IntelligenceRowModel.meeting_id == meeting_id)
            .order_by(IntelligenceRowModel.created_at.desc())
            .first()
        )
        if not row:
            return None
        return json.loads(row.data_json)

    # --- Release Decisions ---
    def save_release_decision(
        self,
        run_id: str,
        meeting_id: str,
        decision: str,
        reasons: List[str],
        flagged_claims: List[str],
        flagged_conflicts: List[str],
        approved_by: Optional[str] = None,
    ) -> ReleaseDecisionModel:
        row = ReleaseDecisionModel(
            run_id=run_id,
            meeting_id=meeting_id,
            decision=decision,
            reasons_json=json.dumps(reasons),
            flagged_claims_json=json.dumps(flagged_claims),
            flagged_conflicts_json=json.dumps(flagged_conflicts),
            approved_by=approved_by,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_latest_release_decision(self, meeting_id: str) -> Optional[ReleaseDecisionModel]:
        return (
            self.db.query(ReleaseDecisionModel)
            .filter(ReleaseDecisionModel.meeting_id == meeting_id)
            .order_by(ReleaseDecisionModel.created_at.desc())
            .first()
        )

    # --- Review Items ---
    def create_review_items(self, items: List[Dict[str, Any]]) -> List[ReviewItemModel]:
        created = []
        for it in items:
            model = ReviewItemModel(
                run_id=it["run_id"],
                meeting_id=it["meeting_id"],
                item_type=it.get("item_type", "claim"),
                reference_id=it["reference_id"],
                original_text=it["original_text"],
                issue_type=it["issue_type"],
                suggested_fix=it.get("suggested_fix"),
                status="pending",
            )
            self.db.add(model)
            created.append(model)
        self.db.commit()
        for m in created:
            self.db.refresh(m)
        return created

    def list_review_items(self, meeting_id: str, status: Optional[str] = None) -> List[ReviewItemModel]:
        q = self.db.query(ReviewItemModel).filter(ReviewItemModel.meeting_id == meeting_id)
        if status:
            q = q.filter(ReviewItemModel.status == status)
        return q.all()

    def get_review_item(self, item_id: str) -> Optional[ReviewItemModel]:
        return self.db.query(ReviewItemModel).filter(ReviewItemModel.id == item_id).first()

    def update_review_item(
        self,
        item_id: str,
        status: str,
        corrected_text: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
    ) -> Optional[ReviewItemModel]:
        item = self.get_review_item(item_id)
        if not item:
            return None
        item.status = status
        if corrected_text is not None:
            item.corrected_text = corrected_text
        if reviewer_notes is not None:
            item.reviewer_notes = reviewer_notes
        item.resolved_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(item)
        return item

    # --- Output Artifacts ---
    def save_output_artifact(
        self,
        run_id: str,
        meeting_id: str,
        audience: str,
        file_path: str,
        canary_present: bool = False,
        status: str = "clean",
    ) -> OutputArtifactModel:
        artifact = OutputArtifactModel(
            run_id=run_id,
            meeting_id=meeting_id,
            audience=audience,
            file_path=file_path,
            canary_present=canary_present,
            status=status,
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def list_output_artifacts(self, meeting_id: str) -> List[OutputArtifactModel]:
        return self.db.query(OutputArtifactModel).filter(OutputArtifactModel.meeting_id == meeting_id).all()

    # --- Webhook Events ---
    def record_webhook_event(
        self,
        event_id: str,
        event_type: str,
        resource_id: str,
        payload_dict: Dict[str, Any],
    ) -> WebhookEventModel:
        event = WebhookEventModel(
            event_id=event_id,
            event_type=event_type,
            resource_id=resource_id,
            payload_json=json.dumps(payload_dict),
            status="received",
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_webhook_event(self, event_id: str) -> Optional[WebhookEventModel]:
        return self.db.query(WebhookEventModel).filter(WebhookEventModel.event_id == event_id).first()

    def update_webhook_event(
        self, event_id: str, status: str, error_message: Optional[str] = None
    ) -> Optional[WebhookEventModel]:
        event = self.get_webhook_event(event_id)
        if not event:
            return None
        event.status = status
        if error_message:
            event.error_message = error_message
        self.db.commit()
        self.db.refresh(event)
        return event

    # --- Ledger Entries ---
    def get_latest_ledger_entry(self, meeting_id: str) -> Optional[LedgerEntryModel]:
        return (
            self.db.query(LedgerEntryModel)
            .filter(LedgerEntryModel.meeting_id == meeting_id)
            .order_by(LedgerEntryModel.index.desc())
            .first()
        )

    def append_ledger_entry(
        self,
        meeting_id: str,
        index: int,
        event_type: str,
        timestamp: str,
        payload_dict: Dict[str, Any],
        transcript_sha256: str,
        prev_hash: str,
        entry_hash: str,
    ) -> LedgerEntryModel:
        entry = LedgerEntryModel(
            meeting_id=meeting_id,
            index=index,
            event_type=event_type,
            timestamp=timestamp,
            payload_json=json.dumps(payload_dict, sort_keys=True),
            transcript_sha256=transcript_sha256,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_ledger_entries(self, meeting_id: str) -> List[LedgerEntryModel]:
        return (
            self.db.query(LedgerEntryModel)
            .filter(LedgerEntryModel.meeting_id == meeting_id)
            .order_by(LedgerEntryModel.index.asc())
            .all()
        )
