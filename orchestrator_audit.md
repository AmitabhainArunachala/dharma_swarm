# Production-Readiness Audit: `orchestrator.py`

**File:** `dharma_swarm/dharma_swarm/orchestrator.py`
**Lines:** 2208
**Auditor:** Senior DevOps — forensic review
**Date:** 2026-04-05

---

## 1. Module Purpose

The `Orchestrator` class is the central dispatch engine of the dharma_swarm system. It connects a duck-typed `TaskBoard` (source of ready tasks) to an `AgentPool` (source of idle agents), matching them one-to-one via topology patterns (fan-out, fan-in, pipeline, broadcast, and genome-based topologies). On each `tick()`, it collects completed/stale background tasks (`_collect_completed`), finds new ready-task-to-idle-agent matches (`route_next`), dispatches work through telos gate checks and claim management (`_assign_dispatch`), executes tasks as background asyncio tasks (`_execute_task`), and persists results to shared notes and stigmergy marks (`_persist_result`). It also maintains a coordination layer built on sheaf cohomology (`_refresh_coordination_state`) that detects global truths and productive disagreements among agents and annotates tasks accordingly. The orchestrator is the beating heart of Loop 1 (Swarm Task Loop) — if it breaks, all downstream feedback loops starve.

---

## 2. Loop Closure Verification

### Loop 1: Swarm Task Loop

#### SENSE: `route_next()` finds ready tasks (lines 274–337)

- **Line 280:** `ready = await self._board.get_ready_tasks()` — queries the task board for all tasks with `PENDING` status.
- **Line 288:** `ready = [t for t in ready if t.id not in self._running_tasks]` — filters out tasks already executing.
- **Line 289:** `ready = [t for t in ready if self._is_retry_window_open(t)]` — filters out tasks in retry backoff (line 704–710 checks `retry_not_before_epoch` in task metadata against `time.time()`).

#### MATCH: `route_next()` matches tasks to idle agents (lines 282–336)

- **Line 282:** `idle = await self._pool.get_idle_agents()` — queries the agent pool for idle agents.
- **Lines 293–336:** Iterates ready tasks. For each, calls `_select_idle_agent(task, available)` (line 294) which uses a multi-tier selection strategy:
  1. **Name-match** (lines 858–870): Checks `director_preferred_agents` / `preferred_agents` metadata.
  2. **Role-match** (lines 873–877): Checks `coordination_preferred_roles` / `preferred_roles` metadata.
  3. **EFE-biased pick** (lines 905–942): Active inference Expected Free Energy routing (feature-flagged via `ENABLE_EFE_ROUTING`).
  4. **Fitness-biased pick** (lines 944–983): Bayesian fitness-biased selection with 10% exploration (feature-flagged via `ENABLE_FITNESS_ROUTING`).
  5. **FIFO fallback** (lines 894–903): First-idle-first-out.

- **Lines 299–313:** YogaNode constraint check — if `_yoga` is wired, `can_dispatch(task, agent)` is called and any blocking verdict skips the task.

#### ACT: `_execute_task()` calls the agent (line 1932–1933)

- **Line 1896:** `asyncio.create_task(self._execute_task(runner, task, td))` — kicks off background execution.
- **Line 1932–1933:** `result = await asyncio.wait_for(runner.run_task(task), timeout=timeout_seconds)` — this is the exact line where the agent runner's LLM call happens.

#### EVALUATE: On completion, results are stored (lines 1972–2029)

