# Constitutional Organism Overnight Build Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn `dharma_swarm` into an overnight-capable constitutional institution builder while preserving `dharma_swarm` as the living organism and `dgc` as the canonical operator interface.

**Architecture:** Keep the existing repo as the single body. `dharma_swarm` remains the runtime, `dgc` remains the CLI/control nerve, and the new work lands as a constitutional layer inside the existing kernel/corpus/telos/director/organism stack. The overnight system runs as a dual loop: outward lanes ship real artifacts into the world, inward lanes improve the nervous system only when they remove a named bottleneck for real missions. `launchd` keeps baseline services alive; `tmux` hosts inspectable, restartable 8-hour lanes; the dashboard becomes the institution cockpit.

**Tech Stack:** Python 3, JSONL/SQLite, FastAPI, Next.js, `pytest`, `tmux`, `launchd`, shell scripts, existing DGC/DHARMA runtime modules.

---

## Canonical Shape

- `dharma_swarm` stays the organism.
- `dgc` stays the operator-facing CLI and control-plane surface.
- `PSMV` stays the archive and source archaeology.
- `~/.dharma/` stays the runtime state and handoff substrate.
- New self-evolution work lands inside `dharma_swarm`, not in a new repo.
- Overnight autonomy uses many proposing/auditing lanes and one code-writing lane until multi-worktree merge discipline is in place.

## 8-Hour Overnight Topology

### Always-On `launchd` Baseline

1. Cron daemon lane:
   - keep canonical runtime heartbeat alive
   - emit state, mission, and error artifacts even if tmux lanes die
2. Dashboard API lane:
   - keep control-plane endpoints available
3. Dashboard web lane:
   - keep operator cockpit reachable
4. Optional nightly supervisor lane:
   - relaunch tmux pack if session disappears before scheduled end

### `tmux` Overnight Lanes

1. `dgc_constitution_director`
   - read-heavy thinkodynamic lane
   - proposes seeds and campaign briefs
2. `dgc_constitution_nursery`
   - turns raw signals into scored seed packets
   - no code writes
3. `dgc_constitution_policy`
   - semantic/legal/governance audit lane
   - checks policy coverage, autonomy tier, and signoff requirements
4. `dgc_constitution_writer`
   - single write-capable Codex lane
   - lands bounded slices only
5. `dgc_constitution_verify`
   - runs focused tests, smoke checks, and tripwires
6. `dgc_constitution_handoff`
   - writes the morning ledger, blockers, and next-run seed list
7. `dgc_caffeine_constitution`
   - machine wakefulness and timed handoff support

## Supervisor Semantics

The overnight pack must be watched by a supervisor-of-supervisors.

It should run on a short cadence using the existing daemon and `launchd` substrate:

- `launchd` keeps the supervisor alive
- supervisor ticks every 5 minutes
- every lane writes a heartbeat and latest snapshot
- supervisor reads those artifacts and decides whether to continue, replan, reduce scope, restart, or halt

The supervisor judges four things, not one:

1. `Liveness`
   - is the lane still ticking?
2. `Progress`
   - did it create a new artifact, meaningful diff, or state transition since the last checkpoint?
3. `Novelty`
   - is it exploring or just repeating the same language, same files, same errors, or same plan?
4. `Quality`
   - are tests, checks, and policy posture improving or degrading?

## Intervention Ladder

`CONTINUE -> REPLAN -> REDUCE_SCOPE -> RESTART_LANE -> FREEZE_AND_HANDOFF -> ALERT_DHYANA`

### If A Lane Is Not Firing

Definition:
- missing heartbeat
- stale heartbeat
- session exists but no artifact delta

Action:
- first event: write warning + ask thinker lane for a short replan brief
- second event: restart that lane only
- third event: freeze the lane, preserve logs, move work to morning handoff, and alert

### If A Lane Finishes In 40 Minutes

This is not automatically success and not automatically failure.

The supervisor should ask:

- did it complete the named mission slice?
- did it leave a durable artifact?
- did verification pass?
- is there another high-leverage slice already queued?

If yes:
- promote result
- write a mini-handoff
- pull the next queued slice from the nursery or mission backlog
- keep the overnight run alive

If no:
- treat it as premature exhaustion
- send it into `REPLAN`
- generate a narrower next slice
- if two fast exhaustions happen in a row, switch that lane to read-only synthesis and stop code-writing for that lane

