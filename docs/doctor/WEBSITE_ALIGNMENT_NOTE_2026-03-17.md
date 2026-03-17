# Website Alignment Note

Date: 2026-03-17

Purpose: keep the website recovery lane aligned across operators and agents.

## Shared understanding

- There are two web surfaces in this repo:
  - the newer Next.js operator dashboard under `dashboard/`
  - the older FastAPI `SwarmLens` site in `dharma_swarm/swarmlens_app.py`
- The likely "beautiful Claude-wired website" is the Next.js dashboard introduced at commit `6b1ad1b`.
- That snapshot included:
  - `dashboard/src/app/dashboard/claude/page.tsx`
  - `dashboard/src/components/chat/ChatInterface.tsx`
  - `dashboard/src/components/chat/ChatOverlay.tsx`
  - `dashboard/src/components/chat/ChatPanel.tsx`
- A safe recovery worktree already exists at:
  - `/tmp/dharma_swarm_ui_6b1ad1b`
- Current website recovery status from the active build lane:
  - dashboard is serving at `http://localhost:3420/dashboard`
  - API is serving at `http://localhost:8420/docs`
  - the immediate boot fix was `dashboard/next.config.ts` setting Turbopack root to `path.resolve(__dirname)`

## Canonical recovery stance

- Do not try to invent a third website.
- Do not broadly rewrite the current dashboard while stabilization is in flight.
- Treat commit `6b1ad1b` as the reference snapshot for the richer Next operator UI.
- Recover selectively from that snapshot into the current branch.

## Website product direction

Target operator surfaces:

- TUI: primary day-to-day operator cockpit
- Web: clean stable operator console

Web V1 should be reduced to:

- Overview
- Tasks
- Agents
- Doctor
- Claude/operator chat lane

Hide or defer until backed by real stable data:

- ontology
- lineage
- evolution
- gates
- workflows
- other "deep" pages

## Critical caution

The current website problem is not "missing visuals". It is contract drift.

Known live risks:

- broken or drifting dashboard API routes
- typed fetch wrapper envelope mismatch
- phantom writes / weak persistence on some backend surfaces
- context-isolation leakage

So the correct sequence is:

1. recover the good operator shell and chat UX from `6b1ad1b`
2. harden the API/read-model contract
3. trim the website to stable operator pages
4. expand only after the runtime truth layer is coherent

## Safe launch paths

Recovered snapshot:

```bash
cd /tmp/dharma_swarm_ui_6b1ad1b
python3 -m uvicorn api.main:app --port 8000
```

In another terminal:

```bash
cd /tmp/dharma_swarm_ui_6b1ad1b/dashboard
npm run dev
```

Current surfaces:

```bash
dgc dashboard
dgc ui next
dgc ui lens
dgc ui api
```

Active dev ports reported by the current website lane:

```text
Dashboard: http://localhost:3420/dashboard
API docs:  http://localhost:8420/docs
```

## Operator instruction

If multiple agents are touching website work:

- use this note as the source of truth
- use `6b1ad1b` as the reference snapshot
- prefer surgical restoration over fresh redesign
- keep the active dashboard/API ports explicit in notes and handoffs
