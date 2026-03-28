# Hot Seam Freeze Plan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop the repo from smearing more work across the hottest central files, finish the few seams that are already mid-flight, and push non-core expansion into dedicated worktrees so the main integration branch can become trustworthy again.

**Architecture:** Treat the repo as three classes of work: `freeze`, `finish`, and `split`. `Freeze` means no new features in the hottest fusion files except blocker fixes. `Finish` means complete the few operational seams already in progress on the current branch. `Split` means move mission/economic/product-surface/experimental expansion into dedicated worktrees so the core runtime is not carrying every ambition at once.

**Tech Stack:** Git worktrees, Python 3, pytest, FastAPI, Next.js dashboard, launchd/tmux operator scripts, existing branch/worktree topology under `/Users/dhyana/dharma_swarm` and `/Users/dhyana/.dharma/worktrees`.

---

## Freeze Rules

For the next stabilization phase, every touched file must fall into exactly one bucket:

- `freeze`: bugfix/test/assertion only
- `finish`: complete the in-flight seam already partly implemented
- `split`: move work to a dedicated worktree before continuing

No new feature work should land in a `freeze` file.

## Current Worktree Inventory To Reuse

Existing worktrees already map well onto the needed split:

- `feat/dgc-operator-shell-clean`
- `feat/dgc-operator-shell`
- `feat/repo-spine-cleanup`
- `feature/overnight-supervisor`
- `mission-rail-v1`
- `feat/verified-runtime-subset`
- `roaming-daemon-20260326`
- `roaming-fixall-20260326`

The main dirty integration branch should not remain the default landing zone for
all categories of work.

---

### Task 1: Freeze The Central Fusion Files

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/plans/2026-03-28-dirty-hot-map.md`
- Create: `docs/plans/2026-03-28-freeze-contract.md`

**Step 1: Write the freeze contract**

Declare these files `freeze-only`:

- `dharma_swarm/swarm.py`
- `dharma_swarm/organism.py`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/orchestrate_live.py`
- `api/main.py`
- `api/routers/chat.py`

Allowed changes:

- blocker bugfixes
- assertions
- adapters
- metrics hooks
- tests
- extraction prep with no behavior expansion

Disallowed changes:

- new product surfaces
- new background loops
- new strategic roles
- new mission rails
- new dashboard narratives

**Step 2: Add operator-facing note**

Document that new work targeting one of these files must explain:

- why the file cannot stay frozen
- why the work cannot live behind a new module
- what test proves the change

**Step 3: Proof**

Run:

```bash
rg -n "freeze-only|Allowed changes|Disallowed changes" docs/plans/2026-03-28-freeze-contract.md CLAUDE.md README.md
```

Expected:

- freeze contract exists
- central fusion files are explicitly named

---

### Task 2: Finish The Provider/Execution Seam On The Current Branch

**Files:**
- Modify: `dharma_swarm/agent_runner.py`
- Modify: `dharma_swarm/providers.py`
- Modify: `dharma_swarm/runtime_provider.py`
- Modify: `dharma_swarm/provider_policy.py`
- Modify: `dharma_swarm/provider_smoke.py`
- Test: `tests/test_agent_runner.py`
- Test: `tests/test_providers.py`
- Test: `tests/test_providers_quality_track.py`
- Test: `tests/test_dashboard_chat_router.py`

**Step 1: Declare the seam "finish here"**

The current branch is already carrying this seam. Do not fork it again until:

- certified lanes are probeable
- artifact-backed completion is enforced
- subprocess vs API worker semantics are honest

**Step 2: Define the finish condition**

The seam is considered finished when:

- `sonnet46_operator` completes live through the real backend
- `kimi_k25_scout` and `glm5_researcher` pass a certification harness
- broken lanes are marked degraded honestly
- dashboard `/api/chat/status` matches live capability

`api/routers/chat.py` may still receive truthfulness/status corrections, but it
is no longer a place for new runtime or UI feature expansion on this branch.

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_agent_runner.py tests/test_providers.py tests/test_providers_quality_track.py tests/test_dashboard_chat_router.py
```

Expected:

- PASS
- provider lanes no longer look healthy when they cannot execute

---

### Task 3: Finish The Temporal Scheduler Seam On The Current Branch

**Files:**
- Modify: `dharma_swarm/cron_runner.py`
- Modify: `dharma_swarm/launchd_job_runner.py`
- Modify: `dharma_swarm/overnight_director.py`
- Modify: `dharma_swarm/pulse.py`
- Modify: `dharma_swarm/doctor.py`
- Modify: `cron_jobs.json`
- Test: `tests/test_cron_runner.py`
- Test: `tests/test_launchd_job_runner.py`
- Test: `tests/test_overnight_director.py`
- Test: `tests/test_pulse.py`
- Test: `tests/test_doctor.py`

**Step 1: Declare the seam "finish here"**

This seam is close enough that splitting it mid-flight would create more state
confusion than it removes.

**Step 2: Define the finish condition**

The seam is finished when:

- `waiting_external -> ready_to_resume` is scheduler-visible
- the real scheduler will resume before the next ordinary cron slot
- `doctor.py` and status surfaces show waiting/resume truthfully

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_cron_runner.py tests/test_launchd_job_runner.py tests/test_overnight_director.py tests/test_pulse.py tests/test_doctor.py
```

