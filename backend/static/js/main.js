/**
 * Meetily Clean Room - Main Application Bootstrap
 * Orchestrates store subscriptions, router, director, and panel renders.
 */
import { store } from "./store.js";
import { ApiClient } from "./api.js";
import { Router } from "./router.js";
import { DirectorMode, DIRECTOR_STEPS } from "./director.js";
import { CommandPalette } from "./panels/palette.js";
import { ClaimsPanel } from "./panels/claims.js";
import { MaskingPanel } from "./panels/masking.js";
import { AudiencesPanel } from "./panels/audiences.js";
import { CrosscheckPanel } from "./panels/crosscheck.js";
import { ReviewPanel } from "./panels/review.js";
import { LeakScanPanel } from "./panels/leakscan.js";
import { LedgerPanel } from "./panels/ledger.js";
import { GateRail } from "./panels/gate.js";

class App {
  static async init() {
    console.log("Initializing Meetily Clean Room Evidence Console...");

    // 1. Initialize Subsystems
    CommandPalette.init();
    DirectorMode.init();
    Router.init();

    // 2. Setup Top Bar Actions
    this.bindTopBarEvents();
    this.bindLeftRailEvents();

    // 3. Subscribe to Store State Changes
    store.subscribe((state) => {
      this.renderWorkspace(state);
    });

    // 4. Initial Pipeline Run (fetches live data or offline fixture)
    await this.loadDemoData();

    // 5. Initial Director Step Setup
    DirectorMode.applyStep(0);
  }

  static async loadDemoData() {
    const stage = document.querySelector("#center-stage");
    if (stage) {
      stage.innerHTML = `<div style="padding:var(--space-6); color:var(--text-secondary); text-align:center;">
        <div style="font-size:var(--text-lg); font-weight:700; color:var(--text-primary); margin-bottom:var(--space-2);">
          Ingesting Diligence Audio & Verifying Claims...
        </div>
        <p style="font-size:var(--text-xs); color:var(--text-muted);">
          Executing deterministic spoken-number normalizer and local evidence re-location.
        </p>
      </div>`;
    }

    const data = await ApiClient.runDemo();
    store.setState({
      data,
      isOffline: Boolean(data.isOfflineFixture),
      isGateOpen: data.gate_decision === "release"
    });

    // Show offline badge if running from fixture
    const offlineBadge = document.querySelector("#offline-fixture-badge");
    if (offlineBadge) {
      offlineBadge.style.display = data.isOfflineFixture ? "inline-flex" : "none";
    }
  }

  static renderWorkspace(state) {
    const stage = document.querySelector("#center-stage");
    const rightRail = document.querySelector("#right-rail");

    if (!stage || !rightRail) return;

    // 1. Render Left Rail Stepper Highlights
    document.querySelectorAll(".step-item").forEach(item => {
      const step = item.dataset.step;
      item.classList.toggle("active", state.activeStep === step);
    });

    // 2. Render Right Rail (Airlock Gate, Leak Scan, Ledger Summary)
    GateRail.render(rightRail, state);

    // 3. Render Center Stage according to Active Step
    switch (state.activeStep) {
      case "ingest":
      case "verify":
        ClaimsPanel.render(stage, state);
        break;
      case "crosscheck":
        CrosscheckPanel.render(stage, state);
        break;
      case "mask":
        MaskingPanel.render(stage, state);
        break;
      case "gate":
      case "review":
        ReviewPanel.render(stage, state);
        break;
      case "distribute":
        AudiencesPanel.render(stage, state);
        break;
      case "seal":
        LedgerPanel.render(stage, state);
        break;
      default:
        ClaimsPanel.render(stage, state);
    }
  }

  static bindTopBarEvents() {
    const btnNext = document.querySelector("#btn-director-next");
    if (btnNext) btnNext.addEventListener("click", () => DirectorMode.next());

    const btnPrev = document.querySelector("#btn-director-prev");
    if (btnPrev) btnPrev.addEventListener("click", () => DirectorMode.prev());

    const btnAutoplay = document.querySelector("#btn-director-autoplay");
    if (btnAutoplay) btnAutoplay.addEventListener("click", () => DirectorMode.toggleAutoplay());

    const btnReset = document.querySelector("#btn-director-reset");
    if (btnReset) btnReset.addEventListener("click", () => DirectorMode.reset());

    const btnPresenter = document.querySelector("#btn-toggle-presenter");
    if (btnPresenter) btnPresenter.addEventListener("click", () => DirectorMode.togglePresenter());

    const btnSearch = document.querySelector("#btn-open-palette");
    if (btnSearch) btnSearch.addEventListener("click", () => CommandPalette.toggle());

    const btnReRun = document.querySelector("#btn-rerun-demo");
    if (btnReRun) btnReRun.addEventListener("click", () => this.loadDemoData());
  }

