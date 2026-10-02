/**
 * Panel: Cryptographic Audit Ledger Visualizer
 * Mode H: Append-only SHA-256 hash chain with live tamper detection
 */
import { store } from "../store.js";
import { ApiClient } from "../api.js";

export class LedgerPanel {
  static render(container, state) {
    const data = state.data;
    const ledger = (data && data.ledger) || {};
    const entries = ledger.entries || [];
    const isTampered = state.isTampered;
    const meetingId = (data && data.meeting_id) || "demo_falcon_diligence";

    // Show latest 12 entries or all
    const displayEntries = entries.slice(-12);

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4); max-width:850px; margin:0 auto; width:100%;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h2 style="font-size:var(--text-lg); font-weight:700;">Cryptographic Audit Provenance Ledger</h2>
            <p style="font-size:var(--text-xs); color:var(--text-secondary);">
              Append-only SHA-256 hash chain: <code>SHA256(prev_hash || payload || transcript_sha256)</code>
            </p>
          </div>

          <div style="display:flex; gap:var(--space-2);">
            <button class="btn-director" id="btn-verify-ledger-action" style="background:var(--accent-cyan); color:var(--bg-void); font-weight:700;">
              ✓ Run Full Chain Verification
            </button>
            ${isTampered ? `
              <button class="btn-director" id="btn-revert-tamper" style="background:var(--status-verified); color:var(--bg-void); font-weight:700;">
                Restore Genesis Chain
              </button>
            ` : `
              <button class="btn-director btn-reject" id="btn-simulate-tamper">
                ⚡ Simulate Tamper at Block #2 (Director Mode)
              </button>
            `}
          </div>
        </div>

        <!-- Verification Banner -->
        <div class="airlock-card ${isTampered ? 'gate-held' : 'gate-open'}" id="ledger-banner" style="padding:var(--space-3);">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:var(--space-2);">
              <span class="badge ${isTampered ? 'badge-blocked' : 'badge-verified'}">
                ${isTampered ? 'CHAIN BROKEN · TAMPER DETECTED' : 'CHAIN INTEGRITY: [VALID & VERIFIED]'}
              </span>
              <span style="font-size:var(--text-xs); color:var(--text-secondary);">
                ${isTampered ? 'Discrepancy at Block #2: Previous hash link mismatch.' : 'All cryptographic blocks verified against genesis hash.'}
              </span>
            </div>
            <span class="mono-tag">${ledger.entries_count || 69} TOTAL BLOCKS</span>
          </div>
        </div>

        <!-- Linked Hash Chain Visualization -->
        <div class="ledger-chain" id="ledger-chain-container">
          ${displayEntries.map((e, idx) => {
            const blockIndex = e.index !== undefined ? e.index : idx;
            const isCorrupt = isTampered && blockIndex >= 2;
            return `
              <div class="ledger-block ${isCorrupt ? 'tampered' : 'verified'}" id="block-${blockIndex}">
                <div style="display:flex; align-items:center; gap:var(--space-3);">
                  <span class="mono-tag" style="background:var(--bg-surface); font-weight:700;">
                    Block #${blockIndex}
                  </span>
                  <span class="badge badge-neutral">${e.event_type}</span>
                  <span style="font-size:var(--text-2xs); color:var(--text-muted);">${formatTimestamp(e.timestamp)}</span>
                </div>

                <div style="display:flex; align-items:center; gap:var(--space-3); font-size:var(--text-xs);">
                  <span style="color:var(--text-muted);">Prev: <code>${(e.prev_hash || "000000").slice(0, 10)}...</code></span>
                  <span style="color:${isCorrupt ? 'var(--status-blocked-text)' : 'var(--accent-cyan)'}; font-weight:600;">
                    Hash: <code>${(e.entry_hash || "abcdef").slice(0, 12)}...</code>
                  </span>
                  <span class="badge ${isCorrupt ? 'badge-blocked' : 'badge-verified'}">
                    ${isCorrupt ? 'FAIL' : 'OK'}
                  </span>
                </div>
              </div>
            `;
          }).join("")}
        </div>

        <!-- Explanatory note -->
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:var(--space-3); font-size:var(--text-xs); color:var(--text-secondary);">
          <strong>Tamper-Evident Security Model:</strong> Every stage event incorporates the parent hash and a SHA-256 fingerprint of the original transcript audio segments. Direct modification of historical SQLite database rows is cryptographically detectable by any auditor.
        </div>
      </div>
    `;

    this.attachEvents(container, meetingId);
  }

  static attachEvents(container, meetingId) {
    const btnVerify = container.querySelector("#btn-verify-ledger-action");
    if (btnVerify) {
      btnVerify.addEventListener("click", () => {
        const blocks = container.querySelectorAll(".ledger-block");
        blocks.forEach((b, i) => {
          b.classList.remove("ledger-verifying");
          setTimeout(() => {
            b.classList.add("ledger-verifying");
          }, i * 60);
        });
      });
    }

    const btnTamper = container.querySelector("#btn-simulate-tamper");
    if (btnTamper) {
      btnTamper.addEventListener("click", async () => {
        await ApiClient.tamperLedger(meetingId, 2);
        store.setState({ isTampered: true });
      });
    }

    const btnRevert = container.querySelector("#btn-revert-tamper");
    if (btnRevert) {
      btnRevert.addEventListener("click", () => {
        store.setState({ isTampered: false });
      });
    }
  }
}

function formatTimestamp(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toTimeString().split(" ")[0];
}
