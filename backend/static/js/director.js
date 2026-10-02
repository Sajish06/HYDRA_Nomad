/**
 * Meetily Clean Room - Director Mode Player
 * Guided presentation controller matching docs/DEMO.md (4-minute script)
 */
import { store } from "./store.js";
import { GateRail } from "./panels/gate.js";

export const DIRECTOR_STEPS = [
  {
    title: "1. Due Diligence Ingestion & Gate Hold",
    step: "verify",
    audience: "deal_team",
    claimId: "claim_vendor_50k",
    caption: "Pipeline ingested meeting audio. Gatekeeper halts release [HELD FOR REVIEW] due to 2 compliance infractions."
  },
  {
    title: "2. Spoken-Number Catch & Local Relocation",
    step: "verify",
    audience: "deal_team",
    claimId: "claim_vendor_50k",
    caption: "CATCH: AI summary claimed '$50,000 approved'. Normalizer caught spoken audio 'fifteen thousand' ($15k) at 00:01:12."
  },
  {
    title: "3. Cross-Source Contradiction: CIM vs Audio",
    step: "crosscheck",
    audience: "deal_team",
    claimId: null,
    caption: "CROSS-CHECK: Spoken EBITDA $4.2M contradicts CIM document stating $3.8M (-$400k variance). Sent to review queue."
  },
  {
    title: "4. Cloud Privacy Boundary & Token Scramble",
    step: "mask",
    audience: "cloud_llm",
    claimId: null,
    caption: "AIRLOCK BOUNDARY: Raw text never exits process. External cloud sees strictly pseudonymized tokens [PERSON_1], [ORG_1]."
  },
  {
    title: "5. Human Review Loop & Gate Release",
    step: "review",
    audience: "deal_team",
    claimId: null,
    caption: "HUMAN CLEARANCE: Compliance officer corrects $50k to $15k and approves CIM note. The physical gate unlocks!"
  },
  {
    title: "6. Audience Morphing & Canary Containment",
    step: "distribute",
    audience: "lender",
    claimId: null,
    caption: "AUDIENCE FAN-OUT: Target becomes 'Project Falcon' for lenders; amounts become ranges for the Board. Canary safe in deal team."
  },
  {
    title: "7. Cryptographic Chain of Custody",
    step: "seal",
    audience: "deal_team",
    claimId: null,
    caption: "AUDIT LEDGER: 69 SHA-256 blocks chained from genesis. Modifying past SQLite rows visibly breaks chain verification."
  }
];

export class DirectorMode {
  static timer = null;

  static init() {
    // Keyboard listener
    window.addEventListener("keydown", (e) => {
      // Ignore when typing inside input or textarea
      if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;

      if (e.key === " " || e.code === "Space") {
        e.preventDefault();
        this.toggleAutoplay();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        this.next();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        this.prev();
      } else if (e.key.toLowerCase() === "r") {
        e.preventDefault();
        this.reset();
      } else if (e.key.toLowerCase() === "p") {
        e.preventDefault();
        this.togglePresenter();
      }
    });
  }

  static applyStep(index) {
    const s = DIRECTOR_STEPS[index];
    if (!s) return;

    store.setState({
      directorStepIndex: index,
      activeStep: s.step,
      activeAudience: s.audience
    });

    if (s.claimId) {
      setTimeout(() => {
        store.selectClaim(s.claimId);
      }, 100);
    }

    if (index >= 4 && !store.getState().isGateOpen) {
      store.setState({ isGateOpen: true });
      GateRail.playReleaseAnimation();
    }

    // Update Director caption bar
    const captionEl = document.querySelector("#caption-text-content");
    const indicatorEl = document.querySelector("#director-step-number");
    if (captionEl) captionEl.textContent = s.caption;
    if (indicatorEl) indicatorEl.textContent = `Step ${index + 1} of ${DIRECTOR_STEPS.length}`;
  }

  static next() {
    const cur = store.getState().directorStepIndex;
    const nextIdx = (cur + 1) % DIRECTOR_STEPS.length;
    this.applyStep(nextIdx);
  }

  static prev() {
    const cur = store.getState().directorStepIndex;
    const prevIdx = (cur - 1 + DIRECTOR_STEPS.length) % DIRECTOR_STEPS.length;
    this.applyStep(prevIdx);
  }

  static reset() {
    this.stopAutoplay();
    store.setState({
      isGateOpen: false,
      isTampered: false,
      isLeakPlanted: false
    });
    this.applyStep(0);
  }

  static toggleAutoplay() {
    const btn = document.querySelector("#btn-director-autoplay");
    if (this.timer) {
      this.stopAutoplay();
      if (btn) btn.classList.remove("active");
    } else {
      this.startAutoplay();
      if (btn) btn.classList.add("active");
    }
  }

  static startAutoplay() {
    this.timer = setInterval(() => {
      this.next();
    }, 8000); // 8s per step = ~1 minute full cycle
  }

  static stopAutoplay() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  static togglePresenter() {
    const isPresenter = !store.getState().presenterMode;
    store.setState({ presenterMode: isPresenter });
    document.body.classList.toggle("presenter-mode", isPresenter);
    const btn = document.querySelector("#btn-toggle-presenter");
    if (btn) btn.classList.toggle("active", isPresenter);
  }
}
