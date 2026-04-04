# Interface Mismatch Map — dharma_swarm

**Generated:** 2026-04-04 | **Scope:** Core runtime path + feedback loops  
**Purpose:** Every place where one module calls another module with the wrong API.  
This document exists because the codebase grew across many sprints without a unified
integration-test harness. Mismatches are silent until the specific call path is exercised
at runtime — usually in production under the live orchestrator.

---

## Summary Table

| # | Severity | Caller | Callee | What's Wrong |
|---|----------|--------|--------|--------------|
| 1 | **BLOCKER** | `tiny_router_shadow.py:542` | `huggingface_hub` | `ImportError` propagates uncaught — crashes every call to `infer_tiny_router_shadow()` in default `auto` backend mode |
| 2 | **BLOCKER** | `orchestrate_live.py:1247` | `persistent_agent.py:51-52` | `role` and `provider_type` passed as raw strings; `PersistentAgent.__init__` requires `AgentRole` enum and `ProviderType` enum |
| 3 | **BLOCKER** | `orchestrate_live.py:1248` | `persistent_agent.py:52` | `provider_type=outcome.child_spec.get("default_provider", "openrouter_free")` is a bare string — Pydantic rejects it at `PersistentAgent.__init__` because `ProviderType` is a `str`-enum and Pydantic v2 validates mode `strict` on model fields |
| 4 | **DEGRADED** | `tiny_router_shadow.py:494` | `huggingface_hub.snapshot_download` | `from huggingface_hub import snapshot_download` raises `ImportError` — caught by `_load_tiny_router_artifacts` caller only if exception propagation chain adds a `try/except`; it does NOT — falls through to crash |
| 5 | **DEGRADED** | `orchestrate_live.py:359` | `message_bus.py:193` | `receive("evolution_loop", limit=20)` — the `status=` kwarg is positional-second; `limit=` is the third positional arg. Call passes `limit=20` as kwarg — this is correct, but the `status` parameter defaults to `"unread"`, so the evolution loop only gets unread messages. After the first `mark_read` call they're marked `"read"` and invisible to `receive()` next cycle — silent data loss |
| 6 | **DEGRADED** | `swarm.py:2087` | `organism.py:1240` | `self._organism.samvara.current_power.value` — assumes `samvara.active` is `True` before accessing `.current_power`; the guard is `if self._organism.samvara.active` at line 2088 but the attribute chain `.current_power.value` is called on the next line without a secondary null-guard if `current_power` itself is `None` |
| 7 | **DEGRADED** | `swarm.py:363-370` | `auto_proposer.py:157` | `AutoProposer(darwin_engine=..., system_monitor=..., fitness_predictor=self._engine.predictor, stigmergy=self._stigmergy, ...)` — `self._stigmergy` can be `None` (set to `None` if StigmergyStore init fails at line 355); `AutoProposer.__init__` accepts `stigmergy: StigmergyStore | None = None` so the type is valid but several internal methods assume non-None and call `await self._stigmergy.read_marks(...)` without guarding |
| 8 | **DEGRADED** | `orchestrate_live.py:314-319` | `meta_evolution.py:68` | `MetaEvolutionEngine(engine, meta_archive_path=..., n_object_cycles_per_meta=2, auto_apply=True)` — constructor signature has `poor_meta_fitness_threshold` (default 0.7) but the call in the second copy at line 1049 uses the same pattern. No mismatch in param names, but `n_object_cycles_per_meta=2` means meta-evolution triggers every 2 object cycles — the engine only adapts after 2 consecutive calls to `observe_cycle_result`. With `cycle_count % 3 == 0` for auto-evolve, the cadence is mismatched: meta runs every 2 cycles, auto-evolve every 3rd cycle — meta never accumulates the 2 required results in the right window |
| 9 | **DEGRADED** | `swarm.py:1883` | `orchestrator.py:599` | `self._orchestrator._classify_failure(error=..., source=..., task=...)` — all three are keyword-only (`*` separator present); call uses correct kwargs — no crash, but `_classify_failure` is a private method being called from outside its class. This is a contract violation: any internal refactor breaks `swarm.py` silently |
| 10 | **DEGRADED** | `swarm.py:1891` | `orchestrator.py:655` | `retry_count, max_retries, backoff = self._orchestrator._resolve_retry_policy(task)` — returns `tuple[int, int, float]` (3 values: retry_count, max_retries, backoff). Unpacking is correct. But at line 1892, `max_retries, backoff = self._orchestrator._apply_failure_retry_defaults(...)` — `_apply_failure_retry_defaults` returns `tuple[int, float]` (2 values). Unpacking is correct. **No crash** but calling private methods across class boundary is a structural mismatch |
| 11 | **DEGRADED** | `orchestrate_live.py:694-696` | `subconscious.py:56` | `SubconsciousStream(stigmergy=store)` where `store = StigmergyStore()` using default path. The `StigmergyStore()` is created fresh here, separate from the one in `swarm.py`. Two `StigmergyStore` instances read from the same JSONL file with separate `asyncio.Lock` instances — not process-safe for concurrent writes from two event-loop tasks |
| 12 | **DEGRADED** | `orchestrate_live.py:694-697` | `shakti.py:119` | Same dual-instantiation as above: `ShaktiLoop(stigmergy=store)` uses a fresh `StigmergyStore`, separate from SwarmManager's `self._stigmergy`. Three separate readers/writers of the same JSONL file across different asyncio tasks |
| 13 | **DEGRADED** | `swarm.py:442` | `witness.py:123` | `WitnessAuditor(cycle_seconds=3600.0, provider=self._router)` — `provider` parameter in `WitnessAuditor.__init__` is typed `Any | None`. The `self._router` is a `ModelRouter` (from `create_default_router()`). Inside `WitnessAuditor._llm_evaluate()`, `provider.complete(request)` is called, but `ModelRouter` is not a bare `LLMProvider` — it has routing logic and a different internal dispatch path. Works if `ModelRouter` has a `complete()` method, which it does (as it wraps providers), but the LLMRequest sent may not match what the router expects for routing metadata |
| 14 | **DEGRADED** | `orchestrate_live.py:875` | `neural_consolidator.py:180` | `NeuralConsolidator(provider=None, base_path=STATE_DIR)` — constructor takes `provider: Optional[CompletionProvider]`. Passing `None` is valid and documented as "algorithmic mode". No crash. But `CompletionProvider` protocol is defined inside `neural_consolidator.py` (line 161) and requires only `async def complete(self, request: Any) -> Any`. **Correct, no mismatch.** |
| 15 | **DEGRADED** | `swarm.py:303-308` | `evolution.py:206` | `DarwinEngine(archive_path=..., traces_path=..., predictor_path=...)` — only 3 of 28 constructor params passed. All others default correctly. `quality_gate_enabled=False` by default so no LLM calls. No crash, but `landscape_probe_workspace` defaults to `None` which disables probing — intentional omission that silently limits functionality |
| 16 | **DEGRADED** | `orchestrate_live.py:1247` | `replication_protocol.py:316-318` | `child_spec["role"]` is already serialized to `.value` (a bare string like `"conductor"`) by `ReplicationOutcome` builder. `child_spec["default_provider"]` is also a bare string (`.value`). The caller at line 1243 imports `AgentRole` and `ProviderType as PT` but **never uses them** to coerce the strings back to enums. `PersistentAgent.__init__` at line 51-52 declares `role: AgentRole` and `provider_type: ProviderType`. Pydantic v2 with `str`-enum coerces valid strings to enums in lax mode — so this **may not crash** at construction time if Pydantic's lax mode handles it, but is semantically wrong and fragile |
| 17 | **DEGRADED** | `orchestrate_live.py:1354-1364` | `conductors.py:63-65` | `CONDUCTOR_CONFIGS` entries carry `role: AgentRole.CONDUCTOR` and `provider_type: ProviderType.ANTHROPIC` (proper enum values). `PersistentAgent` is called with `role=cfg["role"]` and `provider_type=cfg["provider_type"]`. Since these are already enum instances, **no mismatch** — this path is correct |
| 18 | **DEGRADED** | `swarm.py:415-420` | `thinkodynamic_director.py:1877` | `ThinkodynamicDirector(state_dir=self.state_dir, swarm=self)` — constructor accepts `swarm: Any | None = None`. The `init()` method is then called. But `ThinkodynamicDirector.init()` at the call site: `await self._director.init()` — need to verify `init()` exists |
| 19 | **DEGRADED** | `swarm.py:2316` | `auto_proposer.py:737` | `await asyncio.wait_for(self._auto_proposer.cycle(), timeout=30.0)` — `AutoProposer.cycle()` is `async def` returning `CycleLog`. Swarm then reads `ap_result.observations_collected`, `ap_result.proposals_generated`, `ap_result.proposals_submitted`. All three fields exist on `CycleLog` (lines 108-110). **No mismatch.** |
| 20 | **DEGRADED** | `orchestrate_live.py:192` | `message_bus.py:612` | `consume_events("ECC_INSTINCT_SIGNAL", limit=10)` — the event_type string `"ECC_INSTINCT_SIGNAL"` must match what producers emit. No canonical constant is defined for this event type; if any producer uses a different casing or spelling, events are silently dropped |
| 21 | **BLOCKER** | `tiny_router_shadow.py` (called from `router_v1.py:23` and `engine/conversation_memory.py:19`) | `huggingface_hub` module | Any module that imports `router_v1` or `conversation_memory` will trigger the import chain. When `infer_tiny_router_shadow()` is called with default backend `auto`, it calls `_load_tiny_router_artifacts()` which does `from huggingface_hub import snapshot_download` — unguarded `ImportError` |
| 22 | **DEGRADED** | `orchestrate_live.py:375` | `evolution.py:2433` | `await engine.get_fitness_trend(limit=5)` — `get_fitness_trend` signature is `(self, component: str | None = None, limit: int = 20)`. Call is correct. **No mismatch.** |
| 23 | **DEGRADED** | `swarm.py:566` | `agent_runner.py:2869` | `self._agent_pool = AgentPool()` — `AgentPool.__init__(self) -> None` takes no arguments. Correct. But `AgentPool` is only available after `from dharma_swarm.agent_runner import AgentPool` (line 538 in the `try` block). If this import fails (e.g., `agent_memory_manager` dependency missing), `self._agent_pool` stays `None` and downstream calls like `self._agent_pool.spawn(...)` at line 791 crash with `AttributeError: 'NoneType' object has no attribute 'spawn'` — not caught by any guard |
| 24 | **DEGRADED** | `swarm.py:800` | `memory.py:122` | `await self._memory.remember(content, layer=MemoryLayer.SESSION, source="swarm")` — `remember()` signature requires `layer` as second positional param (non-default). All calls in `swarm.py` pass `layer=` as kwarg — correct. **No mismatch.** |
| 25 | **DEGRADED** | `orchestrate_live.py:840-848` | `witness.py:189,383` | `auditor.stop()` and `auditor.get_stats()` — both methods exist. `stop()` sets `self._running = False`. `get_stats()` returns dict with `cycles_completed` key. Accessed at line 834 as `stats['cycles_completed']`. **No mismatch.** |

