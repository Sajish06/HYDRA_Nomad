# Meetily Clean Room

> **A verification, masking, and distribution gatekeeper for meeting intelligence in M&A due diligence.**  
> *Built on the Meetily Pro Automation API.*

---

## 1. Overview & Problem Statement

In mergers and acquisitions (M&A) due diligence, deal teams, corporate development leads, legal counsel, and investment committees rely heavily on meeting records. With the advent of AI meeting recorders, automated summaries are increasingly generated directly from audio transcripts.

However, **piping raw AI meeting summaries directly into downstream channels (Slack, email, data rooms) creates unacceptable legal, financial, and regulatory liability:**

1. **Hallucination & Number Corruption**: LLMs frequently distort crucial figures, dates, and commitments. In a due diligence session, an AI misinterpreting an approved expenditure as **"$50,000"** instead of the spoken **"fifteen thousand"** can derail purchase price adjustments or violate governance protocols.
2. **Confidentiality & Information Barriers**: Deal meetings involve parties with differing legal rights to information:
   - **Deal Team**: Sees all internal names, terms, and unmasked financials.
   - **Outside Counsel**: Requires exact terms and financials, but personal contact information (PII) must be masked.
   - **Lenders / Financing Partners**: Require financial metrics, but the target company must be obscured behind a code name (e.g., *Project Falcon*), and individual participants must be anonymized.
   - **Board of Directors**: Requires executive decisions and action items, with exact numbers generalized to conservative ranges (e.g., `$4.2M` becomes `$4M-$5M`).
   - **External AI Clouds**: Must **never** see raw names, emails, phones, deal targets, or sensitive entities.

**Meetily Clean Room solves this.** It is an automated gatekeeper and compliance verification engine that sits between Meetily Pro's local transcription engine and downstream distribution channels.

> **Disclaimer**: *Meetily Clean Room is an independent open-source hackathon project. It is not affiliated with, officially supported by, or endorsed by Meetily or Zackriya Solutions.*

---

## 2. What Makes This Different: Gatekeeper, Not a Connector

Most AI meeting integrations are passive "connectors": when a meeting ends, they immediately blast the raw summary to Slack or a CRM. 

**Clean Room is an active gatekeeper and compliance layer:**
- **No Blind Trust in AI**: Clean Room treats LLM outputs as untrusted proposals. Every evidence citation is verified against physical audio segments on the local machine.
- **Deterministic Spoken-Number Normalization**: Words like *"fifteen thousand"*, *"15k"*, `"$15,000"`, and `"4.2 million"` are normalized into numbers. Any contradiction with the summary automatically overrules AI verdicts and flags the release.
- **Fail-Closed Boundary Gate**: If verification fails, cross-source conflicts are discovered, or privacy detectors encounter an issue, the release is **BLOCKED** or **HELD FOR REVIEW**. Outputs are never distributed without compliance clearance.
- **One-Way Privacy Gate**: External AI providers receive strictly pseudonymized tokens (`[PERSON_1]`, `[ORGANIZATION_1]`). A hard privacy gatekeeper inspects payloads immediately prior to egress, refusing any call containing sensitive text.
- **Audience-Specific Fan-Out**: Generates 5 distinct, policy-governed releases from a single meeting transcript.
- **Post-Generation Leak Scanner & Canary**: Every written file is scanned for sensitive values. A planted canary (`Zephyrine Quillfeather`) is audited to ensure it appears only in the deal team release.
- **Tamper-Evident Ledger**: A SHA-256 hash-chained audit log seals all actions and decisions cryptographically.

---

## 3. Feature Matrix