- **Shared notes (file):** Lines 2073–2131 (`_persist_result`) — writes `{agent_name}_notes.md` and `provenance/{task_id}.json` to the shared directory.
- **Stigmergy marks:** Lines 2134–2152 (`_persist_result`) — creates a fresh `StigmergyStore(self._stigmergy_dir)` and calls `await store.leave_mark(mark)`.
- **Signal bus:** Lines 1661–1692 (`_handle_task_failure` only) — emits `ALGEDONIC_TASK_DEAD` to `SignalBus.get()` when a task exhausts all retries. **There is NO signal emission on task success.** The `CYBERNETIC_LOOP_MAP.md` claims the orchestrator "Emits SIGNAL_TASK_COMPLETED to signal_bus" — this does not happen. No `SIGNAL_TASK_COMPLETED` or equivalent is emitted anywhere in orchestrator.py on the success path.
- **Economic spine:** **Not called.** The `CYBERNETIC_LOOP_MAP.md` claims "Records cost in economic_spine" — there is zero reference to `economic_spine` anywhere in orchestrator.py. Token cost recording must happen elsewhere (likely inside `agent_runner.run_task()`), but the orchestrator itself does not close this loop.
- **Task board update:** Line 1986–1991 — `_safe_update_task(td.task_id, status=TaskStatus.COMPLETED, result=result, metadata=success_meta)`.
- **Lifecycle event:** Lines 2008–2013 — emits `task_completed` lifecycle event via message bus and event memory.

#### Does tick N influence tick N+1? — PARTIALLY

**What feeds back:**

1. **Task board state**: Completed tasks are marked `COMPLETED`, so they don't appear in `get_ready_tasks()` next tick. Failed tasks are requeued to `PENDING` with updated retry metadata. ✅
2. **Retry backoff**: `retry_not_before_epoch` (line 1580) is set on failure, and `_is_retry_window_open()` (line 289) checks it on the next tick. ✅
3. **Coordination policy**: `_refresh_coordination_state()` (line 1433) reads tasks and messages to detect disagreements, then annotates tasks with `coordination_preferred_roles` and `coordination_route`. On the next tick, `_select_idle_agent()` reads these metadata fields to route differently. ✅ (every 120s)
4. **Latent gold memory**: `_attach_latent_gold()` (line 764) queries `ConversationMemoryStore.latent_gold()` for relevant prior context, attaching it to task metadata before dispatch. ✅

**What does NOT feed back:**

1. **Stigmergy hot_paths**: The orchestrator WRITES stigmergy marks (line 2149) but NEVER READS them. The `CYBERNETIC_LOOP_MAP.md` claims `route_next()` reads `hot_paths()` from stigmergy — this is false. There is no `hot_paths`, `read_marks`, or any stigmergy read call in orchestrator.py. The stigmergy write is fire-and-forget.
2. **Signal bus**: No `SIGNAL_TASK_COMPLETED` is emitted on success. Only `ALGEDONIC_TASK_DEAD` on exhausted retries. The DarwinEngine and DynamicCorrectionEngine cannot receive task-completion signals from the orchestrator because none are emitted.
3. **Economic spine**: Not referenced at all. No cost recording happens here.
4. **Fitness-biased routing**: Feature-flagged off by default (`ENABLE_FITNESS_ROUTING`). Even when enabled, reads from `_telic_seam.query_agent_fitness()` — which is populated by a separate subsystem, not by the orchestrator itself.

