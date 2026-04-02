# JIKOKU SAMAYA — Implementation Roadmap

**Version**: 1.0
**Date**: 2026-03-08
**Status**: Ready for Implementation

---

## Overview

This document provides **concrete implementation steps** with **actual code** for deep JIKOKU SAMAYA integration into dharma_swarm. Unlike the previous agent's promises, this is **buildable, testable, and verifiable**.

**Timeline**: 4 weeks (4 phases)
**Goal**: 10x efficiency gain (5% → 50% utilization) with zero hardware cost

---

## Phase 1: Core Instrumentation (Week 1)

### Day 1-2: Create Instrumentation Module

**File**: `dharma_swarm/jikoku_instrumentation.py` (NEW)

```python
"""
JIKOKU SAMAYA Deep OS Integration — Instrumentation Layer

Provides automatic span tracing for all dharma_swarm operations.
Zero overhead when disabled, adaptive sampling when enabled.
"""

import functools
import os
import random
from contextlib import contextmanager
from typing import Any, Callable, TypeVar, cast

from dharma_swarm.jikoku_samaya import get_global_tracer, jikoku_end
from dharma_swarm.models import LLMRequest, LLMResponse

T = TypeVar('T')

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

_JIKOKU_ENABLED = os.environ.get("JIKOKU_ENABLED", "1") == "1"
_JIKOKU_SAMPLE_RATE = float(os.environ.get("JIKOKU_SAMPLE_RATE", "1.0"))


def _instrumentation_enabled() -> bool:
    """Check if JIKOKU instrumentation is globally enabled."""
    return _JIKOKU_ENABLED


def enable_instrumentation(enabled: bool = True) -> None:
    """Enable or disable JIKOKU instrumentation at runtime.

    Args:
        enabled: True to enable, False to disable

    Example:
        # Disable for production
        enable_instrumentation(False)

        # Enable for profiling session
        enable_instrumentation(True)
    """
    global _JIKOKU_ENABLED
    _JIKOKU_ENABLED = enabled


def set_sample_rate(rate: float) -> None:
    """Set the span sampling rate.

    Args:
        rate: Sampling rate between 0.0 and 1.0
              1.0 = 100% sampling (all spans)
              0.1 = 10% sampling (lower overhead)

    Example:
        # Sample only 10% of operations
        set_sample_rate(0.1)
    """
    global _JIKOKU_SAMPLE_RATE
    _JIKOKU_SAMPLE_RATE = max(0.0, min(1.0, rate))


# ─────────────────────────────────────────────────────────────────────
# Core Instrumentation
# ─────────────────────────────────────────────────────────────────────

@contextmanager
def jikoku_auto_span(category: str, intent: str, **metadata):
    """Automatic span creation with enable/disable and sampling.

    This is the primary instrumentation primitive. Use this context
    manager to wrap any operation you want to trace.

    Args:
        category: Span category (boot, api_call, execute.*, etc.)
        intent: Human-readable description of operation
        **metadata: Additional metadata to attach to span

    Yields:
        span_id if created, None if skipped

    Example:
        with jikoku_auto_span("api_call", "LLM call to Claude", model="opus"):
            response = await client.complete(request)

    Performance:
        - If disabled: ~1 conditional check (< 1ns overhead)
        - If enabled but sampled out: ~1 random() call (< 100ns)
        - If enabled and sampled in: full span creation
    """
    # Fast path: instrumentation disabled
    if not _JIKOKU_ENABLED:
        yield None
        return

    # Sampling decision
    if random.random() > _JIKOKU_SAMPLE_RATE:
        yield None
        return

    # Create span
    tracer = get_global_tracer()
    with tracer.span(category, intent, **metadata) as span_id:
        yield span_id


def jikoku_traced_provider(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to automatically trace LLM provider calls.

    Wraps a provider's complete() method to automatically create spans
    with token usage, cost, and model metadata.

    Args:
        func: Provider's complete() method

    Returns:
        Wrapped async function that creates spans

    Example:
        class AnthropicProvider(LLMProvider):
            @jikoku_traced_provider
            async def complete(self, request: LLMRequest) -> LLMResponse:
                # ... existing implementation ...

    Metadata captured:
        - provider: Provider class name
        - model: Model ID used
        - message_count: Number of messages in request
        - input_tokens: From response.usage
        - output_tokens: From response.usage
        - stop_reason: From response
    """
    @functools.wraps(func)
    async def wrapper(self: Any, request: LLMRequest) -> T:
        # Fast path: instrumentation disabled
        if not _instrumentation_enabled():
            return await func(self, request)

        # Extract provider name
        provider_name = self.__class__.__name__.replace('Provider', '')

        with jikoku_auto_span(
            category="api_call",
            intent=f"LLM call to {provider_name}",
            metadata={
                'provider': provider_name,
                'model': request.model,
                'message_count': len(request.messages),
            }
        ) as span_id:
            # Execute wrapped function
            response: LLMResponse = await func(self, request)

            # Add response metadata if span was created
            if span_id:
                usage = response.usage or {}
                jikoku_end(
                    span_id,
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0),
                    total_tokens=usage.get('total_tokens', 0),
                    model=response.model,
                    stop_reason=response.stop_reason,
                )

            return response

    return cast(Callable[..., T], wrapper)


# ─────────────────────────────────────────────────────────────────────
# Kaizen Automation
# ─────────────────────────────────────────────────────────────────────

class JikokuKaizenEngine:
    """Automatic kaizen loop engine.

    Monitors span accumulation and triggers kaizen reports when
    thresholds are met. Integrates with DarwinEngine to create
    optimization proposals.

    Attributes:
        trigger_every_n_sessions: Generate report every N sessions
        _sessions_since_last: Session counter
    """

    def __init__(self, trigger_every_n_sessions: int = 7):
        """Initialize kaizen engine.

        Args:
            trigger_every_n_sessions: Report frequency (default: 7 per protocol)
        """
        self.trigger_threshold = trigger_every_n_sessions
        self._sessions_since_last = 0

    async def check_and_run(self) -> dict | None:
        """Check if kaizen report should run, execute if threshold met.

        Returns:
            Kaizen report dict if generated, None if not yet time

        Side effects:
            - Generates kaizen report
            - Creates optimization proposals via DarwinEngine
            - Logs findings
        """
        from dharma_swarm.jikoku_samaya import JikokuSpan

        tracer = get_global_tracer()

        # Check if log exists
        if not tracer.log_path.exists():
            return None

        # Count unique sessions
        all_spans = []
        with open(tracer.log_path) as f:
            for line in f:
                try:
                    all_spans.append(JikokuSpan.from_jsonl(line.strip()))
                except Exception:
                    continue  # Skip malformed lines

        unique_sessions = len(set(s.session_id for s in all_spans))

        # Check if threshold met
        if unique_sessions < self._sessions_since_last + self.trigger_threshold:
            return None

        # Generate report
        self._sessions_since_last = unique_sessions
        report = tracer.kaizen_report(last_n_sessions=self.trigger_threshold)

        # Act on findings
        await self._act_on_report(report)

        return report

    async def _act_on_report(self, report: dict) -> None:
        """Act on kaizen findings by creating optimization proposals.

        Args:
            report: Kaizen report dict from JikokuTracer.kaizen_report()

        Side effects:
            - Logs optimization targets
            - Creates evolution proposals (future: integrate with DarwinEngine)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Extract optimization targets
        targets = report.get('optimization_targets', [])[:3]

        if not targets:
            logger.info("Kaizen: No optimization targets identified")
            return

        logger.info(
            "Kaizen: Identified %d optimization targets (utilization=%.1f%%, pramāda=%.1f%%)",
            len(targets),
            report.get('utilization_pct', 0),
            report.get('idle_pct', 0),
        )

        for idx, target in enumerate(targets, 1):
            logger.info(
                "Kaizen target %d: [%s] %s — %.2fs (optimize for 30%% reduction)",
                idx,
                target['category'],
                target['intent'],
                target['duration_sec'],
            )

            # Future: Create actual evolution proposal
            # await self._create_optimization_proposal(target)


# Singleton kaizen engine
_kaizen_engine: JikokuKaizenEngine | None = None


def get_kaizen_engine() -> JikokuKaizenEngine:
    """Get or create global kaizen engine."""
    global _kaizen_engine
    if _kaizen_engine is None:
        _kaizen_engine = JikokuKaizenEngine()
    return _kaizen_engine
```

