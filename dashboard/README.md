# DHARMA COMMAND Dashboard

This directory is the canonical base for the newer web operator UI.

It is not a consumer product site. It is the browser control surface for
`dharma_swarm`.

## Canonical stance

- TUI is the primary operator cockpit.
- This dashboard is the canonical web operator surface.
- `SwarmLens` remains a legacy/alternate web surface in
  `dharma_swarm/swarmlens_app.py`.
- The richer operator-shell reference snapshot is commit `6b1ad1b`.
- Recovery and upgrades should be surgical. Do not invent a third website.

## Web V1 scope

Keep the stable web surface focused on:

- Overview
- Tasks
- Agents
- Doctor
- Claude/operator chat lane

Defer or hide pages that are not backed by stable data contracts.

## Local development

Start the API:

```bash
cd /Users/dhyana/dharma_swarm
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8420
```

Start the dashboard:

```bash
cd /Users/dhyana/dharma_swarm/dashboard
npm run dev -- --port 3420
```

Open:

- Dashboard: `http://localhost:3420/dashboard`
- API docs: `http://localhost:8420/docs`

## Important note

The current dev setup depends on the Turbopack root being pinned to the
dashboard directory in `next.config.ts`.

## Related references

- Website alignment note:
  `docs/doctor/WEBSITE_ALIGNMENT_NOTE_2026-03-17.md`
- Overnight Doctor setup:
  `docs/doctor/DOCTOR_OVERNIGHT_WATCH_SETUP_2026-03-17.md`