Expected:

- PASS
- status surface reflects resume-aware state

---

### Task 4: Split Strategic-Autonomy Hardening Into A Dedicated Worktree

**Files:**
- Use: `dharma_swarm/thinkodynamic_director.py`
- Use: `dharma_swarm/thinkodynamic_canary.py`
- Use: `dharma_swarm/self_improve.py`
- Use: `scripts/system_integration_probe.py`
- Use: `docs/plans/2026-03-27-thinkodynamic-live-canary.md`
- Create: `docs/plans/2026-03-28-strategic-autonomy-worktree-plan.md`

**Step 1: Move this seam off the main integration branch**

Recommended home:

- reuse `feat/verified-runtime-subset` if the focus is truthfulness and canary work
- otherwise create a dedicated worktree such as:

```bash
git -C /Users/dhyana/dharma_swarm worktree add /Users/dhyana/dharma_swarm-strategic-truth-worktree -b feat/strategic-truth origin/main
```

**Step 2: Scope the worktree narrowly**

Allowed scope:

- stale review fix
- generic workflow suppression
- heuristic-only council degradation
- canary/report truthfulness
- self-improve validation scope

Disallowed scope:

- new strategic personas
- new dream-layer capabilities
- new mission generation features

**Step 3: Proof**

Run in the dedicated worktree:

```bash
pytest -q tests/test_thinkodynamic_canary.py tests/test_thinkodynamic_director.py tests/test_self_improve.py
python3 scripts/system_integration_probe.py
```

Expected:

- canary failures are honest
- integration probe degrades when the loop is substantively weak

---

### Task 5: Split Product-Surface Work Into The Existing Operator Worktree

**Files:**
- Use: `api/main.py`
- Use: `api/routers/chat.py`
- Use: `dashboard/src/lib/api.ts`
- Use: `dashboard/src/lib/chatProfiles.ts`
- Use: `dashboard/src/components/chat/ChatInterface.tsx`
- Use: `dashboard/src/app/dashboard/*`

**Step 1: Stop product-surface polishing on the main dirty branch**

Recommended home:

- `/Users/dhyana/dharma_swarm-operator-shell-clean-worktree`
- branch: `feat/dgc-operator-shell-clean`

**Step 2: Keep the scope product-facing only**

Allowed scope:

- dropdowns
- profile presentation
- operator shell transcript UX
- dashboard route cleanup
- frontend compile/test cleanup

Disallowed scope:

- deep runtime/provider semantics
- orchestration logic
- scheduler behavior

**Step 3: Proof**

Run in that worktree:

```bash
pytest -q tests/test_dashboard_chat_router.py tests/test_dgc_cli.py
./node_modules/.bin/tsc --noEmit -p dashboard/tsconfig.json
```

Expected:

- API/dashboard contract stays stable
- frontend build gate becomes trustworthy again

---

### Task 6: Split Scout/Synthesis Work Into A Dedicated Scout Worktree

**Files:**
- Use: `dharma_swarm/scout_report.py`
- Use: `dharma_swarm/scout_framework.py`
- Use: `dharma_swarm/synthesis_agent.py`
- Use: `dharma_swarm/scout_audit.py`
- Use: `dharma_swarm/scout_health.py`
- Use: `tests/test_scout_audit.py`
- Use: `tests/test_scout_health.py`

**Step 1: Move the seam out immediately**

Recommended new home:

```bash
git -C /Users/dhyana/dharma_swarm worktree add /Users/dhyana/dharma_swarm-scout-worktree -b feat/scout-synthesis origin/main
```

**Step 2: Scope it narrowly**

Allowed scope:

- scout runtime
- scout reporting
- synthesis flows
- scout health/audit tests

Disallowed scope:

- edits to central fusion files unless exposed through typed adapters

**Step 3: Proof**

Run in the scout worktree:

```bash
pytest -q tests/test_scout_audit.py tests/test_scout_health.py
```

Expected:

- scout work continues without deepening integration-branch contention

---

### Task 7: Split Governance/Certified-Lanes Work Into A Governance Worktree

**Files:**
- Use: `dharma_swarm/certified_lanes.py`
- Use: `dharma_swarm/canonical_replay.py`
- Use: `dharma_swarm/constitutional_size_check.py`
- Use: `dharma_swarm/dharma_context_mcp.py`
- Use: `docs/plans/2026-03-28-certified-lanes-next-instance-handoff.md`
- Use: `docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md`

