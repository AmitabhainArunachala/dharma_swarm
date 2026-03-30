# Runtime Convergence Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `dharma_swarm` reliably hum by converging runtime context, verification, health reporting, and repo boundaries without broad architectural reinvention.

**Architecture:** Build one canonical hardening loop around the current operator/runtime stack. First establish a trustworthy verify driver and clear the currently known front-door reds. Then centralize runtime root resolution, unify health assembly, add repo-boundary drift checks, and continue only the narrowest high-value `dgc` modularization needed for runtime and ops stability.

**Tech Stack:** Python 3.14, Bash, pytest, FastAPI, Next.js, ESLint, existing `dharma_swarm` runtime modules and scripts

---

### Task 1: Create The Canonical Humming Verification Driver

**Files:**
- Create: `scripts/verify_humming.py`
- Modify: `Makefile`
- Modify: `.github/workflows/tests.yml`
- Create: `tests/test_verify_humming_script.py`

**Step 1: Write the failing test**

- Add a focused unit test for `scripts/verify_humming.py` that monkeypatches command execution and asserts the script runs the canonical phases in order:
  - Python compile
  - targeted operator/API tests
  - dashboard lint
  - dashboard build
  - assurance gate
  - `dgc status`
  - runtime supervision smoke

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest -q tests/test_verify_humming_script.py
```

Expected: FAIL because `scripts/verify_humming.py` does not exist yet.

**Step 3: Write minimal implementation**

- Create `scripts/verify_humming.py` with:
  - explicit ordered phases
  - a summary table at the end
  - non-zero exit on any failing required phase
  - optional flags such as `--skip-dashboard-build` only if they are needed for iteration speed
- Add `verify-humming` to `Makefile`.
- Update CI to call the new script instead of manually duplicating the same logic.

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest -q tests/test_verify_humming_script.py
```

Expected: PASS.

**Step 5: Run the driver once**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: current failures are reported clearly and in one place.

### Task 2: Clear The Known Front-Door Failures

**Files:**
- Modify: `dashboard/src/app/dashboard/cascade/page.tsx`
- Modify: `dashboard/src/app/dashboard/strange-loop/page.tsx`
- Modify: `dharma_swarm/runtime_artifacts.py`
- Modify: `tests/test_runtime_artifacts.py`

**Step 1: Write the failing test for runtime payload serialization**

- Add or extend a test that asserts `runtime_supervision_summary(...)` can be serialized with `json.dumps(...)` without special casing `Path` objects.

**Step 2: Run the targeted backend test to verify it fails**

Run:

```bash
python3 -m pytest -q tests/test_runtime_artifacts.py -k supervision
```

Expected: FAIL because runtime payload fields still contain `Path` objects.

**Step 3: Fix the immediate frontend and runtime reds**

- Replace the unescaped apostrophes in the two dashboard pages.
- Normalize `runtime_supervision_summary(...)` to return JSON-safe values for fields exposed to tooling and endpoints.

**Step 4: Re-run the targeted checks**

Run:

```bash
python3 -m pytest -q tests/test_runtime_artifacts.py -k supervision
npm --prefix dashboard run lint -- --quiet
```

Expected: PASS.

**Step 5: Re-run the full verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: the previous known front-door failures are gone or replaced by the next real blocker.

### Task 3: Introduce A Canonical Runtime Paths Contract

**Files:**
- Create: `dharma_swarm/runtime_paths.py`
- Modify: `dharma_swarm/dgc/context.py`
- Modify: `api/main.py`
- Modify: `api/routers/health.py`
- Modify: `api/chat_tools.py`
- Modify: `run_operator.sh`
- Create: `tests/test_runtime_paths.py`
- Modify: `tests/test_api_main_bootstrap.py`
- Modify: `tests/test_run_operator_script.py`

**Step 1: Write the failing test**

- Add tests for a runtime-paths helper that resolves:
  - `home`
  - `repo_root`
  - `state_root`
  - env files
- Cover env override behavior using `DHARMA_HOME` and `DHARMA_REPO_ROOT`.

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python3 -m pytest -q tests/test_runtime_paths.py tests/test_api_main_bootstrap.py tests/test_run_operator_script.py
```

Expected: FAIL because the canonical path helper does not exist and hot surfaces still use direct `Path.home()` assumptions.

**Step 3: Write minimal implementation**

- Create `dharma_swarm/runtime_paths.py` with one shared resolver.
- Update `dgc/context.py` to use it.
- Update `api/main.py`, `api/routers/health.py`, `api/chat_tools.py`, and `run_operator.sh` to read from the shared contract rather than inlining `~/dharma_swarm` and `~/.dharma`.
- Preserve current defaults so existing local workflows keep working.

**Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python3 -m pytest -q tests/test_runtime_paths.py tests/test_api_main_bootstrap.py tests/test_run_operator_script.py
```

Expected: PASS.

**Step 5: Re-run the verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: runtime root handling remains green and easier to reason about.

### Task 4: Unify Health Payload Assembly

**Files:**
- Modify: `dharma_swarm/runtime_artifacts.py`
- Modify: `api/main.py`
- Modify: `api/routers/health.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_runtime_artifacts.py`
- Modify: `tests/test_api_main_bootstrap.py`

**Step 1: Write the failing tests**