### If A Lane Is Looping

Definition:
- repeated same error three or more times in a window
- no new files, no new states, no passing checks
- high textual similarity across consecutive notes or snapshots
- repeated touching of the same file set without quality delta

Action:
- trip circuit breaker
- stop the current tactic
- write a root-cause memo
- send control back to the thinker/policy lane
- either decompose further, change model/role, or archive the attempt

Looping should never consume the whole night silently.

### If The Whole Pack Goes Quiet

Action:
- preserve all run artifacts
- run a recovery synthesis
- generate a `why_the_pack_stalled.md`
- generate `next_three_recovery_moves.md`
- leave the system in a coherent morning state instead of pretending work happened

## Product Direction

The system being built is an institution cockpit, not a task board.

The first useful operator interface should show:

- constitutional health
- active missions and deadlines
- seed nursery
- promoted campaigns
- evidence confidence
- semantic drift alerts
- legal/compliance queue
- compute and budget burn
- witness chain and gnani verdict

## Module Boundaries

- `dharma_swarm/telos_graph.py`
  becomes the portfolio graph with seed lifecycle, evidence, review, and promotion
- `dharma_swarm/organism.py`
  remains the coherence governor and algedonic source
- `dharma_swarm/thinkodynamic_director.py`
  remains the strategic selector and campaign compiler
- `dharma_swarm/dgc_cli.py`
  remains the canonical operator interface to all new functionality
- `api/` and `dashboard/`
  expose the portfolio, policy, and overnight run state

## New Concepts To Add

- `SeedPacket`
- `PortfolioItem`
- `EvidenceRecord`
- `ReviewDecision`
- `SemanticTerm`
- `PolicyRule`
- `AutonomyTier`
- `CampaignRun`
- `LaneStatus`

## Lifecycle To Implement

`SEED -> NURSERY -> PROBE -> INCUBATING -> ACTIVE -> SCALING -> ARCHIVED -> COMPOSTED`

Promotion must depend on:

- named mission linkage
- evidence threshold
- semantic coverage
- legal posture
- budget cap
- autonomy tier
- kill criteria

## Hard Rules

1. No new repo.
2. No second orchestrator.
3. No bypass around `organism.py` or telos gates.
4. No autonomous external action without explicit autonomy tier and policy coverage.
5. No multi-writer overnight pack in the dirty shared tree.
6. Every overnight lane must write a durable artifact into `~/.dharma/`.

### Task 1: Introduce Constitutional Portfolio Primitives

**Files:**
- Create: `dharma_swarm/constitutional_portfolio.py`
- Modify: `dharma_swarm/telos_graph.py`
- Test: `tests/test_constitutional_portfolio.py`

**Step 1: Write the failing tests**

Cover:
- seed creation with explicit lifecycle state
- promotion from `NURSERY` to `ACTIVE`
- WIP cap enforcement per domain
- rejection when evidence or policy coverage is missing

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_constitutional_portfolio.py -q`

Expected: FAIL because portfolio types and promotion logic do not exist.

**Step 3: Write minimal implementation**

Implement:
- `SeedLifecycle` enum
- `SeedPacket` model
- `PortfolioItem` model
- `PortfolioReview` model
- helper functions for scoring, WIP caps, and promotion eligibility

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_constitutional_portfolio.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/constitutional_portfolio.py dharma_swarm/telos_graph.py tests/test_constitutional_portfolio.py
git commit -m "feat: add constitutional portfolio primitives"
```

### Task 2: Extend `telos_graph.py` Into A Real Seed And Campaign Graph

**Files:**
- Modify: `dharma_swarm/telos_graph.py`
- Modify: `dharma_swarm/telos_substrate.py`
- Test: `tests/test_telos_graph.py`

**Step 1: Write the failing tests**

Cover:
- `propose_seed()` creates `SEED` records with proposer metadata
- `promote_seed()` requires review approval
- `attach_evidence()` persists evidence and review state
- graph listing can filter by lifecycle and domain

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_telos_graph.py -q`

Expected: FAIL with missing methods or missing lifecycle fields.

**Step 3: Write minimal implementation**

Add:
- seed proposal methods
- evidence attachment methods
- lifecycle-aware list and query methods
- substrate seeding for founder genes rather than only flat objectives

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_telos_graph.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/telos_graph.py dharma_swarm/telos_substrate.py tests/test_telos_graph.py
git commit -m "feat: add telos seed lifecycle and evidence graph"
```

