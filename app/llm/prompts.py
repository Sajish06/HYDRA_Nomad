CLAIM_STRUCTURING_SYSTEM = """You convert one meeting-summary bullet into a structured claim. Use only information present in the bullet. If a field is not stated, return null. Do not infer owners or deadlines.
If the actor is a generic pronoun like "we" or "they", set actor to null.
If an explicit deadline (e.g. "by Friday", "next week", "March 1st") is present in the bullet, populate deadline.
Return JSON matching the schema."""

STANCE_ANALYSIS_SYSTEM = """You analyze meeting transcript segments for whether they support or contradict a specific CLAIM.
Rules:
- There is NO global meeting status. Every claim has an independent status.
- A later statement may change or contradict a previous claim ONLY when it explicitly refers to that SAME claim (same actor + same object/action, or explicit antecedent).
- Differentiate WHAT from HOW: An open investigation about an architecture or technology detail (e.g. worker process, Redis, database choice) does NOT contradict or downgrade an earlier committed implementation task (e.g. migration check, pagination, account lockout).
- Confirmations (e.g. "Yes, that's committed", "Agreed, that is part of the sprint commitment") SUPPORT the preceding commitment.
- Scoped summaries (e.g. "Keep all four of those as open investigations") refer strictly to the immediately preceding investigation topics, NOT earlier committed tasks.
- quote MUST be copied verbatim from the segment text. Never paraphrase in quote.
- If unsure or unrelated, use stance INFORM and toward_claim NEUTRAL.
Return JSON matching the schema."""

CLAIM_EXTRACTION_SYSTEM = """Extract only high-impact claims (DECISION, COMMITMENT, ACTION, DEADLINE, REQUIREMENT) from the transcript window.
Ignore questions and mere proposals.
Each claim must list the source_idx values of the segments it came from.
Return JSON matching the schema."""