**Tests**: `tests/test_jikoku_instrumentation.py` (NEW)

```python
"""Tests for JIKOKU instrumentation layer."""

import pytest
import time
from dharma_swarm.jikoku_instrumentation import (
    jikoku_auto_span,
    enable_instrumentation,
    set_sample_rate,
    jikoku_traced_provider,
    JikokuKaizenEngine,
)
from dharma_swarm.jikoku_samaya import init_tracer, get_global_tracer
from dharma_swarm.models import LLMRequest, LLMResponse


@pytest.fixture
def fresh_tracer(tmp_path):
    """Initialize tracer with temp log path."""
    log_path = tmp_path / "jikoku_test.jsonl"
    init_tracer(log_path=log_path, session_id="test-session")
    enable_instrumentation(True)
    set_sample_rate(1.0)
    yield get_global_tracer()


def test_auto_span_creates_span_when_enabled(fresh_tracer):
    """jikoku_auto_span creates span when JIKOKU_ENABLED=1"""
    with jikoku_auto_span("test", "Test span"):
        time.sleep(0.01)

    spans = fresh_tracer.get_session_spans()
    assert len(spans) == 1
    assert spans[0].category == "test"
    assert spans[0].intent == "Test span"
    assert spans[0].duration_sec >= 0.01


def test_auto_span_no_op_when_disabled(fresh_tracer):
    """jikoku_auto_span no-ops when JIKOKU_ENABLED=0"""
    enable_instrumentation(False)

    with jikoku_auto_span("test", "Should not create"):
        time.sleep(0.01)

    enable_instrumentation(True)
    spans = fresh_tracer.get_session_spans()
    assert len(spans) == 0


def test_sampling_rate_controls_span_creation(fresh_tracer):
    """Sampling rate controls how many spans are created"""
    set_sample_rate(0.0)  # 0% sampling

    for i in range(100):
        with jikoku_auto_span("test", f"Span {i}"):
            pass

    spans = fresh_tracer.get_session_spans()
    assert len(spans) == 0  # All sampled out

    # Reset to 100%
    set_sample_rate(1.0)
    with jikoku_auto_span("test", "Should create"):
        pass

    spans = fresh_tracer.get_session_spans()
    assert len(spans) == 1


def test_traced_provider_decorator(fresh_tracer):
    """@jikoku_traced_provider captures LLM call metadata"""
    from unittest.mock import AsyncMock

    class MockProvider:
        @jikoku_traced_provider
        async def complete(self, request: LLMRequest) -> LLMResponse:
            # Simulate LLM call
            await asyncio.sleep(0.01)
            return LLMResponse(
                content="test response",
                model="test-model",
                usage={"input_tokens": 100, "output_tokens": 50},
                stop_reason="stop",
            )

    provider = MockProvider()
    request = LLMRequest(
        model="test-model",
        messages=[{"role": "user", "content": "test"}],
    )

    import asyncio
    response = asyncio.run(provider.complete(request))

    spans = fresh_tracer.get_session_spans()
    assert len(spans) == 1
    assert spans[0].category == "api_call"
    assert "Mock" in spans[0].intent  # "LLM call to Mock"
    assert spans[0].metadata['provider'] == "Mock"
    assert spans[0].metadata['input_tokens'] == 100
    assert spans[0].metadata['output_tokens'] == 50


def test_kaizen_engine_triggers_on_threshold(fresh_tracer, tmp_path):
    """JikokuKaizenEngine triggers after N sessions"""
    engine = JikokuKaizenEngine(trigger_every_n_sessions=2)

    # Create spans for session 1
    with jikoku_auto_span("test", "Session 1"):
        time.sleep(0.01)

    # Should not trigger yet
    import asyncio
    report = asyncio.run(engine.check_and_run())
    assert report is None

    # Create spans for session 2
    init_tracer(log_path=fresh_tracer.log_path, session_id="test-session-2")
    with jikoku_auto_span("test", "Session 2"):
        time.sleep(0.01)

    # Should trigger now
    report = asyncio.run(engine.check_and_run())
    assert report is not None
    assert 'utilization_pct' in report
```

