# Dirty/Hot Map

Date: 2026-03-28
Repo: `/Users/dhyana/dharma_swarm`

## Branch Shape

- Current branch: `checkpoint/dashboard-stabilization-2026-03-19`
- `origin/main...HEAD`: `0 behind / 31 ahead`
- Current HEAD: `307ea50` `Organism Awakening + Shakti Economic Engine`
- Remote main tip: `c098071` `fix: make semantic concept indexing idempotent`

This is not a lightly dirty branch. It is a long-lived integration branch with
multiple active side branches and worktrees around it.

## Working Tree Dirt

Top-level dirty count from `git status --short`:

- `102` `dharma_swarm`
- `74` `tests`
- `35` `docs`
- `15` `scripts`
- `5` `reports`
- `4` `dashboard`
- `3` `api`

Other single-file dirt exists in:

- `README.md`
- `CLAUDE.md`
- `LIVING_LAYERS.md`
- `pyproject.toml`
- `cron_jobs.json`
- `garden_daemon.py`
- `run_daemon.sh`

## Untracked Expansion

Top-level untracked count:

- `44` `dharma_swarm`
- `31` `tests`
- `32` `docs`
- `20` `references`
- `14` `scripts`
- `7` `reports`

Largest untracked clusters:

- `docs/plans` `17`
- `references` `20`
- `scripts` `14`
- `docs/reports` `7`
- `dharma_swarm/a2a` `5`
- `docs/missions` `3`
- `docs/dse` `3`

This means the repo is not just modified. It is actively accreting new
subsystems, plans, reports, and reference corpora.

## Recent Heat

Top-level file-touch frequency in the last 14 days:

- `656` `dharma_swarm`
- `456` `tests`
- `220` `dashboard`
- `95` `docs`
- `64` `scripts`
- `55` `api`

Aggregate churn over the same window:

- `417747` lines added
- `10390` lines deleted

This is massive additive churn, not small maintenance.

## Hottest Files In Recent History

Most repeatedly touched files in the last 14 days:

1. `dharma_swarm/agent_runner.py` `15`
2. `dharma_swarm/dgc_cli.py` `13`
3. `dharma_swarm/swarm.py` `10`
4. `dharma_swarm/organism.py` `10`
5. `dharma_swarm/orchestrator.py` `10`
6. `dharma_swarm/telic_seam.py` `8`
7. `dharma_swarm/providers.py` `7`
8. `dharma_swarm/models.py` `7`
9. `dharma_swarm/evolution.py` `7`
10. `dharma_swarm/thinkodynamic_director.py` `6`
11. `dharma_swarm/orchestrate_live.py` `6`
12. `dharma_swarm/ontology.py` `6`
13. `dharma_swarm/context.py` `6`
14. `api/routers/chat.py` `6`
15. `api/main.py` `5`

Interpretation:

- the real hot seam is not one feature
- it is the center of the runtime:
  - execution
  - orchestration
  - control plane
  - ontology/context
  - provider routing

## Biggest Dirty Diffs Right Now

Largest tracked diffs by current line delta:

1. `dharma_swarm/agent_runner.py` `+1159 / -45`
2. `dharma_swarm/orchestrate_live.py` `+431 / -46`
3. `dharma_swarm/dgc_cli.py` `+387 / -25`
4. `tests/test_dgc_cli.py` `+342 / -0`
5. `tests/test_providers_quality_track.py` `+324 / -2`
6. `dharma_swarm/overnight_director.py` `+311 / -56`
7. `api/routers/chat.py` `+280 / -90`
8. `dharma_swarm/providers.py` `+271 / -90`
9. `dharma_swarm/cron_runner.py` `+257 / -9`
10. `dharma_swarm/self_improve.py` `+254 / -37`
11. `dharma_swarm/mission_contract.py` `+248 / -0`
12. `dharma_swarm/thinkodynamic_director.py` `+238 / -77`
13. `dharma_swarm/doctor.py` `+233 / -19`
14. `dharma_swarm/provider_policy.py` `+206 / -91`
15. `dharma_swarm/launchd_job_runner.py` `+162 / -25`

These are not cosmetic edits. They are structural edits in core execution paths.

## Files That Are Both Hot And Dirty

This is the real danger zone: files touched repeatedly in recent history and
still modified now.

Representative overlap:

- `dharma_swarm/agent_runner.py`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/orchestrate_live.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/runtime_provider.py`
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/provider_smoke.py`
- `dharma_swarm/cron_runner.py`
- `dharma_swarm/launchd_job_runner.py`
- `dharma_swarm/overnight_director.py`
- `api/routers/chat.py`
- `api/main.py`
- `tests/test_agent_runner.py`
- `tests/test_dgc_cli.py`
- `tests/test_dashboard_chat_router.py`
- `tests/test_thinkodynamic_director.py`

If work keeps piling into these same files without consolidation, the repo will
keep feeling "alive" while remaining hard to trust.

## Map Of The Current Seams

### 1. Execution / Provider Seam