**Step 1: Move the seam out immediately**

Recommended new home:

```bash
git -C /Users/dhyana/dharma_swarm worktree add /Users/dhyana/dharma_swarm-governance-worktree -b feat/governance-spine origin/main
```

**Step 2: Keep it about governance, not runtime sprawl**

Allowed scope:

- lane certification contracts
- canonical replay
- constitutional sizing/limits
- context/governance surfaces

Disallowed scope:

- new product UX
- scheduler behavior
- mission/economic expansion

**Step 3: Proof**

Run in the governance worktree:

```bash
pytest -q tests/test_dashboard_chat_router.py tests/test_intelligence_agents.py
```

Expected:

- governance and certified-lane identity stop competing with runtime stabilization

---

### Task 8: Split Mission/Economic/GAIA Expansion Into Mission-Rail Worktrees

**Files:**
- Use: `dharma_swarm/mission_contract.py`
- Use: `dharma_swarm/ginko_orchestrator.py`
- Use: `dharma_swarm/ginko_brier.py`
- Use: `dharma_swarm/field_knowledge_base.py`
- Use: `docs/missions/*`
- Use: `docs/dse/*`
- Use: `references/*`

**Step 1: Move mission expansion off the runtime branch**

Recommended home:

- `/Users/dhyana/dharma_swarm/.worktrees/mission-rail-v1`

If economic closure diverges further, create another dedicated worktree:

```bash
git -C /Users/dhyana/dharma_swarm worktree add /Users/dhyana/dharma_swarm-economic-spine -b feat/economic-spine origin/main
```

**Step 2: Keep runtime coupling explicit**

Mission work may only touch core runtime through:

- typed contracts
- ingestion adapters
- well-scoped router hooks

It may not expand the central fusion files directly.

**Step 3: Proof**

Run in the mission worktree:

```bash
pytest -q tests/test_mission_contract.py
```

Expected:

- mission/economic work no longer competes for the same hot files as runtime stabilization

---

### Task 9: Split Remaining Experimental New Modules Into A Labs Worktree

**Files:**
- Use: `dharma_swarm/a2a/*`
- Use: `dharma_swarm/transcendence*.py`
- Use: `dharma_swarm/smart_router.py`
- Use: `dharma_swarm/semantic_governance.py`
- Use: `dharma_swarm/gaia_platform.py`

**Step 1: Identify experimental accretion**

These files are mostly untracked expansion, not runtime-stabilization blockers.

**Step 2: Move them to a labs worktree**

Recommended new home:

```bash
git -C /Users/dhyana/dharma_swarm worktree add /Users/dhyana/dharma_swarm-labs -b feat/labs-experiments origin/main
```

**Step 3: Proof**

Success means:

- the main branch no longer accumulates new experiments by default
- labs work can proceed without muddying runtime trust

---

### Task 10: Add A Weekly Integration Rhythm

**Files:**
- Modify: `docs/plans/2026-03-28-freeze-contract.md`
- Modify: `docs/plans/2026-03-28-dirty-hot-map.md`
- Modify: `docs/plans/2026-03-28-certified-lanes-next-instance-handoff.md`

**Step 1: Define the weekly rhythm**

- Monday: provider/execution seam
- Tuesday: scheduler/resume seam
- Wednesday: product-surface worktree only
- Thursday: mission/economic worktree only
- Friday: strategic truthfulness worktree only
- Saturday: integration readback into the hot-map doc
- Sunday: no main-branch feature accretion

**Step 2: Require readback before re-opening a frozen file**

Before touching any `freeze-only` file, update the map with:

- why it must be touched
- what competing seam is being deferred
- what test or probe will validate the change

**Step 3: Proof**

Run:

```bash
rg -n "Monday|Tuesday|Wednesday|freeze-only|readback" docs/plans/2026-03-28-freeze-contract.md docs/plans/2026-03-28-dirty-hot-map.md docs/plans/2026-03-28-certified-lanes-next-instance-handoff.md
```

Expected:

- rhythm exists
- reopening a frozen seam requires explicit justification

---

## Stop / Finish / Split Summary

### Stop Touching In Main

- `dharma_swarm/swarm.py`
- `dharma_swarm/organism.py`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/orchestrate_live.py`
- `api/main.py`
- `api/routers/chat.py`

### Finish In Main

- provider/execution seam
- temporal scheduler seam

### Split To Worktrees

- strategic-autonomy truthfulness
- operator shell and dashboard polish
- scout/synthesis
- governance/certified-lanes
- mission/economic/GAIA expansion
- experimental A2A/transcendence/scout/labs work

## Core Sentence

Do not let the hottest files remain the default destination for every new idea.
