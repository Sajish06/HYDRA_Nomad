/**
 * Panel: Human Review Queue & Pipeline Resumption Loop
 * Mode F: Compliance clearance for held claims and cross-source variances
 */
import { store } from "../store.js";
import { ApiClient } from "../api.js";
import { GateRail } from "./gate.js";

export class ReviewPanel {
  static render(container, state) {
    const data = state.data;
    const reviewItems = (data && data.review_items) || [
      {
        id: "item_vendor_50k",
        item_type: "claim",
        original_text: "Sarah Chen approved $50,000 for vendor expenditures related to cloud migration.",
        issue_type: "Numeric mismatch: Claim asserts $50,000, but spoken transcript states 'fifteen thousand' ($15,000).",
        status: "pending"
      },
      {
        id: "item_ebitda_conflict",
        item_type: "conflict",
        original_text: "EBITDA discrepancy: Transcript states $4.2M, but CIM document states $3.8M.",
        issue_type: "Material 9.5% valuation variance between transcript and CIM data room.",
        status: "pending"
      }
    ];

    const activeItems = reviewItems.filter(it => it.status !== "resolved");

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4); max-width:800px; margin:0 auto; width:100%;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h2 style="font-size:var(--text-lg); font-weight:700;">Human Compliance Review Queue</h2>
            <p style="font-size:var(--text-xs); color:var(--text-secondary);">
              Gatekeeper halts release until compliance officer approves, corrects, or rejects held items.
            </p>
          </div>
          <span class="badge ${activeItems.length > 0 ? 'badge-review' : 'badge-verified'}">
            ${activeItems.length > 0 ? `${activeItems.length} PENDING DECISIONS` : 'ALL RESOLVED (GATE UNLOCKED)'}
          </span>
        </div>

        ${activeItems.length === 0 ? `
          <div style="background:var(--bg-surface); border:1px solid var(--status-verified); border-radius:var(--radius-md); padding:var(--space-6); text-align:center;">
            <div style="color:var(--status-verified); font-size:var(--text-xl); font-weight:700; margin-bottom:var(--space-2);">
              ✓ All Compliance Items Resolved
            </div>
            <p style="color:var(--text-secondary); font-size:var(--text-sm); margin-bottom:var(--space-4);">
              Pipeline resumed, corrected claims re-verified, leak scans passed, and audience dossiers released.
            </p>
            <button class="btn-director" id="btn-view-released" style="background:var(--accent-cyan); color:var(--bg-void); font-weight:700; padding:8px 16px;">
              View Released Audience Dossiers →
            </button>
          </div>
        ` : `
          <div class="review-items-list">
            ${activeItems.map(item => `
              <div class="review-item-card" id="rev-${item.id}">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                  <div>
                    <span class="badge badge-blocked">${item.item_type.toUpperCase()} HOLD</span>
                    <div style="font-size:var(--text-base); font-weight:600; color:var(--text-primary); margin-top:var(--space-1);">
                      ${item.original_text}
                    </div>
                  </div>
                  <span class="mono-tag" style="color:var(--status-blocked-text);">${item.issue_type}</span>
                </div>

                <!-- Inline Correction Field (Initially Hidden) -->
                <div class="correction-field" id="corr-box-${item.id}" style="display:none; margin-top:var(--space-2);">
                  <label style="font-size:var(--text-xs); color:var(--text-secondary);">Correct Claim Text (Re-verifies against audio):</label>
                  <input type="text" class="input-correct" id="input-${item.id}" 
                         value="Sarah Chen approved $15,000 for vendor expenditures related to cloud migration." 
                         style="width:100%; padding:6px; background:var(--bg-void); border:1px solid var(--accent-cyan); color:var(--text-primary); border-radius:var(--radius-xs); margin-top:4px;" />
                  <div style="display:flex; gap:var(--space-2); margin-top:6px;">
                    <button class="btn-director btn-approve" data-id="${item.id}" data-action="submit_correction">
                      ✓ Save & Re-verify
                    </button>
                    <button class="btn-director" data-id="${item.id}" data-action="cancel_correction">
                      Cancel
                    </button>
                  </div>
                </div>

                <!-- Primary Action Buttons -->
                <div class="review-actions" id="actions-${item.id}">
                  ${item.id.includes("50k") || item.item_type === "claim" ? `
                    <button class="btn-director btn-correct" data-id="${item.id}" data-action="show_correct">
                      ✎ Correct to $15k
                    </button>
                  ` : `
                    <button class="btn-director btn-approve" data-id="${item.id}" data-action="approve">
                      ✓ Approve As-Is (Notation Added)
                    </button>
                  `}
                  <button class="btn-director btn-approve" data-id="${item.id}" data-action="approve">
                    Approve As-Is
                  </button>
                  <button class="btn-director btn-reject" data-id="${item.id}" data-action="reject">
                    ✕ Reject Claim
                  </button>
                </div>
              </div>
            `).join("")}
          </div>
        `}
      </div>
    `;

    this.attachEvents(container, activeItems);
  }

  static attachEvents(container, activeItems) {
    const btnView = container.querySelector("#btn-view-released");
    if (btnView) {
      btnView.addEventListener("click", () => {
        store.setStep("distribute");
      });
    }

    container.querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const action = btn.dataset.action;

        if (action === "show_correct") {
          const corrBox = container.querySelector(`#corr-box-${id}`);
          const actionsBox = container.querySelector(`#actions-${id}`);
          if (corrBox) corrBox.style.display = "block";
          if (actionsBox) actionsBox.style.display = "none";
          return;
        }

        if (action === "cancel_correction") {
          const corrBox = container.querySelector(`#corr-box-${id}`);
          const actionsBox = container.querySelector(`#actions-${id}`);
          if (corrBox) corrBox.style.display = "none";
          if (actionsBox) actionsBox.style.display = "flex";
          return;
        }

        let correctionText = null;
        if (action === "submit_correction") {
          const input = container.querySelector(`#input-${id}`);
          correctionText = input ? input.value : null;
        }

        // Animate item card resolving
        const card = container.querySelector(`#rev-${id}`);
        if (card) {
          card.style.transition = "all 0.4s ease";
          card.style.opacity = "0.3";
          card.style.transform = "translateX(20px)";
        }

        // Submit decision to backend or simulate
        await ApiClient.reviewDecision(id, action === "submit_correction" ? "correct" : action, correctionText);

        // Update local item status
        const state = store.getState();
        if (state.data && state.data.review_items) {
          const match = state.data.review_items.find(it => it.id === id);
          if (match) match.status = "resolved";
        }

        // Check if all items resolved
        const remaining = activeItems.filter(it => it.id !== id);
        if (remaining.length === 0) {
          store.setState({ isGateOpen: true, activeStep: "distribute" });
          GateRail.playReleaseAnimation();
        } else {
          ReviewPanel.render(container, store.getState());
        }
      });
    });
  }
}