---

## Detailed Sections by Architectural Layer

---

### Layer 0 → Layer 2: Missing Runtime Dependencies

#### MISMATCH-01 — `huggingface_hub` not installed; `tiny_router_shadow.py` crashes
**Severity:** BLOCKER  
**Caller:** `tiny_router_shadow._load_tiny_router_artifacts()` (line 495)  
**Callee:** `huggingface_hub.snapshot_download`

```
# tiny_router_shadow.py:494–495
def _load_tiny_router_artifacts(*, allow_download: bool) -> _TinyRouterCheckpointArtifacts | None:
    from huggingface_hub import snapshot_download   # ← ImportError here
```

**Call chain that hits this:**
```
infer_tiny_router_shadow()                    # tiny_router_shadow.py:649
  → _infer_tiny_router_checkpoint()           # line 557
    → _load_tiny_router_checkpoint_runtime()  # line 542
      → _load_tiny_router_artifacts()         # line 542  ← CRASHES
```

**The `_load_tiny_router_checkpoint_runtime` function does NOT catch the ImportError:**
```python
# line 542
artifacts = _load_tiny_router_artifacts(allow_download=backend == "checkpoint")
# No try/except here — ImportError propagates to _infer_tiny_router_checkpoint
```

**Who calls this:**
- `router_v1.py:285`: `infer_tiny_router_shadow_from_messages(...)` — called for every route decision
- `engine/conversation_memory.py:262`: `infer_tiny_router_shadow(...)` — called on every conversation turn

