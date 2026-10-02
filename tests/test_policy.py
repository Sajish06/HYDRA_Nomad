"""Tests for audience masking policies, range conversions, and citations masking."""

import pytest

from backend.processors.policy import PolicyEngine, amount_to_range
from backend.processors.privacy import PrivacyEngine, Vault
from backend.schemas.policy import DealConfig
from backend.schemas.verification import ClaimItem, EvidenceItem


@pytest.fixture
def test_setup():
    deal_config = DealConfig(
        target_name="Northwind Analytics",
        target_codename="Project Falcon",
        known_people=["Sarah Chen", "Priya Sharma"],
        known_roles={"Sarah Chen": "Chief Financial Officer"},
    )
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)
    policy_engine = PolicyEngine(deal_config=deal_config)
    return policy_engine, vault


def test_amount_to_range_conversions():
    assert amount_to_range("$4.2M") == "$4M-$5M"
    assert amount_to_range("$4,200,000") == "$4M-$5M"
    assert amount_to_range("4.2 million") == "$4M-$5M"
    assert amount_to_range("$15,000") == "$10,000-$20,000"


def test_deal_team_profile_keeps_all(test_setup):
    policy, vault = test_setup
    text = "Sarah Chen confirmed Northwind Analytics generated $4.2M EBITDA."
    masked, _ = policy.mask_text(text, "deal_team", vault)
    assert masked == text


def test_outside_counsel_profile_masks_people_keeps_amounts(test_setup):
    policy, vault = test_setup
    text = "Sarah Chen confirmed Northwind Analytics generated $4.2M EBITDA."
    masked, _ = policy.mask_text(text, "outside_counsel", vault)
    assert "Sarah Chen" not in masked
    assert "[PERSON_" in masked
    assert "Northwind Analytics" in masked
    assert "$4.2M" in masked


def test_lender_profile_replaces_target_with_codename(test_setup):
    policy, vault = test_setup
    text = "Sarah Chen confirmed Northwind Analytics generated $4.2M EBITDA."
    masked, _ = policy.mask_text(text, "lender", vault)
    assert "Northwind Analytics" not in masked
    assert "Project Falcon" in masked
    assert "Sarah Chen" not in masked
    assert "$4.2M" in masked


def test_board_profile_converts_roles_and_ranges(test_setup):
    policy, vault = test_setup
    text = "Sarah Chen reported $4.2M EBITDA and $15,000 expense."
    masked, _ = policy.mask_text(text, "board", vault)
    assert "Sarah Chen" not in masked
    assert "Chief Financial Officer" in masked
    assert "$4M-$5M" in masked
    assert "$10,000-$20,000" in masked


def test_masking_diff_spans(test_setup):
    policy, vault = test_setup
    text = "Contact Sarah Chen."
    diff_resp = policy.diff(text, "outside_counsel", vault)
    assert diff_resp.audience == "outside_counsel"
    assert len(diff_resp.diff_spans) == 1
    span = diff_resp.diff_spans[0]
    assert span.original == "Sarah Chen"
    assert span.category == "PERSON"
    assert span.action == "token"


def test_citations_masked_in_claims(test_setup):
    policy, vault = test_setup
    claim = ClaimItem(
        id="c1",
        text="Sarah Chen approved $15,000.",
        evidence=[
            EvidenceItem(
                text="Sarah Chen: I approve the fifteen thousand dollars.",
                speaker="Sarah Chen",
                timestamp="00:04:12",
            )
        ],
    )
    transformed_list = policy.apply_to_claims([claim], "lender", vault)
    transformed = transformed_list[0]

    assert "Sarah Chen" not in transformed.text
    assert "Sarah Chen" not in transformed.evidence[0].text
    assert "Sarah Chen" not in transformed.evidence[0].speaker
    assert "[PERSON_" in transformed.evidence[0].speaker