**Verdict: PARTIALLY CLOSED.** The task board status loop closes (completed tasks don't re-dispatch; failed tasks retry with backoff). Coordination policy annotates routing metadata. But the stigmergy feedback path claimed in the architecture docs is broken — the orchestrator is write-only for stigmergy. No task-success signals reach the signal bus. The economic spine is entirely absent.

---

### Loop 2: Organism Heartbeat

The organism heartbeat (in `organism.py`) computes four invariants: criticality (spectral radius), closure_ratio, info_retention, and diversity_equilibrium. These computations require data about the agent interaction graph and task outcomes.

**Does the orchestrator emit signals the organism needs?**

- **No direct signal emissions to the organism.** Searching orchestrator.py for `organism`, `heartbeat`, `SIGNAL_HEARTBEAT`, `signal.*emit`, `emit.*signal` returns zero results.
- The orchestrator publishes lifecycle events via the message bus (`_emit_lifecycle_event` at lines 504–571), specifically: `dispatch_assigned`, `dispatch_blocked`, `task_started`, `task_completed`, `task_failed`, `task_retry_scheduled`, `latent_gold_attached`. These are Message objects published to `orchestrator.lifecycle` channel.
- The organism could theoretically read these messages from the bus to compute interaction graphs, but it does not subscribe to the orchestrator's lifecycle channel — organism.py reads from filesystem artifacts (witness logs, shared notes, stigmergy marks), not from the message bus.

**Verdict: OPEN.** The orchestrator does not emit any signals that the organism's invariant computation directly consumes. The organism computes its invariants from filesystem state (which the orchestrator does write to via shared notes and stigmergy), so there is an indirect, delayed path through the filesystem. But this is not a closed cybernetic loop — it's a side-effect dependency with no guaranteed delivery or freshness.

---

## 3. Bug Report

### BUG-01: `_persist_result` creates a new `StigmergyStore` per call — lock isolation
**File:** `orchestrator.py`, line 2137
**Code:**
```python
store = StigmergyStore(self._stigmergy_dir)
```
**What's wrong:** Each call to `_persist_result` (which happens inside `_execute_task`, potentially in concurrent asyncio tasks) creates a **new** `StigmergyStore` instance. Each instance has its own `asyncio.Lock()` (stigmergy.py line 114). Multiple concurrent task completions will have separate lock instances, defeating the concurrency protection. Concurrent appends to the same JSONL file can interleave, corrupting marks.
**Severity:** HIGH — data corruption under concurrent task completion.
**Fix:** Store a single `StigmergyStore` instance as `self._stigmergy_store` in `__init__` and reuse it:
```python
# In __init__:
self._stigmergy_store: Any = None  # lazy init

# In _persist_result, replace line 2137:
if self._stigmergy_store is None:
    from dharma_swarm.stigmergy import StigmergyStore
    self._stigmergy_store = StigmergyStore(self._stigmergy_dir)
store = self._stigmergy_store
```

---

### BUG-02: `_persist_result` — `result` could be `None`, causing `TypeError` at line 2086
**File:** `orchestrator.py`, line 2086
**Code:**
```python
summary = result[:2000] if len(result) > 2000 else result
```
**What's wrong:** The `result` parameter is typed `str` but `runner.run_task()` could return `None` in practice (the orchestrator stores `result` from `await asyncio.wait_for(runner.run_task(task), ...)` which has return type `str` but Python doesn't enforce it). Line 2083 already defensively uses `(result or "")` but line 2086 calls `len(result)` and `result[:2000]` without a None guard. If `result` is `None`, this raises `TypeError: object of type 'NoneType' has no len()`.
**Severity:** MEDIUM — crashes the success path for tasks that return None, causing the task to appear incomplete.
**Fix:**
```python
result = result or ""
summary = result[:2000] if len(result) > 2000 else result
```

---

### BUG-03: `_persist_result` — `result.split()` at line 2139 with potentially None `result`
**File:** `orchestrator.py`, line 2139
**Code:**
```python
lines = [l.strip() for l in result.split("\n") if l.strip()]
```
**What's wrong:** Same as BUG-02. If `result` is `None`, `result.split("\n")` raises `AttributeError`. This is inside a `try/except Exception` block (line 2134) so it won't crash the process, but the stigmergy mark will silently fail to write.
**Severity:** LOW — caught by exception handler, but masks a logic error.
**Fix:** Addressed by the same `result = result or ""` fix in BUG-02.

---

### BUG-04: `_message_discovery` silently drops all broadcast messages
**File:** `orchestrator.py`, line 1329
**Code:**
```python
if message.from_agent not in agent_ids or message.to_agent not in agent_ids:
    return None
```
**What's wrong:** The orchestrator sends messages with `to_agent="*"` (line 1819) for dispatch notifications, and the lifecycle events use `to_agent="*"` (line 537). Since `"*"` is never in `agent_ids`, all orchestrator-originated messages are silently excluded from coordination analysis. Broadcast messages from any source are invisible to the coordination protocol.
**Severity:** MEDIUM — coordination analysis has an incomplete view of inter-agent communication. Disagreement detection misses orchestrator-mediated coordination.
**Fix:** Treat `"*"` as a universal match:
```python
if message.from_agent not in agent_ids:
    return None
if message.to_agent != "*" and message.to_agent not in agent_ids:
    return None
```

---