  static bindLeftRailEvents() {
    document.querySelectorAll(".step-item").forEach(item => {
      item.addEventListener("click", () => {
        store.setStep(item.dataset.step);
      });
    });
  }
}

let activeIdxTab = "dual";

window.selectIndexUploadTab = function(tab) {
  activeIdxTab = tab;
  document.getElementById("idx-view-dual").style.display = tab === "dual" ? "block" : "none";
  document.getElementById("idx-view-single").style.display = tab === "single" ? "block" : "none";
  document.getElementById("idx-view-paste").style.display = tab === "paste" ? "block" : "none";

  document.getElementById("idx-tab-dual").className = tab === "dual" ? "btn-director active" : "btn-director";
  document.getElementById("idx-tab-single").className = tab === "single" ? "btn-director active" : "btn-director";
  document.getElementById("idx-tab-paste").className = tab === "paste" ? "btn-director active" : "btn-director";
};

// Global upload handler for index.html modal
window.submitCustomUploadIndex = async function() {
  const btn = document.getElementById("index-btn-submit-upload");
  const formData = new FormData();
  let hasData = false;

  if (activeIdxTab === "dual") {
    const tFile = document.getElementById("idx-transcript-file")?.files[0];
    const sFile = document.getElementById("idx-summary-file")?.files[0];
    if (!tFile) {
      alert("Please select at least a Raw Transcript file (*.txt, *.json, *.vtt).");
      return;
    }
    formData.append("transcript_file", tFile);
    if (sFile) formData.append("summary_file", sFile);
    hasData = true;
  } else if (activeIdxTab === "single") {
    const sFile = document.getElementById("idx-single-file")?.files[0];
    if (!sFile) {
      alert("Please select a JSON fixture file (*.json).");
      return;
    }
    formData.append("file", sFile);
    hasData = true;
  } else if (activeIdxTab === "paste") {
    const tText = (document.getElementById("idx-paste-transcript")?.value || "").trim();
    const sText = (document.getElementById("idx-paste-summary")?.value || "").trim();
    if (!tText) {
      alert("Please paste your raw transcript text.");
      return;
    }
    formData.append("transcript_text", tText);
    if (sText) formData.append("summary_text", sText);
    hasData = true;
  }

  if (!hasData) return;

  if (btn) {
    btn.textContent = "⏳ Running Verification Gate...";
    btn.disabled = true;
  }

  try {
    const resp = await fetch("/demo/verify", {
      method: "POST",
      body: formData
    });

    if (resp.ok) {
      const result = await resp.json();
      const modal = document.getElementById("upload-modal-index");
      if (modal) modal.style.display = "none";
      
      // Adapt verification result to Clean Room store structure
      const adaptedClaims = result.claims.map(c => ({
        id: c.claim_id,
        text: c.text,
        status: c.status === "VERIFIED" ? "supported" : (c.status === "AMBIGUOUS" ? "partial" : "contradicted"),
        verdict: c.status,
        gate_action: c.gate_action,
        explanation: c.explanation,
        evidence: (c.evidence_chain || []).map(e => ({
          speaker: e.speaker || "Speaker",
          time: e.time || "N/A",
          quote: e.quote,
          stance: e.stance
        }))
      }));

      store.setState({
        data: {
          meeting_id: result.meeting_id,
          title: result.title,
          gate_decision: result.claims.every(c => c.status === "VERIFIED") ? "release" : "held",
          reasons: result.claims.filter(c => c.status !== "VERIFIED").map(c => `${c.claim_id}: ${c.explanation}`),
          claims: adaptedClaims,
          crosscheck_conflicts: [],
          review_queue: [],
          ledger: { entries: [], chain_valid: true }
        },
        activeStep: "verify",
        isOffline: false
      });
    } else {
      let errDetail = "HTTP " + resp.status;
      try {
        const err = await resp.json();
        errDetail = err.detail?.message || err.detail?.error?.message || err.detail || JSON.stringify(err);
      } catch {
        errDetail = await resp.text();
      }
      alert("Verification failed: " + errDetail);
    }
  } catch (err) {
    alert("Upload error: " + err.message);
  } finally {
    if (btn) {
      btn.textContent = "🚀 Verify Claims Against Transcript";
      btn.disabled = false;
    }
  }
};

// Bootstrap on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  App.init();
});