**Fix (callee side):** Wrap the `from huggingface_hub import snapshot_download` in a try/except and return `None` on `ImportError`:
```python
def _load_tiny_router_artifacts(*, allow_download: bool) -> _TinyRouterCheckpointArtifacts | None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return None
    ...
```

Alternatively, install `huggingface_hub` in the environment: `pip install huggingface-hub`.

---

### Layer 1 → Layer 7: Replication Protocol → PersistentAgent Type Mismatch

#### MISMATCH-02 — `orchestrate_live` passes strings where `PersistentAgent` expects enums
**Severity:** BLOCKER (runtime `TypeError` or silent wrong enum coercion)  
**Caller:** `orchestrate_live.py:1245–1257` (`_run_replication_monitor_loop`)  
**Callee:** `persistent_agent.PersistentAgent.__init__()` lines 51–52

**What the caller does:**
```python
# orchestrate_live.py:1243-1257
from dharma_swarm.models import AgentRole, ProviderType as PT  # imported but never used!

child = PersistentAgent(
    name=outcome.child_agent_name,
    role=outcome.child_spec.get("role", "worker"),                # "conductor" (string)
    provider_type=outcome.child_spec.get("default_provider", "openrouter_free"),  # "anthropic" (string)
    model=outcome.child_spec.get("default_model", ""),
    ...
)
```

**What `ReplicationOutcome.child_spec` contains:**
```python
# replication_protocol.py:315-318 — enum values serialized to strings
child_spec_dict["role"] = child_spec.role.value                  # e.g. "conductor"
child_spec_dict["default_provider"] = child_spec.default_provider.value  # e.g. "anthropic"
```

**What `PersistentAgent.__init__` expects:**
```python
# persistent_agent.py:51-52
def __init__(
    self,
    name: str,
    role: AgentRole,         # ← expects AgentRole enum
    provider_type: ProviderType,  # ← expects ProviderType enum
    ...
```

**Fix (caller side):** Use the already-imported enums to coerce:
```python
role=AgentRole(outcome.child_spec.get("role", "worker")),
provider_type=PT(outcome.child_spec.get("default_provider", "openrouter_free")),
```

---

### Layer 2: Swarm → Memory Bus — Silent Data Loss on `receive()`

#### MISMATCH-03 — Evolution loop uses `receive()` with wrong semantics for durable consumption
**Severity:** DEGRADED  
**Caller:** `orchestrate_live.py:359` (`run_evolution_loop`)  
**Callee:** `message_bus.MessageBus.receive()` (line 193)

**What the caller does:**
```python
lifecycle_msgs = await _bus.receive("evolution_loop", limit=20)
# ...
for m in lifecycle_msgs:
    await _bus.mark_read(m.id)
```

**What `receive()` actually does:**
```python
async def receive(
    self, agent_id: str, status: str = "unread", limit: int = 50,
) -> list[Message]:
    """Fetch messages for an agent, ordered by priority then time."""
    ...WHERE status = ?  # default "unread"
```

