# Interface Mismatch Map — dharma_swarm

**Last X-Ray:** 2026-04-08 (fresh audit against current HEAD `c73db94`+)
**Previous version:** 2026-04-04 (55 module pairs, 13 mismatches, 9 prioritized)
**Maintainer:** Guardian Crew (`guardian_crew.py`) — auto-updates every 4 hours
**How to read this:** Severity = BLOCKER (crashes at runtime), DEGRADED (silent failure / wrong behavior), WARNING (structural smell).

---

## What Changed Since Last Audit

| Mismatch | Old Status | New Status | Resolution |
|----------|-----------|-----------|-----------|
| MM-01: huggingface_hub ImportError | BLOCKER | ✅ RESOLVED | `try/except ImportError` added; heuristic fallback path confirmed |
| MM-02/03: PersistentAgent enum coercion | BLOCKER | ⚠️ STILL LIVE | `orchestrate_live.py:1247` still passes bare strings — confirmed by x-ray |
| MM-04: AgentPool None guard | DEGRADED | ✅ RESOLVED | `SubsystemNotReady` raised at line 870, `_agent_pool` guard present |
| MM-06: Dual StigmergyStore | DEGRADED | ✅ RESOLVED | `run_living_layers_loop` now accepts `stigmergy_store` param; passes swarm's store |
| MM-08: ECC_INSTINCT_SIGNAL constant | DEGRADED | ✅ RESOLVED | `SIGNAL_ECC_INSTINCT` defined in `signal_bus.py:40`, used in `instinct_bridge.py` |
| MM-09: samvara.current_power None chain | DEGRADED | ✅ RESOLVED | Double guard present at `swarm.py:2182-2184` |
| MM-10: AutoProposer stigmergy guard | DEGRADED | ✅ RESOLVED | `auto_proposer.py:297` has `if self._stigmergy is None: return` |
| MM-11: WitnessAuditor ModelRouter provider | DEGRADED | ✅ RESOLVED | `swarm.py:456-457` now uses `OpenRouterFreeProvider()` |
| NEW-01: archaeology_ingestion palace.query | BLOCKER | ✅ FIXED THIS SESSION | Replaced with `palace.recall(PalaceQuery(...))` + correct `max_results=` |
| NEW-02: dgm_loop _provider attr | DEGRADED | ✅ FIXED THIS SESSION | Removed nonexistent `hasattr(engine, '_provider')` check |

**Net change:** 7 resolved, 2 new fixed, 1 still live BLOCKER, 4 structural degraded remain.

---

## Current Live Mismatches

### MM-02/03 — BLOCKER: PersistentAgent enum deserialization (still live)

**File:** `orchestrate_live.py:1247`
**What's wrong:** `child_spec.get("role", "worker")` returns a bare string (`"conductor"`).
`PersistentAgent.__init__` declares `role: AgentRole`. Pydantic v2 lax mode may coerce it — but this is brittle and will break on any invalid value.

```python
# CURRENT (brittle):
child = PersistentAgent(
    role=outcome.child_spec.get("role", "worker"),           # str
    provider_type=outcome.child_spec.get("default_provider", "openrouter_free"),  # str
)

# CORRECT:
from dharma_swarm.models import AgentRole, ProviderType as PT
child = PersistentAgent(
    role=AgentRole(outcome.child_spec.get("role", "worker")),
    provider_type=PT(outcome.child_spec.get("default_provider", "openrouter_free")),
)
```

**Fix complexity:** 2 lines. High leverage — replication is a critical path.

---

### MM-05 — DEGRADED: Private Orchestrator method coupling

**File:** `swarm.py:1883-1895`
**What's wrong:** `swarm.py` calls `self._orchestrator._classify_failure()`, `_resolve_retry_policy()`, `_apply_failure_retry_defaults()` — all single-underscore private methods. Any internal refactor of `orchestrator.py` silently breaks `swarm.py`'s retry logic.

**Fix:** Add `Orchestrator.retry_policy_for_failure(task, error, source, meta)` as a public API method. 1-hour refactor.

---

### MM-07 — DEGRADED: MetaEvolutionEngine cadence mismatch

**File:** `orchestrate_live.py:399,407`
**What's wrong:** `observe_cycle_result()` is called twice per cycle number (once with synthetic fitness, once with `auto_evolve` result). `n_object_cycles_per_meta=2` fires after 2 total calls — so meta-adaptation can trigger within a single evolution cycle, not after 2 separate cycles as intended.

**Fix:** Only call `observe_cycle_result` once per cycle — with the actual `CycleResult` from `auto_evolve`, not the synthetic fitness estimate.

---

### MM-12 — DEGRADED: Same as MM-02/03 (second call site)

**File:** `orchestrate_live.py:1354-1364` (conductor configs path)
**Status:** This path uses already-constructed enum values (`role=cfg["role"]` where `cfg["role"]` is `AgentRole.CONDUCTOR`) — no mismatch here. **This is fine.** The problem is only in the replication monitor path at line 1247.

---

## New Module Contracts (Added This Sprint)

These contracts must be maintained by any future changes:

