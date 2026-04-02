# JIKOKU SAMAYA — Deep OS Integration Architecture

**Version**: 1.0
**Date**: 2026-03-08
**Status**: Design Complete, Implementation Pending

---

## Executive Summary

JIKOKU SAMAYA (計測・三昧 - "measured commitment") is a computational efficiency protocol targeting **10x efficiency gain (5% → 50% utilization) with zero hardware cost**. This document specifies **deep OS integration** into dharma_swarm, moving from manual span wrapping to automatic instrumentation.

**Previous failure**: An agent promised this and never delivered.
**This design**: Bulletproof. Buildable. Verifiable.

---

## 1. Current State Assessment

### 1.1 What Exists (Good)

✅ **Core tracer implementation** (`jikoku_samaya.py`):
- Solid span creation/completion logic
- Context manager and manual span control
- JSONL persistence (atomic writes)
- Kaizen report generation with utilization metrics
- Valid category taxonomy
- Global tracer singleton

✅ **Test coverage** (`test_jikoku_samaya.py`):
- 15 tests covering all core functionality
- Pramāda detection validated
- Utilization calculation verified

✅ **Integration guide** (`JIKOKU_SAMAYA_INTEGRATION.md`):
- Clear examples for manual wrapping
- Kaizen dashboard design

### 1.2 What's Missing (Critical Gaps)

❌ **Zero automatic instrumentation**:
- Every span requires manual `with jikoku_span(...)` wrapping
- Easy to forget, inconsistent coverage
- No systematic guarantee of completeness

❌ **No provider integration**:
- LLM calls are the primary compute cost
- Not automatically traced
- Token/cost metadata not captured

❌ **No automatic kaizen loop**:
- Reports exist but require manual invocation
- No self-optimization based on findings
- No evolution engine integration

❌ **No performance overhead control**:
- Observer effect not measured
- No enable/disable mechanism
- Always-on instrumentation could slow system

❌ **No granularity control**:
- One-size-fits-all span creation
- Can't tune instrumentation depth
- No adaptive sampling

---

## 2. System Architecture

### 2.1 Core Design Principles

1. **Zero-overhead when disabled**: Instrumentation must be toggleable with negligible cost
2. **Automatic by default**: Spans created without manual intervention
3. **Minimal observer effect**: Profiling must not significantly slow execution
4. **Actionable kaizen**: Optimization targets automatically fed to evolution engine
5. **Composable spans**: Nested spans for hierarchical timing
6. **Async-native**: All instrumentation async-compatible

### 2.2 Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: Kaizen Automation                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ Auto-Trigger │──▶│ Kaizen Report│──▶│ Evolve Toward│   │
│  │  (cron/tick) │   │   Generator  │   │  Optimization│   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Instrumentation Engine                            │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │  Provider    │   │  Swarm Op    │   │  Evolution   │   │
│  │ Interceptor  │   │ Interceptor  │   │ Interceptor  │   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Span Management                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ Context Vars │   │ Nested Spans │   │ Async Context│   │
│  │   (thread-   │   │   (parent-   │   │  Propagation │   │
│  │    local)    │   │    child)    │   │              │   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Core Tracer (jikoku_samaya.py)                    │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ JikokuTracer │   │  JikokuSpan  │   │   JSONL Log  │   │
│  │              │   │              │   │   Storage    │   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Integration Points (Deep Instrumentation)

### 3.1 Provider Layer Integration

**File**: `dharma_swarm/providers.py`
**Strategy**: Wrap every provider's `complete()` method with automatic span creation

**Implementation approach**:
1. **Decorator-based wrapping** (not monkey-patching, cleaner)
2. Add `@jikoku_traced_provider` decorator to each provider
3. Capture token usage, cost, model selection in metadata

**Why this works**:
- All provider calls already go through `ModelRouter.complete()`
- Single interception point captures all LLM traffic
- Metadata (tokens, cost) already present in `LLMResponse`

**Code structure**:

