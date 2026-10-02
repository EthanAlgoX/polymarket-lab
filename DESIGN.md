---
name: Polymarket Lab
description: A readable local workspace for market discovery, verification and observation.
colors:
  primary: "#087f6c"
  canvas: "#f5f7f8"
  surface: "#ffffff"
  surface-subtle: "#f1f5f4"
  ink: "#172a32"
  muted: "#53666e"
  border: "#dde4e5"
  positive: "#08785f"
  negative: "#ba3d43"
  warning: "#926411"
typography:
  headline:
    fontFamily: "system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  table:
    fontFamily: "system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  control: "6px"
  panel: "8px"
spacing:
  small: "8px"
  medium: "16px"
  panel: "24px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  work-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
---

## Overview

The workspace is designed for repeated reading and comparison on a laptop or desktop in ordinary daylight. Cool neutral backgrounds and white work surfaces make data and its provenance prominent. A restrained emerald accent identifies actions and selection. The product uses the same navigation, language toolbar, controls and tables across all routes.

**The Evidence Rule.** A catalog price, source quote, local fetch time, calculated estimate and saved observation must each remain identifiable. Visual emphasis follows the task rather than the magnitude of a hypothetical profit.

## Colors

Primary color belongs to actions, selected navigation and eligible states. Ink carries ordinary content; muted text carries explanations. Warning and negative colors accompany explicit text, never convey a state alone. Panels and tables use neutral borders instead of decorative gradients or halos. Shared CSS tokens live in `app/static/css/site-shell.css`.

## Typography

A native sans-serif stack covers both English and Chinese without external font requests. Headings use a compact scale; table values use tabular numerals. Prose stays within approximately 75 characters. Code and original identifiers can use monospace; ordinary labels remain sans-serif. Mobile page headings reduce to 24px.

## Layout

Desktop navigation is fixed at 232px, compacting to 210px below 1100px. The sticky global toolbar contains the workspace identity and one language control. Main content has 32px padding, compacting to 24px and then 16px on narrow screens. Task actions sit beside the page heading. Market discovery prioritizes category filters, a labeled toolbar and the table; coverage and scanner scope remain explicit.

Below 760px, navigation becomes an off-canvas menu with backdrop, Escape, focus containment and focus restoration. Tables scroll inside labeled, keyboard-focusable containers; they must not widen the document. Multi-column settings, inspection books and operational panels stack as space requires.

## Elevation & Depth

Work panels are flat bordered surfaces. Shadows are reserved for inspection overlays and configuration notices. Navigation motion lasts 180ms and respects reduced-motion preferences. Data refresh does not animate page entry or reorder a paused log view.

## Shapes

Controls share modest corners; panels are slightly softer. Icons use one thin stroke family. Controls retain native form behavior, visible focus, validation and disabled states. Current selection uses an explicit background and programmatic state.

## Components

- **Navigation:** Discover, Observe and Workspace groups organize all nine destinations. Route highlighting uses `aria-current`.
- **Language control:** English starts without an LLM request. Chinese selection goes through the shared configuration gate. Settings remain accessible beside the control.
- **Tables:** Compact headings, readable rows, deliberate horizontal overflow, pagination and labeled loading/error/empty states.
- **Inspection:** Current market detail is distinct from saved audit evidence. Drawer background is inert while open; original settlement text remains available.
- **Forms:** Labels, units and decimal examples accompany inputs. Failed submissions and language changes preserve drafts. Saving an API does not issue a paid test request.
- **Scanner diagnostics:** Selected, calculated and eligible counts describe one bounded sample. Rejection counts partition excluded markets; fetch time does not imply quote freshness.
- **Records:** Saved snapshots can be inspected inline, and current market inspection is a separate link. Saved estimates are observations, not realized portfolio returns.
- **Logs:** Pause freezes the displayed snapshot, including an in-flight refresh; resume fetches fresh events.

## Do's and Don'ts

- Keep original outcome/token associations and Decimal financial values intact.
- Keep an action adjacent to the evidence needed to decide whether to use it.
- Provide a recovery path for empty, stale, unavailable and failed states.
- Use the shared shell and tokens for new surfaces.
- Do not imply complete catalog coverage from a capped traversal.
- Do not style accumulated paper estimates as account earnings.
- Do not duplicate language controls in a drawer or add an independent locale bypass.
