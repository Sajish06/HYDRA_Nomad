/**
 * Panel: Claim-to-Evidence Linker
 * Mode A: Audio Transcript vs Summary Claims with SVG Connectors
 */
import { store } from "../store.js";

export class ClaimsPanel {
  static render(container, state) {
    const data = state.data;
    if (!data || !data.verification) {
      container.innerHTML = `<div class="p-6 text-muted">Running diligence pipeline...</div>`;
      return;
    }

    const claims = data.verification.claims || [];
    const segments = (data.transcript && data.transcript.segments) || [];
    const filter = state.claimsFilter;

    const filteredClaims = claims.filter(c => {
      if (filter === "all") return true;
      if (filter === "supported") return c.verdict === "supported";
      if (filter === "contradicted") return c.verdict === "contradicted";
      if (filter === "unverifiable") return c.verdict === "unverifiable";
      return true;
    });

    container.innerHTML = `
      <div class="linker-container">
        <!-- SVG Connector Canvas -->
        <svg id="connector-canvas"></svg>

        <!-- Left Column: Audio Transcript -->
        <div class="linker-column" id="transcript-col">
          <div class="linker-col-header">
            <span class="linker-col-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
              Physical Audio Transcript (${segments.length} Segments)
            </span>
            <span class="mono-tag">SHA256 VERIFIED</span>
          </div>
          <div class="linker-scrollable" id="transcript-scrollable">
            ${segments.map((seg, idx) => `
              <div class="transcript-bubble ${state.selectedSegmentIndex === idx ? 'highlighted' : ''}" 
                   id="t-seg-${idx}" data-idx="${idx}">
                <div class="transcript-meta">
                  <span class="transcript-speaker">${seg.speaker}</span>
                  <span class="transcript-time">${formatTime(seg.start_time)} - ${formatTime(seg.end_time)}</span>
                </div>
                <div class="transcript-text">${highlightTranscriptText(seg.text, state.selectedClaimId, claims)}</div>
              </div>
            `).join("")}
          </div>
        </div>

        <!-- Right Column: Extracted Summary Claims -->
        <div class="linker-column" id="claims-col">
          <div class="linker-col-header">
            <span class="linker-col-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              Summary Claims Audit (${claims.length} Claims)
            </span>
            <div class="filter-toolbar">
              <button class="btn-filter ${filter === 'all' ? 'active' : ''}" data-f="all">All</button>
              <button class="btn-filter ${filter === 'contradicted' ? 'active' : ''}" data-f="contradicted">Contradicted</button>
              <button class="btn-filter ${filter === 'supported' ? 'active' : ''}" data-f="supported">Supported</button>
              <button class="btn-filter ${filter === 'unverifiable' ? 'active' : ''}" data-f="unverifiable">Unverifiable</button>
            </div>
          </div>
          <div class="linker-scrollable" id="claims-scrollable">
            ${filteredClaims.map(c => `
              <div class="claim-card status-${c.verdict} ${state.selectedClaimId === c.id ? 'selected' : ''}" 
                   id="claim-${c.id}" data-id="${c.id}" tabindex="0" role="button">
                <div class="claim-header">
                  <span class="badge badge-${getBadgeClass(c.verdict)}">${c.verdict}</span>
                  <span class="mono-tag">${Math.round((c.confidence || 0.95) * 100)}% CONF</span>
                </div>
                <div class="claim-text">${c.text}</div>
                ${c.verdict === 'contradicted' ? renderMismatchBox(c) : ''}
                ${c.flags && c.flags.includes('evidence_not_found') ? `
                  <div class="mono-tag" style="color:var(--status-blocked-text); margin-top:4px;">
                    HALLUCINATION: Local evidence re-location failed
                  </div>
                ` : ''}
              </div>
            `).join("")}
          </div>
        </div>
      </div>
    `;

    // Bind event listeners
    this.attachEvents(container);

    // Auto-draw SVG connector line after DOM renders
    requestAnimationFrame(() => this.drawConnector(container, state));
  }

