# 🛡️ ReqCopilot Proof — Deterministic Local Claim Verification Engine

> **Catching AI meeting summary hallucinations with deterministic, quote-grounded conversational evidence.**

ReqCopilot Proof takes claims extracted from meeting summaries or transcripts (decisions, tasks, requirements, deadlines), searches the raw audio transcript for supporting and contradicting evidence, resolves context and pronouns, checks slot grounding, and lets the claim proceed only if conversational evidence strictly supports it.

---

## 🔑 Core Architectural Principles

1. **Fully Local & Private:** Runs 100% on your machine with Ollama, SQLite FTS5, and SentenceTransformers.
2. **Deterministic Gate:** The LLM never makes the final verdict (`VERIFIED` / `AMBIGUOUS` / `UNSUPPORTED`). A pure-Python state machine decides.
3. **Exact Quote Grounding:** Every displayed quote is verified as a true substring of the raw transcript segment.
4. **Latest Stance Wins:** State machine over ordered evidence handles reversals cleanly (e.g. *"Actually, we decided not to use Redis"*).
5. **Slot Grounding:** Owner, action, object, and deadline are individually validated.
6. **Verify → Minimize → Act:** Verifies on local raw transcript before handing off minimal masked briefs to downstream agents.

---

## 🏗️ Repository Layout

```
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── mock/                      # Fixture meetings (DEMO_001 to DEMO_005)
│   ├── llm_cache/                 # SHA-256 cached LLM responses
│   ├── indexes/                   # FAISS index files
│   └── proof.db                   # SQLite database
├── app/
│   ├── main.py                    # FastAPI application entrypoint
│   ├── config.py                  # Pydantic settings & env config
│   ├── models.py                  # Canonical data models & enums
│   ├── db.py                      # SQLite connection, schema & trace helpers
│   ├── adapters/
│   │   ├── base.py                # MeetingAdapter protocol
│   │   ├── mock_adapter.py        # Mock JSON loader
│   │   └── meetily_adapter.py     # Meetily Automation API adapter
│   ├── ingest/
│   │   ├── loader.py              # Ingest to SQLite & FTS5
│   │   └── indexer.py             # Vector embeddings & FAISS indexer
│   ├── claims/
│   │   ├── from_summary.py        # Summary bullet intake & structuring
│   │   └── from_transcript.py     # Sliding-window transcript extraction
│   ├── retrieval/
│   │   ├── hybrid.py              # Semantic (FAISS) + Lexical (FTS5) + RRF + Tail Scan
│   │   └── embeddings.py          # SentenceTransformers wrapper
│   ├── analysis/
│   │   ├── cues.py                # Regex rule-based cue detector
│   │   ├── stance.py              # Stance analysis, cue merge & quote validator
│   │   ├── context.py             # Antecedent & pronoun resolution
│   │   ├── chain.py               # Evidence chain builder
│   │   └── slots.py               # Actor, action, object, deadline slot grounder
│   ├── gate/
│   │   └── gate.py                # Deterministic verification gate
│   ├── llm/
│   │   ├── client.py              # Ollama client with retry, schema validation & disk cache
│   │   └── prompts.py             # System & user prompt templates
│   ├── api/
│   │   ├── routes_meetings.py     # Meeting indexing & task handoff routes
│   │   ├── routes_claims.py       # Claim verification, evidence & confirmation
│   │   └── routes_demo.py         # One-shot demo endpoints & health check
│   └── masking/
│       └── stub.py                # Stub data-masking module & brief generator
├── ui/
│   └── app.py                     # Streamlit evidence-card UI
├── scripts/
│   ├── warm_cache.py              # Pre-populates LLM cache for offline demo
│   └── eval.py                    # Acceptance evaluation test runner
└── tests/
    ├── test_cues.py               # Rule-based stance cue tests
    ├── test_gate.py               # Table-driven gate decision tests
    ├── test_chain_quotes.py       # Exact quote grounding tests
    ├── test_retrieval.py          # Hybrid retrieval & tail scan tests
    ├── test_fixtures_e2e.py       # Acceptance suite on 5 fixture meetings
    └── test_handoff.py            # Handoff fail-closed security tests
```

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
```bash
cp .env.example .env
```

### 3. Run FastAPI Backend
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive API docs will be available at `http://localhost:8000/docs`.

### 4. Run Streamlit UI
```bash
streamlit run ui/app.py
```
Open `http://localhost:8501` in your browser.

---

## 🧪 Running the Acceptance Tests

```bash
pytest tests/ -v
```
Or run the evaluation runner:
```bash
python scripts/eval.py
```

### Acceptance Fixture Results:
1. `mock_meeting_01_verified.json` → `VERIFIED` (`CLEAN_SUPPORT`, `PROCEED`)
2. `mock_meeting_02_ambiguous.json` → `AMBIGUOUS` (`DEFERRED`, `HUMAN_REVIEW`)
3. `mock_meeting_03_implicit.json` → `VERIFIED` (`resolved_claim` generated, actor grounded)
4. `mock_meeting_04_unsupported.json` → `UNSUPPORTED` (`INFORM_ONLY`, `BLOCK`)
5. `mock_meeting_05_reversal.json` → `AMBIGUOUS` (`REVERSED`, `HUMAN_REVIEW`)

---

## 🛡️ Handoff & Data Masking Contract

ReqCopilot Proof guarantees that unverified claims **fail closed**:
- Calling `/claims/{id}/handoff` on an `AMBIGUOUS` or `UNSUPPORTED` claim returns `409 Conflict (NOT_RELEASED)`.
- Only `VERIFIED` or `USER_CONFIRMED` tasks are released to the masking and cloud execution stages.
- The handoff payload provides `grounding_segments` as a pre-computed minimal context set.