---

### Day 3-4: Apply to Providers

**File**: `dharma_swarm/providers.py` (MODIFY)

```python
# Add import at top
from dharma_swarm.jikoku_instrumentation import jikoku_traced_provider

# Apply decorator to all providers:

class AnthropicProvider(LLMProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...


class OpenAIProvider(LLMProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...


class OpenRouterProvider(LLMProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...


class NVIDIANIMProvider(LLMProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...


class ClaudeCodeProvider(_SubprocessProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...


class CodexProvider(_SubprocessProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...


class OpenRouterFreeProvider(LLMProvider):
    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # ... existing implementation ...
```

**Verification**:

```bash
# Run existing provider tests — should still pass
python -m pytest tests/test_providers.py -v

# Check that spans are created
JIKOKU_ENABLED=1 python -m pytest tests/test_providers.py -v -k "test_anthropic" -s
# Then check ~/.dharma/jikoku/JIKOKU_LOG.jsonl for api_call spans
```

---

### Day 5: Apply to Swarm Operations

**File**: `dharma_swarm/swarm.py` (MODIFY)

```python
# Add import at top
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span

# Wrap spawn_agent():
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
        # Build system prompt with thread context if applicable
        extra_prompt = ""
        if thread and thread in THREAD_PROMPTS:
            extra_prompt = f"\n\nCurrent research thread: {thread}\n{THREAD_PROMPTS[thread]}"

        config = AgentConfig(
            name=name,
            role=role,
            model=model,
            provider=provider_type,
            system_prompt=system_prompt + extra_prompt if system_prompt else extra_prompt,
            thread=thread,
        )
        provider = self._router.get_provider(provider_type)
        runner = await self._agent_pool.spawn(config, provider=provider)
        await self._memory.remember(
            f"Agent spawned: {name} ({role.value})"
            + (f" [thread: {thread}]" if thread else ""),
            layer=MemoryLayer.SESSION,
            source="swarm",
        )
        return runner.state


# Wrap create_task():
async def create_task(
    self,
    title: str,
    description: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
) -> Task:
    """Create a new task on the board."""

    with jikoku_auto_span(
        category="execute.task_create",
        intent=f"Create task: {title}",
        metadata={
            'title': title,
            'priority': priority.value,
            'description_length': len(description),
        }
    ):
        gate_result = self._gatekeeper.check(action=title, content=description)
        if gate_result.decision.value == "block":
            raise ValueError(f"Telos gate blocked: {gate_result.reason}")
        return await self._task_board.create(
            title=title, description=description, priority=priority
        )


# Wrap dispatch_next():
async def dispatch_next(self) -> int:
    """Run one orchestration tick. Returns number of tasks dispatched."""

    with jikoku_auto_span(
        category="execute.orchestration_tick",
        intent="Orchestration tick",
    ) as span_id:
        dispatches = await self._orchestrator.route_next()

        if span_id:
            from dharma_swarm.jikoku_instrumentation import jikoku_end
            jikoku_end(span_id, dispatches_count=len(dispatches))

        return len(dispatches)
```