| Feature | Status | Requirement |
|---|---|---|
| **Deterministic Spoken-Number Normalizer** | **Implemented** | Local Python engine (Offline) |
| **Local Evidence Re-location Check** | **Implemented** | Local Python engine (Offline) |
| **Action Item Owner & Deadline Audit** | **Implemented** | Local Python engine (Offline) |
| **Privacy Tokenizer & In-Memory Vault** | **Implemented** | Local Python engine (Offline) |
| **Audience Policy Engine (5 Profiles)** | **Implemented** | Local Python engine (Offline) |
| **Cross-Source Diligence Reconciler (CIM/Term Sheet)** | **Implemented** | Local Python engine (Offline) |
| **Gatekeeper & Non-Linear Review Loop** | **Implemented** | Local Python engine (Offline) |
| **Post-Generation Leak Scanner & Canary Audit** | **Implemented** | Local Python engine (Offline) |
| **Cryptographic Hash-Chained Audit Ledger** | **Implemented** | Local Python engine (Offline) |
| **Offline Demo Runner & Standalone UI Dashboard** | **Implemented** | Local Python engine (Offline) |
| **Model Context Protocol (MCP) Server** | **Implemented** | Local Python engine (Offline) |
| **HMAC Webhook Receiver with Deduplication** | **Implemented** | Local Python engine (Offline) |
| **Meetily Pro HTTP Client & Schema Adapter** | **Implemented** | Needs live Meetily Pro 1.11.0+ (`127.0.0.1:8420`) |
| **Webhook Registration Script** | **Implemented** | Needs live Meetily Pro 1.11.0+ (`127.0.0.1:8420`) |
| **API Contract Discovery (`discover_api.py`)** | **Implemented** | Needs live Meetily Pro 1.11.0+ (`127.0.0.1:8420`) |
| **Guarded Gemini 2.5 / 1.5 Provider** | **Implemented** | Needs `GEMINI_API_KEY` (`ENABLE_AI=true`) |
| **Drive / Gmail / Slack Remote Sinks** | *Planned* | Post-hackathon road-map |
| **Automated Meeting Summary Regeneration via `write` scope**| *Planned* | Post-hackathon road-map |
| **Marketing Content Verification Workflow (Blog/Social)** | *Planned* | Post-hackathon road-map |

---

## 4. Architecture & Data-Flow Rule

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

### The Invariable Data-Flow Rule
- **No raw confidential text leaves the process** except to Meetily on loopback (`http://127.0.0.1:8420`).
- External AI providers receive strictly masked tokens (`[PERSON_1]`, `[ORGANIZATION_1]`).
- A final privacy check (`ai/guarded.py`) runs immediately before every external call; if sensitive data or vault values are detected, the call is aborted immediately.
- AI evidence quotes are never trusted: local code searches the actual audio transcript segments to confirm existence.

---

## 5. Prerequisites

- **Python**: Version 3.11 or 3.12 (Tested on 3.12).
- **Operating System**: Windows, macOS, or Linux.
- **Git**: For version control.
- *(Optional)* **Meetily Pro 1.11.0+**: With Automation API enabled on `http://127.0.0.1:8420` (not required for demo, tests, or offline mode).
- *(Optional)* **Gemini API Key**: If testing live cloud LLM verification (not required for demo or tests).

---

## 6. Installation & Setup

### Windows PowerShell
```powershell
# 1. Clone repository and enter directory
cd "c:\Users\DELL\Desktop\ASCENT'26"

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Copy configuration template
Copy-Item .env.example .env
```

### Linux / macOS (bash)
```bash
# 1. Clone repository and enter directory
cd meetily-clean-room

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Copy configuration template
cp .env.example .env
```

---

## 7. Environment Configuration