```python
# dharma_swarm/jikoku_instrumentation.py (NEW MODULE)

import functools
from typing import Any, Callable, TypeVar, cast
from dharma_swarm.jikoku_samaya import get_global_tracer
from dharma_swarm.models import LLMRequest, LLMResponse

T = TypeVar('T')

def jikoku_traced_provider(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to automatically trace provider LLM calls."""

    @functools.wraps(func)
    async def wrapper(self: Any, request: LLMRequest) -> T:
        if not _instrumentation_enabled():
            return await func(self, request)

        tracer = get_global_tracer()
        provider_name = self.__class__.__name__.replace('Provider', '')

        with tracer.span(
            category="api_call",
            intent=f"LLM call to {provider_name}",
            metadata={
                'provider': provider_name,
                'model': request.model,
                'message_count': len(request.messages),
            }
        ) as span_id:
            response: LLMResponse = await func(self, request)

            # Add response metadata (tokens, cost) at span end
            usage = response.usage or {}
            tracer.end(span_id,
                      input_tokens=usage.get('input_tokens', 0),
                      output_tokens=usage.get('output_tokens', 0),
                      model=response.model,
                      stop_reason=response.stop_reason)

            return response

    return cast(Callable[..., T], wrapper)
```

**Integration into `providers.py`**:

```python
# Apply decorator to all provider complete() methods

class AnthropicProvider(LLMProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation
```

**Impact**: Every LLM call automatically traced with zero manual intervention.

---

### 3.2 Swarm Operations Integration

**File**: `dharma_swarm/swarm.py`
**Strategy**: Wrap high-level operations (spawn, task creation, evolution cycles)

**Key operations to instrument**:

| Operation | Category | Intent | Metadata |
|-----------|----------|--------|----------|
| `spawn_agent()` | `execute.agent_spawn` | "Spawn agent {name} ({role})" | `agent_id, role, provider, thread` |
| `create_task()` | `execute.task_create` | "Create task {title}" | `task_id, priority` |
| `dispatch_next()` | `execute.orchestration_tick` | "Orchestration tick" | `dispatches_count` |
| `evolve()` | `execute.evolution_proposal` | "Evolution proposal {component}" | `component, change_type, fitness` |

**Implementation approach**: Use context managers in existing methods

**Example for `spawn_agent()`**:

```python
# dharma_swarm/swarm.py

from dharma_swarm.jikoku_instrumentation import jikoku_auto_span

async def spawn_agent(
    self,
    name: str,
    role: AgentRole = AgentRole.GENERAL,
    model: str = "claude-code",
    provider_type: ProviderType = ProviderType.CLAUDE_CODE,
    system_prompt: str = "",
    thread: str | None = None,
) -> AgentState:
    """Spawn a new agent into the pool."""

    with jikoku_auto_span(
        category="execute.agent_spawn",
        intent=f"Spawn agent '{name}' ({role.value})",
        metadata={
            'agent_id': name,
            'role': role.value,
            'provider': provider_type.value,
            'thread': thread,
        }
    ):
        # ... existing spawn logic ...
        return runner.state
```

**Why context managers not decorators**:
- More explicit in async code
- Easier to add metadata from function arguments
- Can conditionally enable/disable per operation

---

### 3.3 Evolution Engine Integration

**File**: `dharma_swarm/evolution.py`
**Strategy**: Wrap proposal pipeline phases

**Key operations**:

| Phase | Category | Intent | Metadata |
|-------|----------|--------|----------|
| `propose()` | `execute.evolution_propose` | "Generate proposal {component}" | `component, change_type, predicted_fitness` |
| `gate_check()` | `execute.evolution_gate` | "Gate check proposal {id}" | `proposal_id, decision, gates_passed` |
| `evaluate()` | `execute.evolution_evaluate` | "Evaluate proposal {id}" | `proposal_id, fitness_score` |
| `archive_result()` | `file_op` | "Archive proposal {id}" | `proposal_id, entry_id, fitness` |

**Implementation**:

```python
# dharma_swarm/evolution.py

async def gate_check(self, proposal: Proposal) -> Proposal:
    """Run dharmic safety gates against a proposal."""

    with jikoku_auto_span(
        category="execute.evolution_gate",
        intent=f"Gate check proposal {proposal.id}",
        metadata={'proposal_id': proposal.id, 'component': proposal.component}
    ) as span_id:
        # ... existing gate check logic ...

        # Add result metadata at end
        jikoku_end(span_id,
                  decision=proposal.gate_decision,
                  gates_passed=proposal.status != EvolutionStatus.REJECTED)

        return proposal
```

---

### 3.4 Agent Execution Integration

**File**: `dharma_swarm/agent_runner.py`
**Strategy**: Wrap task execution in `AgentRunner`

**Key operation**: `_execute_task()`