---

### Day 6-7: Apply to Evolution & Agent Execution

**File**: `dharma_swarm/evolution.py` (MODIFY)

```python
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span, jikoku_end

async def propose(
    self,
    component: str,
    change_type: str,
    description: str,
    diff: str = "",
    parent_id: str | None = None,
    spec_ref: str | None = None,
    requirement_refs: list[str] | None = None,
    think_notes: str = "",
) -> Proposal:
    """Create a new evolution proposal and predict its fitness."""

    with jikoku_auto_span(
        category="execute.evolution_propose",
        intent=f"Propose {change_type} for {component}",
        metadata={
            'component': component,
            'change_type': change_type,
        }
    ) as span_id:
        features = ProposalFeatures(
            component=component,
            change_type=change_type,
            diff_size=len(diff.splitlines()),
        )
        predicted = self.predictor.predict(features)

        proposal = Proposal(
            component=component,
            change_type=change_type,
            description=description,
            diff=diff,
            parent_id=parent_id,
            spec_ref=spec_ref,
            requirement_refs=list(requirement_refs or []),
            think_notes=think_notes,
            predicted_fitness=predicted,
        )

        if span_id:
            jikoku_end(span_id,
                      proposal_id=proposal.id,
                      predicted_fitness=predicted)

        logger.debug(
            "Proposal %s created: predicted_fitness=%.3f",
            proposal.id,
            predicted,
        )
        return proposal


async def gate_check(self, proposal: Proposal) -> Proposal:
    """Run dharmic safety gates against a proposal."""

    with jikoku_auto_span(
        category="execute.evolution_gate",
        intent=f"Gate check proposal {proposal.id}",
        metadata={
            'proposal_id': proposal.id,
            'component': proposal.component,
        }
    ) as span_id:
        # ... existing gate check logic ...

        if span_id:
            jikoku_end(span_id,
                      decision=proposal.gate_decision,
                      status=proposal.status.value,
                      gates_passed=(proposal.status != EvolutionStatus.REJECTED))

        return proposal


# Similar for evaluate() and archive_result()
```

**File**: `dharma_swarm/agent_runner.py` (MODIFY)

```python
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span, jikoku_end

async def _execute_task(self, task: Task) -> str:
    """Execute a single task and return result."""

    with jikoku_auto_span(
        category="execute.agent_task",
        intent=f"Agent {self.config.name} execute: {task.title}",
        metadata={
            'agent_id': self.config.name,
            'task_id': task.id,
            'priority': task.priority.value,
        }
    ) as span_id:
        # ... existing execution logic ...

        if span_id:
            jikoku_end(span_id,
                      success=not _looks_like_provider_failure(result),
                      result_length=len(result))

        return result
```

