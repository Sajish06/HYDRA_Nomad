"""Post-generation leak scanner validating audience output isolation and canaries."""

import re
from pathlib import Path
from typing import Dict, List, Optional

from backend.processors.privacy import Vault
from backend.schemas.policy import DealConfig
from backend.schemas.release import (
    AudienceLeakReport,
    LeakFinding,
    OverallLeakReport,
)


class LeakScanner:
    """Scans distributed artifacts to detect unauthorized entity leaks and verify canary isolation."""

    CANARY_NAME = "Zephyrine Quillfeather"

    def __init__(self, vault: Vault, deal_config: Optional[DealConfig] = None):
        self.vault = vault
        self.deal_config = deal_config or DealConfig()

    def scan_text(self, text: str, audience: str) -> AudienceLeakReport:
        """Scan a single audience document for policy violations and canary containment."""
        findings: List[LeakFinding] = []
        canary_found = self.CANARY_NAME.lower() in text.lower()

        # Canary isolation check:
        # Canary is allowed ONLY in 'deal_team'. If found in any other audience, it is a leak!
        if audience != "deal_team" and canary_found:
            findings.append(
                LeakFinding(
                    sensitive_value=self.CANARY_NAME,
                    category="CANARY",
                    location_index=text.lower().find(self.CANARY_NAME.lower()),
                    rule_violated=f"Canary entity leaked into unauthorized audience: {audience}",
                )
            )

        # Policy-specific checks:
        if audience in ("outside_counsel", "lender", "cloud_llm"):
            # No real person names should appear in these outputs
            for person in self.deal_config.known_people:
                pat = r"\b" + re.escape(person) + r"\b"
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    findings.append(
                        LeakFinding(
                            sensitive_value=person,
                            category="PERSON",
                            location_index=m.start(),
                            rule_violated=f"Real person identity '{person}' leaked in {audience} output",
                        )
                    )

        if audience in ("lender", "cloud_llm"):
            # Target company name must not appear (should be codename or token)
            target = self.deal_config.target_name
            if target:
                pat = r"\b" + re.escape(target) + r"\b"
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    findings.append(
                        LeakFinding(
                            sensitive_value=target,
                            category="TARGET_NAME",
                            location_index=m.start(),
                            rule_violated=f"Real target name '{target}' leaked in {audience} output",
                        )
                    )

        if audience == "board":
            # Exact numbers should have been converted to ranges
            # If "$4.2M" or "$15,000" is found instead of a range, flag as finding
            exact_num_match = re.search(r"\$4\.2M|\$15,000", text)
            if exact_num_match:
                findings.append(
                    LeakFinding(
                        sensitive_value=exact_num_match.group(),
                        category="AMOUNT",
                        location_index=exact_num_match.start(),
                        rule_violated=f"Exact amount '{exact_num_match.group()}' was not converted to range for board",
                    )
                )

        status = "fail" if findings else "pass"
        return AudienceLeakReport(
            audience=audience,
            status=status,
            findings=findings,
            canary_found=canary_found,
            quarantined=False,
        )

    def scan_output_artifacts(
        self, meeting_id: str, run_id: str, artifact_paths: Dict[str, str]
    ) -> OverallLeakReport:
        """Scan all generated output files on disk and quarantine any leaking files."""
        reports: List[AudienceLeakReport] = []
        all_passed = True

        for aud, file_path_str in artifact_paths.items():
            path = Path(file_path_str)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")
            rep = self.scan_text(content, aud)

            if rep.status == "fail":
                all_passed = False
                rep.quarantined = True
                # Quarantine leaking output
                quarantine_path = path.with_suffix(".quarantined")
                path.rename(quarantine_path)

            reports.append(rep)

        return OverallLeakReport(
            meeting_id=meeting_id,
            run_id=run_id,
            all_passed=all_passed,
            audience_reports=reports,
        )