### BUG-05: No `SIGNAL_TASK_COMPLETED` emission on success path
**File:** `orchestrator.py`, success path of `_execute_task` (lines 1972–2029)
**What's wrong:** The `CYBERNETIC_LOOP_MAP.md` states the orchestrator "Emits SIGNAL_TASK_COMPLETED to signal_bus" on task completion. This does not happen. The only SignalBus emission is `ALGEDONIC_TASK_DEAD` at line 1665, which fires only when retries are exhausted. The evolution engine, organism heartbeat, and other downstream loops that depend on task completion signals from the signal bus receive nothing.
**Severity:** HIGH — breaks the feedback path for evolution (Loop 3), witness auditing (Loop 6), and training flywheel (Loop 7). These loops have no signal that a task completed.
**Fix:** Add after line 2013 (after the lifecycle event emission):
```python
# Emit task-completed signal to signal bus
try:
    from dharma_swarm.signal_bus import SignalBus
    SignalBus.get().emit({
        "type": "TASK_COMPLETED",
        "task_id": td.task_id,
        "agent_id": td.agent_id,
        "duration_sec": round(duration_sec, 4),
        "result_chars": len(result or ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
except Exception:
    logger.debug("Task completion signal emission failed", exc_info=True)
```

---

### BUG-06: `_emit_lifecycle_event` creates fire-and-forget tasks without exception handling
**File:** `orchestrator.py`, line 513
**Code:**
```python
asyncio.create_task(
    self._emit_lifecycle_event_impl(event, task_id=task_id, agent_id=agent_id, extra=extra),
    name=f"lifecycle-{event}-{task_id[:8]}",
)
```
**What's wrong:** `asyncio.create_task()` is called without storing the reference or adding a done callback. If the `_emit_lifecycle_event_impl` coroutine raises an exception, Python 3.12+ will log "Task exception was never retrieved" warnings. The task reference is not stored, so it could be garbage-collected before completion (though CPython's event loop holds a reference).
**Severity:** LOW — warnings in logs, no data loss. The impl method has its own try/except.
**Fix:** Add exception suppression via done callback:
```python
bg = asyncio.create_task(
    self._emit_lifecycle_event_impl(event, task_id=task_id, agent_id=agent_id, extra=extra),
    name=f"lifecycle-{event}-{task_id[:8]}",
)
bg.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
```

---

### BUG-07: `_select_idle_agent` modifies caller's list via `.remove()` and `.pop()`
**File:** `orchestrator.py`, lines 885, 891, 897, 901, 903
**Code:**
```python
idle_agents.remove(best)  # line 885
# ...
idle_agents.remove(best)  # line 891
# ...
idle_agents.remove(pick)  # line 897
# ...
idle_agents.remove(pick)  # line 901
# ...
return idle_agents.pop(0)  # line 903
```
**What's wrong:** This method is called from `route_next()` at line 294 with `available = list(idle)` (line 292). The `list(idle)` creates a copy, so this is intentional — the `available` list shrinks as agents are assigned. However, `_select_idle_agent` also receives the **same** `available` list as the `idle_agents` parameter, but `candidates` at line 880 may be a separate subset (`name_matched` or `role_matched`). When `_efe_biased_pick` or `_fitness_biased_pick` returns a candidate from a subset, `idle_agents.remove(best)` removes from the original `available` list — which is correct. But `name_matched` and `role_matched` are separate lists that still contain the removed agent. If the EFE/fitness picks fail and falls through to the FIFO section (lines 894–903), the agent could be in `name_matched` but already removed from `idle_agents`, causing `ValueError` on `idle_agents.remove(pick)`.
**Severity:** MEDIUM — `ValueError` crash when EFE or fitness routing picks an agent, but then code falls through to FIFO fallback on the same call (impossible in current flow since `return` prevents this, but the structure is fragile).
**Actual risk:** After review, `_efe_biased_pick` and `_fitness_biased_pick` return non-None or None. If non-None, the method returns immediately (lines 884–886, 890–892). If both return None, FIFO runs. So the crash scenario doesn't occur in the current logic. This is a code fragility issue, not a runtime bug.
**Severity revised:** LOW — structural fragility.