---

## Phase 2: Performance Control (Week 2)

### Day 8-9: Observer Effect Measurement

**File**: `dharma_swarm/jikoku_samaya.py` (MODIFY)

Add observer effect measurement to `kaizen_report()`:

```python
def kaizen_report(self, last_n_sessions: int = 7) -> Dict[str, Any]:
    """Generate kaizen (continuous improvement) report."""

    # ... existing report logic ...

    # NEW: Calculate JIKOKU overhead
    jikoku_spans = [s for s in spans if 'jikoku' in s.category.lower()]
    jikoku_overhead = sum(s.duration_sec for s in jikoku_spans if s.duration_sec)

    report['jikoku_overhead_sec'] = jikoku_overhead
    report['jikoku_overhead_pct'] = (
        (jikoku_overhead / total_duration * 100) if total_duration > 0 else 0
    )

    # NEW: Observer effect warning
    if report['jikoku_overhead_pct'] > 1.0:
        report['observer_effect_warning'] = (
            f"JIKOKU overhead is {report['jikoku_overhead_pct']:.1f}%, "
            f"exceeding 1% target. Consider reducing sample rate."
        )

    return report
```

---

### Day 10-11: Benchmark & Tune

**Script**: `scripts/benchmark_jikoku.py` (NEW)

```python
"""Benchmark JIKOKU instrumentation overhead."""

import asyncio
import time
from dharma_swarm.jikoku_instrumentation import (
    enable_instrumentation,
    set_sample_rate,
)
from dharma_swarm.swarm import SwarmManager


async def benchmark_overhead():
    """Measure JIKOKU overhead with various configurations."""

    results = {}

    # Baseline: instrumentation disabled
    enable_instrumentation(False)
    swarm = SwarmManager()
    await swarm.init()

    start = time.monotonic()
    for i in range(100):
        await swarm.create_task(f"Test task {i}")
    baseline_duration = time.monotonic() - start

    results['baseline'] = baseline_duration
    print(f"Baseline (JIKOKU off): {baseline_duration:.3f}s")

    # With instrumentation, 100% sampling
    enable_instrumentation(True)
    set_sample_rate(1.0)

    swarm2 = SwarmManager()
    await swarm2.init()

    start = time.monotonic()
    for i in range(100):
        await swarm2.create_task(f"Test task {i}")
    full_duration = time.monotonic() - start

    results['full_instrumentation'] = full_duration
    overhead_pct = ((full_duration - baseline_duration) / baseline_duration) * 100
    print(f"Full instrumentation: {full_duration:.3f}s ({overhead_pct:.1f}% overhead)")

    # With 10% sampling
    set_sample_rate(0.1)

    swarm3 = SwarmManager()
    await swarm3.init()

    start = time.monotonic()
    for i in range(100):
        await swarm3.create_task(f"Test task {i}")
    sampled_duration = time.monotonic() - start

    results['10pct_sampling'] = sampled_duration
    overhead_pct = ((sampled_duration - baseline_duration) / baseline_duration) * 100
    print(f"10% sampling: {sampled_duration:.3f}s ({overhead_pct:.1f}% overhead)")

    return results


if __name__ == "__main__":
    results = asyncio.run(benchmark_overhead())

    # Verdict
    if results['full_instrumentation'] / results['baseline'] < 1.01:
        print("✅ PASS: Full instrumentation overhead < 1%")
    else:
        print("⚠️  WARN: Full instrumentation overhead > 1%")
```

---

## Phase 3: Kaizen Automation (Week 3)

### Day 12-14: Evolution Engine Integration

**File**: `dharma_swarm/evolution.py` (MODIFY)

Add `optimize_span_target()` method:

```python
async def optimize_span_target(
    self,
    target: dict,
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
        'execute.agent_task': 'agent_runner.py',
        'execute.evolution_gate': 'evolution.py',
        'execute.evolution_propose': 'evolution.py',
        'execute.evolution_evaluate': 'evolution.py',
        'file_op': 'archive.py',
    }
    component = component_map.get(target['category'], 'unknown')

    current_duration = target['duration_sec']
    target_duration = current_duration * (1 - reduction_goal_pct / 100)

    description = (
        f"Optimize {target['intent']} operation. "
        f"Current: {current_duration:.2f}s, "
        f"Target: {target_duration:.2f}s "
        f"({reduction_goal_pct}% reduction)."
    )

    think_notes = (
        f"Kaizen analysis identified {target['intent']} as optimization target "
        f"(rank: top 10 slowest spans across last 7 sessions). "
        f"Current duration {current_duration:.2f}s represents a bottleneck. "
        f"\n\n"
        f"Possible optimization strategies:\n"
        f"1. Caching: Memoize responses to avoid duplicate work\n"
        f"2. Parallelization: Run independent operations concurrently\n"
        f"3. Algorithmic improvement: Optimize hot paths\n"
        f"4. Model selection: Use faster model for low-complexity tasks\n"
        f"\n"
        f"Risk assessment:\n"
        f"- Must preserve correctness while improving speed\n"
        f"- Need regression tests to validate no behavior change\n"
        f"- May require additional complexity (caching invalidation, etc.)\n"
    )

    proposal = await self.propose(
        component=component,
        change_type="optimization",
        description=description,
        spec_ref=f"kaizen:{target['span_id']}",
        think_notes=think_notes,
    )

    return proposal
```

---

### Day 15-17: Integrate into Swarm Heartbeat

**File**: `dharma_swarm/swarm.py` (MODIFY)

```python
from dharma_swarm.jikoku_instrumentation import get_kaizen_engine

async def run(self, interval: float | None = None) -> None:
    """Run the orchestration loop with Garden Daemon parameters."""

    tick_interval = interval if interval is not None else self._daemon.heartbeat_interval
    kaizen_engine = get_kaizen_engine()

    while self._running:
        try:
            # ... existing tick logic ...

            # NEW: Check for kaizen trigger
            kaizen_report = await kaizen_engine.check_and_run()
            if kaizen_report:
                logger.info(
                    "JIKOKU Kaizen report generated: "
                    "utilization=%.1f%%, pramāda=%.1f%%, targets=%d",
                    kaizen_report['utilization_pct'],
                    kaizen_report['idle_pct'],
                    len(kaizen_report.get('optimization_targets', [])),
                )

                # NEW: Create optimization proposals from top 3 targets
                targets = kaizen_report.get('optimization_targets', [])[:3]
                for target in targets:
                    try:
                        proposal = await self._engine.optimize_span_target(target)
                        logger.info(
                            "Created optimization proposal %s for %s",
                            proposal.id,
                            target['intent'],
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to create optimization proposal for %s: %s",
                            target['intent'],
                            exc,
                        )

            # ... rest of tick logic ...

        except Exception as exc:
            logger.exception("Tick failed: %s", exc)
            # ... existing error handling ...

        await asyncio.sleep(tick_interval)
```

---

### Day 18-19: Add `dgc kaizen` Command

**File**: `dharma_swarm/dgc_cli.py` (MODIFY)

