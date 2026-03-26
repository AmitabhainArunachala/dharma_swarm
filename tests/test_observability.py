"""Tests for dharma_swarm.observability — Langfuse + local JSONL tracing."""

from __future__ import annotations

import json
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dharma_swarm.observability import (
    LocalTraceStore,
    SwarmObserver,
    TraceSpan,
    _estimate_cost,
    _new_id,
    get_observer,
)


# ---------------------------------------------------------------------------
# TraceSpan serialization
# ---------------------------------------------------------------------------


class TestTraceSpan:
    def test_roundtrip_jsonl(self) -> None:
        span = TraceSpan(
            trace_id="trace_abc",
            span_id="span_123",
            parent_span_id="span_000",
            name="test_span",
            kind="llm_call",
            status="ok",
            start_time="2026-03-25T00:00:00+00:00",
            end_time="2026-03-25T00:00:01+00:00",
            duration_ms=1000.0,
            attributes={"agent": "vajra", "model": "llama-3.3-70b"},
        )
        line = span.to_jsonl()
        restored = TraceSpan.from_jsonl(line)
        assert restored.trace_id == span.trace_id
        assert restored.span_id == span.span_id
        assert restored.parent_span_id == span.parent_span_id
        assert restored.name == span.name
        assert restored.kind == span.kind
        assert restored.status == span.status
        assert restored.duration_ms == span.duration_ms
        assert restored.attributes["agent"] == "vajra"
        assert restored.attributes["model"] == "llama-3.3-70b"

    def test_from_jsonl_ignores_extra_keys(self) -> None:
        data = {
            "trace_id": "t1",
            "span_id": "s1",
            "name": "test",
            "kind": "agent_dispatch",
            "status": "ok",
            "start_time": "",
            "end_time": "",
            "duration_ms": 0.0,
            "attributes": {},
            "parent_span_id": "",
            "totally_unknown_field": "should be ignored",
        }
        span = TraceSpan.from_jsonl(json.dumps(data))
        assert span.trace_id == "t1"
        assert not hasattr(span, "totally_unknown_field") or "totally_unknown_field" not in span.__dataclass_fields__


# ---------------------------------------------------------------------------
# LocalTraceStore
# ---------------------------------------------------------------------------