### Task 3: Add Semantic And Legal Governance Layers

**Files:**
- Create: `dharma_swarm/semantic_lattice.py`
- Create: `dharma_swarm/legal_governance.py`
- Modify: `dharma_swarm/dharma_corpus.py`
- Test: `tests/test_semantic_lattice.py`
- Test: `tests/test_legal_governance.py`

**Step 1: Write the failing tests**

Cover:
- semantic term registration and canonical aliases
- policy rules mapped to autonomy tiers
- required human signoff for external publication, money movement, regulated claims, or partner outreach
- rejection of seeds with undefined core terms

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_semantic_lattice.py tests/test_legal_governance.py -q`

Expected: FAIL because semantic and legal layers do not exist.

**Step 3: Write minimal implementation**

Implement:
- controlled vocabulary with canonical term IDs
- policy rule model with action scope, autonomy tier, and required approvers
- helpers that evaluate a seed or campaign against semantic coverage and legal posture

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_semantic_lattice.py tests/test_legal_governance.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/semantic_lattice.py dharma_swarm/legal_governance.py dharma_swarm/dharma_corpus.py tests/test_semantic_lattice.py tests/test_legal_governance.py
git commit -m "feat: add semantic and legal governance layers"
```

### Task 4: Wire The Dual Loop Into Director And Organism

**Files:**
- Modify: `dharma_swarm/thinkodynamic_director.py`
- Modify: `dharma_swarm/organism.py`
- Modify: `dharma_swarm/mission_contract.py`
- Modify: `dharma_swarm/signal_bus.py`
- Test: `tests/test_thinkodynamic_director.py`
- Test: `tests/test_organism.py`

**Step 1: Write the failing tests**

Cover:
- director selects external work first when a real deadline exists
- internal work only selected when tied to a named bottleneck
- organism HOLD verdict can demote or freeze risky campaigns
- algedonic signals become visible to the portfolio layer

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_thinkodynamic_director.py tests/test_organism.py -q`

Expected: FAIL because portfolio-aware routing and verdict propagation do not exist.

**Step 3: Write minimal implementation**

Implement:
- portfolio-aware mission selection
- dual-loop routing rules
- gnani/algedonic propagation into campaign status
- campaign brief generation with mission linkage and kill criteria

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_thinkodynamic_director.py tests/test_organism.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/thinkodynamic_director.py dharma_swarm/organism.py dharma_swarm/mission_contract.py dharma_swarm/signal_bus.py tests/test_thinkodynamic_director.py tests/test_organism.py
git commit -m "feat: wire dual-loop portfolio into director and organism"
```

### Task 5: Add Canonical `dgc` Commands For The New Layer

**Files:**
- Modify: `dharma_swarm/dgc_cli.py`
- Test: `tests/test_dgc_cli.py`

**Step 1: Write the failing tests**

Cover:
- `dgc seeds status`
- `dgc seeds nursery`
- `dgc seeds promote`
- `dgc policy check`
- `dgc overnight constitution start|status|stop|report`

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_dgc_cli.py -q`

Expected: FAIL because commands do not exist.

**Step 3: Write minimal implementation**

Add subcommands that:
- read and print portfolio state
- check semantic/legal readiness
- launch and report on the overnight pack

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_dgc_cli.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/dgc_cli.py tests/test_dgc_cli.py
git commit -m "feat: add dgc portfolio and overnight commands"
```

### Task 6: Build The Overnight `tmux` Pack

**Files:**
- Create: `scripts/start_constitutional_overnight_tmux.sh`
- Create: `scripts/status_constitutional_overnight_tmux.sh`
- Create: `scripts/stop_constitutional_overnight_tmux.sh`
- Create: `docs/missions/CONSTITUTIONAL_OVERNIGHT_PACK_2026-03-22.md`
- Test: `tests/test_constitutional_overnight_scripts.py`

**Step 1: Write the failing tests**

