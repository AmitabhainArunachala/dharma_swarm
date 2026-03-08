# DGC Forensic Truth Report (2026-03-08)

## Scope
- Repo: `~/dharma_swarm`
- Branch: `split/2026-03-08` @ `8077792`
- Audit mode: static code audit + executable command verification + full pytest evidence log

## Executive Verdict
- DGC is **real and operational** as a local self-evolving orchestrator with gating, scoring, archive lineage, swarm orchestration, TUI runner, and CLI control paths.
- DGC is **not yet the full blueprint stack** (LangGraph/Temporal/Neo4j/RAPTOR are not wired in Python runtime code).
- NVIDIA lanes are **implemented as clients + CLI commands**, but currently **runtime blocked** in this environment (no reachable local services).
- Memory continuity across TUI restarts is now wired to session restore, but cross-session continuity still depends on which entrypoint you run and whether data was externalized.

## Hard Evidence (Commands)
- Full tests: `1745 passed, 5566 warnings in 36.20s`
- Warning pressure: `RuntimeWarning=2`, `asyncio deprecation warnings=10`
- Mission status (strict+tracked): `exit_code=3` (tracked wiring 0/8; accelerator checks blocked).
- Core health check command reports healthy trace/failure metrics.

Evidence files:
- `reports/forensic_pytest_output.txt`
- `reports/forensic_mission_status.json`
- `reports/forensic_status.txt`
- `reports/forensic_health_check.txt`
- `reports/forensic_rag_health.txt`
- `reports/forensic_flywheel_jobs.txt`

## Architecture Reality Matrix
| Claim | Reality | Evidence |
|---|---|---|
| Darwin self-evolution loop | **Implemented** (propose -> gate -> test/sandbox -> evaluate -> archive -> optional auto-commit) | `dharma_swarm/evolution.py` lines ~1-1365 |
| Planner/Executor split | **Implemented in Darwin cycle plan artifact** | `dharma_swarm/evolution.py` lines ~97-223 |
| Mandatory think points | **Implemented in gate system + tests** | `dharma_swarm/telos_gates.py`; `tests/test_telos_gates.py` |
| Circuit breaker / repeated failure signature | **Implemented** | `dharma_swarm/evolution.py` lines ~243-282, ~944-953 |
| Swarm orchestration + ledgers | **Implemented** | `dharma_swarm/orchestrator.py`; `dharma_swarm/session_ledger.py` |
| TUI session continuity restore | **Implemented** | `dharma_swarm/tui/app.py` lines ~164-215 |
| TUI stale runner lock recovery | **Implemented** | `dharma_swarm/tui/app.py` lines ~276-281 and ~418-430; `tui/engine/provider_runner.py` line ~72 |
| Provider matrix | **Partial** (many providers implemented in `providers.py`; TUI runner path only wires Claude adapter) | `dharma_swarm/providers.py`; `dharma_swarm/tui/engine/provider_runner.py` lines ~90-99 |
| Qdrant knowledge backend | **Partial/optional** (client-backed store + fallback local) | `dharma_swarm/engine/knowledge_store.py` |
| Neo4j graph memory | **Not wired in runtime code** | `rg` count = 0 for `neo4j` in Python package code |
| LangGraph workflows | **Not wired in runtime code** | `rg` count = 0 for `langgraph` / `StateGraph` |
| Temporal durable execution | **Not wired in runtime code** | `rg` count = 0 for `temporalio` |
| NVIDIA RAG/Data Flywheel clients | **Implemented but runtime blocked here** | `dharma_swarm/integrations/*.py`, `dgc_cli` rag/flywheel cmds, mission-status accelerators |

## Module Census (File-by-File)
- Python module files audited: **114**
- Status: `{'data_or_script': 11, 'implemented': 101, 'abstract_or_stub': 2}`
- Maturity: `{'verified': 80, 'lightly_verified': 23, 'unverified_or_indirect': 9, 'foundation_abstract': 2}`

Abstract/stub boundary files:
- `dharma_swarm/providers.py` (NotImplementedError markers: 2)
- `dharma_swarm/providers_extended.py` (NotImplementedError markers: 3)

