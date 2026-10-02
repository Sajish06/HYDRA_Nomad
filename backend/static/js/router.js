/**
 * Meetily Clean Room - URL Hash Deep Linking
 */
import { store } from "./store.js";

export class Router {
  static init() {
    window.addEventListener("hashchange", () => this.handleHash());
    this.handleHash(); // initial check

    // Subscribe to store to update URL hash
    store.subscribe((state) => {
      const targetHash = `#step=${state.activeStep}&audience=${state.activeAudience}`;
      if (window.location.hash !== targetHash) {
        window.history.replaceState(null, "", targetHash);
      }
    });
  }

  static handleHash() {
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    const params = new URLSearchParams(hash);
    const step = params.get("step");
    const audience = params.get("audience");

    const updates = {};
    if (step && ["ingest", "verify", "crosscheck", "mask", "gate", "review", "distribute", "seal"].includes(step)) {
      updates.activeStep = step;
    }
    if (audience && ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"].includes(audience)) {
      updates.activeAudience = audience;
    }
    if (Object.keys(updates).length > 0) {
      store.setState(updates);
    }
  }
}
