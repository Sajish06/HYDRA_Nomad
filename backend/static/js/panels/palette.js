/**
 * Component: Command Palette (Ctrl+K)
 * "Ask the Room" with audience-masked cited answers
 */
import { store } from "../store.js";
import { ApiClient } from "../api.js";

export class CommandPalette {
  static init() {
    let backdrop = document.querySelector("#palette-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.id = "palette-backdrop";
      backdrop.className = "palette-backdrop";
      document.body.appendChild(backdrop);
    }

    backdrop.innerHTML = `
      <div class="palette-box">
        <input type="text" class="palette-input" id="palette-search-input" 
               placeholder="Ask the room or run a compliance command... (e.g. EBITDA, expenditure, canary)" />
        <div class="palette-results" id="palette-results-list">
          <div style="padding:var(--space-2); font-size:var(--text-2xs); color:var(--text-muted); text-transform:uppercase; font-weight:700;">
            Suggested Diligence Queries:
          </div>
          <div class="palette-item" data-q="What was the EBITDA?">
            📊 What was the confirmed EBITDA figure?
          </div>
          <div class="palette-item" data-q="Who approved the vendor expenditure and for how much?">
            💰 What vendor expenditure was approved by Sarah Chen?
          </div>
          <div class="palette-item" data-q="Were there any plans for Australia expansion?">
            🌏 Did Northwind discuss expanding to Australia?
          </div>
          <div class="palette-item" data-q="What is the customer concentration risk?">
            ⚠️ What is the top-3 customer concentration?
          </div>
          <div class="palette-item" data-q="Who is Zephyrine Quillfeather?">
            🕵️ Who is Zephyrine Quillfeather? (Canary Check)
          </div>
          <div id="palette-answer-area" style="display:none; margin-top:var(--space-2); padding:var(--space-3); background:var(--bg-void); border:1px solid var(--accent-cyan); border-radius:var(--radius-sm);"></div>
        </div>
      </div>
    `;

    // Keyboard shortcut (Ctrl+K / Cmd+K / Esc)
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        this.toggle();
      } else if (e.key === "Escape" && backdrop.classList.contains("active")) {
        this.close();
      }
    });

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) this.close();
    });

    // Query selection
    backdrop.querySelectorAll(".palette-item").forEach(item => {
      item.addEventListener("click", () => {
        const q = item.dataset.q;
        const input = backdrop.querySelector("#palette-search-input");
        if (input) input.value = q;
        this.executeSearch(q);
      });
    });

    const input = backdrop.querySelector("#palette-search-input");
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && input.value.trim()) {
          this.executeSearch(input.value.trim());
        }
      });
    }
  }

  static toggle() {
    const backdrop = document.querySelector("#palette-backdrop");
    if (!backdrop) return;
    backdrop.classList.toggle("active");
    if (backdrop.classList.contains("active")) {
      const input = backdrop.querySelector("#palette-search-input");
      if (input) {
        input.value = "";
        input.focus();
      }
    }
  }

  static close() {
    const backdrop = document.querySelector("#palette-backdrop");
    if (backdrop) backdrop.classList.remove("active");
  }

  static async executeSearch(query) {
    const answerArea = document.querySelector("#palette-answer-area");
    if (!answerArea) return;

    answerArea.style.display = "block";
    answerArea.innerHTML = `<div style="color:var(--text-secondary); font-size:var(--text-xs);">Scanning verified minutes...</div>`;

    const state = store.getState();
    const meetingId = (state.data && state.data.meeting_id) || "demo_falcon_diligence";
    const res = await ApiClient.askRoom(meetingId, query, state.activeAudience);

    answerArea.innerHTML = `
      <div style="font-size:var(--text-xs); color:var(--accent-cyan); font-weight:700; margin-bottom:4px;">
        ANSWER (MASKED FOR: ${state.activeAudience.toUpperCase()}):
      </div>
      <div style="font-size:var(--text-sm); color:var(--text-primary); margin-bottom:8px; line-height:1.5;">
        ${res.answer}
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span class="mono-tag" style="color:var(--status-verified-text);">CITATION: ${res.citation}</span>
        <button class="btn-director" id="btn-palette-jump" style="padding:2px 8px; font-size:var(--text-2xs);">
          Jump to Source →
        </button>
      </div>
    `;

    const btnJump = answerArea.querySelector("#btn-palette-jump");
    if (btnJump) {
      btnJump.addEventListener("click", () => {
        this.close();
        store.setStep("verify");
      });
    }
  }
}
