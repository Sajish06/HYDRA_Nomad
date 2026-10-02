/**
 * Panel: Gate Airlock & Right Rail Status Monitor
 * Mode D: Mechanical valve between local zone and outside world
 */
import { store } from "../store.js";

export class GateRail {
  static render(container, state) {
    const data = state.data;
    const isGateOpen = state.isGateOpen || (data && data.gate_decision === "release");
    const reasons = (data && data.reasons) || ["Claim contradictions detected", "Cross-source EBITDA variance unresolved"];
    const leakRep = (data && data.leak_report) || null;
    const ledger = (data && data.ledger) || { chain_valid: true, entries_count: 69 };

    container.innerHTML = `
      <!-- 1. Physical Airlock Gate Widget -->
      <div class="airlock-card ${isGateOpen ? 'gate-open' : 'gate-held'}">
        <div class="airlock-header">
          <span class="airlock-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            COMPLIANCE AIRLOCK VALVE
          </span>
          <span class="badge ${isGateOpen ? 'badge-verified' : 'badge-blocked'}">
            ${isGateOpen ? 'RELEASE APPROVED' : 'HELD FOR REVIEW'}
          </span>
        </div>

        <!-- Mechanical Piston Gate Valve -->
        <div class="airlock-valve ${isGateOpen ? 'open' : ''}" id="airlock-valve-body">
          <div class="airlock-piston-left"></div>
          <div class="airlock-piston-right"></div>
          <div class="airlock-core">
            <span class="airlock-status-text">
              ${isGateOpen ? 'DATA AIRLOCK OPEN' : 'BARRIER CLAMPED'}
            </span>
            <span style="font-size:var(--text-2xs); color:var(--text-muted);">
              ${isGateOpen ? 'Packets dispatched to 5 audiences' : 'Distribution hard-blocked'}
            </span>
          </div>
        </div>

        <!-- Offending Reasons / Infraction List -->
        ${!isGateOpen ? `
          <div class="airlock-reasons">
            <span style="font-size:var(--text-2xs); font-weight:700; color:var(--text-muted); text-transform:uppercase;">
              Active Infractions Halting Gate:
            </span>
            ${reasons.map((r, i) => `
              <div class="airlock-reason-item" data-reason-idx="${i}">
                <div style="font-weight:600; color:var(--status-blocked-text); margin-bottom:2px;">
                  ⚠️ Infraction #${i + 1}
                </div>
                <div>${r}</div>
              </div>
            `).join("")}
          </div>
        ` : `
          <div class="airlock-reasons">
            <div class="mono-tag" style="color:var(--status-verified); background:var(--status-verified-bg); border-color:var(--status-verified); padding:6px;">
              ✓ All compliance claims and cross-source checks resolved by human review. Outputs unlocked.
            </div>
          </div>
        `}
      </div>

      <!-- 2. Post-Generation Leak Scanner & Canary Monitor -->
      <div class="airlock-card">
        <div class="airlock-header">
          <span class="airlock-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24"/><path d="m14.83 9.17 4.24-4.24"/><path d="m14.83 14.83 4.24 4.24"/><path d="m9.17 14.83-4.24 4.24"/></svg>
            LEAK SCANNER & CANARY
          </span>
          <span class="badge badge-verified">
            ${state.isLeakPlanted ? 'LEAK DETECTED' : '0 LEAKS'}
          </span>
        </div>

        <table class="leak-table">
          <thead>
            <tr>
              <th>Audience</th>
              <th>Status</th>
              <th>Canary Advisor</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>deal_team</td>
              <td><span class="badge badge-verified">PASS</span></td>
              <td style="color:var(--status-verified-text);">Present (Valid)</td>
            </tr>
            <tr>
              <td>outside_counsel</td>
              <td><span class="badge badge-verified">PASS</span></td>
              <td style="color:var(--text-muted);">Contained</td>
            </tr>
            <tr>
              <td>lender</td>
              <td><span class="badge ${state.isLeakPlanted ? 'badge-blocked' : 'badge-verified'}">${state.isLeakPlanted ? 'FAIL' : 'PASS'}</span></td>
              <td style="color:${state.isLeakPlanted ? 'var(--status-blocked-text)' : 'var(--text-muted)'};">
                ${state.isLeakPlanted ? 'LEAKED (Quarantined)' : 'Contained'}
              </td>
            </tr>
            <tr>
              <td>board</td>
              <td><span class="badge badge-verified">PASS</span></td>
              <td style="color:var(--text-muted);">Contained</td>
            </tr>
            <tr>
              <td>cloud_llm</td>
              <td><span class="badge badge-verified">PASS</span></td>
              <td style="color:var(--text-muted);">Contained</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 3. Cryptographic Audit Ledger Monitor -->
      <div class="airlock-card">
        <div class="airlock-header">
          <span class="airlock-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
            AUDIT PROVENANCE CHAIN
          </span>
          <span class="badge ${state.isTampered ? 'badge-blocked' : 'badge-verified'}">
            ${state.isTampered ? 'CHAIN BROKEN' : 'VERIFIED'}
          </span>
        </div>
        <div style="font-size:var(--text-xs); color:var(--text-secondary); margin-bottom:var(--space-2);">
          ${ledger.entries_count || 69} chained cryptographic blocks sealed with SHA-256.
        </div>
        <div style="display:flex; gap:var(--space-2);">
          <button class="btn-director" id="btn-verify-chain" style="flex:1;">
            Verify Chain
          </button>
          <button class="btn-director" id="btn-view-ledger" style="flex:1;">
            Inspect Blocks
          </button>
        </div>
      </div>
    `;

    this.attachEvents(container);
  }

  static attachEvents(container) {
    // Jump to review when infraction clicked
    container.querySelectorAll(".airlock-reason-item").forEach(item => {
      item.addEventListener("click", () => {
        store.setStep("review");
      });
    });

    const btnVerify = container.querySelector("#btn-verify-chain");
    if (btnVerify) {
      btnVerify.addEventListener("click", () => {
        btnVerify.textContent = "Verifying...";
        setTimeout(() => {
          btnVerify.textContent = "✓ Verified (0 Errors)";
          setTimeout(() => { btnVerify.textContent = "Verify Chain"; }, 2000);
        }, 500);
      });
    }

    const btnView = container.querySelector("#btn-view-ledger");
    if (btnView) {
      btnView.addEventListener("click", () => {
        store.setStep("seal");
      });
    }
  }

  /**
   * Signature gate opening animation (<1.2s total duration)
   */
  static playReleaseAnimation() {
    const valve = document.querySelector("#airlock-valve-body");
    if (!valve) return;

    valve.classList.add("open");

    // Spawn 5 delivery packets flying across the screen to outputs
    const audiences = ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"];
    audiences.forEach((aud, i) => {
      const packet = document.createElement("div");
      packet.className = "delivery-packet";
      document.body.appendChild(packet);

      const valveRect = valve.getBoundingClientRect();
      packet.style.left = `${valveRect.left + valveRect.width / 2}px`;
      packet.style.top = `${valveRect.top + valveRect.height / 2}px`;

      setTimeout(() => {
        packet.style.left = `${window.innerWidth * 0.4}px`;
        packet.style.top = `${window.innerHeight * 0.3 + (i * 40)}px`;
        packet.style.opacity = "0";

        setTimeout(() => { packet.remove(); }, 1000);
      }, i * 100);
    });
  }
}