- Add tests that prove `/health` and `/api/health` are built from the same canonical runtime payload contract for shared fields:
  - status
  - daemon/operator PID state
  - maintenance summary
  - runtime warnings

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python3 -m pytest -q tests/test_api.py tests/test_runtime_artifacts.py tests/test_api_main_bootstrap.py -k 'health or runtime'
```

Expected: FAIL because payload assembly is still duplicated.

**Step 3: Write minimal implementation**

- Add a shared payload builder in `runtime_artifacts.py`.
- Use it from both `/health` and `/api/health`.
- Keep route-specific wrapping logic minimal and honest.

**Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python3 -m pytest -q tests/test_api.py tests/test_runtime_artifacts.py tests/test_api_main_bootstrap.py -k 'health or runtime'
```

Expected: PASS.

**Step 5: Re-run the verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: health surfaces stay aligned.

### Task 5: Fold Repo-Boundary Drift Into Verification

**Files:**
- Modify: `scripts/verify_humming.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `tests/test_verify_humming_script.py`

**Step 1: Write the failing test**

- Add a test that verifies `verify_humming.py` can flag tracked or present repo-local drift categories without failing on normal source:
  - machine-local runtime state
  - oversized generated state under `specs/states/`
  - tracked runtime artifacts in source-root areas that should live under `~/.dharma`

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python3 -m pytest -q tests/test_verify_humming_script.py -k repo_boundary
```

Expected: FAIL because the verification driver does not yet report boundary drift.

**Step 3: Write minimal implementation**

- Add a non-blocking repo-boundary report section to `verify_humming.py`.
- Tighten `.gitignore` only where current intent is unambiguous.
- Update `README.md` with the canonical source-vs-state rule.

**Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python3 -m pytest -q tests/test_verify_humming_script.py -k repo_boundary
```

Expected: PASS.

**Step 5: Run the verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: boundary drift is visible in one place, even if some cleanup remains deferred.

### Task 6: Continue The `dgc` Split Only For Runtime/Ops Commands

**Files:**
- Modify: `dharma_swarm/dgc/main.py`
- Modify: `dharma_swarm/dgc_cli.py`
- Modify: `dharma_swarm/dgc/commands/runtime.py`
- Modify: `dharma_swarm/dgc/commands/ops.py`
- Modify: `tests/test_dgc_modular_main.py`
- Modify: `tests/test_dgc_cli.py`
- Modify: `tests/test_maintenance.py`

**Step 1: Write the failing test**

- Add dispatch tests that prove the runtime/ops commands used by the humming lane route through the modular package:
  - `status`
  - `runtime-status`
  - `health`
  - `maintenance`

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python3 -m pytest -q tests/test_dgc_modular_main.py tests/test_dgc_cli.py tests/test_maintenance.py -k 'status or runtime or health or maintenance'
```

Expected: FAIL where runtime/ops commands still rely on the monolithic path.

**Step 3: Write minimal implementation**

- Move only the highest-value runtime/ops command handlers into the modular command packs.
- Keep `dgc_cli.py` as compatibility glue.
- Do not expand the decomposition beyond the commands required by the verification and runtime-health loops.

**Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python3 -m pytest -q tests/test_dgc_modular_main.py tests/test_dgc_cli.py tests/test_maintenance.py -k 'status or runtime or health or maintenance'
```

Expected: PASS.

**Step 5: Re-run the verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: the humming lane depends less on the monolith.

### Task 7: Make Incomplete Public Surfaces Honest

**Files:**
- Modify: `api/routers/graphql_router.py`
- Modify: `api/graphql/schema.py`
- Create: `tests/test_graphql_router_contract.py`

**Step 1: Write the failing test**

- Add a contract test that asserts the GraphQL surface is either:
  - explicitly disabled, or
  - minimally implemented with honest behavior

**Step 2: Run the targeted test to verify it fails**

Run:

```bash
python3 -m pytest -q tests/test_graphql_router_contract.py
```

Expected: FAIL because the public surface exposes placeholder resolvers.

**Step 3: Write minimal implementation**

- Either guard the GraphQL router behind a clear feature flag, or reduce the public schema to a truthful minimal subset that is actually backed by data.
- Do not invent a broader GraphQL product.

**Step 4: Run the targeted test to verify it passes**

Run:

```bash
python3 -m pytest -q tests/test_graphql_router_contract.py
```

Expected: PASS.

**Step 5: Re-run the verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: public surfaces are more honest and less misleading.

### Task 8: Run The Full Hardening Verification Pass

**Files:**
- No new code expected

**Step 1: Run the canonical verification driver**

Run:

```bash
python3 scripts/verify_humming.py
```

Expected: PASS or a short residual blocker list.

**Step 2: Run the focused runtime/API suite again**

Run:

```bash
python3 -m pytest -q \
  tests/test_runtime_paths.py \
  tests/test_api_main_bootstrap.py \
  tests/test_run_operator_script.py \
  tests/test_api.py \
  tests/test_runtime_artifacts.py \
  tests/test_dgc_modular_main.py \
  tests/test_dgc_cli.py \
  tests/test_maintenance.py
```

Expected: PASS.

**Step 3: Run one CLI smoke**

Run:

```bash
python3 -m dharma_swarm.dgc status
```

Expected: clean status output.

**Step 4: Record the tranche result**

- Write a short report to `reports/deployment_checks/` or `docs/plans/` capturing:
  - baseline failures
  - fixes landed
  - remaining blockers
  - next smallest seam

**Step 5: Commit**

```bash
git add \
  scripts/verify_humming.py \
  Makefile \
  .github/workflows/tests.yml \
  .gitignore \
  README.md \
  api \
  dashboard/src/app/dashboard/cascade/page.tsx \
  dashboard/src/app/dashboard/strange-loop/page.tsx \
  dharma_swarm \
  tests
git commit -m "feat(hardening): converge runtime, verify, and repo spines"
```

Plan complete and saved to `docs/plans/2026-03-30-runtime-convergence-hardening.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
