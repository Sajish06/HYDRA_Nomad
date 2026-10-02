"""Pipeline orchestrator coordinating verification, masking, gating, review, and distribution."""

from pathlib import Path
from typing import Any, Optional, Tuple

import yaml

from backend.ai.base import LLMProvider
from backend.ai.gemini_provider import GeminiProvider
from backend.ai.guarded import GuardedLLMProvider
from backend.config import settings
from backend.logging import logger
from backend.processors.crosscheck import CrossCheckEngine
from backend.processors.distribution import DistributionEngine
from backend.processors.extraction import IntelligenceExtractor
from backend.processors.gate import Gatekeeper
from backend.processors.leakscan import LeakScanner
from backend.processors.ledger import AuditLedger
from backend.processors.policy import PolicyEngine
from backend.processors.privacy import PrivacyEngine, Vault
from backend.processors.verification import VerificationEngine
from backend.schemas.meeting import MeetingSummary, MeetingTranscript
from backend.schemas.policy import DealConfig
from backend.schemas.release import (
    GateDecisionType,
    OverallLeakReport,
    ReleaseDecision,
)
from backend.schemas.verification import (
    Verdict,
    VerificationResult,
)
from backend.storage.models import (
    ProcessingRunModel,
)
from backend.storage.repository import Repository


