# Production-Readiness Audit: `agent_runner.py`

**File:** `dharma_swarm/dharma_swarm/agent_runner.py`  
**Lines:** 3,024  
**Auditor:** Senior DevOps Engineer  
**Date:** 2026-04-05  

---

## 1. Module Purpose

`agent_runner.py` is the execution core of the dharma_swarm agent system. It contains two primary classes — `AgentRunner` (manages the lifecycle and LLM execution of a single agent) and `AgentPool` (manages a fleet of runners). The module receives tasks from the orchestrator, builds system prompts (injecting dharmic context, memory, stigmergy, and fitness feedback), invokes LLM providers through a `ModelRouter` or direct `CompletionProvider`, handles a multi-round local tool loop (read/write/edit/shell/grep/glob), performs semantic quality assessment with repair retries, and then records results across ~10 subsystems: stigmergy marks, signal bus fitness events, economic spine token tracking, telic seam ontology, agent registry, lineage graph, conversation memory, mem-action extraction, observability traces (Langfuse/jikoku), and guardrail checks. It is the sole bridge between the orchestrator's task queue and actual LLM inference. If this module fails, no agent can execute any task, and every downstream feedback loop (evolution, organism, consolidation, witness, training flywheel) is broken.

---

## 2. LLM Execution Path Verification

### Step 1: Task Receipt
- **Method:** `AgentRunner.run_task(task: Task)` — line 1789
- **Entry:** Called by the orchestrator via `_execute_task()`. The task is a `Task` Pydantic model.
- **Lock:** Acquires `self._lock` (line 1801), sets status to `BUSY`.