Largest unverified-or-indirect modules (by LOC):
- `dharma_swarm/jikoku_instrumentation.py` LOC=449 domain=core
- `dharma_swarm/protocols/recursive_reading.py` LOC=447 domain=core
- `dharma_swarm/jikoku_fitness.py` LOC=179 domain=core
- `dharma_swarm/tui/engine/governance.py` LOC=121 domain=tui
- `dharma_swarm/tui/widgets/prompt_input.py` LOC=86 domain=tui
- `dharma_swarm/tui/commands/palette.py` LOC=85 domain=tui
- `dharma_swarm/tui/widgets/tool_call_card.py` LOC=83 domain=tui
- `dharma_swarm/tui/widgets/thinking_panel.py` LOC=61 domain=tui
- `dharma_swarm/tui/theme/dharma_dark.py` LOC=37 domain=tui

Complete file-by-file table:
- `reports/forensic_file_truth_table.md`
- `reports/forensic_file_map.json`
- `reports/forensic_file_inventory.json`

## Build History (What Happened)
- Commit history in this repo has **15 commits** from initial core package to current cron/daemon and TUI/session layers.
- Major progression observed in order: core package -> real LLM calls -> pulse daemon/startup crew -> orchestrator -> v1 godel-claw -> TUI modernization -> engine foundations -> cron wiring.

Timeline (oldest -> newest):
- `40c61cc Phase 1: DHARMA SWARM core package — 13 modules, 115 tests passing`
- `882cdc0 Phase 1.5: Real LLM calls + genome wiring from PSMV ecosystem`
- `1105a9f Add pulse daemon (wraps claude -p) and startup crew (5 PSMV roles)`
- `ce034e2 Add autonomous orchestrator: DGC spawns Claude Code swarms on demand`
- `3af6c95 (tag: pre-overnight-build-20260304) pre-overnight-build checkpoint`
- `f23d403 (tag: v1.0.0-godel-claw, origin/main) godel-claw v1: governed self-evolution, living layers, and unified dgc runtime`
- `db963f4 ops: add CI and split-brain guard, canonicalize verification dgc path`
- `fc85017 tui: stream claude output with cancellable runs; pulse: raise headless timeout`
- `693c476 tui: add explicit clipboard paste/copy support and key bindings`
- `75d127d feat(tui): add native /chat handoff to full Claude UI`
- `73d9fb4 feat(cli): add native Claude chat mode and default-mode switch`
- `b8f04f1 Unify DGC TUI v1.1 provider engine and preserve living-layer research corpus`
- `accc003 (origin/v2-gap-closure) Harden TUI stream runner against oversized NDJSON lines`
- `249ded3 feat(engine): add spine/memory foundation and quality-track tests`
- `8077792 (HEAD -> split/2026-03-08, v2-gap-closure, self-optimize-1772973848, main) feat(pulse): add cron-scheduled jobs with safe idempotent execution`

## Reality Gaps That Matter Most
1. **Infra parity gap**: blueprint mentions LangGraph/Temporal/Neo4j, but Python runtime code currently does not wire them.
2. **Tracked wiring gap**: mission-status strict tracked lane fails because critical files are local/untracked in current worktree (`tracked_count=0/8`).
3. **Accelerator runtime gap**: NVIDIA endpoints unreachable right now; integrations are code-complete but service-lane incomplete.
4. **Warning debt**: 5,566 warnings (mostly asyncio policy deprecations), plus provider timeout coroutine warning signal in test output.
5. **Automation semantics gap**: allout loop executes only mapped actions; unmapped high-level TODOs degrade to noop/skips, generating backlog artifacts faster than substantive mutation.

## Plain-Language Bottom Line
DGC is not fake. It is a substantial, running system with real autonomy machinery and real tests. The issue is not "nothing exists"; the issue is **layer mismatch**: core orchestrator/evolution logic is real, while some advertised infrastructure lanes are still declarative or optional, and operational wiring (tracked files + live services) is what is currently failing mission-readiness gates.

## Recommended Next 7 Actions (High ROI)
1. Commit and track the 8 strict mission-status wiring files so tracked lane can pass.
2. Fix provider timeout warning path in `_SubprocessProvider.complete()` and reduce async-policy warning churn.
3. Add one executable end-to-end smoke that must pass: `dgc mission-status` + `dgc status` + one safe evolution dry run.
4. Promote NVIDIA services from optional probes to deterministic start/verify scripts with clear failure diagnostics.
5. Expand `execute_single_step()` mappings so top-ranked backlog items do real work (not noop fallback).
6. Add explicit policy doc for when auto-commit is allowed versus queued for human review.
7. Decide now whether LangGraph/Temporal/Neo4j stay in phase-2 roadmap or get removed from near-term claims to keep narrative truthful.