```python
# dharma_swarm/agent_runner.py

async def _execute_task(self, task: Task) -> str:
    """Execute a single task and return result."""

    with jikoku_auto_span(
        category="execute.agent_task",
        intent=f"Agent {self.config.name} execute task {task.title}",
        metadata={
            'agent_id': self.config.name,
            'task_id': task.id,
            'priority': task.priority.value,
        }
    ) as span_id:
        # ... existing execution logic ...

        jikoku_end(span_id,
                  success=not _looks_like_provider_failure(result),
                  result_length=len(result))

        return result
```

---

## 4. Performance Overhead Control

### 4.1 Enable/Disable Mechanism

**Problem**: Always-on instrumentation could slow system in production
**Solution**: Global enable flag with negligible overhead when disabled

**Implementation**:

```python
# dharma_swarm/jikoku_instrumentation.py

import os
from contextlib import contextmanager

_JIKOKU_ENABLED = os.environ.get("JIKOKU_ENABLED", "1") == "1"

def _instrumentation_enabled() -> bool:
    """Check if JIKOKU instrumentation is enabled."""
    return _JIKOKU_ENABLED

def enable_instrumentation(enabled: bool = True) -> None:
    """Enable or disable JIKOKU instrumentation at runtime."""
    global _JIKOKU_ENABLED
    _JIKOKU_ENABLED = enabled

@contextmanager
def jikoku_auto_span(category: str, intent: str, **metadata):
    """Auto-span that no-ops when instrumentation disabled."""
    if not _JIKOKU_ENABLED:
        yield None
        return

    tracer = get_global_tracer()
    with tracer.span(category, intent, **metadata) as span_id:
        yield span_id
```

**Usage**:

```bash
# Disable instrumentation for production
export JIKOKU_ENABLED=0
dgc run

# Enable for profiling
export JIKOKU_ENABLED=1
dgc run
```

**Overhead when disabled**: ~1 conditional check per operation (nanoseconds)

---

### 4.2 Adaptive Sampling

**Problem**: Even with instrumentation on, 100% sampling may be too much
**Solution**: Sample spans based on configurable rate

```python
# dharma_swarm/jikoku_instrumentation.py

import random

_JIKOKU_SAMPLE_RATE = float(os.environ.get("JIKOKU_SAMPLE_RATE", "1.0"))

@contextmanager
def jikoku_auto_span(category: str, intent: str, **metadata):
    """Auto-span with adaptive sampling."""
    if not _JIKOKU_ENABLED:
        yield None
        return

    # Sample based on configured rate
    if random.random() > _JIKOKU_SAMPLE_RATE:
        yield None
        return

    tracer = get_global_tracer()
    with tracer.span(category, intent, **metadata) as span_id:
        yield span_id
```

**Usage**:

```bash
# Sample 10% of spans (lower overhead, still useful for trends)
export JIKOKU_SAMPLE_RATE=0.1
```

---

### 4.3 Observer Effect Measurement

**Strategy**: Measure JIKOKU's own overhead and include in kaizen report

```python
# dharma_swarm/jikoku_samaya.py

def kaizen_report(self, last_n_sessions: int = 7) -> Dict[str, Any]:
    """Generate kaizen report with observer effect measurement."""

    # ... existing report logic ...

    # Calculate JIKOKU overhead
    jikoku_spans = [s for s in spans if s.category.startswith('jikoku_')]
    jikoku_overhead = sum(s.duration_sec for s in jikoku_spans if s.duration_sec)

    report['jikoku_overhead_sec'] = jikoku_overhead
    report['jikoku_overhead_pct'] = (jikoku_overhead / total_duration * 100) if total_duration > 0 else 0

    return report
```

**Target**: Keep JIKOKU overhead < 1% of total compute time

---

## 5. Automatic Kaizen Loop

### 5.1 Trigger Strategy

**Goal**: Automatically generate kaizen reports and act on findings

**Triggers**:

1. **Time-based**: Every 7 sessions (as per protocol)
2. **Count-based**: Every 100 spans logged
3. **Manual**: `dgc kaizen` command
4. **Scheduled**: Cron job (already exists: `pulse.py` infrastructure)

**Implementation**:

