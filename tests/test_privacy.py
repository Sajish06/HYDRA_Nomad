"""Tests for privacy detectors, Luhn card verification, stable tokenization, and Vault."""

from backend.processors.privacy import (
    PrivacyEngine,
    Vault,
    luhn_checksum_valid,
)
from backend.schemas.policy import DealConfig


def test_luhn_validation():
    # Valid Visa card example (synthetic test card)
    valid_visa = "4532015112830366"
    assert luhn_checksum_valid(valid_visa) is True

    # Invalid card number (fails Luhn)
    invalid_card = "4532015112830367"
    assert luhn_checksum_valid(invalid_card) is False

    # Short number
    assert luhn_checksum_valid("12345") is False


def test_detectors_coverage():
    deal_config = DealConfig(
        target_name="Northwind Analytics",
        known_people=["Priya Sharma", "David Vance"],
        known_orgs=["Acme Capital"],
    )
    engine = PrivacyEngine(deal_config=deal_config)

    text = (
        "Contact Priya Sharma at priya@northwind.io or 415-555-2671. "
        "SSN is 000-12-3456. API key: sk-abcdef1234567890abcdef123456. "
        "Paid $15,000 on Friday for 15% discount from Acme Capital."
    )

    detected = engine.detect_entities(text)
    categories = {d.category for d in detected}

    assert "PERSON" in categories
    assert "EMAIL" in categories
    assert "PHONE" in categories
    assert "NATIONAL_ID" in categories
    assert "API_KEY" in categories
    assert "AMOUNT" in categories
    assert "DATE" in categories
    assert "PERCENT" in categories
    assert "ORGANIZATION" in categories


def test_stable_session_tokens():
    deal_config = DealConfig(known_people=["David Vance"])
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)

    text1 = "David Vance arrived first."
    text2 = "Then David Vance spoke with outside counsel."

    m1 = vault.tokenize(text1)
    m2 = vault.tokenize(text2)

    # The same entity must yield the identical token [PERSON_1]
    assert "[PERSON_1]" in m1.text
    assert "[PERSON_1]" in m2.text


def test_overlapping_spans_longest_wins():
    deal_config = DealConfig(
        target_name="Northwind Analytics",
        known_orgs=["Northwind"],
    )
    engine = PrivacyEngine(deal_config=deal_config)

    # "Northwind Analytics" should be chosen over just "Northwind"
    text = "The target is Northwind Analytics."
    detected = engine.detect_entities(text)
    matching = [d for d in detected if "Northwind" in d.text]

    assert len(matching) == 1
    assert matching[0].text == "Northwind Analytics"
    assert matching[0].category == "TARGET_NAME"


def test_financial_figures_not_masked_by_default_for_ai():
    deal_config = DealConfig(known_people=["Sarah Chen"])
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)

    text = "Sarah Chen confirmed EBITDA was $4.2M and margin was 25%."
    # Default cloud tokenization masks PERSON and sensitive PII, but preserves AMOUNT and PERCENT for analysis
    masked = vault.tokenize(text)

    assert "[PERSON_1]" in masked.text
    assert "$4.2M" in masked.text
    assert "25%" in masked.text


def test_rehydrate_round_trip():
    deal_config = DealConfig(known_people=["Priya Sharma"])
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)

    original = "Priya Sharma will deliver the report to priya@northwind.io."
    masked = vault.tokenize(original)

    assert "Priya Sharma" not in masked.text
    assert "priya@northwind.io" not in masked.text

    rehydrated = vault.rehydrate(masked.text)
    assert rehydrated == original


def test_coverage_report():
    deal_config = DealConfig(known_people=["David Vance"])
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)

    vault.tokenize("David Vance sent an email to test@domain.com")
    report = vault.get_coverage_report()

    assert report.total_tokens_created >= 2
    assert "PERSON" in report.detected_counts
    assert "EMAIL" in report.detected_counts
    assert "not complete anonymization" in report.notice
