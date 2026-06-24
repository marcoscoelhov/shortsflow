---
name: ShortsFlow
description: Operational review hub for AI-assisted YouTube Shorts production.
colors:
  obsidian-bg: "#09090b"
  slate-chrome: "#0f172a"
  graphite-panel: "#1f1f22"
  ember-accent: "#ff5540"
  ember-accent-strong: "#ffb4a8"
  warm-ink: "#e4e1e6"
  heading-ink: "#f6f1f0"
  muted-rose: "#b8a5a2"
  success-green: "#22c55e"
  warning-amber: "#f59e0b"
  danger-coral: "#ff6b5f"
  info-sky: "#89ceff"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.04em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "SFMono-Regular, Cascadia Mono, Roboto Mono, Liberation Mono, monospace"
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  sm: "8px"
  pill: "999px"
spacing:
  xs: "0.35rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "1.75rem"
components:
  button-primary:
    backgroundColor: "{colors.ember-accent}"
    textColor: "{colors.obsidian-bg}"
    rounded: "{rounded.sm}"
    padding: "0.8rem 0.95rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ember-accent}"
    rounded: "{rounded.sm}"
    padding: "0.8rem 0.95rem"
  badge:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.warm-ink}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.65rem"
  panel:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.warm-ink}"
    rounded: "{rounded.sm}"
    padding: "1.2rem"
---

# Design System: ShortsFlow

## 1. Overview

**Creative North Star: "The Production Desk"**

ShortsFlow should feel like a compact production desk for a channel operator: dark enough for long editing and review sessions, restrained enough for repeated work, and precise enough to separate generation, review, scheduling, and publication decisions. The interface serves the workflow; it should not perform like a brand page.

The system uses a dark operational shell, warm text, ember accents, and quiet semantic colors. Density is intentional. The user should scan a queue, identify risk, open a job, and decide without decoding decorative UI.

**Key Characteristics:**

- Work-focused app shell with persistent navigation and compact operational controls.
- Restrained color strategy: tinted dark neutrals plus rare ember accent.
- Portuguese visible labels for operator-facing states and actions.
- Panels and rows carry hierarchy through spacing, borders, and state badges, not ornamental cards.
- Diagnostics are available, but decision surfaces stay primary.

## 2. Colors

The palette is a warm dark operations palette: near-black graphite, slate chrome, ember action color, and semantic colors used only for state.

### Primary

- **Ember Accent** (`#ff5540`): Primary actions, current selection, and important command affordances.
- **Ember Accent Strong** (`#ffb4a8`): Hover emphasis, warm highlights, and accent contrast against dark surfaces.

### Secondary

- **Info Sky** (`#89ceff`): Informational states only, never general decoration.

### Neutral

- **Obsidian Background** (`#09090b`): App background, tuned off-black for long sessions.
- **Slate Chrome** (`#0f172a`): Sidebar and structural chrome.
- **Graphite Panel** (`#1f1f22`): Main panels, dialogs, and dense surfaces.
- **Warm Ink** (`#e4e1e6`): Default text.
- **Heading Ink** (`#f6f1f0`): Section titles and high-priority labels.
- **Muted Rose** (`#b8a5a2`): Helper text, meta labels, timestamps, and secondary explanations.

### Semantic

- **Success Green** (`#22c55e`): Approved, published, eligible, and completed states.
- **Warning Amber** (`#f59e0b`): Review, scheduled, pending, and needs-attention states.
- **Danger Coral** (`#ff6b5f`): Failed, blocked, rejected, and destructive states.

### Named Rules

**The Ember Is Rare Rule.** Ember is for commands and current attention. If the screen starts reading as orange, the hierarchy is wrong.

**The Semantic Color Rule.** Green, amber, red, and sky mean state. Do not use them as decoration.

## 3. Typography

**Display Font:** System sans stack.
**Body Font:** System sans stack.
**Label/Mono Font:** SFMono-compatible monospace stack.

**Character:** Native, compact, and utilitarian. The system should feel like a production tool, not a publication site.