class PipelineOrchestrator:
    """End-to-end execution of Clean Room processing with transactional stage management."""

    def __init__(
        self,
        repo: Repository,
        vault: Optional[Vault] = None,
        deal_config: Optional[DealConfig] = None,
        doc_source: Optional[Any] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.repo = repo
        self.deal_config = deal_config or self._load_deal_config()
        self.engine = PrivacyEngine(deal_config=self.deal_config)
        self.vault = vault or Vault(engine=self.engine)
        self.policy = PolicyEngine(deal_config=self.deal_config)
        self.verifier = VerificationEngine(vault=self.vault)
        self.extractor = IntelligenceExtractor(vault=self.vault, verifier=self.verifier)
        self.crosschecker = CrossCheckEngine(doc_source=doc_source)
        self.distributor = DistributionEngine(policy_engine=self.policy, vault=self.vault)
        self.scanner = LeakScanner(vault=self.vault, deal_config=self.deal_config)
        self.llm_provider = llm_provider

    def _load_deal_config(self) -> DealConfig:
        """Load deal configuration from disk."""
        path = Path(settings.DEAL_CONFIG_PATH)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return DealConfig(**data)
            except Exception:
                pass
        return DealConfig()

    def _get_provider(self, meeting_id: str) -> Optional[GuardedLLMProvider]:
        """Initialize guarded AI provider if ENABLE_AI is true or mock is provided."""
        if self.llm_provider:
            return GuardedLLMProvider(self.llm_provider, self.vault, meeting_id=meeting_id)

        if settings.ENABLE_AI:
            if settings.GEMINI_API_KEY:
                raw_gemini = GeminiProvider()
                return GuardedLLMProvider(raw_gemini, self.vault, meeting_id=meeting_id)
            else:
                logger.warning("ENABLE_AI=true but no GEMINI_API_KEY provided; falling back to baseline")
        return None

    async def execute_run(
        self,
        meeting_id: str,
        transcript: MeetingTranscript,
        summary: MeetingSummary,
        human_approval: Optional[str] = None,
    ) -> Tuple[ProcessingRunModel, ReleaseDecision, VerificationResult, Optional[OverallLeakReport]]:
        """Run complete processing pipeline from tokenization to distribution."""
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if not meeting:
            raise ValueError(f"Meeting not found: {meeting_id}")

        # Create processing run
        run = self.repo.create_processing_run(meeting.id)

        # Record ledger start event
        AuditLedger.record_event(
            repo=self.repo,
            meeting_id=meeting.id,
            event_type="run_started",
            payload={"run_id": run.id, "stage": "init"},
            transcript_sha256=transcript.sha256_hash,
        )

        try:
            # Stage 1: Privacy Tokenization
            self.repo.update_run_stage(run.id, "privacy_tokenize", "running")
            masked_transcript = self.vault.tokenize(transcript.raw_text or "")
            masked_summary = self.vault.tokenize(summary.summary_text)
            coverage = self.vault.get_coverage_report()

            # Stage 2: Verification and Extraction
            self.repo.update_run_stage(run.id, "verify_and_extract", "running")
            provider = self._get_provider(meeting.id)

            if provider:
                logger.info(f"Running guarded AI verification for run {run.id}")
                draft_claims = await provider.verify_claims(
                    masked_transcript.text, masked_summary.text
                )
                v_result = self.verifier.process_ai_draft(
                    draft_claims, summary, transcript, run_id=run.id
                )

                draft_intel = await provider.extract_intelligence(
                    masked_transcript.text, masked_summary.text
                )
                i_result = self.extractor.process_ai_draft(
                    draft_intel, transcript, meeting.id, run_id=run.id
                )
            else:
                logger.info(f"Running baseline verification for run {run.id}")
                v_result = self.verifier.verify_baseline(summary, transcript, run_id=run.id)
                i_result = self.extractor.extract_baseline(transcript, summary, run_id=run.id)

            # Persist verification and intelligence results
            self.repo.save_verification_result(
                run.id, meeting.id, v_result.overall_status.value, v_result.model_dump(mode="json")
            )
            self.repo.save_intelligence_result(
                run.id, meeting.id, i_result.model_dump(mode="json")
            )

            AuditLedger.record_event(
                repo=self.repo,
                meeting_id=meeting.id,
                event_type="verification_completed",
                payload={
                    "overall_status": v_result.overall_status.value,
                    "supported": v_result.supported_count,
                    "contradicted": v_result.contradicted_count,
                    "unverifiable": v_result.unverifiable_count,
                },
                transcript_sha256=transcript.sha256_hash,
            )

            # Stage 3: Cross-source check
            self.repo.update_run_stage(run.id, "crosscheck", "running")
            conflicts = self.crosschecker.cross_check(transcript)

            # Stage 4: Gatekeeper Evaluation
            self.repo.update_run_stage(run.id, "gate", "running")
            decision = Gatekeeper.evaluate(
                meeting_id=meeting.id,
                run_id=run.id,
                verification=v_result,
                conflicts=conflicts,
                coverage=coverage,
                human_approval=human_approval,
            )

            self.repo.save_release_decision(
                run_id=run.id,
                meeting_id=meeting.id,
                decision=decision.decision.value,
                reasons=decision.reasons,
                flagged_claims=decision.flagged_claim_ids,
                flagged_conflicts=decision.flagged_conflict_ids,
                approved_by=decision.approved_by,
            )

            AuditLedger.record_event(
                repo=self.repo,
                meeting_id=meeting.id,
                event_type="gate_decision",
                payload={
                    "decision": decision.decision.value,
                    "reasons": decision.reasons,
                    "overridden": decision.overridden,
                },
                transcript_sha256=transcript.sha256_hash,
            )

            # Stage 5: Handle Hold vs Release
            leak_report: Optional[OverallLeakReport] = None
            if decision.decision == GateDecisionType.HOLD_FOR_REVIEW:
                self.repo.update_run_stage(run.id, "hold_review", "hold")
                # Populate review items in repository
                review_items_data = []
                for cid in decision.flagged_claim_ids:
                    claim = next((c for c in v_result.claims if c.id == cid), None)
                    if claim:
                        review_items_data.append(
                            {
                                "run_id": run.id,
                                "meeting_id": meeting.id,
                                "item_type": "claim",
                                "reference_id": cid,
                                "original_text": claim.text,
                                "issue_type": "contradiction"
                                if claim.verdict == Verdict.CONTRADICTED
                                else "attribute_unverified",
                                "suggested_fix": None,
                            }
                        )
                for conf_id in decision.flagged_conflict_ids:
                    conflict = next((c for c in conflicts if c.id == conf_id), None)
                    if conflict:
                        review_items_data.append(
                            {
                                "run_id": run.id,
                                "meeting_id": meeting.id,
                                "item_type": "conflict",
                                "reference_id": conf_id,
                                "original_text": f"{conflict.metric}: transcript={conflict.transcript_value} vs {conflict.doc_name}={conflict.doc_value}",
                                "issue_type": "document_conflict",
                                "suggested_fix": f"Reconcile {conflict.metric} value with {conflict.doc_name}",
                            }
                        )
                self.repo.create_review_items(review_items_data)

            elif decision.decision == GateDecisionType.RELEASE:
                # Stage 6: Distribution and Leak Scanning
                self.repo.update_run_stage(run.id, "distribution", "running")
                produced_paths = await self.distributor.distribute(
                    meeting_id=meeting.id,
                    summary=summary,
                    claims=v_result.claims,
                )

                # Persist output artifacts
                for aud, p in produced_paths.items():
                    self.repo.save_output_artifact(
                        run_id=run.id,
                        meeting_id=meeting.id,
                        audience=aud,
                        file_path=p,
                        canary_present=(aud == "deal_team"),
                        status="clean",
                    )

                # Run post-generation leak scan
                self.repo.update_run_stage(run.id, "leakscan", "running")
                leak_report = self.scanner.scan_output_artifacts(
                    meeting.id, run.id, produced_paths
                )

                if not leak_report.all_passed:
                    self.repo.update_run_stage(
                        run.id, "leakscan", "failed", error_message="Leak scan detected privacy violation"
                    )
                else:
                    self.repo.update_run_stage(run.id, "completed", "completed")

                AuditLedger.record_event(
                    repo=self.repo,
                    meeting_id=meeting.id,
                    event_type="output_released",
                    payload={
                        "outputs": list(produced_paths.keys()),
                        "leak_scan_passed": leak_report.all_passed,
                    },
                    transcript_sha256=transcript.sha256_hash,
                )

            return run, decision, v_result, leak_report

        except Exception as e:
            logger.error(f"Pipeline execution failed for run {run.id}: {str(e)}", exc_info=True)
            self.repo.update_run_stage(run.id, "failed", "failed", error_message=str(e))
            raise

    async def resume_after_review(
        self,
        meeting_id: str,
        transcript: MeetingTranscript,
        summary: MeetingSummary,
        reviewer_name: str = "Compliance Reviewer",
    ) -> Tuple[ProcessingRunModel, ReleaseDecision, VerificationResult, Optional[OverallLeakReport]]:
        """Resume pipeline from review resolutions, replacing corrected claims and triggering distribution."""
        meeting = self.repo.get_meeting_by_id(meeting_id)
        if not meeting:
            raise ValueError(f"Meeting not found: {meeting_id}")

        review_items = self.repo.list_review_items(meeting.id)
        # Check if all items are resolved
        pending = [it for it in review_items if it.status == "pending"]
        if pending:
            raise ValueError(f"Cannot release: {len(pending)} review items still pending approval/correction.")

        # Record human review actions in ledger
        for it in review_items:
            AuditLedger.record_event(
                repo=self.repo,
                meeting_id=meeting.id,
                event_type="review_action",
                payload={
                    "item_id": it.id,
                    "action": it.status,
                    "corrected_text": it.corrected_text,
                    "reviewer": reviewer_name,
                },
                transcript_sha256=transcript.sha256_hash,
            )

        # Build updated summary text incorporating any corrections
        updated_summary_text = summary.summary_text
        for it in review_items:
            if it.status == "corrected" and it.corrected_text:
                updated_summary_text = updated_summary_text.replace(it.original_text, it.corrected_text)

        updated_summary = MeetingSummary(
            meeting_id=meeting_id,
            summary_text=updated_summary_text,
            action_items=summary.action_items,
            key_decisions=summary.key_decisions,
            created_at=summary.created_at,
        )

        # Re-execute run with human approval override
        return await self.execute_run(
            meeting_id=meeting.id,
            transcript=transcript,
            summary=updated_summary,
            human_approval=reviewer_name,
        )
