import streamlit as st
import json
import os
import httpx
from pathlib import Path
from typing import Dict, Any, List

# Setup page
st.set_page_config(
    page_title="ReqCopilot Proof — Verification Engine",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
        background: linear-gradient(90deg, #3B82F6 0%, #8B5CF6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .badge-verified {
        background-color: #065F46;
        color: #34D399;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-ambiguous {
        background-color: #78350F;
        color: #FBBF24;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-unsupported {
        background-color: #7F1D1D;
        color: #F87171;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-confirmed {
        background-color: #1E3A8A;
        color: #93C5FD;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-chip {
        background-color: #1E293B;
        color: #94A3B8;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-right: 6px;
    }
    .evidence-item-supports {
        border-left: 3px solid #10B981;
        padding-left: 12px;
        margin-bottom: 10px;
        background: rgba(16, 185, 129, 0.05);
        border-radius: 0 6px 6px 0;
        padding: 8px 12px;
    }
    .evidence-item-contradicts {
        border-left: 3px solid #EF4444;
        padding-left: 12px;
        margin-bottom: 10px;
        background: rgba(239, 68, 68, 0.08);
        border-radius: 0 6px 6px 0;
        padding: 8px 12px;
    }
    .evidence-item-context {
        border-left: 3px solid #64748B;
        padding-left: 12px;
        margin-bottom: 10px;
        background: rgba(100, 116, 139, 0.05);
        border-radius: 0 6px 6px 0;
        padding: 8px 12px;
    }
    .quote-box {
        font-style: italic;
        color: #E2E8F0;
        margin-top: 4px;
    }
    .footnote {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 30px;
        border-top: 1px solid #334155;
        padding-top: 12px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Imports
from app.config import settings, BASE_DIR
from app.adapters.mock_adapter import MockAdapter
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.pipeline import run_verification_pipeline, get_effective_status
from app.models import Meeting, Segment, Participant

# Query Ollama for installed models
def get_installed_ollama_models() -> List[str]:
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/tags")
            if resp.status_code == 200:
                tags = resp.json().get("models", [])
                names = [m.get("name") for m in tags if m.get("name")]
                if names:
                    return names
    except Exception:
        pass
    return ["qwen2.5:7b-instruct", "llama3.2:latest", "llama3.2:3b"]

# Sidebar configuration
st.sidebar.markdown("### 🛡️ ReqCopilot Proof")
st.sidebar.caption("Deterministic local claim verification engine")
st.sidebar.divider()

# Model Selection
available_models = get_installed_ollama_models()
selected_model = st.sidebar.selectbox("Ollama LLM Model", available_models, index=0)
settings.OLLAMA_MODEL = selected_model

# Mock LLM toggle
mock_llm_active = st.sidebar.checkbox("⚡ Use Cached LLM (Fast Demo Mode)", value=False)
settings.MOCK_LLM = 1 if mock_llm_active else 0

st.sidebar.divider()

# Input Mode Selector
input_mode = st.sidebar.radio(
    "📥 Meeting Input Source",
    ["📂 Pre-built Golden Fixtures", "📤 Upload Custom JSON / File", "✍️ Paste Custom Transcript & Summary"]
)

meeting_to_process: Meeting = None
meeting_source_name: str = ""

if input_mode == "📂 Pre-built Golden Fixtures":
    mock_dir = BASE_DIR / "data" / "mock"
    fixtures = sorted([f.name for f in mock_dir.glob("*.json")]) if mock_dir.exists() else []
    selected_fixture = st.sidebar.selectbox("Select Fixture", fixtures)
    meeting_source_name = selected_fixture
    
    if selected_fixture:
        f_path = mock_dir / selected_fixture
        with open(f_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        adapter = MockAdapter()
        meeting_to_process = adapter.load(raw_data)

elif input_mode == "📤 Upload Custom JSON / File":
    st.sidebar.markdown("##### 📄 Upload Files")
    upload_type = st.sidebar.radio("Upload Format", ["Single JSON File (Mock/Full)", "Raw Transcript + Summary File(s)"], index=0)
    
    if upload_type == "Single JSON File (Mock/Full)":
        uploaded_file = st.sidebar.file_uploader("Upload Meeting JSON (`.json`)", type=["json"])
        if uploaded_file is not None:
            meeting_source_name = uploaded_file.name
            content = uploaded_file.read().decode("utf-8")
            try:
                data = json.loads(content)
                adapter = MockAdapter()
                meeting_to_process = adapter.load(data)
                st.sidebar.success(f"Loaded `{uploaded_file.name}` ({len(meeting_to_process.segments)} segments, {len(meeting_to_process.summary_decisions) + len(meeting_to_process.summary_actions)} claims)")
            except Exception as e:
                st.sidebar.error(f"Error parsing JSON: {e}")
    else:
        transcript_file = st.sidebar.file_uploader("1. Raw Transcript (`.txt`, `.vtt`, `.json`)", type=["txt", "vtt", "json"])
        summary_file = st.sidebar.file_uploader("2. Summary / Claims File (`.txt`, `.json`) [Optional]", type=["txt", "json"])
        custom_summary_text = st.sidebar.text_area("Or type/paste summary bullets here:", height=80)
        
        if transcript_file is not None:
            raw_t_text = transcript_file.read().decode("utf-8")
            decisions = []
            
            if summary_file is not None:
                sum_text = summary_file.read().decode("utf-8")
                try:
                    sum_json = json.loads(sum_text)
                    if isinstance(sum_json, dict):
                        decisions = sum_json.get("decisions", []) + sum_json.get("action_items", [])
                    elif isinstance(sum_json, list):
                        decisions = sum_json
                except Exception:
                    decisions = [l.strip().lstrip("-*123456789. ") for l in sum_text.split("\n") if l.strip()]
            elif custom_summary_text.strip():
                decisions = [l.strip().lstrip("-*123456789. ") for l in custom_summary_text.split("\n") if l.strip()]

            meeting_source_name = f"{transcript_file.name}"
            adapter = MockAdapter()
            meeting_to_process = adapter.load({
                "meeting_id": f"UPLOAD_{Path(transcript_file.name).stem}",
                "title": Path(transcript_file.name).stem,
                "raw_transcript": raw_t_text,
                "summary": {
                    "decisions": decisions,
                    "action_items": []
                }
            })
            st.sidebar.success(f"Parsed `{transcript_file.name}` ({len(meeting_to_process.segments)} segments, {len(decisions)} claims)")

elif input_mode == "✍️ Paste Custom Transcript & Summary":
    st.sidebar.info("Paste your raw transcript and summary bullets below.")
    custom_title = st.sidebar.text_input("Meeting Title", value="Project Architecture Sync")
    custom_transcript = st.sidebar.text_area(
        "Raw Transcript",
        value="""Alice (10:15): Should we create a dedicated security review channel?
Bob (10:16): Let's hold off on dedicated channels until next sprint.
Alice (10:17): Okay, agreed.""",
        height=140
    )
    custom_summary = st.sidebar.text_area(
        "Summary Bullets (Decisions & Tasks)",
        value="""- Create a dedicated security review channel.
- Bob will audit permissions by Friday.""",
        height=100
    )
    meeting_source_name = "Pasted Custom Meeting"
    
    # Parse pasted input
    if custom_transcript.strip():
        decisions_list = [l.strip().lstrip("-* ") for l in custom_summary.split("\n") if l.strip()]
        adapter = MockAdapter()
        meeting_to_process = adapter.load({
            "meeting_id": "CUSTOM_MEETING",
            "title": custom_title,
            "raw_transcript": custom_transcript,
            "summary": {
                "decisions": decisions_list,
                "action_items": []
            }
        })

# Verification Trigger Button
run_btn = st.sidebar.button("🚀 Verify Claims Against Transcript", type="primary", use_container_width=True)

# Main App View
st.markdown("<div class='main-header'>ReqCopilot Proof Verification</div>", unsafe_allow_html=True)
st.markdown("Deterministic, local claim verification engine that validates whether extracted decisions, tasks, and requirements are grounded in what was said in the meeting.")

if not meeting_to_process:
    st.info("👋 **Welcome to ReqCopilot Proof!** Choose a pre-built fixture from the sidebar, or upload a custom meeting file below.")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        st.markdown("#### 📤 Upload Custom JSON / Transcript")
        main_upload = st.file_uploader("Drop your `.json` or `.txt` meeting file here", type=["json", "txt"], key="main_file_drop")
        if main_upload:
            content = main_upload.read().decode("utf-8")
            meeting_source_name = main_upload.name
            try:
                data = json.loads(content)
                meeting_to_process = MockAdapter().load(data)
                st.success(f"Loaded `{main_upload.name}` ({len(meeting_to_process.segments)} segments)")
            except Exception:
                meeting_to_process = MockAdapter().load({
                    "meeting_id": f"UPLOAD_{Path(main_upload.name).stem}",
                    "title": Path(main_upload.name).stem,
                    "raw_transcript": content,
                    "summary": {"decisions": [], "action_items": []}
                })
                st.success(f"Parsed `{main_upload.name}`")
    
    with col_up2:
        st.markdown("#### 📋 Supported JSON Format Example")
        st.code("""{
  "title": "Architecture Sync",
  "segments": [
    {"speaker": "Alice", "time": "10:15", "text": "Should we use Redis?"},
    {"speaker": "Bob", "time": "10:16", "text": "Yes, I will benchmark it before Friday."}
  ],
  "summary": {
    "decisions": [],
    "action_items": ["Bob will benchmark Redis before Friday."]
  }
}""", language="json")

    if not meeting_to_process:
        st.stop()

# Execution state
meeting_key = f"{meeting_to_process.meeting_id}_{len(meeting_to_process.segments)}_{meeting_source_name}"
if "verified_results" not in st.session_state or st.session_state.get("current_meeting_key") != meeting_key or run_btn:
    with st.spinner(f"Verifying {len(meeting_to_process.summary_decisions) + len(meeting_to_process.summary_actions)} claims using {settings.OLLAMA_MODEL}..."):
        # 1. Load into DB
        load_meeting_to_db(meeting_to_process, source="mock")
        # 2. Index
        index_meeting(meeting_to_process.meeting_id)
        # 3. Extract claims
        claims = extract_claims_from_summary(meeting_to_process)
        
        # 4. Verify each claim
        v_list = []
        for c in claims:
            v = run_verification_pipeline(c)
            v_list.append({
                "claim_id": c.claim_id,
                "text": c.text,
                "status": v.status.value,
                "effective_status": get_effective_status(c.claim_id, v.status),
                "gate_action": v.gate_action,
                "reasons": [r.value for r in v.reasons],
                "explanation": v.explanation,
                "resolved_claim": v.resolved_claim,
                "final_state": v.final_state,
                "evidence_chain": [e.model_dump() for e in v.evidence_chain],
                "slots": [s.model_dump() for s in v.slots]
            })
            
        st.session_state["verified_results"] = {
            "meeting_id": meeting_to_process.meeting_id,
            "title": meeting_to_process.title,
            "claims": v_list
        }
        st.session_state["current_meeting_key"] = meeting_key

results = st.session_state.get("verified_results", {})
claims_data = results.get("claims", [])

# Render Two-Column Dashboard
col_left, col_right = st.columns([1, 1.25], gap="large")

# Left Column: Raw Transcript
with col_left:
    st.subheader(f"📝 Raw Transcript ({len(meeting_to_process.segments)} segments)")
    st.caption(f"Meeting: **{meeting_to_process.title or meeting_to_process.meeting_id}**")
    
    for seg in meeting_to_process.segments:
        spk = seg.speaker or "Speaker"
        t_str = f"[{seg.time}]" if seg.time else f"[#{seg.idx}]"
        
        st.markdown(f"""
        <div style="margin-bottom: 8px; padding: 6px 10px; background: rgba(255,255,255,0.02); border-radius: 4px;">
            <span style="color: #94A3B8; font-size: 0.8rem; font-family: monospace;">{t_str}</span>
            <strong style="color: #60A5FA; margin-left: 6px;">{spk}:</strong>
            <span style="color: #F1F5F9; margin-left: 4px;">{seg.text}</span>
        </div>
        """, unsafe_allow_html=True)

# Right Column: Claims & Verification Cards
with col_right:
    st.subheader(f"🎯 Verified Claims ({len(claims_data)})")
    
    if not claims_data:
        st.info("No claims found in summary bullets. You can extract claims directly from transcript segments.")

    for idx, c in enumerate(claims_data):
        claim_id = c["claim_id"]
        status = c["status"]
        eff_status = c.get("effective_status", status)
        gate_action = c["gate_action"]
        
        if eff_status == "VERIFIED":
            badge_html = '<span class="badge-verified">✓ VERIFIED · PROCEED</span>'
        elif eff_status == "AMBIGUOUS":
            badge_html = '<span class="badge-ambiguous">⚠ AMBIGUOUS · HUMAN REVIEW</span>'
        elif eff_status == "UNSUPPORTED":
            badge_html = '<span class="badge-unsupported">✕ UNSUPPORTED · BLOCKED</span>'
        elif eff_status == "USER_CONFIRMED":
            badge_html = f'<span class="badge-confirmed">✓ USER CONFIRMED (was {status})</span>'
        elif eff_status == "USER_REJECTED":
            badge_html = f'<span class="badge-unsupported">✕ USER REJECTED (was {status})</span>'
        else:
            badge_html = f'<span class="badge-chip">{eff_status}</span>'

        with st.container(border=True):
            st.markdown(f"{badge_html} &nbsp; <span class='badge-chip'>SUMMARY</span>", unsafe_allow_html=True)
            st.markdown(f"### “{c['text']}”")
            
            if c.get("resolved_claim") and c["resolved_claim"].strip() != c["text"].strip():
                st.markdown(f"**Resolved Claim:** `{c['resolved_claim']}`")

            st.markdown(f"**Explanation:** {c['explanation']}")

            reasons = c.get("reasons", [])
            if reasons:
                reasons_html = " ".join([f"<span class='badge-chip'>{r}</span>" for r in reasons])
                st.markdown(f"<div style='margin-top: 4px; margin-bottom: 8px;'>{reasons_html}</div>", unsafe_allow_html=True)

            # Slot Grounding Matrix
            slots = c.get("slots", [])
            if slots:
                st.markdown("**Slot Grounding:**")
                s_cols = st.columns(len(slots))
                for s_i, s in enumerate(slots):
                    with s_cols[s_i]:
                        s_name = s["slot"].capitalize()
                        s_status = s["status"]
                        s_val = s.get("claim_value") or "—"
                        
                        if s_status == "GROUNDED":
                            icon = "✅"
                        elif s_status == "CONFLICT":
                            icon = "⚠️"
                        elif s_status == "MISSING":
                            icon = "❌"
                        else:
                            icon = "⚪"
                        
                        st.caption(f"{icon} **{s_name}**: `{s_val}` ({s_status})")

            # Evidence Chain
            evidence = c.get("evidence_chain", [])
            if evidence:
                with st.expander(f"🔍 Evidence Chain ({len(evidence)} items)", expanded=True):
                    for e in evidence:
                        rel = e["relation"]
                        css_class = (
                            "evidence-item-supports" if rel == "SUPPORTS"
                            else "evidence-item-contradicts" if rel == "CONTRADICTS"
                            else "evidence-item-context"
                        )
                        t_lbl = f"[{e.get('time') or f'idx {e.get('idx')}'}]"
                        spk_lbl = e.get("speaker") or "Speaker"
                        stance_lbl = e.get("stance")
                        
                        st.markdown(f"""
                        <div class="{css_class}">
                            <div style="font-size: 0.85rem; color: #94A3B8;">
                                <strong>{t_lbl} {spk_lbl}</strong> &nbsp;
                                <span class="badge-chip">{stance_lbl}</span>
                                <span class="badge-chip">{rel}</span>
                            </div>
                            <div class="quote-box">“{e.get('quote')}”</div>
                        </div>
                        """, unsafe_allow_html=True)

            # Interactive Actions
            act_col1, act_col2, act_col3 = st.columns([1, 1, 1])
            
            # Masking preview
            if eff_status in ("VERIFIED", "USER_CONFIRMED"):
                with act_col1:
                    if st.button(f"🛡️ Send to Masking", key=f"mask_{claim_id}"):
                        from app.masking.stub import get_masker
                        from app.models import VerifiedTask, HandoffSegment, ClaimType
                        
                        grounding = [
                            HandoffSegment(idx=e["idx"], speaker=e.get("speaker"), time=e.get("time"), text=e.get("text"))
                            for e in evidence if e["relation"] == "SUPPORTS"
                        ]
                        task = VerifiedTask(
                            task_id=claim_id,
                            meeting_id=meeting_to_process.meeting_id,
                            claim_type=ClaimType.DECISION,
                            task_text=c.get("resolved_claim") or c["text"],
                            actor=None,
                            action=None,
                            object=None,
                            deadline=None,
                            effective_status=eff_status,
                            verified_at="now",
                            verification_hash="hash_local",
                            grounding_segments=grounding
                        )
                        masker = get_masker()
                        brief = masker.mask(task)
                        st.success(f"Task Masked: Brief ID `{brief.brief_id}`")
                        st.code(f"Masked Output: {brief.masked_text}\nEntities Redacted: {brief.entities_masked}\nContext Segments Kept: {brief.segments_kept}")

            # Human confirm/reject
            if eff_status in ("AMBIGUOUS", "UNSUPPORTED"):
                with act_col1:
                    if st.button("✓ Confirm (Release)", key=f"conf_{claim_id}"):
                        from app.db import get_db
                        with get_db() as conn:
                            conn.execute("INSERT INTO confirmations (claim_id, decision, note) VALUES (?, ?, ?)", (claim_id, "CONFIRMED", "Confirmed via UI"))
                        st.rerun()
                with act_col2:
                    if st.button("✕ Reject (Block)", key=f"rej_{claim_id}"):
                        from app.db import get_db
                        with get_db() as conn:
                            conn.execute("INSERT INTO confirmations (claim_id, decision, note) VALUES (?, ?, ?)", (claim_id, "REJECTED", "Rejected via UI"))
                        st.rerun()

            # Reasoning trace
            with st.expander("📊 View Reasoning Trace"):
                from app.db import get_db
                with get_db() as conn:
                    traces = conn.execute("SELECT stage, payload FROM pipeline_trace WHERE claim_id = ? ORDER BY id ASC", (claim_id,)).fetchall()
                for tr in traces:
                    st.markdown(f"**Stage:** `{tr['stage']}`")
                    st.json(json.loads(tr["payload"]) if tr["payload"] else {})

# Permanent Footnote
st.markdown("""
<div class='footnote'>
    🛡️ <strong>ReqCopilot Proof</strong> — <em>VERIFIED means supported by the available conversational evidence, not objectively true.</em>
</div>
""", unsafe_allow_html=True)
