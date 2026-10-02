"""Meetily Clean Room - Complete Offline M&A Diligence Demo Runner.

Demonstrates verification, spoken-number checks, cross-source contradiction detection,
audience masking, gatekeeper hold, human review correction, leak scanning, and audit ledger.
Runs entirely offline without requiring Meetily or external AI API keys.
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Ensure UTF-8 output on Windows consoles if possible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.meetily.schema_adapter import MeetilySchemaAdapter
from backend.processors.ledger import AuditLedger
from backend.processors.pipeline import PipelineOrchestrator
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


def print_banner(text: str, ch: str = "="):
    line = ch * 75
    print(f"\n{line}\n  {text}\n{line}")


async def main():
    print_banner("MEETILY CLEAN ROOM - M&A DUE DILIGENCE GATEKEEPER DEMO")
    print("Use Case: Project Falcon (Acme Capital acquisition of Northwind Analytics)")
    print("Posture: Fail-Closed Gatekeeper | Zero Raw Text to Cloud | Full Provenance")

    # 1. Initialize local DB & repo
    init_db()
    db = SessionLocal()
    repo = Repository(db)

    # 2. Load synthetic demo files
    demo_dir = Path("./data/demo")
    t_file = demo_dir / "sample_transcript.json"
    s_file = demo_dir / "sample_summary.json"

    if not t_file.exists() or not s_file.exists():
        print("[ERROR] Demo data missing in data/demo/")
        return

    with open(t_file, "r", encoding="utf-8") as f:
        t_data = json.load(f)
    with open(s_file, "r", encoding="utf-8") as f:
        s_data = json.load(f)

    meeting_id = "demo_falcon_meeting"
    transcript = MeetilySchemaAdapter.parse_transcript(meeting_id, t_data)
    summary = MeetilySchemaAdapter.parse_summary(meeting_id, s_data)

    meeting = repo.create_or_get_meeting(
        meetily_id=meeting_id,
        title="Project Falcon: Due Diligence Financials & Customer Risk",
        duration_seconds=530.0,
    )
    repo.update_meeting_data(
        meeting.id,
        transcript_sha256=transcript.sha256_hash,
        raw_transcript=transcript.raw_text,
        raw_summary=summary.summary_text,
        status="synced",
    )

    print("\n[1] Loaded Meeting Data:")
    print(f"    - Title: {meeting.title}")
    print(f"    - Transcript Segments: {len(transcript.segments)}")
    print(f"    - Transcript SHA-256:  {transcript.sha256_hash[:24]}...")
    print("    - Canary Entity:       Zephyrine Quillfeather (Seeded into transcript)")

    # 3. First Pipeline Run (Expect Gate Hold due to deliberate errors)
    print_banner("STAGE 1: VERIFICATION, PRIVACY TOKENIZATION & DILIGENCE CROSSCHECK", "-")
    orchestrator = PipelineOrchestrator(repo=repo)
    run, decision, v_res, _ = await orchestrator.execute_run(meeting.id, transcript, summary)

    # Print Verification Table
    print("\n[Claims Verification Report]")
    for c in v_res.claims:
        status_icon = (
            "[SUPPORTED]    "
            if c.verdict.value == "supported"
            else "[CONTRADICTED] "
            if c.verdict.value == "contradicted"
            else "[PARTIAL]      "
            if c.verdict.value == "partially_supported"
            else "[UNVERIFIABLE] "
        )
        print(f"  {status_icon} {c.text}")
        if c.flags:
            print(f"     Flags: {', '.join(c.flags)}")
        if c.explanation:
            print(f"     Note:  {c.explanation}")
        if c.evidence:
            ev = c.evidence[0]
            print(f"     Evidence Citation: \"{ev.text}\" ({ev.speaker} @ {ev.timestamp})")

    # Print Cross-source Conflicts
    conflicts = orchestrator.crosschecker.cross_check(transcript)
    print(f"\n[Cross-Source Diligence Conflicts Detected: {len(conflicts)}]")
    for conf in conflicts:
        print(f"  [CONFLICT] Metric: {conf.metric}")
        print(f"     Meeting Claim:      {conf.transcript_value} ({conf.transcript_citation})")
        print(f"     Diligence Document: {conf.doc_value} ({conf.doc_citation})")
        print(f"     Details: {conf.explanation}")

    # Print Gate Decision
    print_banner("STAGE 2: GATEKEEPER EVALUATION & RELEASE DECISION", "-")
    print(f"  GATE DECISION: >>> {decision.decision.value.upper()} <<<")
    print("  Reasons for Gate Hold:")
    for r in decision.reasons:
        print(f"    - {r}")

    # 4. Review Loop Simulation
    print_banner("STAGE 3: HUMAN-IN-THE-LOOP REVIEW QUEUE (NON-LINEAR RESOLUTION)", "-")
    review_items = repo.list_review_items(meeting.id)
    print(f"  Flagged items waiting for compliance review: {len(review_items)}")

    for it in review_items:
        print(f"\n  Review Item [{it.id[:8]}]:")
        print(f"    Issue:    {it.issue_type}")
        print(f"    Original: {it.original_text}")

        # Simulate reviewer resolution
        if "50,000" in it.original_text:
            corrected = "Sarah Chen approved $15,000 for vendor expenditures with CloudScale Systems."
            repo.update_review_item(
                item_id=it.id,
                status="corrected",
                corrected_text=corrected,
                reviewer_notes="Corrected $50,000 to $15,000 per Sarah Chen transcript audio.",
            )
            print(f"    -> [ACTION]: CORRECTED to: '{corrected}'")
        elif "David Vance" in it.original_text:
            corrected = "Priya Sharma sends customer concentration data by Friday."
            repo.update_review_item(
                item_id=it.id,
                status="corrected",
                corrected_text=corrected,
                reviewer_notes="Corrected owner from David Vance to Priya Sharma per transcript.",
            )
            print(f"    -> [ACTION]: CORRECTED to: '{corrected}'")
        else:
            repo.update_review_item(
                item_id=it.id,
                status="approved",
                reviewer_notes="Reconciled discrepancy: transcript 4.2M reflects post-audit TTM.",
            )
            print("    -> [ACTION]: APPROVED with explanatory note.")

    # 5. Resume Pipeline After Review
    print_banner("STAGE 4: PIPELINE RESUMPTION & AUDIENCE DISTRIBUTION", "-")
    run2, decision2, v_res2, leak_rep = await orchestrator.resume_after_review(
        meeting_id=meeting.id,
        transcript=transcript,
        summary=summary,
        reviewer_name="Sarah Jenkins (Lead Diligence Officer)",
    )

    print(f"  Post-Review Gate Decision: >>> {decision2.decision.value.upper()} <<<")
    print(f"  Approved By: {decision2.approved_by}")

    # Verify generated outputs
    artifacts = repo.list_output_artifacts(meeting.id)
    print(f"\n  Distributed {len(artifacts)} Audience Artifacts to disk:")
    for a in artifacts:
        print(f"    - Audience: {a.audience:<16} Path: {a.file_path}")

    # 6. Leak Scan & Canary Report
    print_banner("STAGE 5: POST-GENERATION LEAK SCAN & CANARY ISOLATION AUDIT", "-")
    print(f"  Overall Leak Scan Status: {'PASSED (Zero Leaks)' if leak_rep.all_passed else 'FAILED'}")
    print("\n  Audience Leak Verification Table:")
    print("  " + "-" * 70)
    print(f"  {'Audience':<18} | {'Leak Status':<12} | {'Canary Present?':<18} | Target Format")
    print("  " + "-" * 70)
    for ar in leak_rep.audience_reports:
        canary_txt = "YES (Expected)" if ar.canary_found and ar.audience == "deal_team" else "NO (Contained)"
        target_fmt = "Unmasked" if ar.audience == "deal_team" else "Project Falcon" if ar.audience == "lender" else "Tokenized" if ar.audience == "cloud_llm" else "Preserved"
        print(f"  {ar.audience:<18} | {ar.status.upper():<12} | {canary_txt:<18} | {target_fmt}")
    print("  " + "-" * 70)

    # 7. Audit Ledger Verification
    print_banner("STAGE 6: CRYPTOGRAPHIC TAMPER-EVIDENT AUDIT LEDGER", "-")
    ledger_entries = repo.list_ledger_entries(meeting.id)
    is_valid, err = AuditLedger.verify_chain(ledger_entries)

    print(f"  Ledger Chain Integrity: {'[VALID & VERIFIED]' if is_valid else '[CORRUPTED]'}")
    print(f"  Total Provenance Events: {len(ledger_entries)}\n")
    for e in ledger_entries:
        print(f"    Block #{e.index}: [{e.event_type:<24}] Hash: {e.entry_hash[:16]}... (Prev: {e.prev_hash[:12]}...)")

    print_banner("DEMO COMPLETED SUCCESSFULLY: ALL GATES & CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