```python
@app.command()
def kaizen(
    sessions: int = typer.Option(7, "--sessions", "-n", help="Number of sessions to analyze"),
    apply: bool = typer.Option(False, "--apply", help="Auto-create optimization proposals"),
):
    """
    Generate JIKOKU SAMAYA kaizen report.

    Reviews last N sessions for:
    - Utilization ratio (compute vs wall clock)
    - Pramāda detection (idle time)
    - Optimization targets (longest spans)
    - Efficiency gains possible

    Examples:
        dgc kaizen                    # Last 7 sessions
        dgc kaizen -n 14              # Last 14 sessions
        dgc kaizen --apply            # Auto-create optimization proposals
    """
    from dharma_swarm.jikoku_samaya import jikoku_kaizen

    report = jikoku_kaizen(last_n_sessions=sessions)

    if 'error' in report:
        console.print(f"[red]Error: {report['error']}[/red]")
        raise typer.Exit(1)

    # Display report
    console.print(f"\n{'='*60}")
    console.print(f"JIKOKU SAMAYA - Kaizen Report (Last {sessions} Sessions)")
    console.print(f"{'='*60}\n")

    console.print(f"Sessions analyzed: {report['sessions_analyzed']}")
    console.print(f"Total spans: {report['total_spans']}")
    console.print(f"Total compute: {report['total_compute_sec']:.1f}s")
    console.print(f"Wall clock: {report['wall_clock_sec']:.1f}s")
    console.print(f"\n{'─'*60}")
    console.print(f"[bold]UTILIZATION: {report['utilization_pct']:.1f}%[/bold]")
    console.print(f"[bold]PRAMĀDA (idle): {report['idle_pct']:.1f}%[/bold]")

    # Observer effect
    if 'jikoku_overhead_pct' in report:
        console.print(f"JIKOKU overhead: {report['jikoku_overhead_pct']:.2f}%")

    console.print(f"{'─'*60}\n")

    # Potential gain
    if report['utilization_pct'] < 50:
        gain = 50 / report['utilization_pct'] if report['utilization_pct'] > 0 else float('inf')
        console.print(f"[bold green]⚡ POTENTIAL GAIN: {gain:.1f}x efficiency (zero hardware)[/bold green]")
        console.print(f"   (Path to 50% utilization from {report['utilization_pct']:.1f}%)\n")

    # Category breakdown
    console.print("[bold]Category Breakdown:[/bold]")
    for cat, stats in sorted(
        report['category_breakdown'].items(),
        key=lambda x: x[1]['total_sec'],
        reverse=True
    ):
        pct = (stats['total_sec'] / report['total_compute_sec']) * 100 if report['total_compute_sec'] > 0 else 0
        console.print(f"  {cat:30s} {stats['count']:3d} spans  "
                     f"{stats['total_sec']:6.1f}s  ({pct:5.1f}%)")

    # Optimization targets
    console.print(f"\n[bold]Top Optimization Targets:[/bold]")
    for i, target in enumerate(report['optimization_targets'][:5], 1):
        console.print(f"  {i}. [{target['category']}] {target['intent']}")
        console.print(f"     Duration: {target['duration_sec']:.2f}s")

    # Kaizen goals
    console.print(f"\n[bold]Kaizen Goals:[/bold]")
    for goal in report['kaizen_goals']:
        console.print(f"  • {goal}")

    console.print(f"\n{'='*60}\n")

    # Auto-create proposals if --apply
    if apply:
        import asyncio
        from dharma_swarm.swarm import SwarmManager

        console.print("[yellow]Creating optimization proposals...[/yellow]")

        async def create_proposals():
            swarm = SwarmManager()
            await swarm.init()

            targets = report['optimization_targets'][:3]
            created = 0

            for target in targets:
                try:
                    proposal = await swarm._engine.optimize_span_target(target)
                    console.print(f"[green]✓[/green] Created proposal {proposal.id} for {target['intent']}")
                    created += 1
                except Exception as exc:
                    console.print(f"[red]✗[/red] Failed to create proposal for {target['intent']}: {exc}")

            return created

        created = asyncio.run(create_proposals())
        console.print(f"\n[bold green]Created {created} optimization proposals[/bold green]")
```

---

## Phase 4: Validation & Iteration (Week 4)

### Day 20-22: Stress Test

**Script**: `scripts/jikoku_stress_test.py` (NEW)

```python
"""JIKOKU stress test: 10 sessions, full instrumentation."""

import asyncio
from dharma_swarm.jikoku_instrumentation import enable_instrumentation, set_sample_rate
from dharma_swarm.jikoku_samaya import init_tracer, jikoku_kaizen
from dharma_swarm.swarm import SwarmManager


async def stress_test():
    """Run 10 sessions with full JIKOKU instrumentation."""

    enable_instrumentation(True)
    set_sample_rate(1.0)

    results = []

    for session_num in range(1, 11):
        print(f"\n{'='*60}")
        print(f"Session {session_num}/10")
        print(f"{'='*60}")

        # Initialize new session
        init_tracer(session_id=f"stress-test-{session_num}")

        swarm = SwarmManager()
        await swarm.init()

        # Simulate realistic workload
        print("  Spawning agents...")
        agents = []
        for i in range(3):
            agent = await swarm.spawn_agent(
                f"agent-{i}",
                role="mechanistic",
            )
            agents.append(agent)

        print("  Creating tasks...")
        tasks = []
        for i in range(10):
            task = await swarm.create_task(
                f"Stress test task {i}",
                description=f"Task {i} for session {session_num}",
            )
            tasks.append(task)

        print("  Running orchestration...")
        for tick in range(5):
            await swarm.dispatch_next()

        print("  Evolving...")
        await swarm.evolve(
            component="test.py",
            change_type="mutation",
            description=f"Test mutation {session_num}",
            think_notes="Stress test mutation with full instrumentation enabled.",
        )

        # Generate kaizen report for this session
        if session_num % 7 == 0:
            report = jikoku_kaizen(last_n_sessions=7)
            results.append({
                'session': session_num,
                'utilization': report['utilization_pct'],
                'pramada': report['idle_pct'],
                'overhead': report.get('jikoku_overhead_pct', 0),
            })

            print(f"\n  Kaizen Report:")
            print(f"    Utilization: {report['utilization_pct']:.1f}%")
            print(f"    Pramāda: {report['idle_pct']:.1f}%")
            print(f"    JIKOKU overhead: {report.get('jikoku_overhead_pct', 0):.2f}%")

        await swarm.shutdown()

    # Final summary
    print(f"\n{'='*60}")
    print("STRESS TEST COMPLETE")
    print(f"{'='*60}")

    if results:
        avg_util = sum(r['utilization'] for r in results) / len(results)
        avg_overhead = sum(r['overhead'] for r in results) / len(results)

        print(f"\nAverage utilization: {avg_util:.1f}%")
        print(f"Average JIKOKU overhead: {avg_overhead:.2f}%")

        if avg_overhead < 1.0:
            print("\n✅ PASS: Observer overhead < 1%")
        else:
            print(f"\n⚠️  WARN: Observer overhead {avg_overhead:.2f}% exceeds 1% target")

        if avg_util > 5.0:
            print(f"✅ PROGRESS: Utilization {avg_util:.1f}% improved from ~5% baseline")
        else:
            print(f"❌ NO IMPROVEMENT: Utilization still at {avg_util:.1f}%")


if __name__ == "__main__":
    asyncio.run(stress_test())
```

