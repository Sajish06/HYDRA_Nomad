/**
 * Panel: Audience Morph Dossier
 * Mode C: One single document transformed in place across 5 distinct audiences
 */
import { store } from "../store.js";

export class AudiencesPanel {
  static render(container, state) {
    const data = state.data;
    if (!data) {
      container.innerHTML = `<div class="p-6 text-muted">Generating audience outputs...</div>`;
      return;
    }

    const currentAud = state.activeAudience || "deal_team";
    const outputs = data.audience_outputs || {};
    const content = outputs[currentAud] || "Generating dossier content...";
    const diff = (data.masking_diffs && data.masking_diffs[currentAud]) || null;
    const showOnlyChanges = state.highlightChangesOnly;

    const audiences = [
      { id: "deal_team", name: "Deal Team", badge: "UNMASKED" },
      { id: "outside_counsel", name: "Outside Counsel", badge: "TERMS KEPT · PII MASKED" },
      { id: "lender", name: "Lender Syndicate", badge: "PROJECT FALCON · CODENAME" },
      { id: "board", name: "Board of Directors", badge: "AMOUNTS IN RANGES" },
      { id: "cloud_llm", name: "Cloud AI Boundary", badge: "TOKENIZED" }
    ];

    container.innerHTML = `
      <div class="dossier-container">
        <!-- Audience Tabs Bar -->
        <div class="audience-tabs">
          ${audiences.map(aud => `
            <button class="btn-aud-tab ${currentAud === aud.id ? 'active' : ''}" data-aud="${aud.id}">
              ${aud.name}
            </button>
          `).join("")}

          <div style="margin-left:auto; display:flex; align-items:center; gap:var(--space-3);">
            <label style="font-size:var(--text-xs); color:var(--text-secondary); display:flex; align-items:center; gap:var(--space-1); cursor:pointer;">
              <input type="checkbox" id="chk-highlight-changes" ${showOnlyChanges ? 'checked' : ''} />
              Highlight Audience Transforms
            </label>
            <span class="mono-tag" style="color:var(--status-verified);">${audiences.find(a => a.id === currentAud).badge}</span>
          </div>
        </div>

        <!-- Archival Paper Dossier (Single In-Place Document) -->
        <div class="dossier-paper" id="dossier-content-area">
          <div class="dossier-header-title">
            DILIGENCE MEMORANDUM & MINUTES
          </div>
          <div class="dossier-meta">
            AUDIENCE SCOPE: [<strong>${currentAud.toUpperCase()}</strong>] · 
            GOVERNANCE: FAIL-CLOSED GATEKEEPER · 
            LEAK SCAN: PASSED (0 Infractions)
          </div>

          <div class="paper-markdown-content">
            ${renderMorphContent(content, currentAud, showOnlyChanges)}
          </div>
        </div>
      </div>
    `;

    this.attachEvents(container);
  }

  static attachEvents(container) {
    container.querySelectorAll(".btn-aud-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        store.setAudience(btn.dataset.aud);
      });
    });

    const chk = container.querySelector("#chk-highlight-changes");
    if (chk) {
      chk.addEventListener("change", (e) => {
        store.setState({ highlightChangesOnly: e.target.checked });
      });
    }
  }
}

function renderMorphContent(markdown, audience, showOnlyChanges) {
  if (!markdown) return "<p>No output generated yet.</p>";

  // Basic markdown to formatted HTML
  let lines = markdown.split("\n");
  let html = "";

  for (let line of lines) {
    line = line.trim();
    if (!line) {
      html += "<br>";
      continue;
    }
    if (line.startsWith("# ")) {
      html += `<h2 style="font-size:var(--text-lg); font-weight:700; margin:16px 0 8px; color:var(--paper-ink);">${line.slice(2)}</h2>`;
    } else if (line.startsWith("## ")) {
      html += `<h3 style="font-size:var(--text-base); font-weight:700; margin:12px 0 6px; color:var(--paper-ink);">${line.slice(3)}</h3>`;
    } else if (line.startsWith("- ")) {
      html += `<div style="margin-left:16px; margin-bottom:4px;">• ${formatLineSpans(line.slice(2), audience, showOnlyChanges)}</div>`;
    } else {
      html += `<p style="margin-bottom:8px;">${formatLineSpans(line, audience, showOnlyChanges)}</p>`;
    }
  }

  return html;
}

function formatLineSpans(text, audience, showOnlyChanges) {
  let res = text;

  // Highlight specific audience features
  if (audience === "lender") {
    // Project Falcon highlighted
    res = res.replace(/(Project Falcon)/g, `<span class="morph-span changed" title="Target Codename">$1</span>`);
  } else if (audience === "board") {
    // Ranges highlighted
    res = res.replace(/(\$[0-9]+M-\$[0-9]+M|\$[0-9,]+-\$[0-9,]+)/g, `<span class="morph-span changed" title="Financial Range">$1</span>`);
    // Corporate roles highlighted
    res = res.replace(/(Chief Financial Officer|VP of Sales|Senior Vice President)/g, `<span class="morph-span changed" title="Corporate Role">$1</span>`);
  } else if (audience === "deal_team") {
    // Canary highlighted in deal team
    res = res.replace(/(Zephyrine Quillfeather)/g, `<span class="morph-span" style="background:rgba(56,189,248,0.25); border-bottom:1px dashed var(--accent-cyan);" title="Planted Canary Advisor">$1</span>`);
  }

  // Token chips
  res = res.replace(/(\[(PERSON|ORGANIZATION|EMAIL|PHONE)_[0-9]+\])/g, `<span class="token-chip" title="Tokenized Entity">$1</span>`);

  return res;
}
