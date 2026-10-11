# UI/UX audit and improvements (0.2)

## Sources and how they were used

| Source | Inspected | Licence | What QuantEngine took |
| --- | --- | --- | --- |
| `nextlevelbuilder/ui-ux-pro-max-skill` | `67803ea` (2026-10-11) | MIT | Its "Financial Dashboard" product row (dark, data-dense, high contrast, accuracy first) and its 119-row `ux-guidelines.csv`. The High/Critical rows drove the fixes below: contrast, reduced motion, controls for auto-rotating content, keyboard alternatives to dragging, target size, loading buttons, inline errors, labelling AI-generated content. |
| `saifyxpro/ui-ux-design-pro-skill` | `3c24c74` | MIT | Type scale (12 px captions, 13 px labels, 14 px dense body), monospace `tabular-nums` for data, four text-ink levels, every component state (default/hover/focus/disabled/loading/error), WCAG 2.2 AA, and the "squint" and "swap" checks. Its "light mode by default" rule was **not** adopted: the product guidance and the user's 3D-surface aesthetic both point to dark for a financial dashboard. |
| `hendurhance/ui-ux` | `3acf624` | CC0 | A curated resource list, used as a reading index. |
| `maxbogo/awesome-ai-tools-for-ui` | `680b351` | none stated | A tool list. Nothing in it was adopted as a dependency; QuantEngine remains offline. |
| `justinhartman/ui-ux-design-library` | `5bd2f97` (2023) | none stated | A reference library of design books and images. Not redistributed. |
| `kevindeasis/awesome-ui` | `c12c45c` | per its LICENSE | A component/library list. Not adopted; the renderer is dependency-free under a strict CSP. |
| *The UI/UX Playbook* (uxpeak) | publisher page | **paid ebook ($49.99)** | Not read in full. Copies that turn up in search are unauthorised uploads and were deliberately not used. uxpeak offers a free preview on its store; buy the full book if you want specific tips mapped into this audit. |

## Measured audit (headless Chromium, 1440×960, all five pages)

The script walks every visible text node and interactive control. Text inside gradient buttons, where contrast cannot be computed from styles, is excluded. Results are in `ui-audit-before.json` and `ui-audit-after.json`.

| Check (threshold) | Before | After |
| --- | --- | --- |
| Text smaller than 12 px | **99** element types | **0** |
| Text contrast below 4.5:1 | 7 | **0** |
| Interactive targets below 24×24 px | 6 | 5\* |

\* The five remaining items are 20×20 checkboxes inside full-width clickable label rows. WCAG 2.2 SC 2.5.8 accepts these through its spacing/equivalent-target exception, because the whole label row is the target.

## Changes
- **Type scale tokens:** 12 / 13 / 14 px, with a raised muted-ink colour (`#9fb3c6`, ≥ 4.5:1 on panels). Monospace data uses `tabular-nums`. Canvas axis labels went from 9 px to 11–12 px.
- **3D surfaces:**
  - Play/pause, rotate and reset toolbar (`role=toolbar`, `aria-pressed`).
  - Arrow keys rotate and tilt, Space pauses, Home resets.
  - Auto-motion stops on hover and focus; it starts paused under `prefers-reduced-motion`.
  - Canvases are focusable, with a visible focus ring.
- **Options form:** the button shows "Calculating…" with `aria-busy`, and errors appear inline next to the button (`role=alert`) as well as in the toast.
- **Assistant (Ctrl+K):** a labelled modal with focus handling and Esc to close, suggestion chips for discoverability (Hick's law), and local-model answers labelled "UNVERIFIED".
- **Layout:** fixed the unit-label/spinner collision that the larger type exposed.

## Not done
- Light theme: the app has a single dark theme.
- Screen-reader walkthrough with NVDA on Windows.
- Responsive layout below 1080 px (the window's minimum width).
- A user test on the actual laptop display.

## 0.2b: Cyberpunk 2099 theme (user direction: high-tech, not "JARVIS blue")

- **Palette:** a near-black base (`#07060a`) with a faint 40 px grid and a static scanline overlay (removed under reduced motion and forced colours). **Crimson neon `#ff2a55`** is the only brand accent. Cyan, amber, violet and acid yellow are reserved for data identity (model families), in a fixed order and never cycled.
- **Shape:** angular cut corners (`clip-path`) on panels, metrics, buttons and nav items; a glowing 64 px neon tick on each panel; uppercase monospace (`Cascadia Mono`, Consolas) for headings and labels.
- **3D surfaces:** the ramp changed from teal/amber to a **magma-like ramp** (deep violet → crimson → orange → gold). Lightness still rises monotonically, so values stay readable in greyscale and for colour-blind viewers, per the dataviz guidance.
- **Charts:** strategy series in crimson, baselines dashed warm grey, correlations as a cyan ↔ crimson diverging scale.
- **Accessibility re-audit after the theme:** 0 texts under 12 px. 5 contrast flags remain, all on `h1` titles, which use gradient-clipped text the script cannot measure; the gradient's darkest stop (`#ff7a95`) on `#07060a` is about 7:1. A `forced-colors` fallback restores solid titles in Windows High Contrast mode. Focus rings are cyan, so they stay visible against the crimson.
- **Fixed during review:** the content security policy blocked inline `style=` colour swatches (now applied via the CSSOM); the learning-curve canvas had no CSS size; the Ask panel's clip-path doubled its border (now a straight border).