**The mismatch:** After `mark_read()` sets `status="read"`, the next call to `receive("evolution_loop")` with the default `status="unread"` will **never return previously read messages**. This is correct if the intent is idempotent one-time consumption, but the evolution loop subscribes to `orchestrator.lifecycle` and expects to drain all lifecycle events each cycle. Once read, old events are permanently invisible. If the evolution loop crashes mid-cycle before `mark_read`, it re-reads the same events next cycle and double-counts completions.

**Fix (caller side):** Use `consume_events("AGENT_LIFECYCLE_COMPLETED", limit=20)` instead, which uses the `consumed_at` timestamp column (not the `status` column) and is idempotent. Or use `receive(..., status="")` to get all messages regardless of status and manage deduplication manually.

---

### Layer 2: Swarm → Agent Pool — Unguarded `None` Pool

#### MISMATCH-04 — `AgentPool` import failure leaves `_agent_pool=None`; downstream crashes on `spawn()`
**Severity:** DEGRADED  
**Caller:** `swarm.py:566` (init) and `swarm.py:791` (spawn_agent)  
**Callee:** `agent_runner.AgentPool`

```python
# swarm.py:538-566
try:
    from dharma_swarm.agent_runner import AgentPool
    ...
    self._agent_pool = AgentPool()
except Exception as e:
    logger.error("Core subsystem init failed: %s", e)
    raise  # ← re-raises, so this is caught by outer try/except which swallows it

# swarm.py:791 — no None guard
runner = await self._agent_pool.spawn(...)  # AttributeError if pool is None
```

The outer `try/except` in `init()` catches and logs but **does not raise**, allowing swarm to continue in a broken state where `_agent_pool` is `None`. Any task dispatch call hits `AttributeError: 'NoneType' has no attribute 'spawn'`.

**Fix:** Add explicit guard before `spawn()`:
```python
if self._agent_pool is None:
    raise SubsystemNotReady("AgentPool not initialized")
```

---

### Layer 2: Swarm → Orchestrator — Private Method Coupling

#### MISMATCH-05 — `swarm.py` directly calls private Orchestrator methods
**Severity:** DEGRADED (structural contract violation)  
**Caller:** `swarm.py:1883–1897`  
**Callee:** `orchestrator.py` private methods `_classify_failure`, `_resolve_retry_policy`, `_apply_failure_retry_defaults`

```python
# swarm.py:1883-1895
failure_class = self._orchestrator._classify_failure(
    error=str(task.result or ""),
    source=source,
    task=task,
)
retry_count, max_retries, backoff = self._orchestrator._resolve_retry_policy(task)
max_retries, backoff = self._orchestrator._apply_failure_retry_defaults(
    task=task, meta=meta, failure_class=failure_class,
    max_retries=max_retries, backoff=backoff,
)
```

These are all single-underscore "private" methods. They work today but any refactor of `orchestrator.py` internals silently breaks `swarm.py`'s retry logic.

**Fix:** Add a public `Orchestrator.retry_policy_for_failure(task, error, source, meta)` method that encapsulates this logic and is part of the stable API.

---

### Layer 3: Living Layers — Dual StigmergyStore Instances

#### MISMATCH-06 — `orchestrate_live` creates separate `StigmergyStore` from `SwarmManager`'s
**Severity:** DEGRADED (coordination failure, not crash)  
**Caller:** `orchestrate_live.py:693–697` (`run_living_layers_loop`)  
**Callee:** `stigmergy.StigmergyStore`

```python
# orchestrate_live.py:693
store = StigmergyStore()                    # default path: ~/.dharma/stigmergy/
stream = SubconsciousStream(stigmergy=store)
loop = ShaktiLoop(stigmergy=store)
```

Meanwhile `swarm.py:352–353` creates:
```python
stigmergy_path = self.state_dir / "stigmergy"
self._stigmergy = StigmergyStore(base_path=stigmergy_path)
```

Both instances hold separate `asyncio.Lock()` objects and write to the same JSONL file (`~/.dharma/stigmergy/marks.jsonl`). The locks are not shared. Concurrent writes from the living-layer loop and the swarm loop can interleave, causing mark corruption or missed writes.

**Fix (caller side):** Pass the existing stigmergy store from swarm into the living layers loop:
```python
async def run_living_layers_loop(shutdown_event, stigmergy_store: StigmergyStore | None = None):
    store = stigmergy_store or StigmergyStore()
```
And in `orchestrate()`, pass `swarm._stigmergy` after init.

---

### Layer 4: Evolution → Signal Bus — Cadence Mismatch for Meta-Evolution

#### MISMATCH-07 — `MetaEvolutionEngine` never accumulates enough results to adapt
**Severity:** DEGRADED (silent no-op)  
**Caller:** `orchestrate_live.py:314–320` and `run_evolution_loop`  
**Callee:** `meta_evolution.MetaEvolutionEngine.observe_cycle_result()`

```python
# orchestrate_live.py:314
meta_engine = MetaEvolutionEngine(
    engine,
    n_object_cycles_per_meta=2,   # adapts after every 2 observed cycles
    auto_apply=True,
)
```

```python
# orchestrate_live.py:399 — only called when cycle_count % 3 == 0 AND auto-evolve runs
meta_engine.observe_cycle_result(synthetic_result)
```

