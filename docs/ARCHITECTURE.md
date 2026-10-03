# Nomad Clean Room: Closed-Loop Autonomous Builder Architecture

## 1. Executive Summary

Nomad (Meetily Clean Room) acts as an autonomous privacy boundary and quality gatekeeper between human meeting transcripts and external coding agents such as Google Antigravity ("AGY").

The closed loop ensures that:
1. **Zero sensitive raw data** ever leaves the Clean Room boundary.
2. Only verified, release-cleared tasks are compiled into build specifications.
3. Coding agents operate in quarantined workspaces (`Desktop\test\<slug>\`).
4. Acceptance criteria are deterministic and evaluated independently by Nomad.
5. Coding agents **cannot edit, tamper with, or influence the judge**.
6. Server-side iteration limits (maximum 3 iterations) are strictly enforced.
7. Every lifecycle event is recorded in a cryptographically signed HMAC audit ledger.

---

## 2. High-Level Closed-Loop Architecture

```text
       +-------------------------------------------------------+
       |           Meetily Meeting Audio / Transcript          |
       +-------------------------------------------------------+
                                  |
                                  v
       +-------------------------------------------------------+
       |         Clean Room Pipeline & Masking Vault           |
       |  - Hallucination / Contradiction Verification         |
       |  - Sensitive Data Masking (PII / Values -> Tokens)    |
       |  - Review Decision Gate (Release vs Review)           |
       +-------------------------------------------------------+
                                  | (Masked Tasks Only)
                                  v
       +-------------------------------------------------------+
       |                Buildable Task Selector                |
       |  - Excludes unverifiable / contradicted tasks         |
       |  - Invariant: Only gate: 'release' tasks pass         |
       +-------------------------------------------------------+
                                  |
                                  v
       +-------------------------------------------------------+
       |         Prompt Compiler (Ollama / Fallback)           |
       |  - Local Ollama API (JSON schema format)              |
       |  - Deterministic Template Fallback on error           |
       |  - Privacy egress check & leak scan                   |
       +-------------------------------------------------------+
                                  |
                 MCP stdio Client | cleanroom_get_masked_brief
                                  v
       +-------------------------------------------------------+
       |             Google Antigravity (AGY) Agent            |
       |                                                       |
       |  1. Receives Masked StructuredPrompt                  |
       |  2. Builds deliverables in: Desktop\test\<slug>\      |
       |  3. Runs local tests (informational only)             |
       +-------------------------------------------------------+
                                  |
                 MCP stdio Client | cleanroom_submit_code_report
                                  v
       +-------------------------------------------------------+
       |             Nomad Server-Side State Machine           |
       |                                                       |
       |  1. Workspace Boundary Guard (rejects escapes)        |
       |  2. Tamper Guard: overwrites tests_nomad\ from judge  |
       |  3. Subprocess Execution in scrubbed environment      |
       |  4. Feedback Re-masking (prevents leak in errors)     |
       |  5. Cryptographic HMAC Ledger Entry                   |
       +-------------------------------------------------------+
               |                                  |
         Passed|                      Needs Revision (< 3 iterations)
               v                                  v
      [Audit Ledger: DONE]              [Masked Feedback Prompt]
                                        (Iteration 2, then 3)
                                                  |
                                                  v
                                        (Capped at 3 -> FAILED)
```

---

## 3. Trust Boundaries & Invariants

| Boundary | Trust Level | Security Controls |
| :--- | :--- | :--- |
| **Meeting Transcript & Summary** | Untrusted / Sensitive | Stored only in Nomad DB; never leaves Clean Room unmasked. |
| **Masking Vault (Token Map)** | Confidential | Encrypted at rest using Fernet (`NOMAD_VAULT_KEY`); ephemeral lifecycle. |
| **Prompt Compiler (Ollama)** | Local Model | Receives masked tasks only (defense-in-depth); validated against Pydantic schema; privacy scan before dispatch. |
| **External Agent (Antigravity)** | Completely Untrusted | Jailed to subfolder; reports are informational; agent-reported test passes are ignored. |
| **Judge Test Suite** | Authoritative | Maintained outside workspace; re-copied and SHA-256 verified at eval time; tamper detected immediately. |
| **Evaluation Process** | Authoritative Subprocess | Scrubbed environment (`PATH` and `SYSTEMROOT` only; no API keys); timeout enforcement. |

---

## 4. Vault Persistence Across Processes

### The Challenge
AGY spawns the MCP server as an independent stdio subprocess. In real-world workflows, the agent may restart the MCP session, spawn child processes, or disconnect between the initial brief and subsequent report submissions. Storing token maps purely in in-memory dictionaries would cause evaluation failures and leak re-hydration bugs across process boundaries.

### Architectural Decision: Encrypted At Rest (`Fernet`)
We evaluated two architectural approaches:

1. **Deterministic Re-derivation:**
   - *Mechanism:* Re-run the masking pipeline over the transcript on every MCP request to re-generate the tokens.
   - *Drawback:* Expensive, nondeterministic if masking model weights or regex rules change, fails if transcript inputs are modified during a session, and cannot guarantee stable token assignments across tool calls.
2. **Encrypted Persistence at Rest (Selected):**
   - *Mechanism:* Serialized token map encrypted with AES-128-CBC / HMAC-SHA256 (via `cryptography.fernet.Fernet`).
   - *Key Source:* `NOMAD_VAULT_KEY` environment variable. If unset, a deterministic key derived from machine-specific hardware IDs is utilized for local development.
   - *File System:* Encrypted files stored in `data/vaults/<identifier>.enc` with restricted file permissions (`0o600`).
   - *Ephemeral Lifecycle:* The encrypted token vault is automatically deleted as soon as a loop run completes (`passed`, `failed_max_iterations`, `rejected`, or `aborted`), unless `PERSIST_TOKEN_MAP=true` is set for debugging.

---

## 5. Acceptance Criteria Catalog & Deterministic Pytest Generation

To guarantee reproducibility and eliminate test hallucination, acceptance tests are never generated as free-form LLM code. Instead, Nomad maintains a closed catalog of 12 typed criteria:

1. `file_exists`: Deliverable exists as a regular file.
2. `html_valid_structure`: Well-formed HTML with balanced `<html>` and `<body>` tags.
3. `html_has_tag`: Expected HTML tag exists with minimum count.
4. `html_title_nonempty`: `<title>` element exists and is non-empty.
5. `html_text_contains`: Expected masked token or literal text is present.
6. `html_form_has_labeled_inputs`: Form inputs have associated `<label for="...">` or `aria-label`.
7. `html_has_meta_viewport`: Responsive `<meta name="viewport">` present.
8. `html_no_external_resources`: No unapproved third-party URLs (`http://`, `https://`, `//`).
9. `css_present`: Inline `<style>` or `<link rel="stylesheet">` present.
10. `js_no_eval`: No `eval()` or `new Function()` invocations in script files.
11. `links_resolve_locally`: Relative `<a>` links point to existing files in the workspace.
12. `no_sensitive_values`: Zero unmasked sensitive raw values appear in any workspace files.

Any criterion that cannot be mapped into this deterministic catalog defaults to `manual_review` and is **never** marked as passed automatically.

---

## 6. Feedback Re-masking & Leak Prevention

When Nomad's local evaluator executes tests against the workspace:
1. Pytest assertions might capture unmasked raw values (e.g., `AssertionError: Expected 'Northwind Corp' but found 'Acme'`).
2. Before returning the evaluation failure messages in the `cleanroom_submit_code_report` response (`next_prompt.previous_feedback`), the evaluator executes a token inversion pass:
   - All known raw sensitive values from the vault are substituted back with their corresponding masked tokens (`[COMPANY_1]`, `[EMAIL_1]`).
   - An egress privacy scan is performed on the feedback text.
3. If an unmaskable leak is detected, Nomad fails closed and replaces the feedback with a sanitized error notification.

---

## 7. Audit Ledger Cryptographic Chaining

Every closed-loop lifecycle event is recorded in SQLite table `nomad_audit_ledger`:
- `loop_brief_issued`
- `loop_report_received`
- `loop_evaluation_verdict`
- `loop_tamper_detected`
- `loop_workspace_violation`
- `loop_aborted`

Each record contains:
- `entry_id`: Monotonically increasing sequence number.
- `prev_hash`: SHA-256 hash of previous ledger entry (tamper-evident chaining).
- `data_hash`: SHA-256 hash of event payload.
- `signature`: HMAC-SHA256 signature using `NOMAD_LEDGER_KEY` (ensuring cryptographic non-repudiation).
- `verified`: Chain integrity verified via `AuditLedger.verify_chain()`.