### Hierarchy

- **Headline** (800, `1.75rem`, `1.1`, `-0.04em`): App title and major surface headers only.
- **Title** (700, `1rem`, `1.25`): Panel titles, row titles, and compact section headings.
- **Body** (400, `1rem`, `1.45`): Main explanatory text and form content. Keep prose near 65 to 75ch.
- **Label** (700, `0.78rem`, `0.06em`, uppercase): Field labels, eyebrow labels, compact operational metadata.

### Named Rules

**The No Hero Type Rule.** This is a product surface. Use hero-scale type only if the screen is intentionally a first-run or brand moment.

**The Label Discipline Rule.** Uppercase labels should be short and functional. Do not use them for decorative flavor.

## 4. Elevation

The system uses tonal layering first and shadows second. Panels rest on dark surfaces with subtle borders. Shadows are reserved for major shells, dialogs, and elevated modal surfaces; rows and small controls should stay flat.

### Shadow Vocabulary

- **Sidebar cast** (`10px 0 44px rgba(0, 0, 0, 0.16)`): Persistent app chrome against the work area.
- **Panel depth** (`0 24px 80px rgba(0, 0, 0, 0.36)`): Major panels when depth is needed.
- **Dialog depth** (`0 30px 90px rgba(0, 0, 0, 0.58)`): Focused interruption surfaces.
- **Action lift** (`0 12px 38px rgba(255, 85, 64, 0.18)`): Primary command emphasis, used sparingly.

### Named Rules

**The Flat Queue Rule.** Queue rows should feel selectable and stable, not like floating cards.

**The Dialog Weight Rule.** Dialogs can be heavier than panels because they interrupt the workflow; ordinary panels should not compete with them.

## 5. Components

### Buttons

- **Shape:** Compact rectangle with 8px radius.
- **Primary:** Ember gradient or solid ember treatment, high weight text, used for decisive commands.
- **Hover / Focus:** Short state transition, visible focus ring, no layout shift.
- **Ghost:** Transparent surface, ember text and border, used for secondary actions that must remain discoverable.

### Chips

- **Style:** Pill shape, low-chroma background, concise label.
- **State:** Selected or semantic chips must include text, not color alone.

### Cards / Containers

- **Corner Style:** 8px radius by default.
- **Background:** Graphite or translucent dark panel over obsidian background.
- **Shadow Strategy:** Shadow only for major panels or interruption surfaces.
- **Border:** Thin full border, never a thick colored side stripe.
- **Internal Padding:** 1rem to 1.5rem depending on density.

### Inputs / Fields

- **Style:** Dark code-like surface, thin border, 8px radius, compact padding.
- **Focus:** Border and focus ring should be visible against dark surfaces.
- **Error / Disabled:** Use semantic color plus explanatory text. Do not rely on color alone.

### Navigation

- **Style:** Persistent left sidebar on desktop, compact mobile navigation when space is constrained.
- **Typography:** Short labels, no icon-only primary nav.
- **States:** Active location should be visible through text, surface, and border treatment.

### Job Rows

Job rows are the signature component. They must keep title, status, progress, Origem do Job, Via de Criacao do Job, and next action scannable without making the row taller than necessary.

## 6. Do's and Don'ts

### Do:

- **Do** prioritize the next operational decision over diagnostic detail.
- **Do** show Origem do Job and Via de Criacao do Job in Portuguese.
- **Do** keep filters and global controls compact until the operator asks for them.
- **Do** use stable row dimensions so progress, badges, and timestamps do not shift layout.
- **Do** keep semantic color tied to state and status.

### Don't:

- **Don't** make the hub look like a landing page, SaaS marketing dashboard, or decorative analytics homepage.
- **Don't** use purple-blue AI gradients, glassmorphism, gradient text, or thick side-stripe accents.
- **Don't** expose internal slugs like `ready_script_bank` or `daily_cycle` in the UI.
- **Don't** bury core review, approval, and scheduling actions behind diagnostic panels.
- **Don't** use modals as the first answer when inline disclosure or a focused control would work.