All settings are validated via Pydantic Settings at startup. Edit `.env` as required:

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Meetily Clean Room` | Service title |
| `APP_ENV` | `development` | `development`, `testing`, or `production` |
| `DEBUG` | `true` | Debug logging toggle |
| `API_HOST` | `127.0.0.1` | Local bind host |
| `API_PORT` | `8000` | Local bind port |
| `MEETILY_BASE_URL` | `http://127.0.0.1:8420` | Meetily Pro Automation API loopback address |
| `MEETILY_API_TOKEN` | `""` | Meetily Bearer token (read scope) |
| `MEETILY_TIMEOUT_SECONDS` | `15` | Connect/read timeout for Meetily calls |
| `DATABASE_URL` | `sqlite:///./data/meetily.db` | SQLite database URI |
| `DATA_DIR` | `./data` | Base storage directory for outputs and logs |
| `WEBHOOK_SECRET` | `""` | HMAC-SHA256 secret for validating Meetily webhooks |
| `WEBHOOK_PUBLIC_URL` | `""` | Public URL for webhook destination (e.g. ngrok tunnel) |
| `WEBHOOK_SIGNATURE_HEADER` | `X-Meetily-Signature` | Header containing webhook HMAC signature |
| `WEBHOOK_SIGNATURE_ALGORITHM`| `sha256` | Hash algorithm (`sha256`) |
| `WEBHOOK_SIGNATURE_PREFIX` | `""` | Optional prefix (e.g. `sha256=`) |
| `WEBHOOK_ALLOW_UNSIGNED` | `false` | Dev-only bypass for testing without signatures |
| `ENABLE_AI` | `false` | Enable external Gemini calls (requires `GEMINI_API_KEY`) |
| `GEMINI_API_KEY` | `""` | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `ENABLE_WEBHOOKS` | `true` | Toggle webhook ingestion route |
| `ENABLE_RAW_STORAGE` | `false` | Store raw transcript in DB (default false: stores SHA256 only) |
| `EXPOSE_RAW_TRANSCRIPTS` | `false` | Expose raw transcripts in API (default false: masked only) |
| `PERSIST_TOKEN_MAP` | `false` | Persist vault token map to disk (default false: in-memory only) |
| `AUDIENCE_PROFILES_PATH` | `./configs/audience_profiles.yaml` | Policy definitions for the 5 audiences |
| `DOCUMENTS_DIR` | `./data/demo/documents` | Directory containing diligence documents (CIM, term sheet) |

---

## 8. Meetily Pro Setup & Connection

### How to Enable the Meetily Pro API
1. Meetily Pro's Automation API is **off by default**.
2. Requires **Meetily Pro version 1.11.0 or higher** with an active license or trial.
3. Open **Meetily Pro Settings** > **Developer / Integrations** > Enable **Local Automation Gateway**.
4. The gateway listens on **`http://127.0.0.1:8420`**. It is only reachable while Meetily is actively running.
5. In Meetily Pro Settings, generate an API token with **`read`** scope. Clean Room only requires read access to inspect meetings, transcripts, and summaries.

### Testing Connection & Fetching Meetings

#### 1. Check Connection
```bash
python scripts/check_meetily_connection.py
```
*Outputs gateway health, latency, and token validation.*

#### 2. Discover OpenAPI Specification
```bash
python scripts/discover_api.py
```
*Downloads `docs/openapi.snapshot.json` and runs an automated contract compatibility check against `backend/meetily/schema_adapter.py`.*

#### 3. Fetch a Meeting
```bash
python scripts/fetch_meeting.py <MEETING_ID>
```
*Fetches metadata, transcript, and summary from Meetily and saves them to `data/raw/`.*

---

## 9. Webhook Setup & Registration

Meetily Pro dispatches signed HTTP webhook notifications when a summary finishes (`summary.completed`).

1. Establish a tunnel to your local Clean Room server if running on a separate network or remote test:
   ```bash
   ngrok http 8000
   ```
2. Update `.env` with your public URL:
   ```env
   WEBHOOK_PUBLIC_URL=https://your-tunnel.ngrok-free.app/api/webhooks/meetily
   ```
3. Register the webhook destination with Meetily:
   ```bash
   python scripts/register_webhook.py
   ```
   > **Important Security Notice**: The registration script prints a one-time HMAC secret returned by Meetily. Copy this secret into `.env` as `WEBHOOK_SECRET`. The secret is never logged or saved to disk automatically.
4. If prompted in Meetily Pro desktop app, click **Approve** on the new webhook destination.

---

## 10. Running the Offline Demo

The full M&A due diligence scenario runs **100% offline** without Meetily, Gemini, or internet connectivity.