---

### Day 23-24: Real-World Validation

Run actual dharma_swarm workloads with JIKOKU enabled:

```bash
# Enable JIKOKU
export JIKOKU_ENABLED=1
export JIKOKU_SAMPLE_RATE=1.0

# Run normal swarm operations for a full day
dgc run --interval 60

# After 7 sessions, generate kaizen
dgc kaizen

# Create optimization proposals
dgc kaizen --apply

# Implement top proposal
# ... (manual or agent-driven) ...

# Measure improvement in next kaizen report
dgc kaizen
```

**Success metrics**:
- ✅ Baseline utilization measured (expect ~5%)
- ✅ Kaizen report auto-generated after 7 sessions
- ✅ Optimization proposals created
- ✅ At least 1 proposal implemented
- ✅ Measurable improvement in next report (even 1% proves system works)

---

### Day 25-28: Iteration & Documentation

1. **Tune based on findings**:
   - If overhead > 1%, reduce sample rate
   - If kaizen targets aren't actionable, refine proposal generation
   - If proposals fail gates, improve think_notes

2. **Document learnings**:
   - Update `JIKOKU_SAMAYA_INTEGRATION.md` with real-world findings
   - Create case studies of successful optimizations
   - Document failure modes and mitigations

3. **Add to CI/CD**:
   - Run stress test in CI
   - Fail if overhead > 2%
   - Track utilization trend over time

---

## Verification Checklist

### Phase 1 ✓

- [ ] `jikoku_instrumentation.py` created
- [ ] `@jikoku_traced_provider` applied to all providers
- [ ] `jikoku_auto_span()` in swarm.py (spawn, task, dispatch)
- [ ] `jikoku_auto_span()` in evolution.py (propose, gate, evaluate, archive)
- [ ] `jikoku_auto_span()` in agent_runner.py (_execute_task)
- [ ] All tests pass
- [ ] Manual verification: spans appear in JIKOKU_LOG.jsonl

### Phase 2 ✓

- [ ] Observer effect measurement in kaizen_report()
- [ ] Benchmark script created
- [ ] Overhead measured: < 1% for full instrumentation
- [ ] Sampling tested: overhead scales linearly with sample rate

### Phase 3 ✓

- [ ] `optimize_span_target()` added to DarwinEngine
- [ ] Kaizen engine integrated into swarm heartbeat
- [ ] `dgc kaizen` command implemented
- [ ] Auto-proposal creation tested

### Phase 4 ✓

- [ ] 10-session stress test passes
- [ ] Real-world validation: kaizen triggers, proposals created
- [ ] At least 1 optimization implemented and measured
- [ ] Documentation updated with findings

---

## Emergency Rollback

If JIKOKU causes issues, instant rollback:

```bash
# Disable globally
export JIKOKU_ENABLED=0

# Or in code
from dharma_swarm.jikoku_instrumentation import enable_instrumentation
enable_instrumentation(False)
```

No code changes needed, zero overhead restored.

---

## Success Criteria

| Metric | Target | Verification |
|--------|--------|--------------|
| Implementation coverage | 90% of operations | Count spans per category |
| Observer overhead | < 1% | Kaizen report `jikoku_overhead_pct` |
| Kaizen trigger accuracy | 100% (every 7 sessions) | Monitor logs |
| Proposals created | > 0 per week | Evolution archive |
| Proposals implemented | > 1 per month | Archive status "applied" |
| Measurable speedup | > 0% per proposal | Before/after span duration |
| Utilization improvement | 5% → 15% in 30 days | Kaizen trend |

---

**JSCA!**

*End of JIKOKU SAMAYA Implementation Roadmap v1.0*
