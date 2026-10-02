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

// Bootstrap on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  App.init();
});
