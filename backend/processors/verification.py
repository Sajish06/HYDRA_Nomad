"""Claim verification engine with spoken-number normalization and local transcript relocation."""

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.processors.number_normalizer import (
    extract_numbers_from_text,
    numbers_compare_equal,
)
from backend.processors.privacy import Vault
from backend.schemas.meeting import MeetingSummary, MeetingTranscript, TranscriptSegment
from backend.schemas.verification import (
    ClaimItem,
    EvidenceItem,
    OmissionItem,
    OverallVerificationStatus,
    Verdict,
    VerificationResult,
)


class VerificationEngine:
    """Verifies meeting summary claims against local transcript evidence."""

    def __init__(self, vault: Optional[Vault] = None):
        self.vault = vault or Vault()

    def relocate_evidence(
        self, quote: str, transcript: MeetingTranscript
    ) -> Tuple[bool, Optional[TranscriptSegment], Optional[str]]:
        """Verify that a cited quote actually exists in the local transcript (substring or fuzzy)."""
        clean_quote = re.sub(r"[^\w\s]", "", quote.lower()).strip()
        if not clean_quote:
            return False, None, None

        quote_words = clean_quote.split()
        if len(quote_words) < 2:
            # Single word check
            for seg in transcript.segments:
                if clean_quote in seg.text.lower():
                    return True, seg, seg.text
            return False, None, None

        # 1. Exact or normalized substring match in segments
        for seg in transcript.segments:
            seg_clean = re.sub(r"[^\w\s]", "", seg.text.lower())
            if clean_quote in seg_clean:
                return True, seg, seg.text

        # 2. Check full transcript text
        full_clean = re.sub(r"[^\w\s]", "", (transcript.raw_text or "").lower())
        if clean_quote in full_clean:
            # Find the best segment
            for seg in transcript.segments:
                seg_words = set(re.sub(r"[^\w\s]", "", seg.text.lower()).split())
                if len(set(quote_words) & seg_words) >= max(2, len(quote_words) // 2):
                    return True, seg, seg.text
            return True, transcript.segments[0] if transcript.segments else None, quote

        # 3. Fuzzy match across segments (threshold >= 0.75)
        best_ratio = 0.0
        best_seg = None
        for seg in transcript.segments:
            seg_clean = re.sub(r"[^\w\s]", "", seg.text.lower())
            # Slide window of similar length
            words = seg_clean.split()
            w_len = len(quote_words)
            for i in range(max(1, len(words) - w_len + 1)):
                window = " ".join(words[i : i + w_len])
                ratio = difflib.SequenceMatcher(None, clean_quote, window).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_seg = seg

        if best_ratio >= 0.75 and best_seg:
            return True, best_seg, best_seg.text

        return False, None, None

    def check_number_consistency(
        self, claim_text: str, evidence_text: str
    ) -> Tuple[bool, Optional[str]]:
        """Verify numeric figures between claim and evidence.

        Returns (is_consistent, conflict_explanation).
        """
        claim_nums = extract_numbers_from_text(claim_text)
        if not claim_nums:
            return True, None

        evidence_nums = extract_numbers_from_text(evidence_text)
        if not evidence_nums:
            # Claim makes a numeric assertion but evidence contains zero numbers
            return False, f"Claim asserts numeric figure {claim_nums[0][0]}, but cited transcript evidence mentions no numbers."

        # Compare claim numbers against evidence numbers
        for c_raw, c_val in claim_nums:
            matched = False
            for _e_raw, e_val in evidence_nums:
                if numbers_compare_equal(c_val, e_val):
                    matched = True
                    break
            if not matched:
                ev_str = ", ".join(f"'{r}' ({v})" for r, v in evidence_nums)
                return (
                    False,
                    f"Numeric mismatch: Claim asserts '{c_raw}' ({c_val}), but transcript evidence states {ev_str}.",
                )

        return True, None

    def check_action_item_attributes(
        self, item_text: str, transcript: MeetingTranscript
    ) -> Tuple[bool, bool, Optional[str], Optional[str]]:
        """Check if action item owner and deadline are confirmed in the transcript.

        Returns (owner_verified, deadline_verified, owner_name, deadline_str).
        """
        owner = None
        deadline = None
        owner_verified = True
        deadline_verified = True

        # Extract explicit owner markers if present: "(Owner: Bob)" or "Bob will..."
        owner_match = re.search(r"\(Owner:\s*([^)]+)\)", item_text, re.IGNORECASE)
        if owner_match:
            owner = owner_match.group(1).strip()
        else:
            # Check known people or names at beginning
            words = item_text.split()
            if words and words[0][0].isupper() and words[0].lower() not in ("the", "to", "ensure", "review", "send", "finalize"):
                owner = words[0]

        # Extract deadline
        due_match = re.search(
            r"(?:by|due|before)\s+(Friday|Monday|Tuesday|Wednesday|Thursday|end of week|next week|\d{4}-\d{2}-\d{2})",
            item_text,
            re.IGNORECASE,
        )
        if due_match:
            deadline = due_match.group(1)

        # Check in transcript
        full_text = transcript.raw_text or ""
        if owner:
            # If owner is mentioned in summary action item, does transcript associate this person?
            # E.g. If transcript says "Priya sends customer concentration data by Friday", but claim says "David sends..."
            if owner.lower() not in full_text.lower():
                owner_verified = False
            else:
                # Find task keywords near owner mention
                task_keywords = [w.lower() for w in item_text.split() if len(w) > 4 and w.lower() != owner.lower()]
                found_near = False
                for seg in transcript.segments:
                    if owner.lower() in seg.text.lower() or (seg.speaker and owner.lower() in seg.speaker.lower()):
                        if any(kw in seg.text.lower() for kw in task_keywords):
                            found_near = True
                            break
                if not found_near:
                    # Stated owner is in transcript, but NOT assigned this specific task
                    owner_verified = False

        if deadline:
            if deadline.lower() not in full_text.lower():
                deadline_verified = False

        return owner_verified, deadline_verified, owner, deadline

    def verify_baseline(
        self, summary: MeetingSummary, transcript: MeetingTranscript, run_id: str
    ) -> VerificationResult:
        """Deterministic baseline verification when AI is disabled."""
        claims: List[ClaimItem] = []
        contradicted_count = 0
        partially_supported_count = 0
        supported_count = 0
        unverifiable_count = 0
        review_reasons: List[str] = []

        # 1. Break summary into candidate sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary.summary_text) if len(s.strip()) > 10]

        # Combine with action items
        raw_items = []
        for s in sentences:
            raw_items.append((s, "claim"))
        for act in summary.action_items:
            raw_items.append((act, "action_item"))

        def norm_word(w: str) -> str:
            clean = re.sub(r"[^\w]", "", w.lower())
            for suf in ("ing", "ed", "es", "s", "d"):
                if len(clean) > 4 and clean.endswith(suf):
                    return clean[: -len(suf)]
            return clean

        for idx, (item_text, claim_type) in enumerate(raw_items):
            claim_id = f"c_{idx + 1}"
            flags: List[str] = ["preliminary"]
            verdict = Verdict.UNVERIFIABLE
            confidence = 0.5
            explanation = ""
            evidence_list: List[EvidenceItem] = []
            evidence_verified = False

            # Find best matching transcript segment by token overlap
            item_words = {norm_word(w) for w in item_text.split() if len(norm_word(w)) >= 3}
            best_seg: Optional[TranscriptSegment] = None
            best_overlap = 0.0

            for seg in transcript.segments:
                seg_combined = f"{seg.speaker} {seg.text}"
                seg_words = {norm_word(w) for w in seg_combined.split() if len(norm_word(w)) >= 3}
                if not seg_words:
                    continue
                overlap = len(item_words & seg_words) / max(1, len(item_words))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_seg = seg

            if best_seg and best_overlap >= 0.25:
                ev_quote = best_seg.text
                ev_item = EvidenceItem(
                    text=ev_quote,
                    speaker=best_seg.speaker,
                    timestamp=f"{int(best_seg.start_time // 60):02d}:{int(best_seg.start_time % 60):02d}"
                    if best_seg.start_time is not None
                    else None,
                    segment_index=best_seg.segment_index,
                )
                evidence_list.append(ev_item)

                # Local relocation check
                loc_found, _, _ = self.relocate_evidence(ev_quote, transcript)
                evidence_verified = loc_found

                # Number consistency check
                num_consistent, num_err = self.check_number_consistency(item_text, ev_quote)
                if not num_consistent:
                    verdict = Verdict.CONTRADICTED
                    confidence = 0.95
                    explanation = num_err or "Number discrepancy detected."
                    flags.append("number_mismatch")
                    contradicted_count += 1
                    review_reasons.append(f"Claim {claim_id}: {explanation}")
                else:
                    if best_overlap >= 0.5 and evidence_verified:
                        verdict = Verdict.SUPPORTED
                        confidence = 0.85
                        explanation = f"Matched transcript segment {best_seg.segment_index} with high lexical overlap."
                        supported_count += 1
                    else:
                        verdict = Verdict.PARTIALLY_SUPPORTED
                        confidence = 0.65
                        explanation = f"Partial lexical overlap ({best_overlap:.0%}) with transcript."
                        partially_supported_count += 1
            else:
                verdict = Verdict.UNVERIFIABLE
                confidence = 0.2
                explanation = "No matching segment found in transcript."
                flags.append("evidence_not_found")
                unverifiable_count += 1
                review_reasons.append(f"Claim {claim_id}: Unverifiable claim with no evidence found.")

            # Check action item attributes
            owner = None
            deadline = None
            owner_verified = True
            deadline_verified = True
            if claim_type == "action_item":
                owner_verified, deadline_verified, owner, deadline = self.check_action_item_attributes(
                    item_text, transcript
                )
                if not owner_verified:
                    flags.append("owner_unverified")
                    verdict = Verdict.CONTRADICTED if verdict == Verdict.SUPPORTED else verdict
                    review_reasons.append(f"Action item {claim_id}: Assigned owner '{owner}' not confirmed in transcript.")
                if not deadline_verified:
                    flags.append("deadline_unverified")
                    review_reasons.append(f"Action item {claim_id}: Stated deadline '{deadline}' not confirmed in transcript.")

            claims.append(
                ClaimItem(
                    id=claim_id,
                    text=item_text,
                    claim_type=claim_type,
                    verdict=verdict,
                    confidence=confidence,
                    explanation=explanation,
                    evidence=evidence_list,
                    evidence_verified=evidence_verified,
                    method="baseline",
                    flags=flags,
                    owner=owner,
                    deadline=deadline,
                    owner_verified=owner_verified,
                    deadline_verified=deadline_verified,
                )
            )

        # Detect transcript omissions
        omissions = self.detect_omissions(summary, transcript)

        overall_status = OverallVerificationStatus.VERIFIED
        if contradicted_count > 0 or any("owner_unverified" in c.flags for c in claims):
            overall_status = OverallVerificationStatus.REVIEW_REQUIRED
        elif unverifiable_count > (len(claims) / 2):
            overall_status = OverallVerificationStatus.FAILED
        elif review_reasons:
            overall_status = OverallVerificationStatus.REVIEW_REQUIRED

        return VerificationResult(
            meeting_id=summary.meeting_id,
            run_id=run_id,
            overall_status=overall_status,
            claims=claims,
            omissions=omissions,
            supported_count=supported_count,
            partially_supported_count=partially_supported_count,
            contradicted_count=contradicted_count,
            unverifiable_count=unverifiable_count,
            review_reasons=review_reasons,
            method="baseline",
        )

    def process_ai_draft(
        self,
        draft_claims: List[Dict[str, Any]],
        summary: MeetingSummary,
        transcript: MeetingTranscript,
        run_id: str,
    ) -> VerificationResult:
        """Validate and post-process AI proposed claims with deterministic local checks."""
        claims: List[ClaimItem] = []
        contradicted_count = 0
        partially_supported_count = 0
        supported_count = 0
        unverifiable_count = 0
        review_reasons: List[str] = []

        for idx, item in enumerate(draft_claims):
            cid = item.get("id") or f"c_{idx + 1}"
            raw_text = item.get("text", "")
            raw_verdict_str = item.get("verdict", "unverifiable")
            try:
                verdict = Verdict(raw_verdict_str)
            except ValueError:
                verdict = Verdict.UNVERIFIABLE

            confidence = float(item.get("confidence", 0.7))
            explanation = item.get("explanation", "")
            claim_type = item.get("claim_type", "claim")
            flags: List[str] = []

            # Rehydrate text locally if needed
            rehydrated_text = self.vault.rehydrate(raw_text)

            # Check evidence quotes
            raw_evidence = item.get("evidence", [])
            evidence_items: List[EvidenceItem] = []
            all_evidence_located = True

            for ev in raw_evidence:
                ev_quote = self.vault.rehydrate(ev.get("text", ""))
                loc_found, real_seg, _ = self.relocate_evidence(ev_quote, transcript)
                if loc_found and real_seg:
                    ts = (
                        f"{int(real_seg.start_time // 60):02d}:{int(real_seg.start_time % 60):02d}"
                        if real_seg.start_time is not None
                        else ev.get("timestamp")
                    )
                    evidence_items.append(
                        EvidenceItem(
                            text=ev_quote,
                            speaker=real_seg.speaker,
                            timestamp=ts,
                            segment_index=real_seg.segment_index,
                        )
                    )
                else:
                    all_evidence_located = False
                    evidence_items.append(
                        EvidenceItem(
                            text=ev_quote,
                            speaker=ev.get("speaker", "Speaker"),
                            timestamp=ev.get("timestamp"),
                            segment_index=None,
                        )
                    )

            # Rule: Mandatory relocation check. If evidence quote cannot be located in local transcript, downgrade!
            if raw_evidence and not all_evidence_located:
                verdict = Verdict.UNVERIFIABLE
                flags.append("evidence_not_found")
                explanation += " [DOWNGRADE: Cited evidence quote could not be verified in local transcript.]"

            # Rule: Deterministic Number Consistency Check (ALWAYS RUNS)
            combined_evidence = " ".join(e.text for e in evidence_items)
            num_consistent, num_err = self.check_number_consistency(rehydrated_text, combined_evidence)
            if not num_consistent and combined_evidence:
                verdict = Verdict.CONTRADICTED
                flags.append("number_mismatch")
                explanation = f"[MANDATORY OVERRIDE] {num_err}"
                review_reasons.append(f"Claim {cid}: {explanation}")

            # Check action item attributes
            owner = item.get("owner")
            deadline = item.get("deadline")
            owner_verified, deadline_verified, o_val, d_val = self.check_action_item_attributes(
                rehydrated_text, transcript
            )
            owner = owner or o_val
            deadline = deadline or d_val

            if claim_type == "action_item":
                if not owner_verified and owner:
                    flags.append("owner_unverified")
                    verdict = Verdict.CONTRADICTED if verdict == Verdict.SUPPORTED else verdict
                    review_reasons.append(f"Action item {cid}: Owner '{owner}' unverified in transcript.")
                if not deadline_verified and deadline:
                    flags.append("deadline_unverified")
                    review_reasons.append(f"Action item {cid}: Deadline '{deadline}' unverified in transcript.")

            if verdict == Verdict.SUPPORTED:
                supported_count += 1
            elif verdict == Verdict.PARTIALLY_SUPPORTED:
                partially_supported_count += 1
            elif verdict == Verdict.CONTRADICTED:
                contradicted_count += 1
            else:
                unverifiable_count += 1

            claims.append(
                ClaimItem(
                    id=cid,
                    text=rehydrated_text,
                    claim_type=claim_type,
                    verdict=verdict,
                    confidence=confidence,
                    explanation=explanation,
                    evidence=evidence_items,
                    evidence_verified=all_evidence_located and len(evidence_items) > 0,
                    method="ai",
                    flags=flags,
                    owner=owner,
                    deadline=deadline,
                    owner_verified=owner_verified,
                    deadline_verified=deadline_verified,
                )
            )

        omissions = self.detect_omissions(summary, transcript)

        overall_status = OverallVerificationStatus.VERIFIED
        if contradicted_count > 0 or any("owner_unverified" in c.flags for c in claims):
            overall_status = OverallVerificationStatus.REVIEW_REQUIRED
        elif unverifiable_count > (len(claims) / 2):
            overall_status = OverallVerificationStatus.FAILED
        elif review_reasons:
            overall_status = OverallVerificationStatus.REVIEW_REQUIRED

        return VerificationResult(
            meeting_id=summary.meeting_id,
            run_id=run_id,
            overall_status=overall_status,
            claims=claims,
            omissions=omissions,
            supported_count=supported_count,
            partially_supported_count=partially_supported_count,
            contradicted_count=contradicted_count,
            unverifiable_count=unverifiable_count,
            review_reasons=review_reasons,
            method="ai",
        )

    def detect_omissions(
        self, summary: MeetingSummary, transcript: MeetingTranscript
    ) -> List[OmissionItem]:
        """Identify key topics, figures, or decisions discussed in transcript but missing from summary."""
        omissions: List[OmissionItem] = []
        summary_text = summary.summary_text.lower()

        # Check for customer concentration or major risk discussion in transcript
        for seg in transcript.segments:
            text_lower = seg.text.lower()
            if "concentration" in text_lower and "concentration" not in summary_text:
                omissions.append(
                    OmissionItem(
                        text="Customer concentration risk discussed in transcript is omitted from summary.",
                        category="risk",
                        evidence=EvidenceItem(
                            text=seg.text,
                            speaker=seg.speaker,
                            timestamp=f"{int(seg.start_time // 60):02d}:{int(seg.start_time % 60):02d}"
                            if seg.start_time is not None
                            else None,
                            segment_index=seg.segment_index,
                        ),
                    )
                )
                break

        return omissions
