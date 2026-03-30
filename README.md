# DHARMA SWARM

DHARMA SWARM is the operator-facing swarm runtime and control-plane codebase behind DHARMA COMMAND.
It combines a Python orchestration core, a FastAPI backend, a Next.js dashboard, and a large research/spec layer that informs the runtime.

## Repo Map

- `dharma_swarm/`: primary Python runtime, swarm coordination, providers, evolution, monitoring, TUI, and operator logic
- `api/`: FastAPI application and routers for the dashboard/control plane
- `dashboard/`: Next.js frontend for DHARMA COMMAND
- `tests/`: pytest coverage for runtime, API, dashboard routers, and TUI flows
- `scripts/`: operator utilities, maintenance tasks, demos, and `repo_xray.py`
- `docs/`: implementation and subsystem documentation
- `reports/`: generated analysis, architecture packets, and audit artifacts
- `specs/`: formal and working specs
- `foundations/`: conceptual and research foundation documents

## Entry Points

- Python package: `dharma-swarm`
- CLI: `dgc`
- API server: `uvicorn api.main:app --host 127.0.0.1 --port 8420 --reload`
- Canonical backend launcher: `bash run_operator.sh`
- Dashboard dev server: `npm --prefix dashboard run dev`

## Common Commands

```bash
make xray
make compile
make test-smoke
make test-all
make dashboard-lint
make dashboard-build
```

## Source Vs State

- Source belongs in the repo: code, tests, docs, small intentional fixtures, and specs meant for review.
- Runtime state belongs under `~/.dharma`: PID files, live logs, runtime databases, stigmergy marks, and other machine-local operator artifacts.
- Generated formal-state dumps under `specs/states/` are treated as local working state unless they are deliberately reduced into a reviewed source artifact.
- `python3 scripts/verify_humming.py` reports repo-boundary drift as a warning so runtime state leaking back into source stays visible.

## What The Inventory Says

Use the built-in static inventory pass to get a current snapshot:

```bash
make xray
```

That report is the fastest way to answer:

- how many Python modules and tests exist
- which files are the largest hotspots
- which local modules have the highest coupling
- what the repo language mix looks like

## Working Notes

- The codebase is split across active runtime code and a large documentation/spec corpus; not every markdown file describes shipped behavior.
- The most coupled runtime surfaces currently sit in the Python core, especially `dharma_swarm/dgc_cli.py`, `dharma_swarm/swarm.py`, `dharma_swarm/agent_runner.py`, and `dharma_swarm/evolution.py`.
- Dashboard and API development are active; expect local changes in `dashboard/`, `api/`, and resident-operator code during ongoing work.

## First Places To Look

- Start at [api/main.py](api/main.py) for the API lifecycle and router registration.
- Start at [run_operator.sh](run_operator.sh) for the canonical local backend boot path.
- Start at [dashboard/package.json](dashboard/package.json) for frontend commands.
- Start at [scripts/repo_xray.py](scripts/repo_xray.py) for repo-wide static indexing.

## GAIA Docs

- `gaia_ui.md`: current user manual for the tracked GAIA runtime surface
- `docs/dse/GAIA_TRAINING_WORKBOOK.md`: hands-on onboarding exercises for new GAIA users
- `docs/dse/GAIA_FACILITATOR_GUIDE.md`: facilitator notes, review keys, and assessment rubric