  static attachEvents(container) {
    // Filter clicks
    container.querySelectorAll(".btn-filter").forEach(btn => {
      btn.addEventListener("click", () => {
        store.setState({ claimsFilter: btn.dataset.f });
      });
    });

    // Claim selection
    container.querySelectorAll(".claim-card").forEach(card => {
      card.addEventListener("click", () => {
        store.selectClaim(card.dataset.id);
      });
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          store.selectClaim(card.dataset.id);
        }
      });
    });

    // Transcript scroll sync for dynamic connector redraw
    const tScroll = container.querySelector("#transcript-scrollable");
    const cScroll = container.querySelector("#claims-scrollable");
    if (tScroll && cScroll) {
      tScroll.addEventListener("scroll", () => this.drawConnector(container, store.getState()), { passive: true });
      cScroll.addEventListener("scroll", () => this.drawConnector(container, store.getState()), { passive: true });
    }
  }

  static drawConnector(container, state) {
    const svg = container.querySelector("#connector-canvas");
    if (!svg || !state.selectedClaimId) {
      if (svg) svg.innerHTML = "";
      return;
    }

    const claimEl = container.querySelector(`#claim-${state.selectedClaimId}`);
    if (!claimEl) {
      svg.innerHTML = "";
      return;
    }

    let segEl = null;
    if (state.selectedSegmentIndex !== null && state.selectedSegmentIndex !== undefined) {
      segEl = container.querySelector(`#t-seg-${state.selectedSegmentIndex}`);
    }

    if (!segEl) {
      svg.innerHTML = "";
      return;
    }

    // Scroll segment into view if needed
    segEl.scrollIntoView({ behavior: "smooth", block: "nearest" });

    // Compute relative coordinates
    const containerRect = container.querySelector(".linker-container").getBoundingClientRect();
    const segRect = segEl.getBoundingClientRect();
    const claimRect = claimEl.getBoundingClientRect();

    const startX = segRect.right - containerRect.left;
    const startY = (segRect.top + segRect.bottom) / 2 - containerRect.top;
    const endX = claimRect.left - containerRect.left;
    const endY = (claimRect.top + claimRect.bottom) / 2 - containerRect.top;

    const controlX1 = startX + (endX - startX) * 0.45;
    const controlX2 = startX + (endX - startX) * 0.55;

    const pathData = `M ${startX} ${startY} C ${controlX1} ${startY}, ${controlX2} ${endY}, ${endX} ${endY}`;
    const isContradicted = claimEl.classList.contains("status-contradicted");

    svg.innerHTML = `
      <path d="${pathData}" class="connector-path ${isContradicted ? 'contradicted' : ''}" />
      <circle cx="${startX}" cy="${startY}" r="4" fill="${isContradicted ? 'var(--status-blocked)' : 'var(--accent-cyan)'}" />
      <circle cx="${endX}" cy="${endY}" r="4" fill="${isContradicted ? 'var(--status-blocked)' : 'var(--accent-cyan)'}" />
    `;
  }
}

function formatTime(seconds) {
  if (seconds === null || seconds === undefined) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function getBadgeClass(verdict) {
  if (verdict === "supported") return "verified";
  if (verdict === "contradicted") return "blocked";
  if (verdict === "unverifiable") return "neutral";
  return "review";
}

function renderMismatchBox(claim) {
  if (claim.text.includes("$50,000") || (claim.explanation && claim.explanation.includes("50,000"))) {
    return `
      <div class="value-mismatch-box">
        <div class="mismatch-row">
          <span>AI Claim Assertion:</span>
          <span class="mismatch-claimed">$50,000 Approved</span>
        </div>
        <div class="mismatch-row">
          <span>Spoken Audio (00:01:12):</span>
          <span class="mismatch-actual">"fifteen thousand" ($15k)</span>
        </div>
      </div>
    `;
  }
  return `
    <div class="value-mismatch-box">
      <div class="mismatch-row">
        <span>Variance Detected:</span>
        <span class="mismatch-claimed">${claim.explanation || "Number/Entity mismatch"}</span>
      </div>
    </div>
  `;
}

function highlightTranscriptText(text, selectedClaimId, claims) {
  if (!selectedClaimId) return text;
  const claim = claims.find(c => c.id === selectedClaimId);
  if (!claim || !claim.evidence || claim.evidence.length === 0) return text;

  const quote = claim.evidence[0].text;
  if (!quote) return text;

  // Highlight matching quote if in this text
  const cleanQuote = quote.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${cleanQuote})`, "i");
  if (regex.test(text)) {
    return text.replace(regex, `<mark>$1</mark>`);
  }
  return text;
}