**The `observe_cycle_result` method:**
```python
# meta_evolution.py:121
def observe_cycle_result(self, cycle_result: CycleResult) -> MetaEvolutionResult | None:
    self._observed_cycles += 1
    ...
    if self._observed_cycles % self.n_object_cycles != 0:
        return None   # no adaptation yet
```

`observe_cycle_result` is also called unconditionally at lines 407–425 when `avg_fitness > 0 or fitness_events`. This means the meta-engine gets called with a `synthetic_result` and then again with `result` from `auto_evolve()` on cycles 3, 6, 9... The two distinct `observe_cycle_result` calls on the same cycle count together toward the `n_object_cycles=2` threshold — so meta-adaptation fires more often than intended (after 2 total calls, which can happen in a single cycle number).

**Fix:** Separate the synthetic-fitness-reporting path from the auto-evolve result path. Only call `observe_cycle_result` once per evolution cycle (with the actual `CycleResult` from `auto_evolve`).

---

### Layer 5: Memory Bus — Untyped Event Strings

#### MISMATCH-08 — `ECC_INSTINCT_SIGNAL` event type has no canonical constant
**Severity:** DEGRADED (silent drop if misspelled)  
**Caller:** `orchestrate_live.py:192`  
**Callee:** `message_bus.MessageBus.consume_events()`

```python
instinct_events = await _instinct_bus.consume_events(
    "ECC_INSTINCT_SIGNAL", limit=10,
)
```

`signal_bus.py` defines canonical signal type constants (`SIGNAL_AGENT_FITNESS`, `SIGNAL_ANOMALY_DETECTED`, etc.) but `"ECC_INSTINCT_SIGNAL"` has no corresponding constant. If any producer emits `"ecc_instinct_signal"` or `"ECC_INSTINCT"`, the swarm loop silently receives zero events — the negative feedback loop is silently broken.

**Fix (structural):** Define `SIGNAL_ECC_INSTINCT = "ECC_INSTINCT_SIGNAL"` in `signal_bus.py` (or a `message_bus_constants.py`) and use it in all producers and consumers.

---

### Layer 6: Organism → Samvara — Potential None Chain

#### MISMATCH-09 — `samvara.current_power.value` accessed without None guard on `current_power`
**Severity:** DEGRADED  
**Caller:** `swarm.py:2086–2088`  
**Callee:** `organism.OrganismRuntime.samvara`

```python
# swarm.py:2086-2088
result["organism_power"] = (
    self._organism.samvara.current_power.value
    if self._organism.samvara.active else None
)
```

`self._organism.samvara.active` is checked, but `current_power` itself is not checked for `None`. If `SamvaraEngine.current_power` is `None` when `active=True` (possible during initialization or after a reset), `.value` raises `AttributeError`.

**Fix:** Add a nested guard:
```python
result["organism_power"] = (
    self._organism.samvara.current_power.value
    if self._organism.samvara.active and self._organism.samvara.current_power is not None
    else None
)
```

---

### Layer 6: AutoProposer → Stigmergy — Unguarded None Dereference

#### MISMATCH-10 — `AutoProposer._stigmergy` can be None; internal methods don't guard
**Severity:** DEGRADED  
**Caller:** `swarm.py:363–370`  
**Callee:** `auto_proposer.AutoProposer.__init__()` + internal methods

```python
# swarm.py:364-370
self._auto_proposer = AutoProposer(
    darwin_engine=self._engine,
    system_monitor=self._monitor,
    fitness_predictor=self._engine.predictor,
    stigmergy=self._stigmergy,   # ← can be None if StigmergyStore init failed
    ...
)
```

Inside `AutoProposer`, methods that scan stigmergy for hotspots do:
```python
marks = await self._stigmergy.read_marks(...)  # AttributeError if None
```

The `__init__` stores `self._stigmergy = stigmergy` without raising on None. Internal methods call `self._stigmergy.read_marks()` without a guard.

**Fix (callee side):** Wrap stigmergy calls in a guard:
```python
if self._stigmergy is None:
    return []  # no stigmergy marks available
marks = await self._stigmergy.read_marks(...)
```

---

### Layer 7 → Layer 2: WitnessAuditor — ModelRouter Passed as LLM Provider

#### MISMATCH-11 — `WitnessAuditor` receives `ModelRouter` as its `provider`; internal dispatch may fail for complex requests
**Severity:** DEGRADED  
**Caller:** `swarm.py:442–445`  
**Callee:** `witness.WitnessAuditor.__init__()` + `_llm_evaluate()`

```python
# swarm.py:442-445
self._witness = WitnessAuditor(
    cycle_seconds=3600.0,
    provider=self._router,  # ModelRouter, not a bare LLMProvider
)
```

`WitnessAuditor._llm_evaluate()` calls `await self._provider.complete(request)` where `request` is a plain `LLMRequest`. `ModelRouter.complete()` expects routing metadata in `request.metadata` to select the right provider lane. Without routing metadata, `ModelRouter` falls back to its default strategy — this may work but is unintentional. The Witness auditor should use a specific, cost-controlled provider (e.g., the free OpenRouter tier) rather than the full router.

