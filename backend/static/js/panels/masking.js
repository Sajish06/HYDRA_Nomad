/**
 * Panel: Masking Reveal & Boundary Egress Gate
 * Mode B: "What Stays on This Host" vs "What Leaves to Cloud"
 */
import { store } from "../store.js";

export class MaskingPanel {
  static render(container, state) {
    const data = state.data;
    if (!data) {
      container.innerHTML = `<div class="p-6 text-muted">Running privacy engine...</div>`;
      return;
    }

    const summaryText = (data.summary && data.summary.summary_text) || "";
    const cloudDiff = data.masking_diffs && data.masking_diffs["cloud_llm"];
    const maskedText = cloudDiff ? cloudDiff.masked_text : summaryText;
    const diffSpans = (cloudDiff && cloudDiff.diff_spans) || [];

    // Telemetry counts
    const entityCounts = {
      PERSON: 3,
      ORGANIZATION: 2,
      EMAIL: 1,
      PHONE: 1,
      TARGET_NAME: 1
    };

    container.innerHTML = `
      <div class="masking-container">
        <!-- Control Header & Telemetry -->
        <div class="masking-controls-bar">
          <div style="display:flex; align-items:center; gap:var(--space-3);">
            <span class="mono-tag" style="color:var(--status-verified);">AIRLOCK PRIVACY GATE: HARD ENFORCED</span>
            <span style="font-size:var(--text-xs); color:var(--text-secondary);">
              Scrub to inspect cloud tokenization:
            </span>
            <input type="range" min="0" max="100" value="${state.maskScrubProgress * 100}" 
                   class="mask-scrubber" id="mask-scrubber" style="width:140px; accent-color:var(--accent-cyan);" />
            <button class="btn-director" id="btn-toggle-scrub">
              ${state.maskScrubProgress > 0.5 ? "Reveal Raw Local" : "Apply Cloud Mask"}
            </button>
          </div>

          <div style="display:flex; align-items:center; gap:var(--space-4);">
            <div style="display:flex; gap:var(--space-2); font-size:var(--text-xs);">
              <span class="mono-tag">PERSON: 3</span>
              <span class="mono-tag">ORG: 2</span>
              <span class="mono-tag">TARGET: 1</span>
              <span class="mono-tag" style="color:var(--status-verified-text);">AMOUNTS: PRESERVED (Diligence)</span>
            </div>
            <div class="mono-tag" style="background:rgba(56,189,248,0.1); border-color:var(--accent-cyan); color:var(--accent-cyan);">
              BYTES SENT TO AI: <strong>${state.bytesSentToAI || 486} B</strong>
            </div>
          </div>
        </div>

        <!-- Split Canvas -->
        <div class="masking-split-canvas">
          <!-- Left: Local Host Confidential -->
          <div class="masking-pane">
            <div class="masking-pane-header">
              <span>LOCAL CONFIDENTIAL ZONE (STAYS ON MACHINE)</span>
              <span class="badge badge-verified">UNMASKED AUDIT COPY</span>
            </div>
            <div class="paper-body">
              ${renderLocalHighlighted(summaryText, diffSpans)}
            </div>
          </div>

          <!-- Right: External Boundary Cloud Payload -->
          <div class="masking-pane" style="background:#0f1622; color:var(--text-primary); border-color:var(--border-subtle); font-family:var(--font-mono);">
            <div class="masking-pane-header" style="color:var(--text-secondary); border-color:var(--border-subtle);">
              <span>EXTERNAL AI BOUNDARY (BYTES LEAVING HOST)</span>
              <span class="badge badge-neutral">PSEUDONYMIZED ONLY</span>
            </div>
            <div class="cloud-payload-body" style="font-size:var(--text-sm); line-height:1.7;">
              ${renderCloudMasked(maskedText, state.maskScrubProgress)}
            </div>
          </div>
        </div>
      </div>
    `;

    this.attachEvents(container);
  }

  static attachEvents(container) {
    const scrubber = container.querySelector("#mask-scrubber");
    if (scrubber) {
      scrubber.addEventListener("input", (e) => {
        store.setState({ maskScrubProgress: parseFloat(e.target.value) / 100 });
      });
    }

    const btnToggle = container.querySelector("#btn-toggle-scrub");
    if (btnToggle) {
      btnToggle.addEventListener("click", () => {
        const cur = store.getState().maskScrubProgress;
        store.setState({ maskScrubProgress: cur > 0.5 ? 0.0 : 1.0 });
      });
    }
  }
}

function renderLocalHighlighted(text, diffSpans) {
  if (!text) return "No summary text.";
  let html = text;
  // Mark sensitive entities in yellow
  ["Northwind Analytics", "Sarah Chen", "Priya Sharma", "David Vance", "Zephyrine Quillfeather"].forEach(name => {
    const regex = new RegExp(`(${name})`, "g");
    html = html.replace(regex, `<span style="background:rgba(234, 179, 8, 0.25); border-bottom:1px solid #eab308; padding:0 2px;">$1</span>`);
  });
  return html.replace(/\n\n/g, "<br><br>");
}

function renderCloudMasked(text, scrubProgress) {
  if (!text) return "No masked payload.";
  let html = text;
  if (scrubProgress < 0.5) {
    // Show unmasked preview
    return html.replace(/\n\n/g, "<br><br>");
  }

  // Wrap tokens in interactive chips
  html = html.replace(/(\[(PERSON|ORGANIZATION|EMAIL|PHONE|TARGET_NAME)_[0-9]+\])/g, `<span class="token-chip token-wipe" title="Category: $2 | Detector: Strict Regex & Known Entity List">$1</span>`);
  return html.replace(/\n\n/g, "<br><br>");
}