| Module | Class | Method | Signature | Notes |
|--------|-------|--------|-----------|-------|
| `memory_palace.py` | `MemoryPalace` | `recall(query)` | `query: PalaceQuery` → `PalaceResponse` | Use `PalaceQuery(text=..., max_results=...)` NOT `query()` |
| `memory_palace.py` | `MemoryPalace` | `ingest(content, source, *, layer, tags, metadata)` | Returns `str` doc_id | All keyword-only after `source` |
| `memory_palace.py` | `PalaceQuery` | `__init__` | `text: str, max_results: int = 10` | NOT `top_k=` |
| `memory_palace.py` | `PalaceResult` | attrs | `.content`, `.source`, `.score`, `.layer` | NOT `.relevance_score` |
| `evolution.py` | `DarwinEngine` | `auto_evolve(provider, source_files, shadow, timeout, context)` | `provider` is required | No `_provider` instance attr |
| `archaeology_ingestion.py` | `ArchaeologyIngestionDaemon` | `run_once()` | async, returns `dict[str, int]` | |
| `dgm_loop.py` | `DGMLoop` | `run_one_generation(source_file, fitness_context, timeout)` | Returns `DGMResult` | |
| `world_actions.py` | `WorldActionResult` | `to_json()` | Returns JSON string | |
| `gnani_lodestone.py` | `GnaniLodestone` | `seed_all()` | async, returns `dict[str, int]` | idempotent |
| `guardian_crew.py` | `GuardianFinding` | attrs | `.severity`, `.check`, `.title`, `.detail`, `.file`, `.line`, `.fix_hint` | |

---

## The Guardian Crew (Future-Proofing)

The old approach was: audit manually every few days, miss things, fix them under fire.

The new approach: `guardian_crew.py` runs as a 15th concurrent loop in `orchestrate_live`.

**Three agents, one cycle (every 4 hours):**

```
AUDITOR        — Scans all .py files for syntax errors
               — Checks method existence for all contracts in _METHOD_EXISTENCE_CHECKS
               — Verifies import chains for all critical modules
               — O(n) scan, no imports executed, safe to run always

LOOP_WATCHER   — Checks that evolution archive, stigmergy, telos, gnani are alive
               — Measures freshness (stale > 24h = DEGRADED)
               — Checks evolution archive for zero applied entries (shadow mode stuck)
               — Reads circuit_breakers.json for open breakers

ROUTER_PROBE   — Reads circuit_breakers.json for open providers
               — Scans last 1000 log lines for repeated provider error patterns
               — Checks env vars for missing API keys
```

**Output:**
- `~/.dharma/guardian/GUARDIAN_REPORT.md` — full report, overwritten each cycle
- `GUARDIAN_REPORT.md` in repo root — version-controlled visibility
- GitHub issues for BLOCKER findings (deduped via `issues_created.json`)

**How to add a new check:** Add one `async def run_*_check()` function, one line in the relevant `run_auditor/run_loop_watcher/run_router_probe` function, one entry in `_METHOD_EXISTENCE_CHECKS` or `_IMPORT_CHECKS`. The report synthesizer handles everything else.

**How to extend the contract registry:**
```python
# Add to _METHOD_EXISTENCE_CHECKS in guardian_crew.py:
("dharma_swarm.your_new_module", "YourClass", "your_method", "BLOCKER"),

# Add to _IMPORT_CHECKS:
("dharma_swarm.your_new_module", "BLOCKER"),
```

---

## Module Pair Status (Refreshed)

| # | Module Pair | Status |
|---|-------------|--------|
| 1 | `orchestrate_live` → `swarm.SwarmManager` | ✅ |
| 2 | `swarm` → `orchestrator.Orchestrator` (public API) | ✅ |
| 3 | `swarm` → `orchestrator._classify_failure` (private) | ⚠️ DEGRADED |
| 4 | `swarm` → `agent_runner.AgentPool` | ✅ |
| 5 | `swarm` → `evolution.DarwinEngine` | ✅ |
| 6 | `swarm` → `meta_evolution.MetaEvolutionEngine` | ⚠️ DEGRADED (cadence) |
| 7 | `swarm` → `auto_proposer.AutoProposer` (stigmergy) | ✅ |
| 8 | `swarm` → `organism.OrganismRuntime.samvara` | ✅ |
| 9 | `swarm` → `witness.WitnessAuditor` | ✅ |
| 10 | `swarm` → `stigmergy.StigmergyStore` | ✅ |
| 11 | `orchestrate_live` → `persistent_agent.PersistentAgent` (replication) | ⚠️ BLOCKER |
| 12 | `orchestrate_live` → `message_bus.receive()` semantics | ⚠️ DEGRADED |
| 13 | `orchestrate_live` → `meta_evolution.observe_cycle_result` cadence | ⚠️ DEGRADED |
| 14 | `orchestrate_live` → `living_layers` (dual StigmergyStore) | ✅ |
| 15 | `archaeology_ingestion` → `memory_palace.recall()` | ✅ (fixed this session) |
| 16 | `dgm_loop` → `evolution.DarwinEngine.auto_evolve()` | ✅ (fixed this session) |
| 17 | `gnani_lodestone` → `task_board.get_by_title()` | ⚠️ DEGRADED (method may not exist) |
| 18 | `gnani_lodestone` → `telos_graph.get_by_name()` | ⚠️ DEGRADED (method may not exist) |
| 19 | `guardian_crew` → `world_actions.github_create_issue()` | ✅ |
| 20 | `orchestrate_live` → `guardian_crew.start_guardian_loop()` | ✅ |

---

*This document is maintained by the Guardian Crew. Do not edit the "Current Live Mismatches" section manually — it will be overwritten on the next guardian cycle. Add new contracts to `guardian_crew.py:_METHOD_EXISTENCE_CHECKS` to ensure they are continuously monitored.*