```python
# dharma_swarm/jikoku_instrumentation.py

class JikokuKaizenEngine:
    """Automatic kaizen loop engine."""

    def __init__(self, trigger_every_n_sessions: int = 7):
        self.trigger_threshold = trigger_every_n_sessions
        self._sessions_since_last = 0

    async def check_and_run(self) -> dict | None:
        """Check if kaizen report should run, execute if so."""
        tracer = get_global_tracer()

        # Get unique session count
        if not tracer.log_path.exists():
            return None

        all_spans = []
        with open(tracer.log_path) as f:
            for line in f:
                all_spans.append(JikokuSpan.from_jsonl(line.strip()))

        unique_sessions = len(set(s.session_id for s in all_spans))

        if unique_sessions >= self._sessions_since_last + self.trigger_threshold:
            self._sessions_since_last = unique_sessions
            report = tracer.kaizen_report(last_n_sessions=self.trigger_threshold)
            await self._act_on_report(report)
            return report

        return None

    async def _act_on_report(self, report: dict) -> None:
        """Act on kaizen findings: create evolution proposals."""

        # Extract optimization targets (longest spans)
        targets = report.get('optimization_targets', [])[:3]

        for target in targets:
            # Create evolution proposal to optimize this span
            proposal_desc = (
                f"Optimize {target['category']} operation: {target['intent']}. "
                f"Current duration: {target['duration_sec']:.2f}s. "
                f"Target: reduce by 30%."
            )

            # This would integrate with DarwinEngine
            # await self._create_optimization_proposal(target, proposal_desc)

            logger.info("Kaizen target identified: %s", proposal_desc)
```

---

### 5.2 Integration with Evolution Engine

**Strategy**: Feed kaizen optimization targets into `DarwinEngine` as proposals

```python
# dharma_swarm/evolution.py

async def optimize_span_target(
    self,
    target: dict,  # From kaizen report
    reduction_goal_pct: float = 30.0,
) -> Proposal:
    """Create evolution proposal to optimize a slow span.

    Args:
        target: Optimization target from kaizen report with keys:
            - span_id, category, intent, duration_sec
        reduction_goal_pct: Target reduction percentage (default 30%)

    Returns:
        Proposal for optimizing the target span
    """

    # Infer component from span category
    component_map = {
        'api_call': 'providers.py',
        'execute.agent_spawn': 'swarm.py',
        'execute.evolution_gate': 'evolution.py',
        'file_op': 'archive.py',
    }
    component = component_map.get(target['category'], 'unknown')

    description = (
        f"Optimize {target['intent']} operation. "
        f"Current: {target['duration_sec']:.2f}s, "
        f"Target: {target['duration_sec'] * (1 - reduction_goal_pct/100):.2f}s "
        f"({reduction_goal_pct}% reduction)."
    )

    proposal = await self.propose(
        component=component,
        change_type="optimization",
        description=description,
        spec_ref=f"kaizen:{target['span_id']}",
        think_notes=(
            f"Kaizen analysis identified {target['intent']} as optimization target. "
            f"Current duration {target['duration_sec']:.2f}s is in top 10 slowest spans. "
            f"Possible optimizations: caching, parallelization, algorithmic improvement. "
            f"Risk: must preserve correctness while improving speed."
        )
    )

    return proposal
```

**Integration into swarm heartbeat**:

```python
# dharma_swarm/swarm.py

async def run(self, interval: float | None = None) -> None:
    """Run orchestration loop with JIKOKU kaizen automation."""

    from dharma_swarm.jikoku_instrumentation import JikokuKaizenEngine
    kaizen_engine = JikokuKaizenEngine(trigger_every_n_sessions=7)

    while self._running:
        # ... existing tick logic ...

        # Check for kaizen trigger
        kaizen_report = await kaizen_engine.check_and_run()
        if kaizen_report:
            logger.info(
                "Kaizen report generated: utilization=%.1f%%, pramāda=%.1f%%",
                kaizen_report['utilization_pct'],
                kaizen_report['idle_pct']
            )
```

---

## 6. Data Flow Architecture

### 6.1 Span Lifecycle

```
┌─────────────────┐
│  Operation      │  ←─── Function call (spawn_agent, LLM call, etc.)
│  Begins         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ jikoku_auto_span│  ←─── Check if enabled, sample decision
│  (entry)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JikokuTracer    │  ←─── Generate span_id, record ts_start
│  .start()       │
└────────┬────────┘
         │
         │  [Operation executes]
         │
         ▼
┌─────────────────┐
│ JikokuTracer    │  ←─── Calculate duration, merge metadata
│  .end()         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JSONL Append    │  ←─── Atomic write to JIKOKU_LOG.jsonl
│                 │
└────────┬────────┘
         │
         │  [On kaizen trigger]
         │
         ▼
┌─────────────────┐
│ Kaizen Report   │  ←─── Aggregate, analyze, generate targets
│  Generator      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Evolution       │  ←─── Create optimization proposals
│  Engine         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Self-Optimization│ ←─── System improves own efficiency
└─────────────────┘
```

