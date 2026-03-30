# Runtime Convergence Hardening Status

**Timestamp:** 2026-03-30T03:56:25Z
**Branch:** `runtime-convergence-hardening`
**Scope:** Tasks 1-7 of `docs/plans/2026-03-30-runtime-convergence-hardening.md`

## Baseline Failures

- No single canonical humming verifier in local and CI loops.
- Runtime/repo root resolution still depended on ambient `Path.home()` assumptions.
- `/health` and `/api/health` assembled overlapping runtime payloads independently.
- The local worktree leaked `dharma_swarm.dgc` imports to the parent checkout instead of owning a local modular package.
- The public GraphQL surface was not honest:
  - `api/graphql/schema.py` hard-failed on import when `strawberry` was absent.
  - the schema advertised placeholder resolvers.
  - `/graphql` had no contract document explaining that only REST compatibility routes were live.

## Fixes Landed

- Added `scripts/verify_humming.py`, wired it into CI, and kept it green.
- Centralized runtime path resolution through `dharma_swarm/runtime_paths.py`.
- Unified runtime health payload assembly in `dharma_swarm/runtime_artifacts.py`.
- Added repo-boundary drift reporting and documented the source-vs-state rule.
- Pulled a local modular `dharma_swarm/dgc/` package into the worktree and restored runtime-path-aware context resolution.
- Recovered resident-seat telemetry in `dgc status` via `dharma_swarm/tui_helpers.py`.
- Replaced the placeholder GraphQL schema with an import-safe, status-only contract in `api/graphql/schema.py`.
- Added a truthful `/graphql` root document in `api/routers/graphql_router.py` while preserving the existing `/graphql/*` REST compatibility routes.
- Moved the tracked PSMV hyperfile branch runtime snapshots under `reports/psmv_hyperfiles_20260313/state_snapshots/` and updated `scripts/start_psmv_hyperfile_branch.sh` so future live state defaults to `~/.dharma/psmv_hyperfile_branch`.

## Verification

- `python3 scripts/verify_humming.py`
  - PASS `7/7`
- `python3 -m pytest -q tests/test_graphql_router.py tests/test_graphql_router_contract.py --tb=short`
  - PASS `5`
- `python3 -m pytest -q tests/test_start_psmv_hyperfile_branch_script.py tests/test_verify_humming_script.py -k 'repo_boundary or psmv or start_psmv' --tb=short`
  - PASS `3`
- `python3 -m pytest -q tests/test_runtime_paths.py tests/test_api_main_bootstrap.py tests/test_run_operator_script.py tests/test_api.py tests/test_runtime_artifacts.py tests/test_dgc_modular_main.py tests/test_dgc_cli.py tests/test_maintenance.py tests/test_graphql_router.py tests/test_graphql_router_contract.py --tb=short`
  - PASS `169`
- `python3 -m dharma_swarm.dgc status`
  - PASS
- `python3 scripts/verify_humming.py`
  - PASS `7/7`, repo boundary clean

## Remaining Blockers

- No required-phase blockers remain in the humming lane.
- Repo boundary is clean.

## Next Smallest Seam

Continue the runtime-path convergence on second-tier scripts that still hardcode `Path.home() / ".dharma"` or repo-relative state assumptions outside the hot operator/API/CLI surfaces. The next highest-value candidates are long-running launchers and maintenance utilities under `scripts/`.

## Commit Status

- No commit created in this tranche.