---

### BUG-08: `_apply_failure_retry_defaults` mutates `meta` dict as side effect
**File:** `orchestrator.py`, lines 685, 698–700
**Code:**
```python
meta["retry_backoff_seconds"] = updated_backoff  # line 685
meta["timeout_seconds"] = round(grown_timeout, 3)  # line 698
meta["retry_backoff_seconds"] = updated_backoff      # line 699
meta["timeout_retry_growth_applied"] = round(grown_timeout, 3)  # line 700
```
**What's wrong:** The method signature returns `tuple[int, float]` but also mutates the `meta` dict passed in. This is an implicit side effect not visible from the call site. When `swarm.py` calls this private method at line 1897, it relies on this side effect to propagate timeout growth — a fragile coupling.
**Severity:** LOW — works correctly but violates single-responsibility; the side effect is undocumented.
**Fix:** Document the side effect in the docstring, or refactor to return a richer result object.

---

### BUG-09: `_handle_task_failure` sets status to `FAILED` then immediately to `PENDING` (double update)
**File:** `orchestrator.py`, lines 1584–1596
**Code:**
```python
await self._safe_update_task(
    td.task_id,
    status=TaskStatus.FAILED,    # First update
    result=error,
    metadata=meta,
)
await self._safe_update_task(
    td.task_id,
    status=TaskStatus.PENDING,   # Second update immediately after
    result=error,
    metadata=meta,
    assigned_to=None,
)
```
**What's wrong:** Two sequential task board updates are made — first setting `FAILED`, then immediately `PENDING`. This is a race condition window: any observer reading the task board between these two calls sees a `FAILED` task that is actually being requeued. It also doubles the write load on the task board. The `FAILED` intermediate state is semantically misleading.
**Severity:** MEDIUM — observable inconsistency and wasted I/O. Could confuse monitoring dashboards or trigger false algedonic signals from other subsystems reading task state.
**Fix:** Combine into a single update:
```python
await self._safe_update_task(
    td.task_id,
    status=TaskStatus.PENDING,
    result=error,
    metadata=meta,
    assigned_to=None,
)
```
Or, if the `FAILED` state is needed for audit trail, introduce a `RETRYING` status.

---

### BUG-10: `route_next()` inline `import time` shadows module-level `time`
**File:** `orchestrator.py`, line 276
**Code:**
```python
import time as _tt; _rn0 = _tt.monotonic()
```
**What's wrong:** This line imports `time` as `_tt` inline, which is a debug instrumentation pattern that shadows the module-level `import time` (line 23). While not technically broken (the module-level `time` is still accessible), this pattern is repeated at lines 276, 341, 1434, 1696 with different aliases (`_tt`, `_t`, `_adt`). It clutters the code and creates naming inconsistency.
**Severity:** LOW — style issue, no runtime impact.
**Fix:** Use the module-level `time` import consistently. Remove inline imports.

---

### BUG-11: `_coordination_task_metadata` returns `None` for tasks not in global truths or disagreements
**File:** `orchestrator.py`, line 1237
**Code:**
```python
else:
    return None
```
**What's wrong:** Tasks that are neither in `global_truths` nor in `disagreements` get no coordination metadata update. This means a task that was previously annotated as `coordination_state: "uncertain"` will retain that annotation permanently, even after the disagreement is resolved. There is no "clear coordination state" path.
**Severity:** MEDIUM — stale coordination metadata accumulates, potentially misrouting tasks after disagreements resolve.
**Fix:** Add a "resolved" state path:
```python
else:
    # Clear stale coordination state if previously annotated
    if updated.get("coordination_state") in ("coherent", "uncertain"):
        assign("coordination_state", "untracked")
        assign("coordination_review_required", False)
        remove("coordination_preferred_roles")
        return updated if changed else None
    return None
```

---

### BUG-12: Hardcoded paths and magic strings
**File:** `orchestrator.py`, multiple locations