---

### 6.2 Storage Format

**File**: `~/.dharma/jikoku/JIKOKU_LOG.jsonl`
**Format**: One JSON object per line (JSONL)

**Example entries**:

```jsonl
{"span_id":"session-001-span-1-1709856000000","category":"api_call","intent":"LLM call to Anthropic","ts_start":"2026-03-08T12:00:00.000000+00:00","ts_end":"2026-03-08T12:00:03.200000+00:00","duration_sec":3.2,"session_id":"session-001","agent_id":"coder","task_id":"task-123","metadata":{"provider":"Anthropic","model":"claude-opus-4","input_tokens":1200,"output_tokens":800}}
{"span_id":"session-001-span-2-1709856003500","category":"execute.agent_spawn","intent":"Spawn agent 'planner' (mechanistic)","ts_start":"2026-03-08T12:00:03.500000+00:00","ts_end":"2026-03-08T12:00:04.100000+00:00","duration_sec":0.6,"session_id":"session-001","agent_id":"planner","task_id":null,"metadata":{"role":"mechanistic","provider":"claude-code","thread":"mechanistic"}}
{"span_id":"session-001-span-3-1709856004200","category":"execute.evolution_gate","intent":"Gate check proposal prop-456","ts_start":"2026-03-08T12:00:04.200000+00:00","ts_end":"2026-03-08T12:00:04.250000+00:00","duration_sec":0.05,"session_id":"session-001","agent_id":null,"task_id":null,"metadata":{"proposal_id":"prop-456","component":"swarm.py","decision":"allow","gates_passed":true}}
```

---

## 7. Implementation Phases

### Phase 1: Core Instrumentation (Week 1)

**Goal**: Automatic span creation for all major operations
**Deliverables**:
1. Create `dharma_swarm/jikoku_instrumentation.py` module
2. Add `@jikoku_traced_provider` decorator
3. Apply decorator to all providers in `providers.py`
4. Add `jikoku_auto_span()` context manager to:
   - `swarm.py`: `spawn_agent()`, `create_task()`, `dispatch_next()`
   - `evolution.py`: `propose()`, `gate_check()`, `evaluate()`, `archive_result()`
   - `agent_runner.py`: `_execute_task()`
5. Test with `JIKOKU_ENABLED=1` and verify spans created

**Success criteria**:
- Run `dgc spawn agent test mechanistic`
- Run `dgc task "test task"`
- Check `~/.dharma/jikoku/JIKOKU_LOG.jsonl` for spans
- Verify all operations instrumented

---

### Phase 2: Performance Control (Week 2)

**Goal**: Zero-overhead disable and adaptive sampling
**Deliverables**:
1. Implement `_instrumentation_enabled()` check
2. Add `enable_instrumentation()` runtime toggle
3. Implement adaptive sampling with `JIKOKU_SAMPLE_RATE`
4. Add observer effect measurement to kaizen report
5. Benchmark overhead with instrumentation on/off

**Success criteria**:
- `JIKOKU_ENABLED=0`: overhead < 0.01%
- `JIKOKU_ENABLED=1`: overhead < 1%
- `JIKOKU_SAMPLE_RATE=0.1`: spans appear at ~10% rate

---

### Phase 3: Kaizen Automation (Week 3)

**Goal**: Automatic optimization proposal generation
**Deliverables**:
1. Create `JikokuKaizenEngine` class
2. Implement `check_and_run()` trigger logic
3. Add `optimize_span_target()` to `DarwinEngine`
4. Integrate kaizen engine into `swarm.run()` heartbeat
5. Add cron job for scheduled kaizen (use existing `pulse.py` infrastructure)

**Success criteria**:
- After 7 sessions, kaizen report auto-generated
- Optimization proposals created for top 3 targets
- Proposals appear in evolution archive

---

### Phase 4: Validation & Iteration (Week 4)

**Goal**: Real-world validation and tuning
**Deliverables**:
1. Run 10-session stress test with full instrumentation
2. Measure actual utilization improvement
3. Tune sampling rates and thresholds
4. Document findings in kaizen reports
5. Iterate on optimization proposals

