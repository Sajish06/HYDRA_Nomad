/**
 * Panel: Cross-Source Diligence Reconciler
 * Mode E: Side-by-side comparison between spoken meeting audio and data room documents
 */
import { store } from "../store.js";

export class CrosscheckPanel {
  static render(container, state) {
    const data = state.data;
    const conflicts = (data && data.conflicts) || [];

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4); max-width:840px; margin:0 auto; width:100%;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h2 style="font-size:var(--text-lg); font-weight:700;">Cross-Source Diligence Reconciliation</h2>
            <p style="font-size:var(--text-xs); color:var(--text-secondary);">
              Reconciles spoken transcript claims against data room documents (CIM, Term Sheet).
            </p>
          </div>
          <span class="badge badge-review">1 CRITICAL VARIANCE DETECTED</span>
        </div>

        <!-- Discrepancy Card: EBITDA Conflict -->
        <div class="crosscheck-card">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-subtle); padding-bottom:var(--space-2);">
            <div style="display:flex; align-items:center; gap:var(--space-2);">
              <span class="badge badge-blocked">METRIC CONTRADICTION</span>
              <span style="font-size:var(--text-base); font-weight:700;">Metric: Adjusted EBITDA (FY23)</span>
            </div>
            <span class="mono-tag" style="color:var(--status-blocked-text); background:var(--status-blocked-bg); border-color:var(--status-blocked);">
              DELTA: -$400,000 (9.5% VARIANCE)
            </span>
          </div>

          <div class="crosscheck-grid">
            <!-- Source 1: Spoken Audio -->
            <div class="crosscheck-source-box">
              <div class="crosscheck-source-label">
                <span>SOURCE 1: SPOKEN AUDIO</span>
                <span class="mono-tag">transcript@00:00:43</span>
              </div>
              <div class="crosscheck-source-val">$4,200,000 ($4.2M)</div>
              <p style="font-size:var(--text-xs); color:var(--text-secondary); margin-top:var(--space-1); font-style:italic;">
                "Sarah Chen: ...our adjusted EBITDA was four point two million dollars for the fiscal year."
              </p>
            </div>

            <!-- Source 2: CIM Document -->
            <div class="crosscheck-source-box">
              <div class="crosscheck-source-label">
                <span>SOURCE 2: CIM DOCUMENT</span>
                <span class="mono-tag">cim.md:line 8</span>
              </div>
              <div class="crosscheck-source-val">$3,800,000 ($3.8M)</div>
              <p style="font-size:var(--text-xs); color:var(--text-secondary); margin-top:var(--space-1); font-style:italic;">
                "Financial Overview: Adjusted EBITDA (FY23): $3.8M on $24M revenue."
              </p>
            </div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; background:var(--bg-void); padding:var(--space-3); border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
            <div style="font-size:var(--text-xs); color:var(--text-secondary);">
              <strong>Diligence Risk:</strong> Purchasing price multiple adjustment if CIM understates spoken performance or CFO was optimistic.
            </div>
            <button class="btn-director" id="btn-resolve-crosscheck" style="background:var(--accent-cyan); color:var(--bg-void); font-weight:700;">
              Forward to Review Queue →
            </button>
          </div>
        </div>

        <!-- Matching Source (No Conflict) -->
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:var(--space-3); opacity:0.8;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:var(--space-2);">
              <span class="badge badge-verified">MATCH</span>
              <span style="font-size:var(--text-sm); font-weight:600;">Metric: Annual Recurring Revenue (ARR)</span>
            </div>
            <span class="mono-tag" style="color:var(--status-verified-text);">0% VARIANCE ($24M == $24M)</span>
          </div>
        </div>
      </div>
    `;

    this.attachEvents(container);
  }

  static attachEvents(container) {
    const btn = container.querySelector("#btn-resolve-crosscheck");
    if (btn) {
      btn.addEventListener("click", () => {
        store.setStep("review");
      });
    }
  }
}
