"""Tests for distribution fan-out and leak scanning with canary verification."""

from pathlib import Path

import pytest

from backend.processors.distribution import DistributionEngine
from backend.processors.leakscan import LeakScanner
from backend.processors.policy import PolicyEngine
from backend.processors.privacy import PrivacyEngine, Vault
from backend.schemas.meeting import MeetingSummary
from backend.schemas.policy import DealConfig
from backend.schemas.verification import ClaimItem, EvidenceItem, Verdict


@pytest.fixture
def distribution_setup(tmp_path):
    deal_config = DealConfig(
        target_name="Northwind Analytics",
        target_codename="Project Falcon",
        known_people=["Sarah Chen", "Zephyrine Quillfeather"],
        known_roles={"Sarah Chen": "Chief Financial Officer"},
    )
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)
    policy = PolicyEngine(deal_config=deal_config)
    dist = DistributionEngine(
        policy_engine=policy,
        vault=vault,
        output_base_dir=tmp_path / "outputs",
    )
    scanner = LeakScanner(vault=vault, deal_config=deal_config)
    return dist, scanner, vault, tmp_path


@pytest.mark.asyncio
async def test_distribution_and_canary_isolation(distribution_setup):
    dist, scanner, vault, tmp_path = distribution_setup

    # Canary included in summary/claim
    summary = MeetingSummary(
        meeting_id="m_canary_test",
        summary_text="Sarah Chen and advisor Zephyrine Quillfeather discussed Northwind Analytics revenue of $4.2M.",
        action_items=["Zephyrine Quillfeather to review audit."],
    )
    claims = [
        ClaimItem(
            id="c1",
            text="Zephyrine Quillfeather attended diligence with Sarah Chen.",
            verdict=Verdict.SUPPORTED,
            evidence=[
                EvidenceItem(
                    text="Zephyrine Quillfeather: I approve the schedule.",
                    speaker="Zephyrine Quillfeather",
                )
            ],
        )
    ]

    produced = await dist.distribute("m_canary_test", summary, claims)
    assert len(produced) == 5
    assert "deal_team" in produced
    assert "lender" in produced
    assert "board" in produced
    assert "outside_counsel" in produced

    # Run leak scan across outputs
    scan_report = scanner.scan_output_artifacts("m_canary_test", "run_dist", produced)
    assert scan_report.all_passed is True

    # 1. Verify Canary in deal_team
    dt_content = Path(produced["deal_team"]).read_text(encoding="utf-8")
    assert "Zephyrine Quillfeather" in dt_content
    assert "Sarah Chen" in dt_content
    assert "Northwind Analytics" in dt_content

    # 2. Verify Canary NOT in any other audience
    for aud in ("outside_counsel", "lender", "board", "cloud_llm"):
        content = Path(produced[aud]).read_text(encoding="utf-8")
        assert "Zephyrine Quillfeather" not in content

    # 3. Verify lender has codename instead of real target
    lender_content = Path(produced["lender"]).read_text(encoding="utf-8")
    assert "Project Falcon" in lender_content
    assert "Northwind Analytics" not in lender_content
    assert "Sarah Chen" not in lender_content


def test_leak_scanner_catches_and_quarantines_leak(distribution_setup):
    _, scanner, _, tmp_path = distribution_setup

    leak_dir = tmp_path / "leaky_meeting"
    leak_dir.mkdir(parents=True, exist_ok=True)
    leaky_file = leak_dir / "lender.md"
    # Unmasked target name and unmasked person in lender output!
    leaky_file.write_text(
        "# Lender Report\nNorthwind Analytics generated $4.2M. Sarah Chen was present.",
        encoding="utf-8",
    )

    report = scanner.scan_output_artifacts(
        "leaky_meeting", "run_leak", {"lender": str(leaky_file)}
    )

    assert report.all_passed is False
    rep = report.audience_reports[0]
    assert rep.status == "fail"
    assert len(rep.findings) >= 2
    assert rep.quarantined is True
    # Verify file was quarantined
    assert not leaky_file.exists()
    assert (leak_dir / "lender.quarantined").exists()
