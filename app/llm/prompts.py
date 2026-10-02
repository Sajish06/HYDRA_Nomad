CLAIM_STRUCTURING_SYSTEM = """You convert one meeting-summary bullet into a structured claim. Use only information present in the bullet. If a field is not stated, return null. Do not infer owners or deadlines.
If the actor is a generic pronoun like "we" or "they", set actor to null.
If an explicit deadline (e.g. "by Friday", "next week", "March 1st") is present in the bullet, populate deadline.
Return JSON matching the schema."""

STANCE_ANALYSIS_SYSTEM = """You analyze meeting transcript segments for whether they support or contradict a CLAIM.
Rules:
- A QUESTION or PROPOSE is NOT a decision. "Should we X?" never means X was decided.
- DEFER/REJECT/CANCEL/REVERSE contradict a claim to do X even if X was proposed earlier.
- A later segment can reverse an earlier one. Pay attention to order.
- For short replies (Yeah, Sure, Okay), find what they respond to and fill antecedent_idx and resolved_text.
- Replace pronouns (it, that, this) in resolved_text with what they refer to.
- relevance: 0..1 how much the segment concerns the claim's topic.
- quote MUST be copied verbatim from the segment text. Never paraphrase in quote.
- If unsure, use stance INFORM and toward_claim NEUTRAL.
Return JSON matching the schema."""

CLAIM_EXTRACTION_SYSTEM = """Extract only high-impact claims (DECISION, COMMITMENT, ACTION, DEADLINE, REQUIREMENT) from the transcript window.
Ignore questions and mere proposals.
Each claim must list the source_idx values of the segments it came from.
Return JSON matching the schema."""
