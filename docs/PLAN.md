# Meetily Clean Room - Implementation Plan

## 1. Project Overview
"Meetily Clean Room" is a verification, masking, and distribution gatekeeper for meeting intelligence in M&A due diligence. It ensures:
1. **Summary Verification**: Every claim, action item, and figure is verified against the meeting transcript using spoken-number normalization and local evidence re-location.
2. **Audience-Specific Masking & Leak Defense**: Sensitive data is tokenized/masked before any external AI exposure or audience distribution (`deal_team`, `outside_counsel`, `lender`, `board`, `cloud_llm`).
3. **Cross-Source Contradiction Checks**: Flags discrepancies between meeting statements and diligence documents (e.g. CIM).
4. **Human Review & Non-Linear Gate**: Holds releases when contradictions or unverified claims arise, enabling correction/approval loops and hash-chained audit ledgers.

---

## 2. Implementation Stages & Exit Criteria

### Stage 1: Foundation & Base Infrastructure
- Project scaffolding (`backend/`, `data/`, `docs/`, `scripts/`, `tests/`, `configs/`).
- `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, `LICENSE`.
- Configuration system with `pydantic-settings` (`backend/config.py`).
- Structured logging without transcript or token leakage (`backend/logging.py`).
- Storage engine (`backend/storage/database.py`, `models.py`, `repository.py`) using SQLite and threadpool execution.
- Core Pydantic schemas (`backend/schemas/`).
- FastAPI initialization (`backend/main.py`).
- **Exit Criteria**: App imports cleanly; pytest runs and collects test suite.

### Stage 2: Meetily Client & Schema Adapter
- HTTPX async client with robust timeout, retries, and custom exception hierarchy (`backend/meetily/client.py`, `errors.py`).
- Schema adapter isolating all external Meetily API response structures (`backend/meetily/schema_adapter.py`).
- Documented API assumptions in `docs/meetily_api_assumptions.md`.
- Helper scripts: `scripts/check_meetily_connection.py`, `scripts/fetch_meeting.py`, `scripts/discover_api.py`.
- **Exit Criteria**: `tests/test_meetily_client.py` passes using mocked responses (`respx`).

### Stage 3: Privacy Engine & Audience Policies
- Privacy detectors (regex + heuristics + known entities fallback for PERSON, ORG, EMAIL, PHONE, CARD with Luhn validation, API_KEY, NATIONAL_ID, AMOUNT, PERCENT, DATE).
- In-memory `Vault` maintaining stable session tokens, rehydration, and sensitive value indexing for leak scans.
- Policy engine with declarative profiles (`configs/audience_profiles.yaml`, `configs/deal.yaml`).
- Masking diff utility and coverage report.
- **Exit Criteria**: `tests/test_privacy.py` and `tests/test_policy.py` pass.

### Stage 4: AI Boundary, Verification & Business Extraction
- `LLMProvider` interface and `GuardedLLMProvider` privacy gate with hard abort on sensitive data leaks, plus egress logger.
- Deterministic `FakeProvider` and official `google.genai` SDK provider (`gemini_provider.py`).
- Claim splitting and verification engine (`processors/verification.py`):
  - Spoken-number normalization and deterministic figure matching.
  - Action item owner and deadline verification.
  - Local evidence quote re-location check (downgrading unlocated claims to `unverifiable`).
  - Omission detection.
- M&A business intelligence extraction (`processors/extraction.py`).
- **Exit Criteria**: `tests/test_verification.py`, `tests/test_extraction.py`, and `tests/test_guarded_ai.py` pass.

### Stage 5: Gatekeeper, Review Loop, Leak Scan, Crosscheck & Ledger
- Diligence document source abstraction (`sources/base.py`, `sources/local_folder.py`).
- Cross-source check (`processors/crosscheck.py`) comparing transcript metrics against CIM/Term Sheet.
- Gatekeeper release decision engine (`processors/gate.py`).
- Review loop state machine for approve/correct/reject (`api/review.py`).
- Distribution fan-out (`processors/distribution.py`) writing audience markdown and JSON.
- Leak scanner (`processors/leakscan.py`) validating all outputs and canary isolation.
- Hash-chained audit ledger (`processors/ledger.py`).
- **Exit Criteria**: Tests for gate, review, leak scan, crosscheck, and ledger pass.

### Stage 6: Pipeline Orchestration, Webhooks & REST API
- Pipeline orchestrator (`processors/pipeline.py`) with retry and transactional stages.
- Webhook receiver (`POST /api/webhooks/meetily`) with HMAC signature verification, deduplication, and background execution.
- Webhook registration script (`scripts/register_webhook.py`).
- Complete REST endpoints matching spec.
- **Exit Criteria**: Pipeline, webhook, and API test suites pass.

### Stage 7: Demo Suite & MCP Server
- Synthetic M&A dataset in `data/demo/` (transcript with canary, flawed summary, CIM, term sheet).
- Offline interactive demo script (`scripts/run_demo.py`).
- Static, zero-dependency HTML/CSS/JS dashboard (`backend/static/demo.html`).
- FastModelContextProtocol (MCP) server (`backend/mcp_server/server.py`).
- **Exit Criteria**: `python scripts/run_demo.py` executes successfully offline; static dashboard works; MCP unit tests pass.

### Stage 8: Documentation & Final Quality Assurance
- Comprehensive `README.md`, `docs/ARCHITECTURE.md`, `docs/DEMO.md`.
- `ruff check .` passes without errors.
- Secrets scan and clean offline startup test.

---

## 3. Risk Assessment & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Unknown Meetily API & Webhook formats | High | Strict isolation in `schema_adapter.py` and `webhooks.py`, config-driven headers, snapshot discovery script. |
| Third-party NLP / spaCy dependency bloat | Medium | Pure-Python deterministic regex + known entities list as reliable default; optional extras isolated. |
| LLM hallucinations in citations | High | Mandatory local transcript re-location check; downgrade hallucinated evidence automatically. |
| Number normalization errors | Medium | Dedicated number parser handling "$15k", "fifteen thousand", "$15,000", "4.2 million", etc. |
| Accidental raw data egress | Critical | Fail-closed `GuardedLLMProvider` privacy gate with regex & vault sensitive value scans. |

---

## 4. Fallback / Scope Pruning Strategy

If execution time runs short, features will be preserved strictly by priority:
- **MUST items (Non-negotiable)**: Core client, database, privacy vault, audience policies, claim verification with number normalization, gatekeeper, review loop, leak scanner, REST API, synthetic demo data.
- **SHOULD items (Retained unless blocked)**: Cross-source check, hash-chained ledger, Gemini provider, MCP server, single-file demo UI dashboard.
- **COULD items (First to cut if necessary)**: Google Drive MCP connector, spaCy/Presidio runtime NER (regex + deal config entities already satisfies all requirements).