| Line | Hardcoded Value | Should Be |
|------|----------------|-----------|
| 1677 | `Path.home() / ".dharma" / "algedonic_signals.jsonl"` | Config constant or derived from `_runtime_root()` |
| 2077 | `f"{agent_name}_notes.md"` | Pattern from config |
| 1665 | `"ALGEDONIC_TASK_DEAD"` | Constant from `signal_bus.py` |
| 136 | `120.0` (coordination refresh interval) | Config field |
| 844 | `0.1` (exploration rate) | Config field |

**Severity:** LOW — works but hampers configurability.

---

### BUG-13: `_safe_get_task` swallows all exceptions silently
**File:** `orchestrator.py`, lines 1527–1534
**Code:**
```python
async def _safe_get_task(self, task_id: str) -> Task | None:
    board_get = getattr(self._board, "get", None)
    if not board_get:
        return None
    try:
        return await board_get(task_id)
    except Exception:
        return None
```
**What's wrong:** All exceptions are silently swallowed — including `TypeError` from wrong arguments, `ConnectionError` from database failures, and `KeyboardInterrupt` (though that inherits from `BaseException`). No logging at any level. A database outage would cause every task lookup to silently return `None`, making the orchestrator believe tasks don't exist.
**Severity:** MEDIUM — silent data loss during infrastructure failures.
**Fix:** Add at minimum debug logging:
```python
except Exception as exc:
    logger.debug("Task board get failed for %s: %s", task_id, exc)
    return None
```

---

### BUG-14: `_init_telic_seam` catches all exceptions including import errors
**File:** `orchestrator.py`, lines 144–155
**Code:**
```python
def _init_telic_seam(self) -> Any | None:
    try:
        from dharma_swarm.ontology_runtime import get_shared_registry
        from dharma_swarm.telic_seam import TelicSeam
        # ...
    except Exception:
        logger.debug("Failed to initialize local telic seam", exc_info=True)
        return None
```
**What's wrong:** The `debug` log level means this failure is invisible unless debug logging is enabled. If the telic seam fails to initialize, fitness-biased routing silently degrades to FIFO with no indication. A `SyntaxError` in `telic_seam.py` would be swallowed at debug level.
**Severity:** LOW — acceptable for optional subsystems, but should at least log at `info` level.

---

### BUG-15: `_collect_completed` iterates `_running_tasks` dict while building removal list — safe but fragile
**File:** `orchestrator.py`, lines 2158–2175
**What's wrong:** The pattern is correct (iterating to collect, then removing in a second pass). However, `_active_dispatches` iteration at line 2180 has the same task_ids as keys, and `_handle_task_failure` (called at line 2201) calls `self._active_dispatches.pop(task_id, None)` at line 2200 which mutates the dict during what could be concurrent iteration if multiple stale items exist. Actually, the stale list is fully built before the mutation loop, so this is safe. No bug here upon closer inspection.

---

## 4. Style and Quality Assessment

### Naming Consistency
- **Generally consistent snake_case** throughout. Method names use clear verb prefixes: `_collect_completed`, `_assign_dispatch`, `_handle_task_failure`, `_persist_result`.
- **Inconsistency:** `_select_idle_agent` vs `_efe_biased_pick` vs `_fitness_biased_pick` — the selection methods use different naming patterns (verb_noun vs adjective_noun).
- **Inconsistency:** `_safe_get_task` / `_safe_update_task` use a `_safe_` prefix to indicate exception swallowing, but `_emit_lifecycle_event` also swallows exceptions without the prefix.
- **Internal timing variables** are chaotic: `_rn0`, `_tt`, `_t0`, `_ad0`, `_adt`, `_gate_t0`, `_pe_t0`, `_cs_t0`. These are debug instrumentation that should be removed or standardized.

### Docstrings
- **Present on public methods:** `dispatch()`, `fan_out()`, `fan_in()`, `route_next()`, `tick()`, `tick_settle_only()`, `run()`, `stop()`, `graceful_stop()` all have docstrings.
- **Missing on most private methods:** `_handle_task_failure`, `_assign_dispatch`, `_collect_completed`, `_refresh_coordination_state`, `_select_idle_agent` lack docstrings.
- **`_persist_result` has a good docstring** (lines 2066–2070).
- **`_execute_task` has a one-line docstring** that's accurate (line 1922).

