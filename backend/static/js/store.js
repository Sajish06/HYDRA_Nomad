/**
 * Meetily Clean Room - Central Reactive Store
 */

class Store {
  constructor() {
    this.state = {
      data: null,
      isLoading: false,
      isOffline: false,
      activeStep: "verify", // ingest, verify, crosscheck, mask, gate, review, distribute, seal
      activeAudience: "deal_team", // deal_team, outside_counsel, lender, board, cloud_llm
      selectedClaimId: null,
      selectedSegmentIndex: null,
      claimsFilter: "all",
      highlightChangesOnly: false,
      maskScrubProgress: 1.0, // 0 = original, 1 = tokenized
      presenterMode: false,
      directorMode: true,
      directorStepIndex: 0,
      isGateOpen: false,
      isTampered: false,
      isLeakPlanted: false,
      bytesSentToAI: 486
    };
    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  setState(partial) {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  notify() {
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  setStep(step) {
    this.setState({ activeStep: step });
  }

  setAudience(aud) {
    this.setState({ activeAudience: aud });
  }

  selectClaim(claimId) {
    let segmentIndex = null;
    if (this.state.data && this.state.data.verification) {
      const claim = this.state.data.verification.claims.find(c => c.id === claimId);
      if (claim && claim.evidence && claim.evidence.length > 0) {
        segmentIndex = claim.evidence[0].segment_index;
      }
    }
    this.setState({ selectedClaimId: claimId, selectedSegmentIndex: segmentIndex });
  }
}

export const store = new Store();