Core files:

- `dharma_swarm/agent_runner.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/runtime_provider.py`
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/provider_smoke.py`
- `api/routers/chat.py`

Why it is hot:

- provider audit
- certified lanes
- subprocess vs API tool execution
- false-green completion fixes
- dashboard chat surface

Status:

- hottest and dirtiest seam in the repo

### 2. Control Plane / Operator Seam

Core files:

- `dharma_swarm/dgc_cli.py`
- `api/main.py`
- `api/routers/chat.py`
- `dashboard/src/lib/api.ts`
- `dashboard/src/lib/chatProfiles.ts`

Why it is hot:

- operator shell
- dashboard profile registry
- chat routing
- runtime truth surfaces

Status:

- high-risk because both API and CLI surfaces are moving at once

### 3. Strategic Autonomy Seam

Core files:

- `dharma_swarm/orchestrate_live.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/self_improve.py`
- `dharma_swarm/startup_crew.py`

Why it is hot:

- thinkodynamic live canary findings
- self-improve validation concerns
- strategic planning vs execution truthfulness

Status:

- substantively degraded in live runs even when tests pass

### 4. Temporal / Scheduler Seam

Core files:

- `dharma_swarm/overnight_director.py`
- `dharma_swarm/cron_runner.py`
- `dharma_swarm/launchd_job_runner.py`
- `dharma_swarm/pulse.py`
- `dharma_swarm/doctor.py`
- `cron_jobs.json`

Why it is hot:

- REA-style wait/resume work
- launchd state machine
- external wait handoff
- scheduler truth surfaces

Status:

- real progress exists, but scheduler closure is not finished

### 5. Mission / Economic / Field Seam

Core files:

- `dharma_swarm/mission_contract.py`
- `dharma_swarm/ginko_orchestrator.py`
- `dharma_swarm/ginko_brier.py`
- `dharma_swarm/field_knowledge_base.py`
- `docs/missions/*`
- `docs/dse/*`

Why it is hot:

- mission rails
- economic closure spine
- field intelligence expansion
- GAIA/cybernetics activation work

Status:

- fast-growing, but not yet clearly tied into one canonical operator flow

### 6. Assurance / Witness Seam

Core files:

- `dharma_swarm/assurance/scanner_api_envelope.py`
- `dharma_swarm/assurance/scanner_lifecycle.py`
- `dharma_swarm/assurance/scanner_providers.py`
- `dharma_swarm/assurance/scanner_storage.py`
- `dharma_swarm/doctor.py`
- `tests/test_assurance.py`

Why it is hot:

- tests have been green while runtime truth is mixed
- scanners are being used to close the gap between claimed and actual behavior

Status:

- strategically important, still not the canonical truth surface

### 7. Scout / Synthesis Seam

Core files:

- `dharma_swarm/scout_report.py`
- `dharma_swarm/scout_framework.py`
- `dharma_swarm/synthesis_agent.py`
- `dharma_swarm/scout_audit.py`
- `dharma_swarm/scout_health.py`
- `tests/test_scout_audit.py`
- `tests/test_scout_health.py`

Why it matters:

- this is not just more docs or helper code
- it is a new operational seam with new runtime-facing modules and tests

Status:

- should not keep being born directly in the already-hot integration branch

### 8. Governance / Certified-Lanes Seam

Core files:

- `dharma_swarm/certified_lanes.py`
- `dharma_swarm/canonical_replay.py`
- `dharma_swarm/constitutional_size_check.py`
- `dharma_swarm/dharma_context_mcp.py`
- `docs/plans/2026-03-28-certified-lanes-next-instance-handoff.md`
- `docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md`

Why it matters:

- this is a real governance layer forming, not peripheral cleanup
- it cuts across runtime identity, replay, constitutional limits, and operator truth

Status:

- important, but it should no longer accrete directly on the integration branch

## What This Means

The repo is not uniformly chaotic. It has a center of gravity:

- execution/provider routing
- control plane
- strategic autonomy
- temporal scheduler state

The rest of the dirt mostly radiates outward from those seams.

## Recommended Reading Order

If resuming cold, read in this order:

1. `docs/plans/2026-03-28-certified-lanes-next-instance-handoff.md`
2. `docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md`
3. `dharma_swarm/agent_runner.py`
4. `dharma_swarm/providers.py`
5. `api/routers/chat.py`
6. `dharma_swarm/thinkodynamic_director.py`
7. `dharma_swarm/cron_runner.py`
8. `dharma_swarm/launchd_job_runner.py`
9. `dharma_swarm/overnight_director.py`
10. `dharma_swarm/dgc_cli.py`

## Blunt Read

The repo’s current problem is not “too many files” in the abstract.

It is that the same few central files are:

- historically hot
- currently dirty
- architecturally central
- carrying multiple concerns at once

That is where trust erodes.

The addendum conclusion also stands: this has become a branch-governance problem,
not just a hot-files problem.

The first move is not another feature. It is to stop smearing more work across
the same hot seams without consolidation.
