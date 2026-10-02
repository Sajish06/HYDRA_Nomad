# Meetily Clean Room - UI Design Specification
**Concept: The Forensic Meeting Evidence Room & Compliance Airlock**

---

## 1. Design Concept

Traditional AI meeting tools act as passive SaaS dashboards with bubbly cards and purple-to-blue gradients. **Meetily Clean Room is an evidence vault and compliance gatekeeper for high-stakes M&A due diligence.**

The aesthetic is inspired by:
- **The Forensic Evidence Room**: Timestamped transcripts, audio segment tags, red margin contradiction flags, and physical chain-of-custody seals.
- **The Paper Case File**: Diligence dossiers rendered on archival, warm paper surfaces with precise typographic hierarchy, authentic redaction bars, and inline evidence badges.
- **The Airlock / Physical Gate**: A visible boundary valve between the confidential local machine and the outside world. When claims contradict or leaks threaten, the airlock physically seals; when human compliance approves, packets visually flow into audience-governed dossiers.

---

## 2. Color Palette & Contrast Specifications (WCAG AA Certified)

```css
/* Core Workspace: Deep Industrial Ink */
--bg-void:        #070a0f; /* Deepest background */
--bg-surface:     #0d131d; /* Left/right control rails */
--bg-card:        #141d2b; /* Interactive tool cards */
--bg-card-hover:  #1b273a; /* Hover state */
--border-subtle:  #212e42; /* Hairline dividers */
--border-focus:   #38bdf8; /* Focused control boundary */

/* Document Surfaces: Archival Warm Paper */
--paper-bg:       #f7f4ed; /* Authentic document surface */
--paper-card:     #efeae0; /* Nested document card */
--paper-border:   #dcd5c7; /* Document boundary */
--paper-ink:      #12161f; /* Primary document typography (14.2:1 contrast) */
--paper-muted:    #555d6e; /* Secondary document annotations (5.8:1 contrast) */
--paper-redacted: #161a22; /* Pure physical redaction bar */

/* Semantic Status Signals (Restrained, status-only) */
--status-verified:   #10b981; /* Supported / Verified (AA compliant) */
--status-verified-bg:#064e3b; 
--status-review:     #f59e0b; /* Hold / Review required */
--status-review-bg:  #78350f;
--status-blocked:    #ef4444; /* Contradicted / Quarantined */
--status-blocked-bg: #7f1d1d;
--accent-cyan:       #38bdf8; /* Single active brand accent */

/* Text Hierarchy on Ink Surfaces */
--text-primary:   #f1f5f9; /* Contrast > 15:1 against #070a0f */
--text-secondary: #94a3b8; /* Contrast > 6.5:1 against #070a0f */
--text-muted:     #64748b; /* Contrast > 4.5:1 against #070a0f */
```

---

## 3. Typography Scale & Font System

Zero external network fonts required. Utilizes a curated, deliberate system stack:

- **Document Minutes & Case Files**: Serif humanist stack (`Charter, "Newsreader", "Georgia", "Cambria", serif`). Provides the gravitas of a formal legal minutes dossier.
- **Evidence Citations, Hashes, Tokens, Timestamps**: Monospace stack (`ui-monospace, "SF Mono", "Cascadia Code", "Consolas", monospace`).
- **Control Chrome, Stepper, Status Tags**: Precision sans-serif stack (`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).

| Scale Token | Size | Line Height | Tracking | Usage |
|---|---|---|---|---|
| `text-xs` | 11px (0.6875rem) | 16px | +0.05em | Badges, timestamps, hash blocks |
| `text-sm` | 13px (0.8125rem) | 18px | +0.02em | Metadata tags, table headers, labels |
| `text-base` | 15px (0.9375rem) | 22px | normal | Stepper items, control buttons |
| `text-body` | 16px (1.0000rem) | 26px | normal | Document body, transcript dialogue |
| `text-lg` | 18px (1.1250rem) | 26px | -0.01em | Panel section headers, claim statements |
| `text-xl` | 22px (1.3750rem) | 30px | -0.02em | Modal titles, gate banner headline |
| `text-2xl`| 28px (1.7500rem) | 34px | -0.03em | Console top bar deal title |

---

## 4. Layout Architecture (1920x1080 Projector Optimized)

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: [LOGO] Meetily Clean Room  |  Project Falcon (Northwind Analytics)  |  [STATUS]     │
│ [Director: Step 2 of 7]  [▶ Next Step]  [⌨ Autoplay: Space]  [R: Reset]  [Presenter Mode]   │
├──────────────┬───────────────────────────────────────────────────────────────┬──────────────┤
│ LEFT RAIL    │ CENTER STAGE (Dynamic per active stepper phase)               │ RIGHT RAIL   │
│ (260px)      │ (Flexible: min 850px)                                         │ (360px)      │
│              │                                                               │              │
│ 1. Ingest    │  MODE A: Claim-to-Evidence Linker (Split Canvas)              │ AIRLOCK GATE │
│ 2. Verify  ● │  ┌─────────────────────────┬────────────────────────────────┐ │ [VALVE: HELD]│
│ 3. Cross-chk │  │ Audio Transcript        │ Extracted Summary Claims       │ │ 2 Holds Active│
│ 4. Mask      │  │ [00:00:43] Sarah Chen:  │ 1. $50,000 vendor expenditure  │ │              │
│ 5. Gate      │  │ "...fifteen thousand..."│    [CONTRADICTED] 98% conf     │ │ OFFENDING:   │
│ 6. Review    │  │ (Linked with SVG curve) │    Val mismatch: $50k vs $15k  │ │ Claim #1     │
│ 7. Distribute│  └─────────────────────────┴────────────────────────────────┘ │ Conflict #1  │
│ 8. Ledger    │                                                               │ ──────────── │
│              │  MODE B: Masking Reveal / Audience Morph                      │ LEAK SCANNER │
│ ──────────── │  ┌──────────────────────────────────────────────────────────┐ │ [100% CLEAN] │
│ MASK STATS:  │  │ Audience: [deal] [counsel] [lender] [board] [cloud_llm]  │ │ Canary: Safe │
│ 14 Entities  │  │ Project Falcon / EBITDA $4M-$5M / [PERSON_1]             │ │ ──────────── │
│ 0 B unmasked │  │ (In-place morph with wipe animations)                    │ │ AUDIT CHAIN │
│              │  └──────────────────────────────────────────────────────────┘ │ Block #68: OK│
└──────────────┴───────────────────────────────────────────────────────────────┴──────────────┘
```

---

## 5. Interaction Matrix (MUST / SHOULD / COULD)

### [MUST] Primary Interactions
1. **Claim-to-Evidence Linking**:
   - Left column shows transcript segments; right column shows summary claims.
   - Hovering or clicking a claim computes bounding rectangles, auto-scrolls the transcript segment into view, and renders an animated dynamic SVG connector path between the claim tag and audio span.
   - Contradicted claims display a high-visibility crimson margin bar and a `"Value Mismatch"` comparison badge (`$50,000` claimed vs `fifteen thousand` spoken).
2. **Masking Reveal & In-Place Scrub**:
   - Interactive split view: raw local transcript on left vs tokenized external payload on right.
   - Draggable scrubber slider and hold-to-reveal toggle that scrub across entities, triggering a 250ms character-scramble transition into tokens (`[PERSON_1]`, `[ORGANIZATION_1]`).
   - Live telemetry: Entity count breakdown by category and exact "Bytes Sent to AI" counter.
3. **In-Place Audience Morphing**:
   - Single paper document with 5 audience tabs (`deal_team`, `outside_counsel`, `lender`, `board`, `cloud_llm`).
   - Switching tabs triggers an in-place transformation: exact amounts smoothly transition into ranges (`$4.2M` -> `$4M-$5M`), target names convert to codenames (`Project Falcon`), and contact details become roles.
   - "Highlight Changes Only" toggle underlines modified spans.
4. **Physical Gate & Airlock Metaphor**:
   - The right rail hosts a stylized industrial airlock valve.
   - In `HOLD_FOR_REVIEW`, dual mechanical bars clamp shut in crimson with clickable infraction badges that immediately focus the offending claim or conflict.
   - Upon resolution, the airlock valve turns green, unclamps, and visual delivery packets travel along SVG conduits to the 5 output dossiers (<1.2s total duration).
5. **Cross-Source Contradiction Card**:
   - Side-by-side reconciliation card displaying transcript quote (`$4.2M` @ 00:00:43) against CIM document quote (`$3.8M` @ cim.md:line 8) with a direct "Send to Review" button.
6. **Human Review Loop**:
   - Interactive review queue with inline `Approve`, `Correct` (inline text field + immediate re-verify), and `Reject`.
   - Resolving all items triggers a live pipeline re-run with animated stepper indicators.
7. **Leak Scanner & Canary Audit**:
   - Scanner executes a visual laser-sweep across all 5 generated output dossiers.
   - Confirms advisor `Zephyrine Quillfeather` appears in `deal_team` and is 100% blocked from all other releases.
   - "Plant Canary Leak" button in Director mode demonstrates instant quarantine of a corrupted document.
8. **Director Mode (Presenter Player)**:
   - Floating control bar with `Previous`, `Next`, `Autoplay` (Space bar), `Reset` (`R` key), and `Presenter Mode` (`P` key: scales text to 120%, hides technical debug panels).
   - Drives the full 4-minute hackathon pitch script synchronously with the UI.

### [SHOULD] Secondary Interactions
1. **Interactive Hash-Chain Ledger**:
   - Visual chain of interconnected blocks showing `prev_hash`, `entry_hash`, and payload summaries.
   - "Verify Chain" triggers a cascading verification pulse across all blocks.
   - "Simulate Tamper" button mutates Block #2's payload, visibly breaking the chain at Block #3 and painting all downstream blocks crimson.
2. **Command Palette (`Ctrl+K` / `Cmd+K`)**:
   - Instant spotlight modal supporting "Ask the room" questions with verified citations masked for the active audience.
3. **Coverage Honesty Disclosure**:
   - Transparent compliance panel detailing active regex heuristics, known-entity limits, and explicit note: *"Masking reduces exposure risk; not complete anonymization"*.
4. **URL Hash Deep Linking**:
   - Keeps URL hash in sync with active step and audience (`#step=masking&audience=lender`).

---

## 6. Motion & Accessibility Rules

1. **Functional Motion Only**: Every animation communicates cause-and-effect (e.g., connector linking, airlock sealing, packet distribution). Zero decorative bobbing or ambient spinning.
2. **Timing Standards**:
   - Micro-interactions (hover, tooltip, tag selection): `150ms - 250ms` (`cubic-bezier(0.16, 1, 0.3, 1)`).
   - Layout transitions (step change, drawer slide): `300ms - 400ms`.
   - Gate Airlock sequence: `900ms - 1200ms` total.
3. **`prefers-reduced-motion` Enforcement**:
   - Media query `@media (prefers-reduced-motion: reduce)` disables all SVG path animations, scrambles, and transforms; states update instantaneously with subtle 100ms opacity fades.
4. **Accessibility & Contrast**:
   - All interactive controls have high-contrast `:focus-visible` outlines (`2px solid var(--border-focus)`).
   - Text elements meet or exceed WCAG AA (minimum 4.5:1 for body, 3:1 for large text).
   - Status is always conveyed with both text labels/icons and color, never color alone.
   - Screen reader announcements wired via `aria-live="polite"` regions.
