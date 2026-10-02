from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from app.masking import (
    PrivacyMaskingEngine,
    MeetingHandoff,
    ProcessingResult
)

router = APIRouter(prefix="/masking", tags=["Privacy Masking Engine"])

# Global engine instance
masking_engine = PrivacyMaskingEngine()

@router.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "ASCENT Privacy Masking & Minimization Engine",
        "layer_1_semantic": "active",
        "layer_2_deterministic_firewall": "active"
    }

@router.post("/process-verified-meeting", response_model=ProcessingResult)
def process_verified_meeting(handoff: MeetingHandoff) -> ProcessingResult:
    """
    Executes the Two-Layer Privacy Pipeline:
      1. Layer 1: Semantic Decomposition (isolates business secrets).
      2. Layer 2: Deterministic Firewall (scrubs credentials & PII, validates leak gate).
      3. Outputs clean AgentTaskPayload and verified_tasks.md.
    """
    try:
        result = masking_engine.process_verified_tasks(
            handoff_data=handoff,
            output_md_path="outputs/verified_tasks.md"
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