### Module Size and Decomposition
At 2208 lines, this module is **significantly too large**. It conflates at least five distinct responsibilities:

1. **Dispatch logic** (route_next, dispatch, fan_out, fan_in, _assign_dispatch): ~400 lines
2. **Task execution and lifecycle** (_execute_task, _handle_task_failure, _collect_completed): ~350 lines
3. **Agent selection** (_select_idle_agent, _efe_biased_pick, _fitness_biased_pick): ~100 lines
4. **Coordination/sheaf analysis** (_refresh_coordination_state and 15+ helper methods): ~600 lines
5. **Result persistence** (_persist_result): ~100 lines
6. **Retry/failure classification** (_classify_failure, _resolve_retry_policy, etc.): ~150 lines
7. **Claim management** (_prepare_claim, _resolve_timeout_seconds, etc.): ~100 lines
8. **Coordination task metadata** (_coordination_task_metadata and helpers): ~300 lines

**Recommended decomposition:**
- `orchestrator_core.py` — tick, route_next, dispatch, fan_out, fan_in (~300 lines)
- `orchestrator_execution.py` — _execute_task, _handle_task_failure, _collect_completed (~350 lines)
- `orchestrator_coordination.py` — all sheaf/coordination methods (~600 lines)
- `orchestrator_selection.py` — agent selection strategies (~150 lines)
- `orchestrator_persistence.py` — _persist_result, shared notes, stigmergy (~150 lines)
- `orchestrator_retry.py` — failure classification, retry policy, backoff (~200 lines)

### Copy-Paste Patterns
- **Timing instrumentation**: Lines 276, 341, 1434, 1696 all have inline `import time as _xx; _t0 = _xx.monotonic()` + scattered `logger.info("...: %.1fs", ...)`. This should be extracted into a context manager or decorator.
- **Lifecycle event emission**: The pattern `self._record_task_event(...)` + `self._record_progress_event(...)` + `await self._emit_lifecycle_event(...)` is repeated at lines 1597–1627, 1637–1659, 1824–1865, 2000–2013. Should be a single method.
- **`_safe_update_task` + `_safe_get_task`**: Same exception-swallowing pattern duplicated.
- **Telic seam record attempts**: Lines 1704–1713, 1741–1749, 1792–1800 all follow the same `if self._telic_seam is not None: try: ... except: logger.debug(...)` pattern.

### Type Hints
- **Public methods are well-typed**: `tick() -> dict[str, int]`, `route_next() -> list[TaskDispatch]`, `dispatch() -> list[TaskDispatch]`.
- **Private methods are mostly typed** but several use `Any` excessively: `runner: Any` (line 1921), `task_board: Any` (line 76), `agent_pool: Any` (line 77).
- **Missing type hints** on: `_record_task_event`, `_record_progress_event` (return types).

### Overall Quality Rating: **5/10**

**Strengths:**
- Solid defensive programming in many paths (None guards on `_board`, `_pool`, `_bus`)
- Good use of asyncio patterns (background tasks, timeouts, cancellation)
- Comprehensive claim management and retry logic
- The coordination/sheaf analysis is sophisticated and well-structured

**Weaknesses:**
- Module is 3-4x too large for a single file
- Debug timing instrumentation pollutes the code
- Critical feedback loops claimed in architecture docs are not implemented (signal bus, stigmergy read-back)
- Multiple StigmergyStore instances with unsynchronized locks
- Silent exception swallowing in critical paths
- No unit tests visible (not in scope, but concerning for a 2208-line module)

---

## 5. Recommended Fixes (Priority Order)

### 1. Emit `SIGNAL_TASK_COMPLETED` on success path
**File:** `orchestrator.py`, after line 2013
**Impact:** Closes Loop 1's signal feedback path. Evolution, witness, and training flywheel all need this signal.
```python
try:
    from dharma_swarm.signal_bus import SignalBus
    SignalBus.get().emit({
        "type": "TASK_COMPLETED",
        "task_id": td.task_id,
        "agent_id": td.agent_id,
        "duration_sec": round(duration_sec, 4),
        "result_chars": len(result or ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
except Exception:
    logger.debug("Task completion signal emission failed", exc_info=True)
```

