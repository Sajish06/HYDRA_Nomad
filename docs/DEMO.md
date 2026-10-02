# Meetily Clean Room - Live Demo Script (4 Minutes)

This script provides a step-by-step guide for presenting **Meetily Clean Room** in a 4-minute hackathon pitch or technical walkthrough.
The demo runs completely offline and requires zero external credentials or network connectivity.

---

## Preparation (Before Starting)
1. Open terminal in repository root.
2. Start the Clean Room server in one terminal window:
   ```bash
   python -m uvicorn backend.main:app --port 8000
   ```
3. Open browser at `http://127.0.0.1:8000/demo`.

---

## Timed Walkthrough

### 0:00 - 0:45 | The Problem: Why Meeting Summary Connectors Fail in M&A
- **Action**: Display the empty Clean Room UI dashboard or slide.
- **Narrative**:
  > "Today, teams use AI tools to record and summarize meetings. But in M&A due diligence, you cannot simply pipe raw AI summaries to Slack or email.
  > First, AI summaries hallucinate figures and action items. If an AI misquotes an approved expenditure as $50,000 instead of $15,000, that is an immediate compliance failure.
  > Second, in M&A, different audiences have different legal rights to see data: the deal team sees everything, lenders must only see a code name like 'Project Falcon', outside counsel cannot see personal identities, and the board needs financial ranges, not exact figures.
  > Meetily Clean Room is not a connector—it is a **compliance gatekeeper**."

---

### 0:45 - 1:45 | Step 1: Execution & Verification Catches
- **Action**: Click the blue button **"▶ Run Due Diligence Demo"** on the dashboard (or run `python scripts/run_demo.py` in terminal).
- **What the Audience Sees**:
  - The Gate Banner turns **RED**: `RELEASE GATE STATUS: HELD FOR REVIEW`.
  - Claims table populates with color-coded badges.
- **Highlight the Three Big Catches**:
  1. **Spoken-Number Normalization Catch**:
     - Point to Claim: `Sarah Chen approved $50,000 for vendor expenditures...` (Marked **🔴 CONTRADICTED**).
     - Click the claim to reveal the local evidence quote: *"I approve the fifteen thousand dollars vendor expenditure"*.
     - Explain: *"Our deterministic normalizer equated 'fifteen thousand' with $15,000, detected the discrepancy against the summary's $50,000 assertion, and automatically overrode the verdict."*
  2. **Hallucination Downgrade**:
     - Point to Claim: `Northwind plans to expand into Australia...` (Marked **⚪ UNVERIFIABLE**).
     - Point out the flag `evidence_not_found`. Explain that local code physically searched the transcript audio segments; because the quote was invented by the AI, it was demoted.
  3. **Action Item Owner Audit**:
     - Point to Action Item: `David Vance sends customer concentration data...` (Flagged `owner_unverified`). Transcript audio shows Priya Sharma took that task.

---

### 1:45 - 2:30 | Step 2: Cross-Source Diligence Conflicts & Egress Privacy Split
- **Action**: Scroll down to the **Cross-Source Contradictions** panel.
- **What the Audience Sees**:
  - Yellow warning card: `⚠️ EBITDA Discrepancy`.
  - Transcript states: `$4.2M` (`transcript@00:00:43`).
  - Diligence Document (`cim.md:line 8`) states: `$3.8M`.
- **Narrative**:
  > "Clean Room doesn't just check the meeting against itself; it cross-checks meeting claims against the diligence data room documents. Here, it caught an unannounced divergence between the CIM and the CFO's spoken words."
- **Action**: Point to the **Privacy Egress Gate Split View** (top right).
- **Highlight**:
  - The raw transcript with names and companies on the left vs the masked text on the right (`[PERSON_1]`, `[ORGANIZATION_1]`).
  - Show the **"Bytes Sent to AI"** counter: proving only masked text touched external boundaries.

---

### 2:30 - 3:15 | Step 3: Human Review Loop & Gate Release
- **Action**: Scroll to the **Human Review Queue** panel.
- **What the Audience Sees**:
  - Items awaiting compliance decision: the $50,000 expenditure contradiction and the CIM conflict.
- **Action**:
  - Click the green button **"Correct to $15k"** next to the $50,000 item.
  - Click **"Approve As-Is"** on the CIM note.
- **What the Audience Sees**:
  - The system resumes the pipeline.
  - Gate Banner switches from **RED** to **🟢 RELEASE APPROVED**.
- **Narrative**:
  > "Notice the system is non-linear. The gatekeeper halted the release until a human compliance officer resolved the items. Once corrected, the pipeline resumed, re-verified the corrected claim, and unlocked distribution."

---

### 3:15 - 4:00 | Step 4: Audience Tailoring, Leak Scanner & Audit Ledger
- **Action**: Click through the **Audience Tabs** in Panel 5:
  1. Click `deal_team`: Show unmasked names, real target name, and the synthetic canary `Zephyrine Quillfeather`.
  2. Click `lender`: Show that target name automatically became `Project Falcon`, and people became tokens.
  3. Click `board`: Show exact figure `$4.2M` became `$4M-$5M`, and `$15,000` became `$10,000-$20,000`.
  4. Point to the **Leak Scan Badge**: `100% PASSED (0 Leaks)`.
     - Explain: *"Our canary entity appeared in the deal team dossier, but zero instances leaked into outside counsel, lenders, or external cloud logs."*
- **Action**: Scroll to Panel 6 (Cryptographic Ledger) and click **"Verify Chain"**.
- **What the Audience Sees**:
  - Alert: `Chain Integrity: [VALID & VERIFIED]`.
  - Block hashes chaining back to the genesis block `#0`.
- **Wrap Up**:
  > "Meetily Clean Room turns messy meeting audio into verified, audience-governed intelligence dossiers with complete cryptographic audit provenance. Thank you!"
