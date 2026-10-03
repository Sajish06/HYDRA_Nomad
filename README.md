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

## 🤖 Nomad Closed-Loop Autonomous Builder (Antigravity Integration)

Nomad integrates with external autonomous coding agents (Google Antigravity / "AGY") via the **Model Context Protocol (MCP)** over stdio.

```text
verified + masked JSON
        |
        v
 Ollama / Fallback compiles a STRUCTURED PROMPT from masked tasks
        |
        v
 Nomad MCP server (stdio)  <---- AGY pulls brief: cleanroom_get_masked_brief
        |                           AGY builds deliverables in: Desktop\test\<slug>\
        |                           AGY reports: cleanroom_submit_code_report
        v
 Nomad evaluates locally (re-runs acceptance tests in isolated subprocess)
        |
        +-- passed ---------------> HMAC ledger entry, done
        +-- needs revision -------> re-masked feedback returned to AGY (iteration 2, then 3)
        +-- still failing after 3 -> stop, failed_max_iterations, ledger entry
```

### Quickstart: Running the Closed-Loop Demo (PowerShell)

Run the autonomous build demo with synthetic fake AGY behaviors:

```powershell
# Multi-turn revision demo: agent fails iteration 1, gets masked feedback, passes iteration 2
python scripts/run_closed_loop_demo.py --behavior fix_on_second

# Single-turn pass
python scripts/run_closed_loop_demo.py --behavior good

# Hard iteration cap: stops at iteration 3
python scripts/run_closed_loop_demo.py --behavior never_passes

# Real Desktop mode (writes to Desktop\test)
python scripts/run_closed_loop_demo.py --behavior fix_on_second --use-real-desktop
```

### Running Closed-Loop Automated Tests

```powershell
# Unit test suite (Task selection, compiler, criteria catalog, evaluator, vault, ledger)
pytest tests/test_closed_loop_unit.py -v

# Mock Ollama HTTP API server tests
pytest tests/test_ollama_mock.py -v

# Real MCP server stdio protocol & stdout hygiene test
pytest tests/test_mcp_protocol.py -v

# All 8 fake AGY behaviors (good, fix_on_second, never_passes, lies, tamper, escape, leaky, abandon)
pytest tests/test_fake_agy_behaviors.py -v
```

### Antigravity Registration & Workspace Utilities

```powershell
# Check registration in ~/.gemini/config/mcp_config.json and detect schema drift
python scripts/check_agy_registration.py

# Apply MCP registration with automated backup and diff preview
python scripts/check_agy_registration.py --apply

# Safely clean temporary test workspaces in Desktop\test
python scripts/clean_workspace.py --all-test-runs
```

### Environment Configuration

The following environment variables configure the closed loop (see `.env.example`):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ENABLE_OLLAMA` | `false` | Enable local Ollama LLM for prompt compilation. If false or unavailable, uses deterministic fallback. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama HTTP API endpoint. |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name to use for prompt compilation. |
| `AGY_WORKSPACE_ROOT`| `<Desktop>\test` | Root directory where AGY workspaces are created. |
| `MAX_ITERATIONS` | `3` | Maximum loop iterations before failing closed (hard-capped at 3). |
| `NOMAD_VAULT_KEY` | Derived | 32-byte urlsafe base64 key for Fernet vault encryption at rest. |
| `NOMAD_LEDGER_KEY` | None | HMAC key for signing AuditLedger entries. |
| `PERSIST_TOKEN_MAP` | `false` | Retain encrypted token map files after terminal loop verdicts (for debugging). |

### Documentation References

- [`docs/STATUS.md`](file:///c:/Users/DELL/Desktop/ASCENT'26/docs/STATUS.md): System audit, component inventory, and verification results.
- [`docs/ARCHITECTURE.md`](file:///c:/Users/DELL/Desktop/ASCENT'26/docs/ARCHITECTURE.md): Architectural design, security boundaries, and encrypted vault tradeoffs.
- [`docs/CLOSED_LOOP.md`](file:///c:/Users/DELL/Desktop/ASCENT'26/docs/CLOSED_LOOP.md): Complete MCP tool contracts with sample JSON requests/responses.
- [`docs/AGY_MANUAL_TEST.md`](file:///c:/Users/DELL/Desktop/ASCENT'26/docs/AGY_MANUAL_TEST.md): Step-by-step instructions for testing with the real Google Antigravity agent.
