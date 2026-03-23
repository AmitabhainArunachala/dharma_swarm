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
- Qwen surgeon lane

Defer or hide pages that are not backed by stable data contracts.

## Local development

Start the API:

```bash
cd /Users/dhyana/dharma_swarm
bash run_operator.sh
```

Start the dashboard:

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/run_dashboard_ui.sh
```

Open:

- Dashboard: `http://localhost:3420/dashboard`
- API docs: `http://localhost:8420/docs`

The browser dashboard now defaults to same-origin API calls. In normal use, the
UI talks to relative `/api/...` paths on port `3420`, and Next proxies those to
the FastAPI backend on `8420`. Keep `NEXT_PUBLIC_API_URL` unset unless you
intentionally want the browser to bypass that proxy.

## Durable local runtime

For a stable operator setup on macOS, install the dashboard API and frontend as
launch agents instead of keeping them alive in ad hoc shells:

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/install_dashboard_launch_agents.sh install
```

Useful commands:

```bash
bash scripts/dashboard_ctl.sh start
bash scripts/dashboard_ctl.sh status
bash scripts/dashboard_ctl.sh restart
bash scripts/dashboard_ctl.sh logs
bash scripts/install_dashboard_launch_agents.sh uninstall
```

These launch agents call the repo-owned runner scripts:

- `run_operator.sh`
- `scripts/run_dashboard_ui.sh`

That keeps one canonical startup path for the product shell, the local GUI, and
future packaging work.

## Runtime surface

The operator dashboard includes a runtime page at `/dashboard/runtime` that
shows:

- current API transport mode
- backend/chat readiness
- profile availability and contract version
- the local product-shell startup commands

That page is meant to be the first stop when the GUI looks stale or a model lane
disappears.

## Desktop shell

A repo-local macOS shell scaffold lives in `desktop-shell/`. It does not fork
the dashboard UI. It wraps the same route surface and opens the existing local
dashboard runtime instead.

That means the route structure stays stable:

- browser dev: `http://127.0.0.1:3420/dashboard`
- app shell: same dashboard routes, but inside a native window

## Important note

The current dev setup depends on the Turbopack root being pinned to the
dashboard directory in `next.config.ts`.

## Related references

- Website alignment note:
  `docs/doctor/WEBSITE_ALIGNMENT_NOTE_2026-03-17.md`
- Overnight Doctor setup:
  `docs/doctor/DOCTOR_OVERNIGHT_WATCH_SETUP_2026-03-17.md`