class TestLocalTraceStore:
    def test_write_and_read_spans(self, tmp_path: Path) -> None:
        store = LocalTraceStore(tmp_path)
        span = TraceSpan(
            trace_id="t1",
            span_id="s1",
            name="agent_dispatch:vajra",
            kind="agent_dispatch",
            status="ok",
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=datetime.now(timezone.utc).isoformat(),
            duration_ms=42.5,
            attributes={"agent": "vajra", "task_id": "task_001"},
        )
        store.write_span(span)

        results = store.get_spans()
        assert len(results) == 1
        assert results[0].trace_id == "t1"
        assert results[0].attributes["agent"] == "vajra"

    def test_filter_by_agent(self, tmp_path: Path) -> None:
        store = LocalTraceStore(tmp_path)
        for i, agent in enumerate(["vajra", "leela", "vajra"]):
            store.write_span(TraceSpan(
                trace_id=f"t{i}",
                span_id=f"s{i}",
                name=f"dispatch:{agent}",
                kind="agent_dispatch",
                status="ok",
                start_time=datetime.now(timezone.utc).isoformat(),
                attributes={"agent": agent},
            ))

        vajra_spans = store.get_spans(agent="vajra")
        assert len(vajra_spans) == 2
        leela_spans = store.get_spans(agent="leela")
        assert len(leela_spans) == 1

    def test_filter_by_kind(self, tmp_path: Path) -> None:
        store = LocalTraceStore(tmp_path)
        store.write_span(TraceSpan(
            trace_id="t1", span_id="s1", name="llm", kind="llm_call",
            status="ok", start_time=datetime.now(timezone.utc).isoformat(),
            attributes={},
        ))
        store.write_span(TraceSpan(
            trace_id="t2", span_id="s2", name="evo", kind="evolution",
            status="ok", start_time=datetime.now(timezone.utc).isoformat(),
            attributes={},
        ))

        assert len(store.get_spans(kind="llm_call")) == 1
        assert len(store.get_spans(kind="evolution")) == 1
        assert len(store.get_spans(kind="nonexistent")) == 0

    def test_filter_by_status(self, tmp_path: Path) -> None:
        store = LocalTraceStore(tmp_path)
        store.write_span(TraceSpan(
            trace_id="t1", span_id="s1", name="ok_span", kind="agent_dispatch",
            status="ok", start_time=datetime.now(timezone.utc).isoformat(),
            attributes={},
        ))
        store.write_span(TraceSpan(
            trace_id="t2", span_id="s2", name="err_span", kind="agent_dispatch",
            status="error", start_time=datetime.now(timezone.utc).isoformat(),
            attributes={"error": "timeout"},
        ))

        assert len(store.get_spans(status="error")) == 1
        assert len(store.get_spans(status="ok")) == 1

    def test_limit(self, tmp_path: Path) -> None:
        store = LocalTraceStore(tmp_path)
        for i in range(10):
            store.write_span(TraceSpan(
                trace_id=f"t{i}", span_id=f"s{i}", name="test",
                kind="agent_dispatch", status="ok",
                start_time=datetime.now(timezone.utc).isoformat(),
                attributes={},
            ))
        assert len(store.get_spans(limit=3)) == 3

    def test_cost_write_and_summary(self, tmp_path: Path) -> None:
        store = LocalTraceStore(tmp_path)
        now_iso = datetime.now(timezone.utc).isoformat()
        store.write_cost({
            "timestamp": now_iso,
            "agent": "vajra",
            "provider": "openrouter",
            "cost_usd": 0.005,
        })
        store.write_cost({
            "timestamp": now_iso,
            "agent": "vajra",
            "provider": "openrouter",
            "cost_usd": 0.003,
        })
        store.write_cost({
            "timestamp": now_iso,
            "agent": "leela",
            "provider": "anthropic",
            "cost_usd": 0.010,
        })

        # All costs
        all_costs = store.get_cost_summary()
        assert "vajra/openrouter" in all_costs
        assert abs(all_costs["vajra/openrouter"] - 0.008) < 1e-9
        assert abs(all_costs["leela/anthropic"] - 0.010) < 1e-9

        # Filter by agent
        vajra_costs = store.get_cost_summary(agent="vajra")
        assert "vajra/openrouter" in vajra_costs
        assert "leela/anthropic" not in vajra_costs

    def test_thread_safety(self, tmp_path: Path) -> None:
        """Concurrent writes should not corrupt the file."""
        store = LocalTraceStore(tmp_path)
        errors: list[Exception] = []

        def writer(offset: int) -> None:
            try:
                for i in range(50):
                    store.write_span(TraceSpan(
                        trace_id=f"t{offset}_{i}",
                        span_id=f"s{offset}_{i}",
                        name="concurrent",
                        kind="agent_dispatch",
                        status="ok",
                        start_time=datetime.now(timezone.utc).isoformat(),
                        attributes={"thread": offset},
                    ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        results = store.get_spans(limit=300)
        assert len(results) == 200  # 4 threads * 50 spans


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


class TestCostEstimation:
    def test_free_providers(self) -> None:
        assert _estimate_cost("ollama", 1000, 500) == 0.0
        assert _estimate_cost("nvidia_nim", 1000, 500) == 0.0
        assert _estimate_cost("openrouter_free", 1000, 500) == 0.0

    def test_paid_providers(self) -> None:
        cost = _estimate_cost("anthropic", 1000, 1000)
        # 1K input * 0.003 + 1K output * 0.015 = 0.018
        assert abs(cost - 0.018) < 1e-9

    def test_unknown_provider_uses_default(self) -> None:
        cost = _estimate_cost("some_new_provider", 1000, 1000)
        # Default: 0.001 + 0.005 = 0.006
        assert abs(cost - 0.006) < 1e-9

    def test_zero_tokens(self) -> None:
        assert _estimate_cost("anthropic", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# SwarmObserver (high-level interface)
# ---------------------------------------------------------------------------


class TestSwarmObserver:
    def test_trace_agent_dispatch_local(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        trace_id = obs.trace_agent_dispatch(
            agent="vajra",
            task_id="task_001",
            task_title="Analyze agent behavior",
            provider="openrouter",
            model="llama-3.3-70b",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=1234.5,
            success=True,
            result_preview="The analysis shows...",
        )
        assert trace_id.startswith("trace_")

        spans = obs.local_store.get_spans(agent="vajra")
        assert len(spans) == 1
        assert spans[0].kind == "agent_dispatch"
        assert spans[0].attributes["model"] == "llama-3.3-70b"
        assert spans[0].attributes["cost_usd"] > 0

        costs = obs.local_store.get_cost_summary()
        assert len(costs) > 0

    def test_trace_agent_dispatch_error(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        obs.trace_agent_dispatch(
            agent="leela",
            task_id="task_002",
            task_title="Failed task",
            provider="anthropic",
            model="claude-3",
            success=False,
            error="Rate limit exceeded",
        )

        spans = obs.local_store.get_spans(status="error")
        assert len(spans) == 1
        assert "Rate limit" in spans[0].attributes["error"]

    def test_trace_llm_call(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        trace_id = obs.trace_llm_call(
            provider="openrouter",
            model="llama-3.3-70b",
            prompt="What is consciousness?",
            response="A complex phenomenon...",
            prompt_tokens=10,
            completion_tokens=50,
            latency_ms=800.0,
            agent="vajra",
            task_id="task_003",
        )
        assert trace_id.startswith("trace_")

        spans = obs.local_store.get_spans(kind="llm_call")
        assert len(spans) == 1

    def test_trace_evolution_cycle(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        trace_id = obs.trace_evolution_cycle(
            proposals=[{"mutation": "add_retry"}, {"mutation": "reduce_temp"}],
            fitness_scores={"add_retry": 0.85, "reduce_temp": 0.72},
            outcomes={"winner": "add_retry"},
            duration_ms=3000.0,
        )
        assert trace_id.startswith("trace_")

        spans = obs.local_store.get_spans(kind="evolution")
        assert len(spans) == 1
        assert spans[0].attributes["num_proposals"] == 2

    def test_trace_stigmergy_mark(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        trace_id = obs.trace_stigmergy_mark(
            agent="vajra",
            channel="research_findings",
            salience=0.85,
            content="Found interesting pattern in layer 27",
        )
        assert trace_id.startswith("trace_")

        spans = obs.local_store.get_spans(kind="stigmergy")
        assert len(spans) == 1
        assert spans[0].attributes["salience"] == 0.85

    def test_trace_context_manager_success(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        with obs.trace_context("test_operation", agent="vajra", task_id="t1") as span:
            time.sleep(0.01)  # Simulate work
            span.kind = "agent_dispatch"

        spans = obs.local_store.get_spans()
        assert len(spans) == 1
        assert spans[0].status == "ok"
        assert spans[0].duration_ms >= 10  # At least 10ms

    def test_trace_context_manager_error(self, tmp_path: Path) -> None:
        obs = SwarmObserver(tmp_path)
        with pytest.raises(ValueError, match="boom"):
            with obs.trace_context("failing_op", agent="leela") as span:
                raise ValueError("boom")

        spans = obs.local_store.get_spans(status="error")
        assert len(spans) == 1
        assert "boom" in spans[0].attributes["error"]

    def test_langfuse_not_available_without_keys(self, tmp_path: Path) -> None:
        """Without env vars, Langfuse should silently degrade."""
        obs = SwarmObserver(tmp_path)
        assert not obs.langfuse_available

        # Should still work — just local
        obs.trace_agent_dispatch(
            agent="test",
            task_id="t1",
            task_title="test",
        )
        assert len(obs.local_store.get_spans()) == 1

    def test_no_performance_impact(self, tmp_path: Path) -> None:
        """Tracing 100 dispatches should take less than 500ms."""
        obs = SwarmObserver(tmp_path)
        start = time.monotonic()

        for i in range(100):
            obs.trace_agent_dispatch(
                agent=f"agent_{i % 5}",
                task_id=f"task_{i}",
                task_title=f"Task number {i}",
                provider="openrouter",
                model="llama-3.3-70b",
                prompt_tokens=100,
                completion_tokens=50,
                latency_ms=float(i),
            )

        elapsed_ms = (time.monotonic() - start) * 1000.0
        assert elapsed_ms < 500, f"100 traces took {elapsed_ms:.1f}ms — too slow"

        # Verify all written
        assert len(obs.local_store.get_spans(limit=200)) == 100


# ---------------------------------------------------------------------------
# get_observer singleton
# ---------------------------------------------------------------------------


class TestGetObserver:
    def test_returns_singleton(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import dharma_swarm.observability as obs_mod

        # Reset the module singleton for this test
        monkeypatch.setattr(obs_mod, "_observer", None)

        o1 = get_observer(tmp_path)
        o2 = get_observer(tmp_path)
        assert o1 is o2


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


class TestNewId:
    def test_prefix(self) -> None:
        assert _new_id("trace").startswith("trace_")
        assert _new_id("span").startswith("span_")

    def test_uniqueness(self) -> None:
        ids = {_new_id("x") for _ in range(1000)}
        assert len(ids) == 1000
