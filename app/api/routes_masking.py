from pathlib import Path
from typing import Optional, Union, Dict, Any
from fastapi import APIRouter, HTTPException

from app.masking import (
    PrivacyMaskingEngine,
    MeetingHandoff,
    ProcessingResult
)

router = APIRouter(prefix="/masking", tags=["Privacy Masking"])
engine = PrivacyMaskingEngine()

@router.post("/process-verified-meeting", response_model=ProcessingResult)
def process_verified_meeting(handoff: MeetingHandoff):
    """Processes verified commitments from Verification Engine, applies privacy masking & minimal context, and generates sanitized Markdown."""
    try:
        result = engine.process_verified_tasks(
            handoff_data=handoff,
            output_md_path="outputs/verified_tasks.md"
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "MASKING_ENGINE_ERROR", "message": str(exc)}}
        )

@router.post("/unmask-text")
def unmask_text(payload: Dict[str, str]):
    """Detokenizes masked text using local secret vault for the specified meeting."""
    meeting_id = payload.get("meeting_id")
    masked_text = payload.get("masked_text", "")
    if not meeting_id:
        raise HTTPException(status_code=400, detail="meeting_id is required")
    unmasked = engine.unmask_text(meeting_id=meeting_id, masked_text=masked_text)
    return {"meeting_id": meeting_id, "unmasked_text": unmasked}
