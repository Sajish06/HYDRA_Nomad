# 🛡️ NOMAD — Deterministic Local Claim Verification Engine 

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

## 🔒 Dual-Layer Privacy Masking Engine & Reversible Vault

Nomad features an enterprise **Zero-Trust Privacy Masking Architecture** to guarantee that **no raw secrets, PII, or confidential commercial context ever leave your local environment**.

```text
 Raw Meeting Intelligence / Commitments
                │
                ▼
🧠 Layer 1: Semantic Context Scrubbing (Ollama / Qwen)
   - Extracts intent & quarantines sensitive commercial/deal context
                │
                ▼
⚡ Layer 2: Deterministic Privacy Firewall (High-Speed Regex Rules)
   - Credentials (API Keys, JWTs, Passwords, DB URIs)
   - PII (Emails, Phones, SSNs, Credit Cards)
   - Network Infrastructure (IP Addresses, Hostnames)
   - Financial Data (Monetary amounts, deal percentages)
                │
                ▼
🔑 Local Reversible Entity Vault (Encrypted Token Map)
   - Maps raw values <──> Reversible Tokens ([SECRET_CREDENTIAL_1], [PII_1])
   - Encrypted at rest using Fernet symmetric key (NOMAD_VAULT_KEY)
                │
                ▼
🛡️ Pre-Dispatch Leak Inspector Gate
   - Scans outbound briefs; fails closed (PrivacyLeakError) if leaks detected
                │
                ▼
 Masked Brief Dispatched to Downstream AI Agents (Antigravity IDE)
```

### Core Masking Components

1. **Semantic Decomposer (`app/masking/semantic.py`)**: Parses meeting context using local LLMs to isolate sensitive commercial terms without breaking feature specifications.
2. **Deterministic Firewall (`app/masking/firewall.py`)**: Executes sub-10ms pattern scrubbing to ensure zero missed credentials or PII.
3. **Reversible Vault (`app/masking/vault.py`)**: Maintains session-isolated token-to-secret dictionaries encrypted at rest for safe local re-hydration.
4. **Leak Inspector (`app/masking/validator.py`)**: Egress gate performing exact string verification prior to Model Context Protocol (MCP) dispatch.

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
