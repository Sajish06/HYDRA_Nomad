# Meetily Clean Room - Architecture & System Design

## 1. Architectural Philosophy: The Gatekeeper Paradigm

Most AI meeting integrations act as **connectors**: they take raw AI summaries from a meeting recorder and blindly blast them into Slack, email, or a CRM.

**Meetily Clean Room is a gatekeeper and compliance layer.** Designed specifically for high-stakes **M&A due diligence**, it enforces two non-negotiable guarantees:
1. **Verifiable Meeting Intelligence**: Every factual claim, financial figure, and action item in an AI summary is verified against the meeting transcript using spoken-number normalization and local evidence re-location.
2. **Deterministic Information Barriers**: No confidential information reaches unauthorized audiences or external AI clouds. Single meetings are segmented into tailored audience outputs (`deal_team`, `outside_counsel`, `lender`, `board`), and any output that leaks sensitive information is automatically quarantined.

---

## 2. Core Data Flow & Privacy Gate Rule

The architecture enforces a strict one-way boundary:

```text
       Raw Transcript & Summary (Local Host Only)
                         |
                [privacy.tokenize]
                         |
      +------------------+------------------+
      |                                     |
[In-Memory Vault]                 [Masked Text with Tokens]
(Reversible token map,                      |
 sensitive values index,            [ai/guarded.py]
 NOT persisted to disk)             (Hard privacy abort check)
      |                                     |
      |                            [External Cloud LLM]
      |                            (Receives ONLY masked text)
      |                                     |
      |                            [Draft Claims & Extractions]
      |                                     |
      +------------------+------------------+
                         |
               [vault.rehydrate]
                         |
        [Local Evidence Re-location Check]
        (Downgrades any hallucinated quote)
                         |
       [Deterministic Number & Entity Check]
       (Normalizes spoken forms: "$15k" == "fifteen thousand")
                         |
       [Cross-Source Diligence Reconciler]
       (Compares transcript figures vs CIM/Term Sheet)
                         |
             [Gatekeeper Release Decision]
             - RELEASE: If 100% verified & clean
             - HOLD_FOR_REVIEW: If contradictions/conflicts found
                         |
      +------------------+------------------+
      | (If Held)                           | (If Released)
[Review Loop Queue]                 [Policy Engine: 5 Audiences]
(Approve / Correct / Reject)                 |
      |                             [Local Filesystem Fan-Out]
(Resumes pipeline on resolution)             |
                                    [Leak Scanner & Canary Check]
                                    (Scans outputs; quarantines leaks)
                                             |
                                   [Hash-Chained Audit Ledger]
```

### The Invariable Privacy Rule
Under no circumstances does raw, unmasked confidential text exit the local machine to external AI APIs. Immediately prior to dispatching any external AI request, `ai/guarded.py` runs a multi-pattern regex and vault scan. If any unmasked email, phone, credit card, SSN, API key, or known sensitive deal entity is present, the call is aborted and a `PrivacyGateError` is raised.

Furthermore, every AI call is logged to `data/outputs/<meeting_id>/ai_egress.jsonl` with an exact byte count and masked payload sample, providing undeniable evidence of data hygiene.

---

## 3. Subsystem Breakdown

### 3.1 Meetily Pro Adapter & Client (`backend/meetily/`)
- Interacts with the local Meetily Pro Automation API gateway running on loopback (`http://127.0.0.1:8420`).
- Strict isolation of external API variations within `schema_adapter.py`.
- Custom exception mapping (`MeetilyConnectionError`, `MeetilyAuthError`, `MeetilyNotFound`, `MeetilyServerError`).
- Bounded exponential backoff retries on connection failures and 5xx responses.
- Config-driven HMAC webhook verification (`webhooks.py`) supporting constant-time signature comparison and deduplication on `event_id`.

### 3.2 Privacy & Vault Engine (`backend/processors/privacy.py`)
- Category detectors: `EMAIL`, `PHONE`, `CARD` (Luhn algorithm mod 10 validated), `API_KEY` (high entropy and prefix), `NATIONAL_ID` (SSN), `PERSON`, `ORGANIZATION`, `TARGET_NAME`, `AMOUNT`, `PERCENT`, `DATE`.
- Deterministic overlap resolution: longest match wins.
- In-memory `Vault` maintaining stable session tokens (`[PERSON_1]`, `[EMAIL_1]`).
- Financial metrics (`AMOUNT`, `PERCENT`, `DATE`) are preserved during external AI processing because financial figures are the subject of diligence analysis, but masked per audience profile.
- Token map is strictly in-memory and destroyed on process exit unless `PERSIST_TOKEN_MAP=true` is explicitly enabled.

### 3.3 Audience Policy Engine (`backend/processors/policy.py`)
Transforms raw structured intelligence into audience-specific releases:
- **`deal_team`**: Unmasked; full access.
- **`outside_counsel`**: Legal terms and financials kept; names and contact details masked.
- **`lender`**: Target company substituted with code name (`Project Falcon`); personal identities masked.
- **`board`**: Decisions and action items preserved; names mapped to corporate roles; financial figures generalized into ranges (`$4.2M` -> `$4M-$5M`).
- **`cloud_llm`**: Irreversibly tokenized for external boundary.
- Diff helper generates character offset spans for visual UI comparison.

### 3.4 Verification & Spoken-Number Normalizer (`backend/processors/verification.py`, `number_normalizer.py`)
- Spoken number normalizer converts words ("fifteen thousand", "four point two million", "15k", "$15,000") into canonical numbers for deterministic comparison.
- Mismatched numbers force a `CONTRADICTED` verdict regardless of what an AI verifier claimed.
- Mandatory local evidence re-location: every quoted transcript citation is checked against the local transcript segments. If not found, the claim is downgraded to `UNVERIFIABLE` with flag `evidence_not_found`.
- Action item audit: flags unverified owners (`owner_unverified`) and deadlines.
- Omission detector: surfaces topics present in transcript audio but missing from the summary.

### 3.5 Cross-Source Diligence Reconciler (`backend/processors/crosscheck.py`, `sources/`)
- Interfaces with local document directories via `DocumentSource` abstraction.
- Compares meeting assertions against formal deal documentation (e.g. CIM, Term Sheet).
- Pinpoints contradictory metrics with dual citations: `transcript@00:00:12` vs `cim.md:line 8`.

### 3.6 Gatekeeper & Human Review Loop (`backend/processors/gate.py`, `api/review.py`)
- Non-linear workflow gatekeeper: halts distribution if contradictions, unverified owners, or cross-source conflicts exist (`HOLD_FOR_REVIEW`).
- Enables human compliance officers to approve, correct, or reject items.
- Upon resolution of all flagged items, the pipeline resumes from masking onward, applies corrections, executes leak scans, and delivers output artifacts.

### 3.7 Post-Generation Leak Scanner & Canary (`backend/processors/leakscan.py`)
- Scans every generated audience document on disk against the Vault's sensitive values index.
- Canary Verification: seeds synthetic advisor `Zephyrine Quillfeather` into the transcript; confirms the canary appears exclusively in `deal_team` output, and is quarantined if leaked into any other audience.

### 3.8 Cryptographic Audit Ledger (`backend/processors/ledger.py`)
- Append-only hash chain: `entry_hash = SHA256(prev_hash || canonical_json(payload) || transcript_sha256)`.
- Records run start, verification completion, gate decisions, review actions, and release distribution.
- Cryptographic verification algorithm `verify_chain` detects any single-byte tampering in database records or links.
- Note: Tamper-evident on host machine; not a distributed consensus network.
