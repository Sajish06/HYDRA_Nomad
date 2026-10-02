/**
 * Meetily Clean Room - API Client
 * The sole module in the application that performs HTTP fetch calls.
 * Implements seamless offline fixture fallback.
 */

export class ApiClient {
  static isOffline = false;

  /**
   * Run the M&A diligence synthetic pipeline.
   * Falls back to offline fixture if server is unreachable.
   */
  static async runDemo() {
    try {
      const response = await fetch("/api/demo/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      this.isOffline = false;
      return await response.json();
    } catch (err) {
      console.warn("API unreachable, loading offline fixture:", err.message);
      this.isOffline = true;
      const fixtureResp = await fetch("/static/fixtures/demo-fixture.json");
      const data = await fixtureResp.json();
      data.isOfflineFixture = true;
      return data;
    }
  }

  /**
   * Submit reviewer decision on held item (approve, correct, reject).
   */
  static async reviewDecision(itemId, action, correction = null) {
    if (this.isOffline) {
      return { status: "simulated_resolved", action, item_id: itemId };
    }
    const resp = await fetch(`/api/review/${itemId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, correction })
    });
    return await resp.json();
  }

  /**
   * Fetch ledger entries and verification state.
   */
  static async getLedger(meetingId) {
    if (this.isOffline) return null;
    const resp = await fetch(`/api/meetings/${meetingId}/ledger`);
    return await resp.json();
  }

  /**
   * Director action: Plant an intentional canary leak.
   */
  static async plantLeak(meetingId, audience = "lender") {
    if (this.isOffline) {
      return { status: "leak_planted_simulated", audience };
    }
    const resp = await fetch(`/api/meetings/${meetingId}/plant-leak?audience=${audience}`, {
      method: "POST"
    });
    return await resp.json();
  }

  /**
   * Director action: Tamper with a ledger block payload.
   */
  static async tamperLedger(meetingId, index = 1) {
    if (this.isOffline) {
      return { status: "tampered", tampered_index: index, chain_valid: false };
    }
    const resp = await fetch(`/api/meetings/${meetingId}/tamper-ledger?index=${index}`, {
      method: "POST"
    });
    return await resp.json();
  }

  /**
   * Ask the room with audience-masked cited answers.
   */
  static async askRoom(meetingId, question, audience = "deal_team") {
    if (this.isOffline) {
      return {
        question,
        audience,
        answer: "Offline answer: EBITDA is $4.2M on $24M ARR.",
        citation: "transcript@00:00:43"
      };
    }
    const resp = await fetch(`/api/meetings/${meetingId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, audience })
    });
    return await resp.json();
  }
}
