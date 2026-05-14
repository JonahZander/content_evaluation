# Design Language

## Principles

- **White and grayscale only.** No color accents. The palette runs from `#ffffff` through shades of gray to `#0a0a0a`. Category distinctions use gray weight, not hue.
- **No curves.** Every surface, button, input, pill, and card uses `border-radius: 0`. The layout reads as a composed grid of rectangles.
- **Tiles, not cards.** UI sections share walls rather than floating independently. One outer border contains the shell; interior sections are separated by single shared `1px` lines — never two adjacent borders or gaps between panels.
- **Translucent surfaces.** Panels and cards use `rgba` backgrounds at roughly `0.68` opacity so the background layer remains visible through the interface. Surfaces layer visually rather than occlude each other.
- **Flat interactions.** Hover states change background color only — no `translateY` lift, no shadow growth.
- **System sans-serif.** Body text uses the OS system font stack (`-apple-system`, `BlinkMacSystemFont`, etc.). IBM Plex Mono is reserved for labels, metadata, pills, and any monospace-specific UI.

## Color Tokens

Defined in `apps/web/app/globals.css`:

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#ffffff` | Page background |
| `--bg-panel` | `rgba(255,255,255,0.68)` | Shell and section backgrounds |
| `--bg-card` | `rgba(250,250,250,0.68)` | Card and inset surfaces |
| `--ink` | `#0a0a0a` | Primary text, borders, active states |
| `--muted` | `#6b6b6b` | Secondary text, labels, metadata |
| `--line` | `#e5e5e5` | All dividers, borders, shared walls |

Category colors are grayscale variants of the same named tokens (e.g. `--sky`, `--teal`, `--amber`) so existing code paths continue to work without change. They range from `#1a1a1a` (near-black, AI likelihood) to `#8a8a8a` (lighter gray, editorial).

## Layout Structure

The shell is the single outer container. It holds one `1px solid var(--line)` perimeter border. All sections inside it:

- Use `border-bottom: 1px solid var(--line)` to separate from the next row — never `border-top`
- Use `border-right: 1px solid var(--line)` on non-last children to divide horizontal tile groups
- Do not add their own full border or shadow

This produces a layout that looks like a collapsed grid — one line between any two adjacent surfaces, never two.

## Background Animation

A `DotGrid` component (`src/components/DotGrid/DotGrid.tsx`) renders as a fixed full-viewport canvas at `z-index: 0` behind all content. It shows a grid of small gray dots (`#d4d4d4`) that darken on cursor proximity and scatter on fast mouse movement or click, powered by GSAP's InertiaPlugin. Opacity is set to `0.5` so it reads as texture rather than foreground.

The dot grid is visible through translucent panels and is intended to add subtle motion without drawing attention away from the content.

## Progress Bar

The progress bar is intentionally square (`border-radius: 0`) with a gradient fill that runs from light gray (`#c0c0c0`) to near-black (`#1a1a1a`) as progress increases. The track background is `#ebebeb`. An animated shimmer overlay runs during active states.

## What This Is Not

- Not a component library — these rules live in `ReviewWorkbench.module.css` and `globals.css`, not in a shared design system package.
- Not final — empty states and additional detail panels may introduce new surfaces that should follow these same principles.
