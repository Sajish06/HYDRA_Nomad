"""Cross-source discrepancy detector comparing meeting transcripts against diligence documents."""

import re
from typing import Dict, List, Optional, Tuple

from backend.processors.number_normalizer import (
    extract_numbers_from_text,
    numbers_compare_equal,
)
from backend.schemas.meeting import MeetingTranscript
from backend.schemas.release import CrossSourceConflict
from backend.sources.base import DocumentSource
from backend.sources.local_folder import LocalFolderSource


class CrossCheckEngine:
    """Detects discrepancies between spoken meeting claims and diligence documents (e.g. CIM)."""

    def __init__(self, doc_source: Optional[DocumentSource] = None):
        self.doc_source = doc_source or LocalFolderSource()

    def _extract_metric_from_text(self, text: str) -> List[Tuple[str, str, float, Optional[str]]]:
        """Extract (metric_name, raw_string, parsed_numeric, period) from text."""
        results = []
        metrics = ["EBITDA", "Revenue", "Valuation"]

        # 1. Identify period if present
        period = None
        period_match = re.search(r"\b(FY\s*\d{2,4}|202[0-9]|TTM|Q[1-4])\b", text, re.IGNORECASE)
        if period_match:
            period = period_match.group(1).upper()

        # Clean period string from text so years/quarters don't get parsed as financial values
        clean_text = re.sub(
            r"\(?\b(?:FY\s*\d{2,4}|202[0-9]|TTM|Q[1-4])\b\)?", "", text, flags=re.IGNORECASE
        )

        for metric in metrics:
            if re.search(r"\b" + metric + r"\b", clean_text, re.IGNORECASE):
                # Extract numbers from this sentence/line
                nums = extract_numbers_from_text(clean_text)
                for raw_val, num_val in nums:
                    results.append((metric, raw_val, num_val, period))

        return results

    def cross_check(self, transcript: MeetingTranscript) -> List[CrossSourceConflict]:
        """Compare transcript metrics with documents in the diligence folder."""
        conflicts: List[CrossSourceConflict] = []
        doc_names = self.doc_source.list_documents()

        # 1. Extract transcript metrics with citations
        transcript_metrics: Dict[str, List[Tuple[str, float, str, Optional[str]]]] = {}
        for seg in transcript.segments:
            extracted = self._extract_metric_from_text(seg.text)
            ts = (
                f"{int(seg.start_time // 60):02d}:{int(seg.start_time % 60):02d}"
                if seg.start_time is not None
                else "00:00"
            )
            citation = f"transcript@{ts} ({seg.speaker})"
            for metric, raw, num, period in extracted:
                if metric not in transcript_metrics:
                    transcript_metrics[metric] = []
                transcript_metrics[metric].append((raw, num, citation, period))

        # 2. Extract metrics from external documents
        conflict_idx = 1
        for doc_name in doc_names:
            try:
                lines = self.doc_source.get_document_lines(doc_name)
            except Exception:
                continue

            for line_no, line_content in lines:
                doc_extracted = self._extract_metric_from_text(line_content)
                for metric, doc_raw, doc_num, doc_period in doc_extracted:
                    # Check if transcript discussed this metric
                    if metric in transcript_metrics:
                        for tr_raw, tr_num, tr_citation, tr_period in transcript_metrics[metric]:
                            # Compare numbers
                            if not numbers_compare_equal(tr_num, doc_num, tolerance=0.01):
                                conflict_id = f"conf_{conflict_idx}"
                                conflict_idx += 1
                                explanation = (
                                    f"Material discrepancy on {metric}: Transcript asserts {tr_raw} ({tr_num:,.0f}), "
                                    f"whereas diligence document '{doc_name}' states {doc_raw} ({doc_num:,.0f})."
                                )
                                conflicts.append(
                                    CrossSourceConflict(
                                        id=conflict_id,
                                        metric=metric,
                                        period=doc_period or tr_period,
                                        transcript_value=tr_raw,
                                        transcript_citation=tr_citation,
                                        doc_name=doc_name,
                                        doc_value=doc_raw,
                                        doc_citation=f"{doc_name}:line {line_no}",
                                        severity="high",
                                        explanation=explanation,
                                    )
                                )

        return conflicts
