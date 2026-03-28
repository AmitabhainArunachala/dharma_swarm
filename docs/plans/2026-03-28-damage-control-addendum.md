# Damage Control Addendum

Date: 2026-03-28
Repo: `/Users/dhyana/dharma_swarm`
Branch: `checkpoint/dashboard-stabilization-2026-03-19`
Head: `307ea5065c80caff2cc6b0f73afae4fe83fac612`

## Independent Read

The earlier hot-map is directionally correct, but the tree has moved further into
multi-seam contention since that snapshot. This is no longer just a "hot files"
problem. It is a branch-governance problem.

Current git shape:

- `origin/main...HEAD`: `0 behind / 31 ahead`
- dirty entries: `253`
- tracked dirty: `122`
- untracked: `131`

Current dirty distribution by top-level area:

- `dharma_swarm`: `102`
- `tests`: `74`
- `docs`: `34`
- `scripts`: `15`
- `dashboard`: `4`
- `api`: `3`

## Findings

### 1. The trust bottleneck is still the central fusion seam

The following files are both central and materially dirty right now:

- `dharma_swarm/agent_runner.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/orchestrate_live.py`
- `dharma_swarm/overnight_director.py`
- `dharma_swarm/thinkodynamic_director.py`
- `api/routers/chat.py`
- `dharma_swarm/cron_runner.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/mission_contract.py`

Current diff size for the worst of them:

- `dharma_swarm/agent_runner.py`: `1314` added / `45` removed
- `dharma_swarm/orchestrate_live.py`: `431` added / `46` removed
- `dharma_swarm/dgc_cli.py`: `387` added / `25` removed
- `dharma_swarm/overnight_director.py`: `311` added / `56` removed
- `dharma_swarm/providers.py`: `271` added / `90` removed
- `api/routers/chat.py`: `280` added / `35` removed

This means the same files are serving as runtime, orchestration, operator UX, and
integration surfaces at the same time.

### 2. Two new seams are active that the current freeze plan underweights

There are now at least two additional live seams beyond the original six-seam map.

Scout and synthesis seam:

- `dharma_swarm/scout_report.py`
- `dharma_swarm/scout_framework.py`
- `dharma_swarm/synthesis_agent.py`
- `dharma_swarm/scout_audit.py`
- `dharma_swarm/scout_health.py`
- `tests/test_scout_audit.py`
- `tests/test_scout_health.py`

Constitutional and certified-lanes seam:

- `dharma_swarm/certified_lanes.py`
- `dharma_swarm/canonical_replay.py`
- `dharma_swarm/constitutional_size_check.py`
- `dharma_swarm/dharma_context_mcp.py`
- `docs/plans/2026-03-28-certified-lanes-next-instance-handoff.md`
- `docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md`

These are not minor edits. They are new subsystems being born directly in the
integration branch.

### 3. The branch is being used as a catch-all landing zone

The branch already has a large worktree topology available, including dedicated
homes for operator-shell, mission rail, overnight supervisor, repo spine cleanup,
verified runtime, and roaming work. Despite that, the main branch is still taking
new experiments and new operational seams directly.

That is the core governance failure.

### 4. Product-surface and runtime truth are still coupled

This coupling is still visible in:

- `api/routers/chat.py`
- `dashboard/src/lib/chatProfiles.ts`
- `dashboard/src/lib/chatProfiles.test.ts`

If dashboard/profile work and provider/runtime work continue landing in the same
branch at the same time, operator trust will stay low even if individual tests
pass.

## Damage-Control Call

### Freeze now

Treat these as `freeze-only` until the branch is trustworthy again:

- `dharma_swarm/swarm.py`
- `dharma_swarm/organism.py`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/orchestrate_live.py`
- `api/main.py`
- `api/routers/chat.py`

Allowed:

- blocker bugfixes
- assertions
- adapters
- metrics
- truthfulness/status corrections
- tests

Disallowed:

- new product surfaces
- new strategic roles
- new background loops
- new mission rails
- new experimental subsystems

### Finish here

Only two seams are worth finishing on this branch:

1. Provider and execution truthfulness
2. Scheduler and resume-state truthfulness

That means:

- `dharma_swarm/agent_runner.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/runtime_provider.py`
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/cron_runner.py`
- `dharma_swarm/launchd_job_runner.py`
- `dharma_swarm/overnight_director.py`
- `dharma_swarm/doctor.py`

### Split immediately

Do not continue these on the integration branch:

Scout and synthesis work:

- move `scout_*`, `synthesis_agent.py`, and scout tests to a dedicated scout worktree

Constitutional and certified-lanes work:

- move `certified_lanes.py`, `canonical_replay.py`, `constitutional_size_check.py`,
  `dharma_context_mcp.py`, and their plan docs to a dedicated governance worktree

Mission and economic expansion:

- move `mission_contract.py`-adjacent expansion to the existing mission worktree

Dashboard polish:

- move `dashboard/src/lib/chatProfiles*` and related operator shell UI work to the
  operator-shell clean worktree

## Blunt Read

The repo is not mainly suffering from "too much ambition". It is suffering from
too many ambitions being integrated into the same branch at once.

If the next 24 hours do not enforce a stop/finish/split discipline, the cost is
not just merge pain. The cost is losing the ability to know which surfaces are
actually real.