### Step 2: Telos Gate Check
- **Method:** `check_with_reflective_reroute()` — line 1853
- **Synchronous call** (verified in `telos_gates.py:816` — it's a plain `def`, not `async def`).
- Called from inside an `async def` without issue.
- If gate returns `BLOCK`, raises `RuntimeError` (line 1864). This is caught by the outer `except Exception` at line 2267.
- **Status: Executes correctly.**

### Step 3: System Prompt Construction
- **Method:** `_build_system_prompt(config)` — line 802, called via `_build_prompt()` at line 965
- **Layers injected:**
  1. `V7_BASE_RULES` from `daemon_config.py` (line 816) — or `config.system_prompt` if non-CLAUDE_CODE with explicit prompt (line 807-808)
  2. `ROLE_BRIEFINGS[config.role.value]` (line 817)
  3. `DharmaAttractor().ambient_seed()` (line 826) — try/except, swallowed on failure
  4. `_build_self_state_block(config.name)` (line 834) — agent identity, samvara, recognition seed
  5. `load_behavioral_corrections(config.name)` (line 843) — neural consolidator weights
  6. `build_agent_context(role, thread)` (line 852) — **ONLY for CLAUDE_CODE providers** (guarded by `config.provider == ProviderType.CLAUDE_CODE` at line 850)
  7. `SHAKTI_HOOK` (line 862) — universal perception mode
  8. `inject_mem_instruction(prompt)` (line 871) — MemPO-style actions
- **User message layers** (in `_build_prompt`, lines 966-1052):
  1. Task title + description
  2. Completion contract brief (mission_contract)
  3. Memory recall (`read_memory_context` + `read_latent_gold_context`)
  4. Fitness feedback from SignalBus
  5. Plan context from reflective reroute
- **After `_build_prompt`:**
  - `_inject_stigmergy_context()` at line 1876 — adds stigmergy marks to the user message
  - Agent self-editing memory appended to system prompt at line 1899
- **FINDING:** `build_agent_context()` is only called for CLAUDE_CODE providers (line 850). Non-CLAUDE_CODE agents (OpenRouter, Groq, etc.) never get multi-layer context injection from `context.py`. This appears intentional but means the vast majority of agents running through free providers lack the full context pipeline.
- **Status: Executes, but context.py is gated on provider type.**

### Step 4: LLM Invocation
- **Method:** `_invoke_provider()` — line 1502
- **Path A (routed):** If provider has `complete_for_task` and `record_task_feedback` methods (checked via `_is_routed_provider()` at line 1509):
  - Builds `ProviderRouteRequest` via `_build_route_request()` (line 1511)
  - Calls `provider.complete_for_task(route_request, request, available_provider_types=...)` (line 1517)
  - Returns `(route_request, route_decision, response)`
- **Path B (direct):** Falls through to `provider.complete(request)` (line 1523)
- **Tool loop:** If sandbox exists and tooling required (line 1714-1721), enters `_complete_with_tool_loop()` (line 1625) which iterates up to `max_tool_rounds` (default 8), feeding tool results back as `role: "tool"` messages.
- **Timeout:** Handled via `asyncio.wait_for()` at line 1941, using `_semantic_attempt_timeout_seconds()`. On timeout, builds a repair request and retries if attempts remain.
- **Status: Executes correctly. Provider fallback happens inside ModelRouter, not in agent_runner.**

### Step 5: Response Parsing
- **Tool calls:** Checked via `response.tool_calls` (line 1654). If present, enters tool loop; tool results appended with `role: "tool"` messages.
- **Text:** `response.content` extracted at line 1727.
- **Provider failure detection:** `_looks_like_provider_failure()` at line 1985 — checks for error prefixes.
- **Semantic assessment:** `_assess_completion_semantics()` at line 1987 — async, checks quality.
- **Checkpoint honoring:** `_assess_honors_checkpoint()` at line 1996 — sync, checks artifact existence.
- **Status: Executes correctly.**

### Step 6: Result Storage
- **Stigmergy marks:** `_leave_task_mark()` at line 2117 — async, best-effort (try/except).
- **Shared notes:** NOT directly written here. Result is returned to the orchestrator which handles shared note persistence.
- **Signal bus:** `_emit_fitness_signal()` at line 2190 — emits `AGENT_FITNESS` to in-memory bus and durable `MessageBus`.
- **Status: Executes correctly. Multiple storage paths, all try/except guarded.**

### Step 7: Cost Recording
- **Economic spine:** Lines 2247-2258 — calls `self._economic_spine.spend_tokens(agent_id, step_tokens, mission_id)`.
- **Token counting:** `_response_total_tokens()` at line 689 — reads `usage.total_tokens` or sums `prompt_tokens + completion_tokens`.
- **Cumulative tracking:** `self._tokens_used_total += step_tokens` at line 2249.
- **Status: Executes, but only if `economic_spine` is attached (it's `None` by default).**

### Step 8: Swabhaav Ratio / Fitness
- **Method:** `_emit_fitness_signal()` at line 2552
- **Computation:** `MetricsAnalyzer().analyze(result)` returns `sig.swabhaav_ratio`, `sig.entropy`, `sig.recognition_type`.
- **Emission:** Emitted as `AGENT_FITNESS` event to SignalBus (in-memory) and MessageBus (durable).
- **Status: Executes, fully try/except guarded.**

### Step 9: DarwinEngine Connection
- **Direct connection:** NONE. `agent_runner.py` does NOT import or call `DarwinEngine` directly.
- **Indirect:** Fitness signals emitted to `SignalBus` are consumed by the evolution loop in `orchestrate_live.py`, which feeds them to `DarwinEngine`.
- **Active inference:** `_start_active_inference()` at line 1747 and `_observe_active_inference()` at line 1764 — a prediction/observation loop for Bayesian quality estimation. Separate from DarwinEngine.
- **Status: No direct DarwinEngine integration. Feedback flows through signal bus.**

### Error Swallowing Assessment
Almost every subsystem call in `run_task()` is wrapped in its own `try/except Exception` that logs at `DEBUG` level and continues. The following subsystem failures are **silently swallowed**:
- Lifecycle signal emission (lines 1806-1816)
- Conversation logging (lines 1884-1893, 2038-2049)
- Observability traces (lines 2063-2079, 2297-2314)
- Guardrail checks (lines 2082-2102)
- Lineage recording (lines 2138-2154)
- MemPO extraction (lines 2157-2179)
- AgentRegistry logging (lines 2193-2207, 2322-2337)
- Telic seam recording (lines 2210-2240, 2339-2370)
- Economic tracking (lines 2247-2258)

Only the **core LLM call** and **telos gate** failures propagate. This is by design ("best-effort sidecars") but means ~15 subsystems could be silently broken in production without any alerting.

---

## 3. Bug Report

### BUG-01: Missing `await` on `_execute_completion_attempt` — Coroutine never awaited in edge case  
**File:** `agent_runner.py`, line 1929  
**Code:**
```python
attempt_result = self._execute_completion_attempt(
    task,
    current_request,
    attempt_index=attempt_index,
)
```
**What's wrong:** `_execute_completion_attempt` is `async def` (line 1692). Line 1929 creates the coroutine but does NOT `await` it. It is later awaited at lines 1941 (`asyncio.wait_for(attempt_result, ...)`) or 1952 (`await attempt_result`). This is **intentionally correct** — the coroutine is created first so it can be optionally wrapped with `wait_for`. **Not a bug.** False alarm; retracted.

### BUG-02: `:.2f` format on fallback string `'?'` causes `ValueError`  
**File:** `agent_runner.py`, lines 1032-1033  
**Code:**
```python
f"swabhaav={evt.get('swabhaav_ratio', '?'):.2f}, "
f"entropy={evt.get('entropy', '?'):.2f}, "
```
**What's wrong:** If `swabhaav_ratio` or `entropy` keys are missing from the event dict, `evt.get('swabhaav_ratio', '?')` returns the string `'?'`. The `:.2f` format specifier then raises `ValueError: Unknown format code 'f' for object of type 'str'`. This crashes the fitness injection, which is caught by the outer `try/except` and silently swallowed — so no fitness context is ever injected into agent prompts.  
**Severity:** MEDIUM — Degrades agent performance by silently dropping fitness feedback.  
**Fix:**
```python
f"swabhaav={evt.get('swabhaav_ratio', 0.0):.2f}, "
f"entropy={evt.get('entropy', 0.0):.2f}, "
```

### BUG-03: `_memory_palace` attribute never initialized  
**File:** `agent_runner.py`, line 2169  
**Code:**
```python
palace = getattr(self, "_memory_palace", None)
for ma in mem_actions:
    await store_mem_action(palace, ma)
```
**What's wrong:** `_memory_palace` is never set in `__init__` or anywhere else on `AgentRunner`. `getattr(self, "_memory_palace", None)` always returns `None`. The `store_mem_action(palace, ma)` function presumably receives `None` and either no-ops or crashes. Mem actions extracted from agent output are never persisted to the Memory Palace.  
**Severity:** MEDIUM — Silent data loss for <mem> action persistence.  
**Fix:** Either initialize `self._memory_palace = None` in `__init__` and wire it up during spawn, or remove the dead code.

### BUG-04: `_last_mem_action` attribute never initialized  
**File:** `agent_runner.py`, line 2167  
**Code:**
```python
self._last_mem_action = mem_actions[-1]
```
**What's wrong:** `_last_mem_action` is never initialized in `__init__`. This works on first write (Python creates instance attributes dynamically), but if any code reads `self._last_mem_action` before a task with mem actions runs, it raises `AttributeError`. Fragile pattern.  
**Severity:** LOW — Works by accident but violates initialization discipline.  
**Fix:** Add `self._last_mem_action: Any = None` to `__init__`.

### BUG-05: `LLMRequest.messages` typed as `list[dict[str, str]]` but tool loop writes `dict[str, Any]`  
**File:** `agent_runner.py`, line 1658-1666, cross-ref `models.py` line 312  
**Code:**
```python
# models.py:312
messages: list[dict[str, str]]

# agent_runner.py:1658-1666
updated_messages.append({
    "role": "assistant",
    "content": response.content or "",
    "tool_calls": [  # <-- list[dict], not str
        _normalized_tool_call_payload(...)
    ],
})
```
**What's wrong:** The `tool_calls` value is a `list[dict[str, Any]]`, not a `str`. Pydantic validation on `model_copy(update={"messages": updated_messages})` (line 1686) may reject this if strict validation is enabled, or silently coerce/drop the field. At minimum, the type annotation is inaccurate and makes static analysis unreliable.  
**Severity:** MEDIUM — May cause silent data loss of tool_calls in message history during copy, depending on Pydantic validation mode. Tool loop could malfunction if tool_calls are stripped.  
**Fix:** Change `models.py:312` to:
```python
messages: list[dict[str, Any]]
```

### BUG-06: Duplicate priority→score mappings with inconsistent values  
**File:** `agent_runner.py`, lines 68-73 (`_PRIORITY_SALIENCE`) and lines 377-382 (`_priority_score`)  
**Code:**
```python
# _PRIORITY_SALIENCE (used for memory salience + stigmergy marks)
TaskPriority.LOW: 0.30,  TaskPriority.NORMAL: 0.50,
TaskPriority.HIGH: 0.70, TaskPriority.URGENT: 0.90,

# _priority_score (used for route request urgency)
TaskPriority.LOW: 0.18,  TaskPriority.NORMAL: 0.40,
TaskPriority.HIGH: 0.72, TaskPriority.URGENT: 0.95,
```
**What's wrong:** Two separate mappings from `TaskPriority` to a 0-1 score with different values for the same priorities. Confusing and likely unintentional divergence. `_PRIORITY_SALIENCE` is used for memory salience; `_priority_score` for routing urgency. The semantic distinction is unclear.  
**Severity:** LOW — Different contexts may justify different scales, but the naming doesn't make this clear. Maintenance hazard.  
**Fix:** Either unify into one mapping, or document the intentional difference. Rename `_priority_score` to `_priority_urgency_score` to clarify.

### BUG-07: `_inject_stigmergy_context` creates a NEW `StigmergyStore` per task  
**File:** `agent_runner.py`, lines 1080-1082  
**Code:**
```python
from dharma_swarm.stigmergy import StigmergyStore, _derive_channel
store = StigmergyStore(base_path=prompt_state_dir / "stigmergy")
marks = await store.query_relevant(...)
```
**What's wrong:** Every task execution creates a fresh `StigmergyStore` instance. This is the same dual-instance problem documented in INTERFACE_MISMATCH_MAP.md (MISMATCH-06). Each `StigmergyStore` has its own `asyncio.Lock`, so concurrent agents writing marks to the same JSONL file can corrupt data.  
**Severity:** MEDIUM — Data corruption risk under concurrent agent execution.  
**Fix:** Pass the shared `StigmergyStore` from the swarm into `AgentRunner`, or use a singleton factory.

### BUG-08: `_leave_task_mark` creates yet another `StigmergyStore` via `_get_default_store()`  
**File:** `agent_runner.py`, line 1341  
**Code:**
```python
await _get_default_store().leave_mark(mark)
```
**What's wrong:** `_get_default_store()` likely returns a module-level singleton, but it's a THIRD store instance in addition to the one in `_inject_stigmergy_context` and the one in `swarm.py`. Same concurrent-write risk.  
**Severity:** MEDIUM — Compounds BUG-07. Multiple lock-unsynchronized writers.  
**Fix:** Inject a shared store reference into `AgentRunner.__init__`.

### BUG-09: `_build_prompt` fitness injection uses format specifiers that crash on missing keys  
**File:** `agent_runner.py`, lines 1032-1033, 1040  
**See BUG-02.** Additionally, line 1040:
```python
f"duration={evt.get('duration_seconds', '?')}s"
```
This one is safe (no format specifier), but the inconsistency between formatted and unformatted fallback values suggests the author forgot the format specifier would fail on strings.  
**Severity:** See BUG-02.

### BUG-10: `_build_system_prompt` returns early for non-CLAUDE_CODE agents with explicit `system_prompt`  
**File:** `agent_runner.py`, lines 807-808  
**Code:**
```python
if config.system_prompt and config.provider != ProviderType.CLAUDE_CODE:
    return config.system_prompt
```
**What's wrong:** If a non-CLAUDE_CODE agent has a `system_prompt` set, ALL contextual injections are skipped: no dharma attractor, no self-state, no behavioral corrections, no SHAKTI_HOOK, no mem instructions. The agent gets a static prompt with zero live awareness. This is technically intentional ("explicit system_prompt is final") but architecturally dangerous: any agent with an explicit prompt loses the entire dharmic context pipeline.  
**Severity:** MEDIUM — Architectural concern. Any agent configuration that sets `system_prompt` silently disables live context, breaking the strange loop for that agent.  
**Fix:** Consider always appending live context even when `system_prompt` is explicit. Add a `skip_context_injection: bool` metadata flag for cases where raw prompt is truly desired.

### BUG-11: `AgentPool.assign()` and `AgentPool.release()` directly access `runner._lock`  
**File:** `agent_runner.py`, lines 2986, 2993  
**Code:**
```python
async with runner._lock:
    runner._state.current_task = task_id
```
**What's wrong:** External code (the pool) reaches into the runner's private `_lock`. This violates encapsulation. If the locking strategy changes (e.g., `RLock`, per-field locks), pool code breaks.  
**Severity:** LOW — Works but fragile.  
**Fix:** Add public methods `runner.set_current_task(task_id)` and `runner.clear_current_task()`.

### BUG-12: `AgentPool.get_result()` always returns `None`  
**File:** `agent_runner.py`, lines 2997-3003  
**Code:**
```python
async def get_result(self, agent_id: str) -> str | None:
    return None
```
**What's wrong:** This method satisfies a duck-type contract but always returns `None`. The docstring says "actual results are collected via `_execute_task` in the orchestrator." If any consumer calls `get_result` expecting a real result, they get `None`.  
**Severity:** LOW — By design, but a maintenance trap. Anyone reading the interface would expect it to work.  
**Fix:** Either remove the method and update the interface, or implement result caching.

### BUG-13: `_task_file_path` re-imports `re` at module scope AND locally  
**File:** `agent_runner.py`, line 1125  
**Code:**
```python
def _task_file_path(task: Task) -> str:
    import re  # ← already imported at module level (line 13)
```
**What's wrong:** `re` is already imported at module level on line 13. The local import is dead code.  
**Severity:** LOW — No runtime impact, just noise.  
**Fix:** Remove `import re` from line 1125.

### BUG-14: `_FILE_REFERENCE_PATTERN` defined but never used  
**File:** `agent_runner.py`, lines 126-128  
**Code:**
```python
_FILE_REFERENCE_PATTERN = re.compile(
    r"(?<![\w/])(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+\.(?:py|md|json|yaml|yml|toml|txt|ts|tsx|js|jsx|sh))(?![\w/])"
)
```
**What's wrong:** Compiled regex at module scope but never used anywhere in the file. Dead code.  
**Severity:** LOW — Wastes import-time cycles compiling a regex that's never used.  
**Fix:** Remove or move to the module that needs it.

### BUG-15: `_META_OBSERVATION_HINTS` defined but never used  
**File:** `agent_runner.py`, lines 129-141  
**Code:**
```python
_META_OBSERVATION_HINTS = (
    "system", "control plane", "orchestrator", ...
)
```
**What's wrong:** Tuple defined at module scope but never referenced.  
**Severity:** LOW — Dead code.  
**Fix:** Remove.

### BUG-16: `_REASONING_LEAK_MARKERS` defined but never used  
**File:** `agent_runner.py`, lines 118  
**Severity:** LOW — Dead code.  
**Fix:** Remove.

### BUG-17: `_EXPLORATION_PREAMBLE_MARKERS` defined but never used  
**File:** `agent_runner.py`, lines 119-125  
**Severity:** LOW — Dead code.  
**Fix:** Remove.

### BUG-18: `config.metadata.get(...)` on line 650 — no guard for non-dict metadata  
**File:** `agent_runner.py`, line 650  
**Code:**
```python
or config.metadata.get("session_id")
```
**What's wrong:** In `_build_route_request`, `config.metadata` is typed as `dict[str, Any]` per the model, so `.get()` is valid. However, other methods like `_tool_loop_max_rounds` (line 1221) also call `config.metadata.get(...)` without checking if metadata is dict. Since `AgentConfig.metadata` has a `default_factory=dict`, this should always be a dict. **Not a bug** — the Pydantic model guarantees it.

### BUG-19: Silent economic tracking skip when `_economic_spine` is `None`  
**File:** `agent_runner.py`, lines 2250-2256  
**What's wrong:** `self._economic_spine` defaults to `None` (line 1386). It's only set if `set_economic_spine()` is called externally. If the caller forgets to wire it up, all token spending is silently lost — no cost tracking for any agent.  
**Severity:** MEDIUM — Silent loss of cost data. No warning logged when spine is None.  
**Fix:** Log a warning on the first task if `_economic_spine` is None:
```python
if self._economic_spine is None:
    logger.warning("No economic_spine attached to %s — costs not tracked", self._config.name)
```

### BUG-20: `_new_stigmergy_store_per_query` inside `_inject_stigmergy_context` is wasteful  
**File:** `agent_runner.py`, line 1082  
**What's wrong:** See BUG-07. Beyond the data corruption risk, creating a new store per task is also wasteful: each instance opens and parses the JSONL file, builds indexes, etc.  
**Severity:** LOW (performance) — Combined with BUG-07 for the safety concern.

### BUG-21: `_build_route_request` accesses `config.metadata.get("session_id")` without `_task_metadata()` wrapper  
**File:** `agent_runner.py`, line 650  
**What's wrong:** This accesses `config.metadata` directly, while other methods use `_task_metadata(task)` for task metadata. This is actually correct — it's reading from config metadata, not task metadata. **Not a bug.**

### BUG-22: Tool loop tool_call_id mismatch between assistant message and tool result  
**File:** `agent_runner.py`, lines 1663 and 1672  
**Code:**
```python
# In assistant message (line 1663):
_normalized_tool_call_payload(tool_call, ordinal=index)  # id = tool_call["id"] or "tool-call-{index}"

# In tool result (line 1672):
tool_id = str(tool_call.get("id") or f"tool-call-{round_index}-{index}")
```
**What's wrong:** The `tool_call_id` in the assistant message is generated as `tool_call.get("id") or f"tool-call-{ordinal}"` (from `_normalized_tool_call_payload`, line 1273), where `ordinal=index` (1-based within the round). But the `tool_call_id` in the tool result message (line 1672) is `tool_call.get("id") or f"tool-call-{round_index}-{index}"` — a DIFFERENT fallback format including `round_index`. If the LLM response doesn't include tool call IDs (which many providers don't), the assistant message says `tool-call-1` but the tool result says `tool-call-2-1` (on round 2). **The IDs won't match**, causing the LLM to not associate the tool result with the tool call on subsequent rounds.  
**Severity:** HIGH — Breaks the tool loop for any provider that doesn't return tool call IDs. The LLM receives orphaned tool results.  
**Fix:** Ensure consistent ID generation. In the tool result loop, use the same ID from the normalized payload:
```python
for index, tool_call in enumerate(response.tool_calls, start=1):
    normalized = _normalized_tool_call_payload(tool_call, ordinal=index)
    tool_id = normalized["id"]
    ...
    updated_messages.append({
        "role": "tool",
        "tool_call_id": tool_id,
        ...
    })
```

### BUG-23: `_StigmergyStore` private import `_derive_channel` and `_get_default_store`  
**File:** `agent_runner.py`, lines 1080 and 1322  
**Code:**
```python
from dharma_swarm.stigmergy import StigmergyStore, _derive_channel
from dharma_swarm.stigmergy import StigmergicMark, _get_default_store
```
**What's wrong:** Importing private (`_`-prefixed) functions from another module. Any refactor of `stigmergy.py` internals silently breaks `agent_runner.py`.  
**Severity:** LOW — Structural coupling to internal API.  
**Fix:** Make these functions part of the public API (remove the underscore) or add public wrappers.

---

## 4. Style and Quality Assessment

### Naming Consistency
- **Mostly consistent.** Private methods use `_` prefix. Module-level constants use `_UPPER_SNAKE_CASE`. Helper functions use `_lower_snake_case`.
- **Inconsistency:** `_PRIORITY_SALIENCE` vs `_priority_score` — one is a dict constant, the other is a function returning from an inline dict. Different naming styles for the same semantic purpose.
- **Inconsistency:** `_task_file_path` vs `_task_action_name` vs `_task_text` — similar patterns, good consistency here.
- **Inconsistency:** Some methods like `_record_idea_uptake`, `_record_follow_up_shard_outcome`, `_record_retrieval_citation_uptake`, `_record_retrieval_outcome`, `_mark_idea_outcome` are sync methods that call into `ConversationMemoryStore` — but similar methods like `_record_task_memory` are async. The sync ones create a new DB connection per call rather than reusing one.

### Docstrings
- **Present** on most public methods and important private methods.
- **Accurate** where present.
- **Missing** on many helper functions (`_coerce_bool`, `_metadata_number`, `_metadata_bool`, `_parse_provider_types`, etc.) — though these are simple enough to be self-documenting.
- The class-level docstring for `AgentRunner` is minimal.

### Module Size
**3,024 lines is far too large.** This module should be decomposed:

1. **`agent_runner_prompt.py`** (~250 lines) — `_build_system_prompt`, `_build_prompt`, `_inject_stigmergy_context`, `_build_self_state_block`
2. **`agent_runner_routing.py`** (~200 lines) — `_build_route_request`, `_available_provider_types`, `_allow_provider_routing`, `_requires_tooling`, `_requires_frontier_precision`, `_is_privileged_action`, and all the routing metadata helpers
3. **`agent_runner_tools.py`** (~250 lines) — `_execute_local_tool`, `_complete_with_tool_loop`, `_LOCAL_OPENAI_TOOL_DEFINITIONS`, `_LOCAL_TOOL_RUNTIME_DIRECTIVE`, `_normalized_tool_call_payload`, `_tool_call_parameters`
4. **`agent_runner_memory.py`** (~200 lines) — `_record_task_memory`, `_record_failure_memory`, `_emit_fitness_signal`, `_record_conversation_turn`, `_record_idea_uptake`, `_record_follow_up_shard_outcome`, `_mark_idea_outcome`, `_record_retrieval_outcome`, `_record_retrieval_citation_uptake`, `_memory_plane_db_path`
5. **`agent_runner_feedback.py`** (~80 lines) — `_record_router_feedback`, `_feedback_quality_score`
6. **`agent_runner.py`** (~400 lines) — `AgentRunner` class with `run_task`, `start`, `stop`, `heartbeat`, lifecycle
7. **`agent_pool.py`** (~200 lines) — `AgentPool` class
8. **`agent_runner_helpers.py`** (~200 lines) — All module-level helpers and constants

### Copy-Paste Patterns
- **Telic seam recording** is duplicated identically in the success path (lines 2210-2240) and failure path (lines 2339-2370). Should be extracted to a helper method.
- **Observability tracing** is duplicated in success (lines 2063-2079) and failure (lines 2297-2314) paths. Should be extracted.
- **AgentRegistry logging** is duplicated in success (lines 2193-2207) and failure (lines 2322-2337) paths.
- **Conversation logging** (`log_agent_turn`) is duplicated at lines 1884-1893 and 2038-2049.
- General pattern: the `run_task` method has a massive success block and a massive failure block that repeat ~80% of the same subsystem calls with minor variations.

### Overall Code Quality Rating: **5/10**

**Justification:**
- (+) Correct duck-typing with `Protocol` classes for provider interface
- (+) Robust metadata extraction helpers with multiple fallback keys
- (+) Comprehensive try/except isolation prevents subsystem failures from killing tasks
- (+) Tool loop is well-implemented with proper message threading
- (-) Module is 3x too large — should be 6-8 files
- (-) Massive copy-paste in success/failure paths
- (-) 4+ dead code constants at module scope
- (-) Silent error swallowing in ~15 subsystem calls with only DEBUG logging
- (-) Tool call ID mismatch bug (BUG-22) breaks core functionality
- (-) Multiple `StigmergyStore` instances causing data corruption risk
- (-) No production alerting for critical subsystem failures
- (-) `_memory_palace` never wired up — dead feature code

---

## 5. Recommended Fixes (Priority Order)

### 1. Fix tool call ID mismatch in tool loop (BUG-22)
**File:** `agent_runner.py`, lines 1669-1683  
**Impact:** HIGH — Breaks tool loop for providers without native tool call IDs  
**Change:**
```python
# BEFORE (lines 1669-1683):
for index, tool_call in enumerate(response.tool_calls, start=1):
    params = _tool_call_parameters(tool_call)
    tool_name = str(tool_call.get("name") or "")
    tool_id = str(tool_call.get("id") or f"tool-call-{round_index}-{index}")
    ...

# AFTER:
for index, tool_call in enumerate(response.tool_calls, start=1):
    normalized = _normalized_tool_call_payload(tool_call, ordinal=index)
    params = _tool_call_parameters(tool_call)
    tool_name = str(tool_call.get("name") or "")
    tool_id = normalized["id"]
    ...
```

### 2. Fix `:.2f` format crash on missing fitness keys (BUG-02)
**File:** `agent_runner.py`, lines 1032-1033  
**Impact:** MEDIUM — Silently drops all fitness context from agent prompts  
**Change:**
```python
# BEFORE:
f"swabhaav={evt.get('swabhaav_ratio', '?'):.2f}, "
f"entropy={evt.get('entropy', '?'):.2f}, "

# AFTER:
f"swabhaav={evt.get('swabhaav_ratio', 0.0):.2f}, "
f"entropy={evt.get('entropy', 0.0):.2f}, "
```

### 3. Fix `LLMRequest.messages` type to `list[dict[str, Any]]` (BUG-05)
**File:** `models.py`, line 312  
**Impact:** MEDIUM — Prevents Pydantic from stripping tool_calls from message dicts  
**Change:**
```python
# BEFORE:
messages: list[dict[str, str]]

# AFTER:
messages: list[dict[str, Any]]
```

### 4. Inject shared `StigmergyStore` instead of creating per-task instances (BUG-07, BUG-08)
**File:** `agent_runner.py`, `AgentRunner.__init__` and `AgentPool.spawn`  
**Impact:** MEDIUM — Prevents data corruption from concurrent writes  
**Change:** Add `stigmergy_store: StigmergyStore | None = None` parameter to `AgentRunner.__init__` and use it in `_inject_stigmergy_context` and `_leave_task_mark`.

### 5. Initialize `_memory_palace` and `_last_mem_action` in `__init__` (BUG-03, BUG-04)
**File:** `agent_runner.py`, `AgentRunner.__init__` (after line 1383)  
**Impact:** MEDIUM — Enables mem action persistence; prevents AttributeError  
**Change:**
```python
self._memory_palace: Any = None
self._last_mem_action: Any = None
```

### 6. Add warning when `_economic_spine` is None on first task (BUG-19)
**File:** `agent_runner.py`, inside `run_task`, near line 2247  
**Impact:** MEDIUM — Makes silent cost tracking failures visible  
**Change:**
```python
if self._economic_spine is None:
    logger.warning(
        "Agent %s has no economic_spine — token costs not tracked",
        self._config.name,
    )
```

### 7. Extract duplicated success/failure recording into helper methods
**File:** `agent_runner.py`  
**Impact:** LOW (quality) — Reduces ~200 lines of copy-paste  
**Change:** Create `_record_observability_trace(task, response, latency_ms, success, error=None)`, `_record_telic_seam(task, agent_id, cell_id, task_type, success, result_text, latency_ms)`, `_record_registry_log(task, success, response, latency_ms, text)`.

### 8. Remove dead code constants (BUG-14, BUG-15, BUG-16, BUG-17)
**File:** `agent_runner.py`, lines 118-141, 126-128  
**Impact:** LOW — Cleanup  
**Change:** Remove `_REASONING_LEAK_MARKERS`, `_EXPLORATION_PREAMBLE_MARKERS`, `_FILE_REFERENCE_PATTERN`, `_META_OBSERVATION_HINTS`.

### 9. Remove redundant `import re` in `_task_file_path` (BUG-13)
**File:** `agent_runner.py`, line 1125  
**Impact:** LOW — Cleanup  
**Change:** Delete line 1125.

### 10. Decompose module into 6-8 smaller files
**Impact:** LOW (immediate), HIGH (long-term maintainability)  
**Change:** See decomposition plan in Section 4. This is a larger refactor that should be done after the functional bugs are fixed.

---

*End of Audit Report*
