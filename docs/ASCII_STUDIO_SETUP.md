# ASCII Studio Setup

**Date**: 2026-03-24
**Location**: `~/dharma_swarm/tools/ascii_studio/`
**Source**: https://github.com/vansh-nagar/ascii-studio
**Status**: Cloned, dependencies installed, build verified

## What ASCII Studio Is

ASCII Studio is a Next.js 16 web application that converts video into precise,
high-performance ASCII animations rendered in the browser. It ships 5 built-in
animation components (Star, Rainbow Fire, Red Fire, Pitstop/Red Fire variant,
CD Spin) as React components with a shadcn/ui-based gallery interface.

It is a **component registry** — each animation is a self-contained `.tsx` file
that renders ASCII art frame-by-frame in a `<pre>` block using requestAnimationFrame.
The animations are pure client-side JavaScript, no server processing required.

## Tech Stack

- Next.js 16.2.0 (App Router)
- React 19.2.4
- TypeScript 5
- Tailwind CSS 4
- shadcn/ui components
- Framer Motion for transitions

## Installation (Completed)

```bash
cd ~/dharma_swarm/tools
git clone https://github.com/vansh-nagar/ascii-studio.git ascii_studio
cd ascii_studio
npm install          # 811 packages, 778MB with node_modules
npx next build       # Compiles successfully, static pages generated
```

To run the dev server:
```bash
cd ~/dharma_swarm/tools/ascii_studio
npm run dev          # http://localhost:3000
```

To build for production:
```bash
npm run build        # Static output in .next/
npm start            # Serve production build
```

## Directory Structure

```
ascii_studio/
  src/
    app/
      page.tsx                    # Main page, renders AsciiAnimationsGrid
      layout.tsx                  # Root layout with theme provider
    components/
      ascii/
        star.tsx                  # Star animation (~large, pre-rendered frames)
        rainbow-fire.tsx          # Rainbow fire (~500KB+, dense frame data)
        red-fire.tsx              # Red fire animation
        pitstop.tsx               # Pitstop variant (~500KB+)
        cd.tsx                    # CD spinning animation (~768KB)
      landing/
        grid.tsx                  # Gallery grid layout
        navbar.tsx                # Navigation bar
        search-context.tsx        # Search/filter context
        copy-drop-down.tsx        # Copy animation code dropdown
    hooks/
      use-mobile.ts              # Mobile detection hook
    lib/
      utils.ts                   # Utility functions
  registry.json                  # shadcn component registry
  components.json                # shadcn config
```

## dharma_swarm Use Cases

### 1. R_V Contraction Visualization

Convert R_V participation ratio contraction data into ASCII animations:
- Encode PR_late/PR_early ratio as frame-by-frame ASCII density
- High R_V (1.0) = full character density, low R_V (<0.737) = sparse/contracted
- Layer-by-layer animation showing contraction through transformer depth
- Export as static HTML for paper supplementary materials

**Approach**: Create a new component in `src/components/ascii/` that takes
R_V timeseries data and renders it as contracting geometric patterns. The
existing animation components show the pattern — large arrays of pre-rendered
ASCII frames played back at 30-60fps.

### 2. Agent Topology Animations

Visualize dharma_swarm agent interactions as ASCII network graphs:
- Nodes = agents (labeled with provider + role)
- Edges = stigmergy marks / message passing
- Animate task routing through the orchestrator
- Show Darwin Engine evolution cycles as generational ASCII trees

### 3. Session Garden ASCII Export

Convert session garden state (`tools/session_garden/`) into ASCII art:
- Each session = a plant/tree whose size reflects depth
- Garden overview as grid showing active/dormant/archived sessions
- Export as terminal-renderable text for `dgc` CLI output

### 4. Terminal Dashboard Widgets

The ASCII animation pattern (pre-rendered frames in TSX) could be adapted
for the Textual TUI dashboard — render system health, pulse, or evolution
metrics as animated ASCII widgets.

## How the Animations Work

Each animation component is a large TypeScript file containing pre-computed
ASCII frames as string arrays. The component uses `useEffect` +
`requestAnimationFrame` to cycle through frames, rendering each inside a
monospace `<pre>` element. Some files exceed 500KB because they embed
hundreds of dense text frames.

This is NOT a real-time video-to-ASCII converter. It is a gallery of
pre-baked ASCII animations. To create new animations, you would:

1. Generate ASCII frames externally (e.g., using Python + opencv + ascii-magic)
2. Export frames as a TypeScript string array
3. Create a new component following the pattern in `src/components/ascii/`
4. Register it in `src/components/landing/grid.tsx`

## Alternative Tools (If This Repo Becomes Unavailable)

| Tool | Language | What It Does |
|------|----------|-------------|
| [ascii-magic](https://pypi.org/project/ascii-magic/) | Python | Image/video to ASCII, pip installable |
| [video-to-ascii](https://github.com/joelibaceta/video-to-ascii) | Python | Terminal video playback as ASCII |
| [asciinema](https://asciinema.org/) | Go/Python | Record + share terminal sessions |
| [jp2a](https://github.com/cslarsen/jp2a) | C | JPEG to ASCII converter |
| [termtosvg](https://github.com/nbedos/termtosvg) | Python | Terminal to animated SVG |
| [rich](https://github.com/Textualize/rich) | Python | Rich text + ASCII art in terminal (already a dharma_swarm dependency) |

For dharma_swarm's Python-centric stack, `ascii-magic` or `video-to-ascii`
may be more practical for programmatic ASCII generation than this Next.js
gallery. The value of ascii-studio is as a **display layer** and **component
pattern** rather than a conversion pipeline.

## Gotchas

**Trigger**: Running `npm install` in ascii_studio
**Symptom**: 778MB added to tools/ directory
**Fix**: Add `tools/ascii_studio/node_modules/` and `tools/ascii_studio/.next/` to `.gitignore` before committing. These should never enter the dharma_swarm repo.
**Category**: storage

**Trigger**: Building with `npx next build`
**Symptom**: BABEL deoptimization warnings for rainbow-fire.tsx and pitstop.tsx (>500KB each)
**Fix**: This is expected — the animation frame data is intentionally large. The warnings are cosmetic and the build succeeds.
**Category**: build

**Trigger**: Assuming ascii-studio converts video to ASCII in real-time
**Symptom**: Confusion about what the tool actually does
**Fix**: It is a pre-baked animation gallery, not a converter. For real-time conversion, use Python tools like `ascii-magic` or `video-to-ascii`.
**Category**: conceptual