**Success criteria**:
- Baseline utilization measured
- At least one optimization proposal implemented
- Measurable efficiency gain (even 1% proves system works)

---

## 8. Risk Analysis & Mitigation

### Risk 1: Observer Effect Too High

**Risk**: Instrumentation slows system enough to invalidate measurements
**Likelihood**: Medium
**Impact**: High (defeats purpose)
**Mitigation**:
- Benchmark early (Phase 2)
- Adaptive sampling (trade completeness for speed)
- Async-native spans (no blocking)
- Ability to fully disable (`JIKOKU_ENABLED=0`)

---

### Risk 2: Span Proliferation

**Risk**: Too many spans, log file grows too large
**Likelihood**: Medium
**Impact**: Medium (storage, analysis slowdown)
**Mitigation**:
- Category taxonomy limits span types
- Log rotation (keep last 30 days)
- Sampling reduces volume
- JSONL format compresses well (gzip)

---

### Risk 3: Kaizen Proposals Don't Improve

**Risk**: Auto-generated optimization proposals fail or make things worse
**Likelihood**: High (initially)
**Impact**: Low (no worse than manual proposals)
**Mitigation**:
- Proposals still go through telos gates (safety)
- Fitness evaluation catches regressions
- Human review on low-confidence proposals
- Iterative refinement (Reflexion pattern)

---

### Risk 4: Integration Complexity

**Risk**: Too many integration points, hard to maintain
**Likelihood**: Medium
**Impact**: Medium (tech debt)
**Mitigation**:
- All instrumentation in single module (`jikoku_instrumentation.py`)
- Consistent pattern (`jikoku_auto_span()` everywhere)
- Feature flag for rollback (`JIKOKU_ENABLED=0`)
- Comprehensive test coverage

---

## 9. Success Metrics

### 9.1 Technical Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Instrumentation coverage | 0% | 90% | % of operations with spans |
| Observer overhead | N/A | < 1% | Kaizen report `jikoku_overhead_pct` |
| Span completeness | N/A | > 95% | % spans with valid duration |
| Kaizen trigger accuracy | N/A | 100% | Triggers every 7 sessions |

### 9.2 Efficiency Metrics

| Metric | Baseline | Target (30 days) | Target (90 days) | Measurement |
|--------|----------|------------------|------------------|-------------|
| System utilization | ~5% | 15% | 30% | Kaizen report `utilization_pct` |
| Pramāda (idle) | ~95% | 85% | 70% | Kaizen report `idle_pct` |
| Efficiency gain | 1x | 3x | 6x | `50 / utilization_pct` |

**Path to 10x**: If we reach 30% utilization in 90 days, we're on track for 50% (10x) by end of year.

---

### 9.3 Kaizen Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Optimization proposals created | > 0 per week | Evolution archive count |
| Proposals implemented | > 1 per month | Archive status "applied" |
| Measurable speedup | > 0% per proposal | Before/after span duration |
| Proposal success rate | > 30% | Fitness > 0.6 after implementation |

---

## 10. Component Reference

### 10.1 New Modules

**`dharma_swarm/jikoku_instrumentation.py`** (NEW):
- `jikoku_auto_span()`: Context manager for auto-instrumentation
- `jikoku_traced_provider()`: Decorator for provider wrapping
- `JikokuKaizenEngine`: Automatic kaizen loop
- `enable_instrumentation()`: Runtime enable/disable
- `_instrumentation_enabled()`: Global flag check

### 10.2 Modified Modules

**`dharma_swarm/providers.py`**:
- Apply `@jikoku_traced_provider` to all providers

**`dharma_swarm/swarm.py`**:
- Wrap `spawn_agent()`, `create_task()`, `dispatch_next()` with `jikoku_auto_span()`
- Integrate `JikokuKaizenEngine` into `run()` loop

**`dharma_swarm/evolution.py`**:
- Wrap `propose()`, `gate_check()`, `evaluate()`, `archive_result()` with `jikoku_auto_span()`
- Add `optimize_span_target()` method

**`dharma_swarm/agent_runner.py`**:
- Wrap `_execute_task()` with `jikoku_auto_span()`

**`dharma_swarm/jikoku_samaya.py`**:
- Add observer effect measurement to `kaizen_report()`