### 1. Terminal Demo Runner
```powershell
python scripts/run_demo.py
```
This script executes the entire pipeline:
1. Loads synthetic transcript (`Northwind Analytics`, canary `Zephyrine Quillfeather`, `$15,000` approval, `$4.2M` EBITDA).
2. Detects the planted summary hallucination: summary claims **"$50,000 approved"**, while transcript shows **"fifteen thousand"** -> **CONTRADICTED**.
3. Flags an invented claim about Australia expansion -> **UNVERIFIABLE (evidence_not_found)**.
4. Identifies cross-source conflict: transcript states **EBITDA $4.2M** vs CIM states **$3.8M** -> **CROSS-SOURCE CONFLICT**.
5. Halts release: **GATE STATUS: HOLD_FOR_REVIEW**.
6. Simulates a compliance officer correcting the expenditure claim and resolving the conflict.
7. Resumes the pipeline, fans out 5 audience-masked dossiers, passes the leak scanner, and cryptographically verifies the SHA-256 ledger chain.

### 2. Standalone Web Dashboard
```powershell
python -m uvicorn backend.main:app --port 8000
```
Open your browser to: **`http://127.0.0.1:8000/demo`**

- **Interactive Verification**: Click on claims to see exact timestamped evidence segments.
- **Privacy Gate Split View**: Side-by-side comparison of raw text vs pseudonymized cloud tokens, complete with an egress byte counter.
- **Cross-Source Conflict Cards**: Direct comparison between meeting quotes and CIM document lines.
- **Audience Outputs**: Switch between `deal_team`, `outside_counsel`, `lender` (*Project Falcon*), and `board` (*ranges*).
- **Human Review Loop**: Click **Correct** or **Approve** to resolve holds and unlock release.
- **Ledger Verification**: Click **Verify Chain** to test the SHA-256 hash sequence.

---

## 11. Model Context Protocol (MCP) Server

Meetily Clean Room includes a built-in MCP server (`mcp_server/server.py`) that exposes compliance tools to AI assistants like Claude Desktop, Cursor, or Claude Code over standard I/O (stdio).

### Exposed MCP Tools
1. `cleanroom_process_meeting(meeting_id)`: Triggers ingestion, verification, cross-checking, and gate evaluation.
2. `cleanroom_get_verification(meeting_id)`: Returns claims, evidence citations, and verdicts.
3. `cleanroom_get_conflicts(meeting_id)`: Returns cross-source contradictions against data room documents.
4. `cleanroom_get_output(meeting_id, audience)`: Retrieves audience-governed intelligence dossier.
5. `cleanroom_review_decide(item_id, action, correction)`: Submits human review approval, correction, or rejection.
6. `cleanroom_leak_report(meeting_id)`: Retrieves leak-scan status and canary audit results.
7. `cleanroom_ask(meeting_id, question, audience)`: Answers questions using verified citations, strictly masked for the requested audience.

### Claude Desktop Configuration
Add the following snippet to your `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/Library/Application Support/Claude/` on macOS):

```json
{
  "mcpServers": {
    "meetily-clean-room": {
      "command": "python",
      "args": ["-m", "backend.mcp_server.server"],
      "cwd": "C:\\Users\\DELL\\Desktop\\ASCENT'26",
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```
*(Note: MCP client integration marked as compatible with Model Context Protocol 2.x standard; configuration snippet provided for agent setup).*

---

## 12. REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health, DB connectivity, and active configuration |
| `GET` | `/demo` | Standalone browser-based compliance dashboard |
| `POST` | `/api/demo/run` | Execute end-to-end synthetic due diligence demo |
| `GET` | `/api/meetings` | List all tracked meetings and status |
| `GET` | `/api/meetings/{id}` | Get meeting details (masked unless raw exposure enabled) |
| `POST` | `/api/meetings/{id}/sync` | Sync transcript/summary from local Meetily Pro gateway |
| `POST` | `/api/meetings/{id}/process` | Trigger full verification and gating pipeline |
| `GET` | `/api/meetings/{id}/status` | Get current processing run state and stage |
| `POST` | `/api/meetings/{id}/retry` | Retry failed processing run |
| `GET` | `/api/meetings/{id}/verification`| Fetch claim verdicts, evidence quotes, and flags |
| `GET` | `/api/meetings/{id}/intelligence`| Fetch structured M&A business intelligence items |
| `GET` | `/api/meetings/{id}/conflicts` | Fetch contradictions between transcript and documents |
| `GET` | `/api/meetings/{id}/outputs` | List generated audience output dossiers |
| `GET` | `/api/meetings/{id}/outputs/{aud}`| Download specific audience output markdown/JSON |
| `GET` | `/api/meetings/{id}/leakscan` | Fetch leak scan report and canary isolation status |
| `GET` | `/api/meetings/{id}/masking-diff`| Get visual character offset diff for audience masking |
| `GET` | `/api/meetings/{id}/review` | Fetch pending review items requiring human clearance |
| `POST` | `/api/review/{item_id}/decision`| Submit review decision (`approve`, `correct`, `reject`) |
| `GET` | `/api/meetings/{id}/ledger` | Fetch hash-chained cryptographic audit log |
| `GET` | `/api/meetings/{id}/ledger/verify`| Verify cryptographic integrity of ledger blocks |
| `POST` | `/api/webhooks/meetily` | Ingest signed Meetily Pro `summary.completed` event |