### 2. Use a single shared `StigmergyStore` instance
**File:** `orchestrator.py`, `__init__` + `_persist_result`
**Impact:** Prevents JSONL corruption from concurrent writes with isolated locks.
```python
# __init__:
self._stigmergy_store: Any = None

# _persist_result, replace line 2137:
if self._stigmergy_store is None:
    from dharma_swarm.stigmergy import StigmergyStore as _SS
    self._stigmergy_store = _SS(self._stigmergy_dir)
store = self._stigmergy_store
```

### 3. Guard against `None` result in `_persist_result`
**File:** `orchestrator.py`, before line 2086
**Impact:** Prevents TypeError crash on the success path when runner returns None.
```python
# Add before line 2086:
result = result or ""
```

### 4. Fix broadcast message filtering in `_message_discovery`
**File:** `orchestrator.py`, line 1329
**Impact:** Coordination analysis includes orchestrator-originated messages.
```python
if message.from_agent not in agent_ids:
    return None
if message.to_agent != "*" and message.to_agent not in agent_ids:
    return None
```

### 5. Eliminate double task-board update on retry
**File:** `orchestrator.py`, lines 1584–1596
**Impact:** Removes race window and halves write load.
```python
# Replace the two _safe_update_task calls with one:
await self._safe_update_task(
    td.task_id,
    status=TaskStatus.PENDING,
    result=error,
    metadata=meta,
    assigned_to=None,
)
```

### 6. Add logging to `_safe_get_task` exception handler
**File:** `orchestrator.py`, line 1533
**Impact:** Makes database failures visible.
```python
except Exception as exc:
    logger.debug("Task board get failed for %s: %s", task_id, exc)
    return None
```

### 7. Add done callback to fire-and-forget lifecycle tasks
**File:** `orchestrator.py`, line 513
**Impact:** Suppresses "Task exception was never retrieved" warnings.
```python
_bg = asyncio.create_task(
    self._emit_lifecycle_event_impl(event, task_id=task_id, agent_id=agent_id, extra=extra),
    name=f"lifecycle-{event}-{task_id[:8]}",
)
_bg.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
```

### 8. Remove inline timing imports
**File:** `orchestrator.py`, lines 276, 341, 1434, 1696
**Impact:** Code clarity. Use module-level `time` consistently.
```python
# Remove: import time as _tt; _rn0 = _tt.monotonic()
# Replace with: _rn0 = time.monotonic()
```

### 9. Extract coordination subsystem to separate module
**File:** `orchestrator.py` → new `orchestrator_coordination.py`
**Impact:** Reduces module from 2208 to ~1500 lines. Improves testability.
Move: `_refresh_coordination_state`, `_list_coordination_agents`, `_list_coordination_tasks`, `_list_coordination_messages`, `_message_discovery`, `_task_discovery`, `_task_overlap_channels`, `_merge_coordination_channels`, `_coordination_claim_key_from_message`, `_coordination_claim_key_from_task`, `_coordination_task_agent_id`, `_coordination_task_metadata`, `_apply_coordination_task_policy`, `_merge_coordination_context`, `_coordination_signature_payload`, `_coordination_confidence`, `_empty_coordination_summary`, `get_coordination_summary`.

### 10. Add stigmergy read-back for routing feedback
**File:** `orchestrator.py`, in `route_next()` or `_select_idle_agent()`
**Impact:** Closes the stigmergy feedback path claimed in the architecture docs.
```python
# In route_next(), after getting ready tasks:
try:
    if self._stigmergy_store is None:
        from dharma_swarm.stigmergy import StigmergyStore as _SS
        self._stigmergy_store = _SS(self._stigmergy_dir)
    hot = await self._stigmergy_store.hot_paths(window_hours=1, min_marks=2)
    # Use hot paths to influence task prioritization
    # ... (implementation depends on hot_paths return format)
except Exception:
    pass
```

---

*End of Audit Report*
