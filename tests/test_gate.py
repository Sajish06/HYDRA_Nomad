import pytest
from app.models import (
    Claim, EvidenceItem, Participant, SlotCheck, ClaimType,
    Status, Reason, Stance
)
from app.gate.gate import evaluate_gate

def make_claim(
    claim_id="c1",
    text="Create dedicated Tech and Design teams.",
    actor=None,
    action="create",
    obj="dedicated Tech and Design teams",
    deadline=None
):
    return Claim(
        claim_id=claim_id,
        meeting_id="DEMO_001",
        text=text,
        source="SUMMARY",
        type=ClaimType.DECISION,
        actor=actor,
        action=action,
        object=obj,
        deadline=deadline,
        normalized=text
    )

def test_gate_clean_support():
    claim = make_claim()
    participants = [Participant(name="Lead", role="lead", has_authority=True)]
    evidence = [
        EvidenceItem(idx=0, speaker="Advisor", time="10:12", text="You need separate technical and design divisions.", quote="You need separate technical and design divisions.", stance=Stance.SUGGEST, relation="CONTEXT"),
        EvidenceItem(idx=1, speaker="Lead", time="10:31", text="Let's definitely create dedicated teams for both.", quote="Let's definitely create dedicated teams for both.", stance=Stance.DECIDE, relation="SUPPORTS")
    ]
    slots = [
        SlotCheck(slot="actor", claim_value=None, status="NOT_APPLICABLE"),
        SlotCheck(slot="action", claim_value="create", status="GROUNDED"),
        SlotCheck(slot="object", claim_value="dedicated Tech and Design teams", status="GROUNDED"),
        SlotCheck(slot="deadline", claim_value=None, status="NOT_APPLICABLE")
    ]
    v = evaluate_gate(claim, evidence, participants, slots)
    assert v.status == Status.VERIFIED
    assert v.gate_action == "PROCEED"
    assert Reason.CLEAN_SUPPORT in v.reasons

def test_gate_no_relevant_evidence():
    claim = make_claim()
    v = evaluate_gate(claim, [], [], [])
    assert v.status == Status.UNSUPPORTED
    assert v.gate_action == "BLOCK"
    assert Reason.NO_RELEVANT_EVIDENCE in v.reasons

def test_gate_inform_only():
    claim = make_claim()
    evidence = [
        EvidenceItem(idx=0, speaker="Alice", time="14:05", text="We discussed improving the website.", quote="We discussed improving the website.", stance=Stance.INFORM, relation="CONTEXT"),
        EvidenceItem(idx=1, speaker="Bob", time="14:06", text="Yeah, there are some things we could improve.", quote="Yeah, there are some things we could improve.", stance=Stance.INFORM, relation="CONTEXT")
    ]
    v = evaluate_gate(claim, evidence, [], [])
    assert v.status == Status.UNSUPPORTED
    assert v.gate_action == "BLOCK"
    assert Reason.INFORM_ONLY in v.reasons

def test_gate_proposal_only():
    claim = make_claim()
    evidence = [
        EvidenceItem(idx=0, speaker="Alice", time="10:20", text="We should probably use Redis.", quote="We should probably use Redis.", stance=Stance.PROPOSE, relation="SUPPORTS")
    ]
    slots = [SlotCheck(slot="action", claim_value="create", status="GROUNDED")]
    v = evaluate_gate(claim, evidence, [], slots)
    assert v.status == Status.AMBIGUOUS
    assert v.gate_action == "HUMAN_REVIEW"
    assert Reason.PROPOSAL_ONLY in v.reasons

def test_gate_deferred():
    claim = make_claim(text="Create sponsorship channel.")
    evidence = [
        EvidenceItem(idx=0, speaker="Member", time="10:35", text="Should we create a sponsorship channel?", quote="Should we create a sponsorship channel?", stance=Stance.QUESTION, relation="CONTEXT"),
        EvidenceItem(idx=1, speaker="Lead", time="10:36", text="Let's hold off on sponsorships until next semester.", quote="Let's hold off on sponsorships until next semester.", stance=Stance.DEFER, relation="CONTRADICTS")
    ]
    v = evaluate_gate(claim, evidence, [], [])
    assert v.status == Status.AMBIGUOUS
    assert v.gate_action == "HUMAN_REVIEW"
    assert Reason.DEFERRED in v.reasons

def test_gate_reversal():
    claim = make_claim(text="Use Redis.")
    evidence = [
        EvidenceItem(idx=0, speaker="Alice", time="10:20", text="We should probably use Redis.", quote="We should probably use Redis.", stance=Stance.PROPOSE, relation="SUPPORTS"),
        EvidenceItem(idx=1, speaker="Alice", time="10:22", text="Okay, let's investigate it.", quote="Okay, let's investigate it.", stance=Stance.DECIDE, relation="SUPPORTS"),
        EvidenceItem(idx=2, speaker="Bob", time="10:40", text="Actually, we decided not to use Redis.", quote="Actually, we decided not to use Redis.", stance=Stance.REVERSE, relation="CONTRADICTS")
    ]
    v = evaluate_gate(claim, evidence, [], [])
    assert v.status == Status.AMBIGUOUS
    assert v.gate_action == "HUMAN_REVIEW"
    assert Reason.REVERSED in v.reasons

def test_gate_ungrounded_actor():
    claim = make_claim(actor="Bob")
    evidence = [
        EvidenceItem(idx=0, speaker="Lead", time="10:31", text="Let's definitely create dedicated teams for both.", quote="Let's definitely create dedicated teams for both.", stance=Stance.DECIDE, relation="SUPPORTS")
    ]
    slots = [
        SlotCheck(slot="actor", claim_value="Bob", status="MISSING"),
        SlotCheck(slot="action", claim_value="create", status="GROUNDED")
    ]
    v = evaluate_gate(claim, evidence, [], slots)
    assert v.status == Status.AMBIGUOUS
    assert Reason.UNGROUNDED_ACTOR in v.reasons

def test_gate_ungrounded_deadline():
    claim = make_claim(deadline="Friday")
    evidence = [
        EvidenceItem(idx=0, speaker="Lead", time="10:31", text="Let's definitely create dedicated teams for both.", quote="Let's definitely create dedicated teams for both.", stance=Stance.DECIDE, relation="SUPPORTS")
    ]
    slots = [
        SlotCheck(slot="deadline", claim_value="Friday", status="MISSING"),
        SlotCheck(slot="action", claim_value="create", status="GROUNDED")
    ]
    v = evaluate_gate(claim, evidence, [], slots)
    assert v.status == Status.AMBIGUOUS
    assert Reason.UNGROUNDED_DEADLINE in v.reasons

def test_gate_unresolved_reference():
    claim = make_claim()
    evidence = [
        EvidenceItem(idx=0, speaker="Bob", time="10:31", text="Sure, I'll do it.", quote="Sure, I'll do it.", stance=Stance.ACCEPT, relation="SUPPORTS")
    ]
    slots = [SlotCheck(slot="action", claim_value="create", status="GROUNDED")]
    v = evaluate_gate(claim, evidence, [], slots, flags=[Reason.UNRESOLVED_REFERENCE])
    assert v.status == Status.AMBIGUOUS
    assert Reason.UNRESOLVED_REFERENCE in v.reasons
