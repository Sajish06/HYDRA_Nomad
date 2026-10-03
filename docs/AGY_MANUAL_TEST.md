# Nomad: Manual Testing Guide for Google Antigravity (AGY)

This guide provides step-by-step instructions for testing the Nomad closed-loop system using a **real Google Antigravity (AGY)** agent instance.

---

## 1. Prerequisites & Registration

### Step 1.1: Verify & Register Nomad MCP Server
Run the registration diagnosis script to register the Nomad MCP server with Antigravity:

```powershell
# Preview configuration and check drift (Safe mode)
python scripts/check_agy_registration.py

# Apply registration to ~/.gemini/config/mcp_config.json (creates backup automatically)
python scripts/check_agy_registration.py --apply
```

This ensures Antigravity recognizes `nomad-cleanroom` over stdio transport.

### Step 1.2: Prepare a Verified Meeting
Initialize the synthetic meeting fixture in your local SQLite database:

```powershell
python -c "from scripts.run_closed_loop_demo import setup_demo_meeting; setup_demo_meeting('mtg_real_agy_test')"
```

---

## 2. Test Execution in Google Antigravity

1. Open the **Antigravity IDE** or launch an AGY agent chat session.
2. In the chat prompt, paste the exact instruction below:

```text
Use the nomad-cleanroom MCP server. Call cleanroom_get_masked_brief for meeting mtg_real_agy_test, build exactly what the brief asks inside the workspace path it gives you, then call cleanroom_submit_code_report. If the verdict is 'revise', follow the returned prompt. Stop on 'passed' or 'failed_max_iterations'.
```

---

## 3. Post-Run Verification Checklist

After AGY signals completion, perform the following verification checks:

### 3.1 Check Workspace Deliverables
Verify that files were created exclusively inside the designated `Desktop\test` subfolder:

```powershell
Get-ChildItem -Path "$HOME\Desktop\test" -Recurse
```

- Deliverables (`index.html`, `contact.html`) must exist.
- Files must be well-formed static HTML.
- Zero files should have been created or modified outside this subfolder.

### 3.2 Verify Privacy & Token Masking
Ensure that **no sensitive unmasked values** were leaked into AGY's session or workspace:

```powershell
# Search for any raw fixture values in the workspace files
Select-String -Path "$HOME\Desktop\test\*\*.html" -Pattern "555-0199", "sarah.connor@cyberdyne.io", "Cyberdyne Systems"
```
*Expected result: 0 matches found.* Deliverables should only contain masked tokens (e.g. `[EMAIL_1]`) or generic text.

### 3.3 Verify Cryptographic Audit Ledger
Verify that every lifecycle step was recorded in Nomad's tamper-evident audit ledger:

```powershell
python -c "from backend.storage.database import SessionLocal; from backend.storage.repository import Repository; from backend.processors.ledger import AuditLedger; db = SessionLocal(); repo = Repository(db); entries = repo.list_ledger_entries('mtg_real_agy_test'); valid, err = AuditLedger.verify_chain(entries); print(f'Ledger entries: {len(entries)}, Chain Valid: {valid}')"
```

---

## 4. Clean Up Workspace

When finished with testing, delete the test artifacts safely:

```powershell
# Preview cleanup
python scripts/clean_workspace.py --all-test-runs --dry-run

# Execute cleanup
python scripts/clean_workspace.py --all-test-runs
```