---

## 13. Privacy, Security & Compliance Notes

1. **Risk Reduction, Not Complete Anonymization**: Automated masking significantly reduces data exposure risk. However, no automated heuristic or NER model guarantees 100% anonymization against sophisticated inference attacks. Clean Room provides structured risk reduction.
2. **Deterministic Overlap Resolution**: Detectors prioritize longest-span matches to prevent partial tokenization errors (e.g. `$4.2M` is captured as an entire entity rather than splitting the `4`).
3. **In-Memory Vault**: Token maps are kept exclusively in memory during the execution lifecycle. They are destroyed upon process termination unless `PERSIST_TOKEN_MAP=true` is explicitly set in `.env`.
4. **Hard Egress Gate**: External AI requests pass through `ai/guarded.py`. Any payload containing unmasked emails, phone numbers, credit cards, SSNs, API tokens, or known target company names is rejected locally before transmission.
5. **AI Egress Logging**: All payloads sent to external AI are recorded to `data/outputs/<meeting_id>/ai_egress.jsonl` with an exact byte count and masked payload sample, providing an audit trail of data exiting the environment.
6. **Tamper-Evident Ledger**: Ledger entries use SHA-256 hashing where each block incorporates the previous hash, payload canonical JSON, and transcript SHA-256. Any modification to past database rows will cause `verify_chain` to fail immediately. Note that this provides tamper evidence on the host machine, not decentralized Byzantine fault tolerance.

---

## 14. Testing

The entire test suite is designed to run offline without Meetily Pro, Gemini, or internet access:

```bash
# Run complete test suite
pytest -v

# Run with coverage report
pytest --cov=backend tests/
```

All 55+ tests cover:
- Meetily client HTTP handling, retries, and error mapping (mocked with `respx`).
- Webhook signature validation, idempotency deduplication, and replay protection.
- Privacy detectors, Luhn card check, and Vault tokenization.
- Audience policy transformations, range conversion, and codename replacement.
- Spoken-number normalization and local evidence re-location.
- Gatekeeper hold-for-review logic and human review loop resumption.
- Leak scanning, canary isolation, and ledger cryptographic verification.

---

## 15. Limitations & Future Work

### Current Limitations
- **Local Machine Boundary**: The audit ledger ensures tamper-evidence against local database edits, but does not notarize entries to an external blockchain or transparency log.
- **Document Formats**: The cross-source reconciler currently parses plain text, markdown, and JSON diligence documents. PDF table extraction is planned.
- **Local Meetily Requirement for Live Mode**: Live sync requires Meetily Pro 1.11.0+ running on the same computer with the Automation API enabled.

### Future Work
- **Marketing Workflow Module**: Repurpose the Clean Room verification core for marketing interviews—verifying quotes from recorded customer interviews before syndicating to blogs, LinkedIn, or case studies.
- **Cloud Sinks**: Modular sinks for pushing approved audience dossiers directly to Google Drive, Box, Notion, or Slack.
- **Summary Regeneration (`write` scope)**: Allow Clean Room to trigger summary regeneration with corrective prompts in Meetily Pro if a summary fails verification.

---

## 16. License

This project is licensed under the terms of the [MIT License](LICENSE).