**`dharma_swarm/dgc_cli.py`**:
- Add `dgc kaizen` command (already in integration guide, just implement)

---

## 11. Testing Strategy

### 11.1 Unit Tests

**New tests** (`tests/test_jikoku_instrumentation.py`):

```python
def test_auto_span_creates_span_when_enabled():
    """jikoku_auto_span creates span when JIKOKU_ENABLED=1"""
    enable_instrumentation(True)
    with jikoku_auto_span("test", "Test span"):
        pass
    spans = get_global_tracer().get_session_spans()
    assert len(spans) == 1

def test_auto_span_no_op_when_disabled():
    """jikoku_auto_span no-ops when JIKOKU_ENABLED=0"""
    enable_instrumentation(False)
    with jikoku_auto_span("test", "Test span"):
        pass
    spans = get_global_tracer().get_session_spans()
    assert len(spans) == 0

def test_traced_provider_captures_metadata():
    """@jikoku_traced_provider captures token/cost metadata"""
    # ... test provider decorator captures LLMResponse metadata

def test_kaizen_engine_triggers_on_threshold():
    """JikokuKaizenEngine triggers every N sessions"""
    # ... test trigger logic

def test_optimize_span_target_creates_proposal():
    """optimize_span_target creates valid proposal"""
    # ... test proposal generation from kaizen target
```

### 11.2 Integration Tests

**Scenario 1**: Full instrumentation smoke test

```python
async def test_full_instrumentation_smoke():
    """All major operations create spans"""
    enable_instrumentation(True)
    init_tracer()

    swarm = SwarmManager()
    await swarm.init()

    # Spawn agent (should create span)
    agent = await swarm.spawn_agent("test", AgentRole.MECHANISTIC)

    # Create task (should create span)
    task = await swarm.create_task("Test task")

    # Dispatch (should create span)
    await swarm.dispatch_next()

    # Check spans created
    spans = get_global_tracer().get_session_spans()
    categories = [s.category for s in spans]

    assert "execute.agent_spawn" in categories
    assert "execute.task_create" in categories
    assert "execute.orchestration_tick" in categories
```

**Scenario 2**: Kaizen loop integration

```python
async def test_kaizen_loop_creates_proposals():
    """Kaizen engine creates optimization proposals"""
    swarm = SwarmManager()
    await swarm.init()

    # Generate 7 sessions worth of spans (trigger threshold)
    for i in range(7):
        # ... create spans ...

    kaizen_engine = JikokuKaizenEngine()
    report = await kaizen_engine.check_and_run()

    assert report is not None
    assert 'optimization_targets' in report

    # Check proposals created in evolution archive
    entries = await swarm._engine.archive.list_all()
    optimization_proposals = [e for e in entries if e.change_type == "optimization"]
    assert len(optimization_proposals) > 0
```

---

## 12. Future Enhancements (Beyond v1.0)

### 12.1 Distributed Tracing

**Goal**: Track spans across agent boundaries (multi-agent tasks)
**Approach**: OpenTelemetry-compatible span propagation

### 12.2 Real-Time Dashboard

**Goal**: Live utilization monitoring
**Approach**: WebSocket server streaming kaizen metrics to TUI

### 12.3 Predictive Kaizen

**Goal**: Predict optimization opportunities before they become bottlenecks
**Approach**: ML model trained on span history

### 12.4 Cost Optimization

**Goal**: Track $ cost per operation, optimize for lowest cost/quality ratio
**Approach**: Add cost metadata to spans, kaizen report on cost targets

---

## 13. Conclusion

This architecture provides:

✅ **Automatic instrumentation**: Zero manual span wrapping required
✅ **Zero-overhead disable**: Production-safe with toggle
✅ **Adaptive sampling**: Tune observer effect
✅ **Automatic kaizen loop**: Self-optimization without human intervention
✅ **Evolution engine integration**: Optimization proposals auto-generated
✅ **Phased implementation**: 4 weeks to full deployment
✅ **Comprehensive testing**: Unit + integration coverage
✅ **Risk mitigation**: Every risk has mitigation strategy

**The promise**: 10x efficiency gain (5% → 50% utilization) with zero hardware cost.

**The path**: 4 phases, 30 days, measurable milestones.

**The difference from previous failure**: This is a complete, buildable specification. Not promises—provable architecture.

---

**JSCA!**

*End of JIKOKU SAMAYA Deep OS Integration Architecture v1.0*
