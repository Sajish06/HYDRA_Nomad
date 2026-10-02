"""Tests for guarded LLM provider privacy enforcement and egress logging."""

import pytest

from backend.ai.fake_provider import FakeProvider
from backend.ai.guarded import GuardedLLMProvider, PrivacyGateError
from backend.processors.privacy import PrivacyEngine, Vault
from backend.schemas.policy import DealConfig


@pytest.fixture
def guarded_setup(tmp_path):
    deal_config = DealConfig(
        target_name="Northwind Analytics",
        known_people=["Sarah Chen"],
    )
    engine = PrivacyEngine(deal_config=deal_config)
    vault = Vault(engine=engine)
    provider = FakeProvider(mode="good")
    guarded = GuardedLLMProvider(
        provider=provider,
        vault=vault,
        meeting_id="test_egress_meeting",
        egress_dir=tmp_path / "outputs",
    )
    return guarded, vault


@pytest.mark.asyncio
async def test_unmasked_email_aborts_ai_call(guarded_setup):
    guarded, _ = guarded_setup
    unmasked_text = "Please reach out to sarah.chen@northwind.io to confirm the numbers."

    with pytest.raises(PrivacyGateError) as exc_info:
        await guarded.verify_claims(masked_transcript=unmasked_text, masked_summary="Valid summary")

    assert "Unmasked email detected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_unmasked_vault_sensitive_value_aborts_ai_call(guarded_setup):
    guarded, vault = guarded_setup
    # Tokenize first to register Sarah Chen in vault
    vault.tokenize("Sarah Chen is CFO.")

    # Try sending raw "Sarah Chen" to external AI
    leaky_transcript = "In this meeting Sarah Chen presented the financials."

    with pytest.raises(PrivacyGateError) as exc_info:
        await guarded.verify_claims(masked_transcript=leaky_transcript, masked_summary="Summary")

    assert "Raw sensitive value 'Sarah Chen' detected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_masked_payload_passes_and_logs_egress(guarded_setup, tmp_path):
    guarded, vault = guarded_setup
    raw_text = "Sarah Chen presented EBITDA of $4.2M."
    masked = vault.tokenize(raw_text)

    # Call guarded provider with tokenized text
    res = await guarded.verify_claims(
        masked_transcript=masked.text,
        masked_summary="[PERSON_1] presented EBITDA of $4.2M.",
    )
    assert len(res) >= 1

    # Check egress log
    log_file = guarded.egress_log_file
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Sarah Chen" not in content
    assert "[PERSON_1]" in content
    assert '"bytes_sent":' in content