Cover:
- session names are stable
- only one write-capable lane is started
- mission file path is passed through
- status script reports all expected lanes

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_constitutional_overnight_scripts.py -q`

Expected: FAIL because scripts do not exist.

**Step 3: Write minimal implementation**

Launch lanes:
- `dgc_constitution_director`
- `dgc_constitution_nursery`
- `dgc_constitution_policy`
- `dgc_constitution_writer`
- `dgc_constitution_verify`
- `dgc_constitution_handoff`
- `dgc_caffeine_constitution`

Each lane must write logs into `~/.dharma/constitution/<run_id>/`.

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_constitutional_overnight_scripts.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/start_constitutional_overnight_tmux.sh scripts/status_constitutional_overnight_tmux.sh scripts/stop_constitutional_overnight_tmux.sh docs/missions/CONSTITUTIONAL_OVERNIGHT_PACK_2026-03-22.md tests/test_constitutional_overnight_scripts.py
git commit -m "feat: add constitutional overnight tmux pack"
```

### Task 7: Add `launchd` Supervisors For The Overnight Pack

**Files:**
- Create: `scripts/com.dharma.constitution-supervisor.plist`
- Modify: `scripts/install_dashboard_launch_agents.sh`
- Test: `tests/test_custodians.py`

**Step 1: Write the failing tests**

Cover:
- plist renders absolute paths
- plist points to the start script and log files
- supervisor can be installed without conflicting with the cron daemon

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_custodians.py -q`

Expected: FAIL because the new plist path is unknown.

**Step 3: Write minimal implementation**

Add:
- a launchd agent for scheduled nightly startup
- an install path in existing launch-agent tooling
- log and PID destinations under `~/.dharma/constitution/`

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_custodians.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/com.dharma.constitution-supervisor.plist scripts/install_dashboard_launch_agents.sh tests/test_custodians.py
git commit -m "feat: add launchd supervisor for constitutional overnight pack"
```

### Task 8: Expose The Institution Cockpit In API And Dashboard

**Files:**
- Create: `api/routers/constitutional.py`
- Modify: `api/main.py`
- Create: `dashboard/src/app/dashboard/constitution/page.tsx`
- Create: `dashboard/src/components/dashboard/ConstitutionControlPlane.tsx`
- Test: `tests/test_constitutional_router.py`
- Test: `dashboard/src/lib/constitutionalControlPlane.test.ts`

**Step 1: Write the failing tests**

Cover:
- API returns portfolio, lane status, policy queue, and run summary
- dashboard renders sections for nursery, campaigns, policy, and run health

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_constitutional_router.py -q`

Run: `cd ~/dharma_swarm/dashboard && npm test -- constitutionalControlPlane`

Expected: FAIL because endpoint and UI do not exist.

**Step 3: Write minimal implementation**

Expose:
- `/constitutional/status`
- `/constitutional/seeds`
- `/constitutional/policy-queue`
- `/constitutional/runs/latest`

Render:
- constitutional health strip
- nursery table
- promotion queue
- overnight lane health
- morning handoff summary

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_constitutional_router.py -q`

Run: `cd ~/dharma_swarm/dashboard && npm test -- constitutionalControlPlane`

Expected: PASS

**Step 5: Commit**

```bash
git add api/routers/constitutional.py api/main.py dashboard/src/app/dashboard/constitution/page.tsx dashboard/src/components/dashboard/ConstitutionControlPlane.tsx tests/test_constitutional_router.py dashboard/src/lib/constitutionalControlPlane.test.ts
git commit -m "feat: add constitutional control plane API and dashboard"
```

### Task 9: Add Morning Handoff And Quality Ledger

**Files:**
- Create: `dharma_swarm/overnight_handoff.py`
- Modify: `dharma_swarm/daemon_config.py`
- Modify: `dharma_swarm/pulse.py`
- Test: `tests/test_overnight_handoff.py`

**Step 1: Write the failing tests**

Cover:
- morning ledger is written even after partial lane failure
- ledger includes wins, blockers, evidence delta, policy delta, and next seeds
- ledger links back to logs and run artifacts

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_overnight_handoff.py -q`

Expected: FAIL because the handoff builder does not exist.

**Step 3: Write minimal implementation**

Add:
- run manifest writer
- morning summary generator
- “next 3 seeds” output for the following night

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_overnight_handoff.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/overnight_handoff.py dharma_swarm/daemon_config.py dharma_swarm/pulse.py tests/test_overnight_handoff.py
git commit -m "feat: add overnight handoff and quality ledger"
```

