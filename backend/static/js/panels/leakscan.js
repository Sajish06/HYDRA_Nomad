/**
 * Panel: Post-Generation Leak Scanner & Canary Isolation Audit
 * Mode G: Scans all 5 audience files for sensitive entities and canary leaks
 */
import { store } from "../store.js";
import { ApiClient } from "../api.js";

export class LeakScanPanel {
  static render(container, state) {
    const isLeaking = state.isLeakPlanted;
    const meetingId = (state.data && state.data.meeting_id) || "demo_falcon_diligence";

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4); max-width:850px; margin:0 auto; width:100%;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h2 style="font-size:var(--text-lg); font-weight:700;">Post-Generation Leak Scanner & Canary Audit</h2>
            <p style="font-size:var(--text-xs); color:var(--text-secondary);">
              Inspects generated markdown dossiers on host disk. Ensures canary never leaves deal team.
            </p>
          </div>

          <div style="display:flex; gap:var(--space-2);">
            ${isLeaking ? `
              <button class="btn-director" id="btn-revert-leak" style="background:var(--status-verified); color:var(--bg-void); font-weight:700;">
                ✓ Restore Clean State
              </button>
            ` : `
              <button class="btn-director btn-reject" id="btn-plant-leak">
                ⚡ Plant Leak in Lender File (Director Mode)
              </button>
            `}
          </div>
        </div>

        <!-- Scanner Card with Laser Sweep -->
        <div class="airlock-card" style="position:relative; overflow:hidden;">
          <div class="scanner-laser"></div>
          
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--space-3);">
            <div style="display:flex; align-items:center; gap:var(--space-2);">
              <span class="badge ${isLeaking ? 'badge-blocked' : 'badge-verified'}">
                ${isLeaking ? 'CRITICAL LEAK DETECTED' : '100% CLEAN · 0 LEAKS'}
              </span>
              <span style="font-size:var(--text-xs); color:var(--text-secondary);">
                ${isLeaking ? 'Artifact quarantined immediately' : '5 Output Files Inspected'}
              </span>
            </div>
            <span class="mono-tag">VAULT MATCHES: ${isLeaking ? '1 INFRACTION' : '0'}</span>
          </div>

          <table class="leak-table">
            <thead>
              <tr>
                <th>Audience Dossier</th>
                <th>Scan Status</th>
                <th>Target Name</th>
                <th>Canary Advisor (Zephyrine Quillfeather)</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>deal_team.md</strong></td>
                <td><span class="badge badge-verified">PASS</span></td>
                <td>Northwind Analytics</td>
                <td style="color:var(--status-verified-text);">Allowed (Deal Team)</td>
                <td><span class="mono-tag">Delivered</span></td>
              </tr>
              <tr>
                <td><strong>outside_counsel.md</strong></td>
                <td><span class="badge badge-verified">PASS</span></td>
                <td>Northwind Analytics</td>
                <td style="color:var(--text-muted);">None (Contained)</td>
                <td><span class="mono-tag">Delivered</span></td>
              </tr>
              <tr style="${isLeaking ? 'background:rgba(239,68,68,0.1); border-left:3px solid var(--status-blocked);' : ''}">
                <td><strong>lender.md</strong></td>
                <td>
                  <span class="badge ${isLeaking ? 'badge-blocked' : 'badge-verified'}">
                    ${isLeaking ? 'FAIL (LEAK)' : 'PASS'}
                  </span>
                </td>
                <td>${isLeaking ? '<span style="color:var(--status-blocked-text); font-weight:700;">Northwind Analytics (LEAK)</span>' : 'Project Falcon'}</td>
                <td style="color:${isLeaking ? 'var(--status-blocked-text); font-weight:700;' : 'var(--text-muted)'};">
                  ${isLeaking ? '⚠️ CANARY LEAKED!' : 'None (Contained)'}
                </td>
                <td>
                  <span class="mono-tag" style="${isLeaking ? 'color:var(--status-blocked-text); border-color:var(--status-blocked);' : ''}">
                    ${isLeaking ? 'QUARANTINED' : 'Delivered'}
                  </span>
                </td>
              </tr>
              <tr>
                <td><strong>board.md</strong></td>
                <td><span class="badge badge-verified">PASS</span></td>
                <td>Northwind Analytics</td>
                <td style="color:var(--text-muted);">None (Contained)</td>
                <td><span class="mono-tag">Delivered</span></td>
              </tr>
              <tr>
                <td><strong>cloud_llm.md</strong></td>
                <td><span class="badge badge-verified">PASS</span></td>
                <td>[TARGET_NAME_1]</td>
                <td style="color:var(--text-muted);">None (Contained)</td>
                <td><span class="mono-tag">Delivered</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Canary Explanation Box -->
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:var(--space-3); font-size:var(--text-xs); color:var(--text-secondary); line-height:1.6;">
          <strong>Canary Audit Protocol:</strong> The synthetic advisor name <em>"Zephyrine Quillfeather"</em> was seeded into segment #12 of the meeting audio. Clean Room policy permits this name strictly in internal <code>deal_team</code> dossiers. Any presence in <code>outside_counsel</code>, <code>lender</code>, <code>board</code>, or external AI boundary logs automatically marks the output as quarantined.
        </div>
      </div>
    `;

    this.attachEvents(container, meetingId);
  }

  static attachEvents(container, meetingId) {
    const btnPlant = container.querySelector("#btn-plant-leak");
    if (btnPlant) {
      btnPlant.addEventListener("click", async () => {
        btnPlant.textContent = "Planting Leak...";
        await ApiClient.plantLeak(meetingId, "lender");
        store.setState({ isLeakPlanted: true });
      });
    }

    const btnRevert = container.querySelector("#btn-revert-leak");
    if (btnRevert) {
      btnRevert.addEventListener("click", () => {
        store.setState({ isLeakPlanted: false });
      });
    }
  }
}
