"""Gatekeeper evaluating verification results, cross-source conflicts, and privacy before distribution."""

import uuid
from typing import List, Optional

from backend.schemas.policy import PrivacyCoverageReport
from backend.schemas.release import (
    CrossSourceConflict,
    GateDecisionType,
    ReleaseDecision,
)
from backend.schemas.verification import (
    OverallVerificationStatus,
    Verdict,
    VerificationResult,
)


class Gatekeeper:
    """Evaluates whether meeting intelligence outputs may be safely distributed."""

    @staticmethod
    def evaluate(
        meeting_id: str,
        run_id: str,
        verification: VerificationResult,
        conflicts: List[CrossSourceConflict],
        coverage: Optional[PrivacyCoverageReport] = None,
        human_approval: Optional[str] = None,
    ) -> ReleaseDecision:
        """Make release / hold / block decision."""
        # If manually approved by human reviewer, allow release with override
        if human_approval:
            return ReleaseDecision(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                run_id=run_id,
                decision=GateDecisionType.RELEASE,
                reasons=[f"Manual human approval granted by: {human_approval}"],
                flagged_claim_ids=[],
                flagged_conflict_ids=[],
                overridden=True,
                approved_by=human_approval,
            )

        reasons: List[str] = []
        flagged_claims: List[str] = []
        flagged_conflicts: List[str] = []

        # 1. Check for contradicted claims
        for claim in verification.claims:
            if claim.verdict == Verdict.CONTRADICTED:
                flagged_claims.append(claim.id)
                reasons.append(f"Contradicted claim {claim.id}: '{claim.text}' ({claim.explanation})")
            elif "owner_unverified" in claim.flags:
                flagged_claims.append(claim.id)
                reasons.append(f"Unverified action item owner for {claim.id}: '{claim.text}'")
            elif "deadline_unverified" in claim.flags:
                flagged_claims.append(claim.id)
                reasons.append(f"Unverified deadline for {claim.id}: '{claim.text}'")

        # 2. Check for cross-source document conflicts
        for conf in conflicts:
            flagged_conflicts.append(conf.id)
            reasons.append(f"Diligence conflict {conf.id}: {conf.explanation}")

        # 3. Decision evaluation
        decision = GateDecisionType.RELEASE
        if flagged_claims or flagged_conflicts or verification.overall_status != OverallVerificationStatus.VERIFIED:
            decision = GateDecisionType.HOLD_FOR_REVIEW

        return ReleaseDecision(
            id=str(uuid.uuid4()),
            meeting_id=meeting_id,
            run_id=run_id,
            decision=decision,
            reasons=reasons,
            flagged_claim_ids=flagged_claims,
            flagged_conflict_ids=flagged_conflicts,
            overridden=False,
            approved_by=None,
        )