### Task 10: Add A Real Overnight Supervisor

**Files:**
- Create: `dharma_swarm/overnight_supervisor.py`
- Modify: `dharma_swarm/loop_supervisor.py`
- Modify: `dharma_swarm/dgc_cli.py`
- Modify: `scripts/start_constitutional_overnight_tmux.sh`
- Modify: `scripts/status_constitutional_overnight_tmux.sh`
- Test: `tests/test_overnight_supervisor.py`

**Step 1: Write the failing tests**

Cover:
- stale heartbeat detection
- early-finish detection
- loop detection from repeated errors and repeated snapshots
- automatic `REPLAN` creation after early completion without next slice
- lane freeze after repeated retry storms

**Step 2: Run test to verify it fails**

Run: `cd ~/dharma_swarm && pytest tests/test_overnight_supervisor.py -q`

Expected: FAIL because the overnight supervisor does not exist.

**Step 3: Write minimal implementation**

Implement:
- per-lane heartbeat contract
- supervisor state machine
- intervention ladder
- recovery artifact writer
- `dgc overnight constitution supervise|status`

**Step 4: Run test to verify it passes**

Run: `cd ~/dharma_swarm && pytest tests/test_overnight_supervisor.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add dharma_swarm/overnight_supervisor.py dharma_swarm/loop_supervisor.py dharma_swarm/dgc_cli.py scripts/start_constitutional_overnight_tmux.sh scripts/status_constitutional_overnight_tmux.sh tests/test_overnight_supervisor.py
git commit -m "feat: add overnight supervisor with replan and loop recovery"
```

### Task 11: Run Full Verification And Dry-Run The 8-Hour Pack

**Files:**
- Modify as needed based on failures
- Verify: `tests/`, `scripts/`, `docs/missions/CONSTITUTIONAL_OVERNIGHT_PACK_2026-03-22.md`

**Step 1: Run focused Python verification**

Run:

```bash
cd ~/dharma_swarm && pytest \
  tests/test_constitutional_portfolio.py \
  tests/test_telos_graph.py \
  tests/test_semantic_lattice.py \
  tests/test_legal_governance.py \
  tests/test_thinkodynamic_director.py \
  tests/test_organism.py \
  tests/test_constitutional_overnight_scripts.py \
  tests/test_overnight_handoff.py -q
```

Expected: PASS

**Step 2: Run CLI smoke**

Run:

```bash
cd ~/dharma_swarm && python3 -m dharma_swarm.dgc_cli seeds status
cd ~/dharma_swarm && python3 -m dharma_swarm.dgc_cli policy check
cd ~/dharma_swarm && python3 -m dharma_swarm.dgc_cli overnight constitution status
```

Expected: commands return structured output without tracebacks.

**Step 3: Run overnight pack dry run**

Run:

```bash
cd ~/dharma_swarm && bash scripts/start_constitutional_overnight_tmux.sh 1 --dry-run
cd ~/dharma_swarm && bash scripts/status_constitutional_overnight_tmux.sh
cd ~/dharma_swarm && bash scripts/stop_constitutional_overnight_tmux.sh
```

Expected: all lanes render correctly and teardown succeeds cleanly.

**Step 4: Record rollout note**

Write:
- what remains manual
- what still requires human signoff
- what the first real 8-hour run should target

**Step 5: Commit**

```bash
git add .
git commit -m "chore: verify constitutional overnight build pack"
```

## First Real 8-Hour Mission

The first overnight run should not try to build the whole future at once.

It should target:

1. seed/campaign lifecycle inside `telos_graph.py`
2. semantic/legal readiness gate
3. `dgc` overnight commands
4. one inspectable dashboard page
5. morning quality ledger

## What Wants To Emerge

The system is pointing toward a clean three-body arrangement:

- `dharma_swarm`: the living runtime and self-evolving organism
- `dgc`: the operator, control, and introspection interface
- constitutional portfolio layer inside `dharma_swarm`: the governed seed factory that turns signals into ventures, research programs, and campaigns

That gives one body, one interface, one evolution substrate.

Plan complete and saved to `docs/plans/2026-03-22-constitutional-organism-overnight-build.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