**Fix (caller side):** Pass a specific provider:
```python
from dharma_swarm.providers import OpenRouterFreeProvider
self._witness = WitnessAuditor(
    cycle_seconds=3600.0,
    provider=OpenRouterFreeProvider(),
)
```

---

### Layer 8 → Layer 2: Replication Monitor — Enum Deserialization Gap

#### MISMATCH-12 (companion to MISMATCH-02) — `child_spec["role"]` is string `.value` but never coerced back
**Severity:** BLOCKER  
**Caller:** `orchestrate_live.py:1243-1257`  
**Callee:** `replication_protocol.py:315-318` → `persistent_agent.py:51`

Full data flow:
1. `AgentSpec.role` = `AgentRole.CONDUCTOR` (enum)
2. `replication_protocol.py:316`: `child_spec_dict["role"] = child_spec.role.value` → `"conductor"` (string)
3. `ReplicationOutcome.child_spec` = `{"role": "conductor", "default_provider": "anthropic", ...}`
4. `orchestrate_live.py:1247`: `role=outcome.child_spec.get("role", "worker")` → `"conductor"` (string)
5. `PersistentAgent.__init__(role: AgentRole)` receives `"conductor"` (string)

Pydantic v2 with `str`-enum coerces valid string values to enum members in lax validation mode, so this **may succeed** at construction time — but if `AgentRole` ever enforces strict mode (or if an invalid value like `"worker"` is passed and `AgentRole.WORKER` doesn't exist), it raises `ValueError`.

**Root cause:** `AgentRole` does have `WORKER = "worker"` (line 44 of models.py) but `default_provider` defaults to `"openrouter_free"` which maps to `ProviderType.OPENROUTER_FREE`. The deserialization depends on Pydantic's lax string coercion and is brittle.

**Fix (caller side):** Explicitly coerce:
```python
from dharma_swarm.models import AgentRole, ProviderType as PT
child = PersistentAgent(
    name=outcome.child_agent_name,
    role=AgentRole(outcome.child_spec.get("role", "general")),
    provider_type=PT(outcome.child_spec.get("default_provider", "openrouter_free")),
    ...
)
```

---

## Module Pair Verification Summary

| # | Module Pair | Status |
|---|-------------|--------|
| 1 | `orchestrate_live` → `swarm.SwarmManager.__init__` | ✅ Correct (`state_dir`, `daemon_config`) |
| 2 | `orchestrate_live` → `swarm.SwarmManager.init()` | ✅ Correct (no args) |
| 3 | `orchestrate_live` → `swarm.SwarmManager.tick()` | ✅ Correct (no args) |
| 4 | `orchestrate_live` → `swarm.SwarmManager.status()` | ✅ Correct; returns `SwarmState` with correct fields |
| 5 | `orchestrate_live` → `swarm.SwarmManager.list_agents()` | ✅ Correct (no args) |
| 6 | `orchestrate_live` → `swarm.SwarmManager.shutdown()` | ✅ Correct (no args) |
| 7 | `swarm` → `orchestrator.Orchestrator.__init__` | ✅ Correct (all kwargs match) |
| 8 | `swarm` → `orchestrator.Orchestrator.route_next()` | ✅ Correct |
| 9 | `swarm` → `orchestrator.Orchestrator.tick()` | ✅ Correct |
| 10 | `swarm` → `orchestrator.Orchestrator.tick_settle_only()` | ✅ Correct |
| 11 | `swarm` → `orchestrator.Orchestrator.graceful_stop()` | ✅ Correct |
| 12 | `swarm` → `orchestrator._classify_failure` | ⚠️ Works but private method coupling |
| 13 | `swarm` → `agent_runner.AgentPool.__init__` | ✅ Correct |
| 14 | `swarm` → `agent_runner.AgentPool.spawn()` | ✅ Correct (all kwargs match) |
| 15 | `swarm` → `evolution.DarwinEngine.__init__` | ✅ Correct (subset of params) |
| 16 | `swarm` → `evolution.DarwinEngine.gate_check()` | ✅ Correct |
| 17 | `swarm` → `evolution.DarwinEngine.get_fitness_trend()` | ✅ Correct |
| 18 | `swarm` → `evolution.DarwinEngine.propose()` | ✅ Correct |
| 19 | `swarm` → `meta_evolution.MetaEvolutionEngine.__init__` | ✅ Correct |
| 20 | `swarm` → `auto_proposer.AutoProposer.__init__` | ✅ Correct (stigmergy may be None — internal bug) |
| 21 | `swarm` → `auto_proposer.AutoProposer.cycle()` | ✅ Correct; CycleLog fields all accessed correctly |
| 22 | `swarm` → `organism.OrganismRuntime.__init__` | ✅ Correct |
| 23 | `swarm` → `organism.OrganismRuntime.heartbeat()` | ✅ Correct |
| 24 | `swarm` → `organism.OrganismRuntime.status()` | ⚠️ Returns `dict` assigned to `SwarmState.organism`; potential None chain on `samvara.current_power` |
| 25 | `swarm` → `stigmergy.StigmergyStore.__init__` | ✅ Correct |
| 26 | `swarm` → `stigmergy.StigmergyStore.decay()` | ✅ Correct |
| 27 | `swarm` → `memory.StrangeLoopMemory.remember()` | ✅ Correct (all callers pass `layer=`) |
| 28 | `swarm` → `monitor.SystemMonitor.__init__` | ✅ Correct |
| 29 | `swarm` → `monitor.SystemMonitor.detect_anomalies()` | ✅ Correct |
| 30 | `swarm` → `witness.WitnessAuditor.__init__` | ⚠️ Provider is ModelRouter, not bare LLMProvider |
| 31 | `swarm` → `witness.WitnessAuditor.run_cycle()` | ✅ Correct |
| 32 | `swarm` → `signal_bus.SignalBus.emit()` | ✅ Correct |
| 33 | `swarm` → `signal_bus.SignalBus.drain()` | ✅ Correct |
| 34 | `orchestrate_live` → `evolution.DarwinEngine.auto_evolve()` | ✅ Correct (all kwargs match signature) |
| 35 | `orchestrate_live` → `meta_evolution.MetaEvolutionEngine` | ⚠️ Cadence mismatch (see MISMATCH-07) |
| 36 | `orchestrate_live` → `message_bus.MessageBus.receive()` | ⚠️ See MISMATCH-03 |
| 37 | `orchestrate_live` → `message_bus.MessageBus.consume_events()` | ✅ Correct |
| 38 | `orchestrate_live` → `message_bus.MessageBus.mark_read()` | ✅ Correct |
| 39 | `orchestrate_live` → `replication_protocol.ReplicationProtocol.__init__` | ✅ Correct |
| 40 | `orchestrate_live` → `replication_protocol.ReplicationProtocol.run()` | ✅ Correct |
| 41 | `orchestrate_live` → `persistent_agent.PersistentAgent.__init__` | ❌ BLOCKER — enum vs string (MISMATCH-02) |
| 42 | `orchestrate_live` → `subconscious.SubconsciousStream.__init__` | ⚠️ Duplicate StigmergyStore (MISMATCH-06) |
| 43 | `orchestrate_live` → `shakti.ShaktiLoop.__init__` | ⚠️ Duplicate StigmergyStore (MISMATCH-06) |
| 44 | `orchestrate_live` → `witness.WitnessAuditor.__init__` | ✅ Correct for this call site |
| 45 | `orchestrate_live` → `witness.WitnessAuditor.run_cycle()` | ✅ Correct |
| 46 | `orchestrate_live` → `witness.WitnessAuditor.get_stats()` | ✅ Correct |
| 47 | `orchestrate_live` → `neural_consolidator.NeuralConsolidator.__init__` | ✅ Correct |
| 48 | `orchestrate_live` → `consolidation.ConsolidationCycle.__init__` | ✅ Correct |
| 49 | `orchestrate_live` → `consolidation.ConsolidationCycle.run()` | ✅ Correct; `ConsolidationOutcome` attrs match |
| 50 | `orchestrate_live` → `population_control.PopulationController.__init__` | ✅ Correct |
| 51 | `orchestrate_live` → `population_control.PopulationController.get_all_probation()` | ✅ Correct; `ProbationStatus.is_complete`, `.cycles_remaining` exist |
| 52 | `orchestrate_live` → `tiny_router_shadow.infer_tiny_router_shadow` | ❌ BLOCKER — `huggingface_hub` missing (MISMATCH-01) |
| 53 | `agent_runner` → `telos_gates.check_with_reflective_reroute()` | ✅ Correct (all kwargs match) |
| 54 | `agent_runner` → `economic_spine.EconomicSpine.spend_tokens()` | ✅ Correct |
| 55 | `conductors.py` → `persistent_agent.PersistentAgent.__init__` | ✅ Correct — enum values from `conductors.py` are proper enum instances |

---

## Bootstrap Sequence

Apply fixes in this order (most upstream blockers first):

### Fix 1 — **CRITICAL** — `huggingface_hub` guard in `tiny_router_shadow.py`
**File:** `dharma_swarm/tiny_router_shadow.py`  
**Lines:** 494–495  
**Change:** Wrap import in try/except to return None and fall through to heuristic mode:
```python
# BEFORE:
def _load_tiny_router_artifacts(*, allow_download: bool) -> _TinyRouterCheckpointArtifacts | None:
    from huggingface_hub import snapshot_download

# AFTER:
def _load_tiny_router_artifacts(*, allow_download: bool) -> _TinyRouterCheckpointArtifacts | None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return None
```
**Why first:** This crashes `router_v1` and `conversation_memory` on the very first request. Every agent message processed through the router fails. Blocks the entire swarm.

---

### Fix 2 — **CRITICAL** — `PersistentAgent` enum coercion in `orchestrate_live.py`
**File:** `dharma_swarm/orchestrate_live.py`  
**Lines:** 1243–1257  
**Change:**
```python
# BEFORE:
child = PersistentAgent(
    name=outcome.child_agent_name,
    role=outcome.child_spec.get("role", "worker"),
    provider_type=outcome.child_spec.get("default_provider", "openrouter_free"),

# AFTER:
child = PersistentAgent(
    name=outcome.child_agent_name,
    role=AgentRole(outcome.child_spec.get("role", "general")),
    provider_type=PT(outcome.child_spec.get("default_provider", "openrouter_free")),
```
**Why second:** Every successful replication event causes a crash at agent spawn time. All child agents fail to start.

---

### Fix 3 — **IMPORTANT** — Add `AgentPool` None guard in `swarm.spawn_agent()`
**File:** `dharma_swarm/swarm.py`  
**Line:** ~790 (before `self._agent_pool.spawn(...)`)  
**Change:**
```python
if self._agent_pool is None:
    raise SubsystemNotReady("AgentPool not initialized — cannot spawn agents")
```
**Why third:** If the agent_runner import fails on boot, the swarm appears healthy (no exception raised) but silently cannot spawn any agents.

---

### Fix 4 — **IMPORTANT** — `AutoProposer` stigmergy None guard
**File:** `dharma_swarm/auto_proposer.py`  
**Location:** All methods that call `await self._stigmergy.read_marks(...)`  
**Change:** Add guard:
```python
if self._stigmergy is None:
    return []
```
before every `self._stigmergy.` call inside the class.  
**Why fourth:** AutoProposer silently crashes every 30 minutes (the `_auto_proposer_interval_ticks` cycle) when `_stigmergy` is None, logging an exception and losing the autonomy feedback loop.

---

### Fix 5 — **IMPORTANT** — Deduplicate `StigmergyStore` instances
**File:** `dharma_swarm/orchestrate_live.py`  
**Lines:** 688–697  
**Change:** Pass the swarm's stigmergy store into the living layers loop:
```python
async def run_living_layers_loop(
    shutdown_event: asyncio.Event,
    stigmergy_store: StigmergyStore | None = None,
) -> None:
    store = stigmergy_store or StigmergyStore()
```
And update the call site in `orchestrate()` to wire it up after swarm init.  
**Why fifth:** Concurrent writes to the same JSONL without shared locks can corrupt the stigmergy trail, which is the coordination backbone for subconscious and Shakti perception.

---

### Fix 6 — **MODERATE** — `Orchestrator.receive()` semantics fix
**File:** `dharma_swarm/orchestrate_live.py`  
**Line:** 359  
**Change:** Replace `receive()` + `mark_read()` with `consume_events()`:
```python
lifecycle_msgs = await _bus.consume_events("AGENT_LIFECYCLE_COMPLETED", limit=20)
completions = sum(
    1 for m in lifecycle_msgs
    if m.get("payload", {}).get("event") == "task_completed"
)
```
And update the producer in `orchestrator.py` to emit `"AGENT_LIFECYCLE_COMPLETED"` events (not messages) via `_bus.emit_event()`.  
**Why sixth:** Affects evolution fitness context, not correctness. Fix after critical path is stable.

---

### Fix 7 — **MODERATE** — `WitnessAuditor` provider type
**File:** `dharma_swarm/swarm.py`  
**Lines:** 442–445  
**Change:** Pass a cost-appropriate provider:
```python
from dharma_swarm.providers import OpenRouterFreeProvider
self._witness = WitnessAuditor(
    cycle_seconds=3600.0,
    provider=OpenRouterFreeProvider(),
)
```
**Why seventh:** Not a crash, but witnesses may use expensive models unintentionally through the full router.

---

### Fix 8 — **MODERATE** — `samvara.current_power` None guard
**File:** `dharma_swarm/swarm.py`  
**Lines:** 2086–2088  
**Change:**
```python
result["organism_power"] = (
    self._organism.samvara.current_power.value
    if (self._organism.samvara.active
        and self._organism.samvara.current_power is not None)
    else None
)
```
**Why eighth:** Rare crash during organism initialization or samvara reset. Non-blocking but causes the entire tick to fail and log an unhandled exception.

---

### Fix 9 — **LOW** — Canonicalize `ECC_INSTINCT_SIGNAL` event type
**File:** `dharma_swarm/signal_bus.py` + all producers  
**Change:** Add constant:
```python
SIGNAL_ECC_INSTINCT = "ECC_INSTINCT_SIGNAL"
```
And use it everywhere.  
**Why last:** No crash, but silent data loss if any producer uses a different spelling.

---

## Resolution Status

| Fix | MISMATCH | Status | Commit |
|-----|----------|--------|--------|
| 1 | MISMATCH-01 | **RESOLVED** | `5ed4a3e` — guard huggingface_hub import |
| 2 | MISMATCH-02/12 | **RESOLVED** | `98341b4` — coerce strings to enums for PersistentAgent |
| 3 | MISMATCH-04 | **RESOLVED** | `d0ecc87` — AgentPool None guard before spawn |
| 4 | MISMATCH-10 | **ALREADY GUARDED** | Guard already exists at auto_proposer.py:297 |
| 5 | MISMATCH-06 | **RESOLVED** | `b56d208` — accept shared StigmergyStore in run_living_layers |
| 6 | MISMATCH-03 | **RESOLVED** | `b7f5c3e` — replace receive/mark_read with consume_events |
| 7 | MISMATCH-11 | **RESOLVED** | `d45a5e0` — use OpenRouterFreeProvider for WitnessAuditor |
| 8 | MISMATCH-09 | **RESOLVED** | `3816065` — guard samvara.current_power for None |
| 9 | MISMATCH-08 | **RESOLVED** | `38c5f61` — canonicalize ECC_INSTINCT_SIGNAL constant |

---

*End of Interface Mismatch Map*
