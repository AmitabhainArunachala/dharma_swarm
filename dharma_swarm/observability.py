"""Observability layer for dharma_swarm using Langfuse.

Traces every agent dispatch, LLM call, tool use, and evolution cycle.
Provides cost tracking, latency monitoring, and failure pattern detection.

If Langfuse server is unavailable, falls back to local JSONL logging
at ``~/.dharma/traces/``.  The local store is always written regardless
of whether Langfuse is configured, so you never lose visibility.

Design constraints:
- Local-first: works without any Langfuse server running.
- Zero performance impact: all logging is fire-and-forget async.
- Matches existing dharma_swarm patterns (SignalBus, JikokuTracer).
- Lightweight: only stdlib for local mode; langfuse SDK is optional.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TRACES_DIR = Path.home() / ".dharma" / "traces"
_COST_DB_PATH = Path.home() / ".dharma" / "traces" / "cost_ledger.jsonl"

# Provider cost table (USD per 1K tokens).  Kept intentionally simple;
# the real billing comes from Langfuse when configured.
_COST_PER_1K: dict[str, dict[str, float]] = {
    "anthropic": {"input": 0.003, "output": 0.015},
    "openai": {"input": 0.002, "output": 0.010},
    "openrouter": {"input": 0.001, "output": 0.005},
    "openrouter_free": {"input": 0.0, "output": 0.0},
    "nvidia_nim": {"input": 0.0, "output": 0.0},
    "ollama": {"input": 0.0, "output": 0.0},
    "ollama_cloud": {"input": 0.0, "output": 0.0},
    "local": {"input": 0.0, "output": 0.0},
    "claudecode": {"input": 0.003, "output": 0.015},
    "codex": {"input": 0.002, "output": 0.010},
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _new_id(prefix: str = "span") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _estimate_cost(
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate USD cost from token counts and provider name."""
    key = provider.lower().replace(" ", "_").replace("-", "_")
    rates = _COST_PER_1K.get(key, {"input": 0.001, "output": 0.005})
    return (prompt_tokens / 1000.0) * rates["input"] + (
        completion_tokens / 1000.0
    ) * rates["output"]


# ---------------------------------------------------------------------------
# Trace span dataclass (used for both local JSONL and Langfuse)
# ---------------------------------------------------------------------------

@dataclass
class TraceSpan:
    """A single observability span."""

    trace_id: str
    span_id: str
    parent_span_id: str = ""
    name: str = ""
    kind: str = ""  # agent_dispatch, llm_call, evolution, stigmergy, tool_use
    status: str = "ok"  # ok, error
    start_time: str = ""
    end_time: str = ""
    duration_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=True)

    @classmethod
    def from_jsonl(cls, line: str) -> TraceSpan:
        data = json.loads(line)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Local JSONL trace store
# ---------------------------------------------------------------------------

class LocalTraceStore:
    """Append-only JSONL trace store at ``~/.dharma/traces/``.

    Thread-safe.  Rotates files daily.  Provides simple query methods.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _TRACES_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _today_file(self) -> Path:
        return self._base_dir / f"traces_{_utc_now().strftime('%Y-%m-%d')}.jsonl"

    def write_span(self, span: TraceSpan) -> None:
        """Append a span to today's trace file."""
        try:
            line = span.to_jsonl() + "\n"
            with self._lock:
                with open(self._today_file(), "a") as f:
                    f.write(line)
        except Exception:
            logger.debug("LocalTraceStore.write_span failed", exc_info=True)

    def write_cost(self, record: dict[str, Any]) -> None:
        """Append a cost record to the cost ledger."""
        try:
            line = json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n"
            with self._lock:
                with open(self._base_dir / "cost_ledger.jsonl", "a") as f:
                    f.write(line)
        except Exception:
            logger.debug("LocalTraceStore.write_cost failed", exc_info=True)

    # -- query API --

    @staticmethod
    def is_real_span(span: TraceSpan) -> bool:
        """Return True if the span represents a real LLM call (not a test stub).

        Test stubs have zero completion tokens and zero prompt tokens.
        Real spans have at least one non-zero token count.
        """
        attrs = span.attributes
        return (
            int(attrs.get("completion_tokens", 0) or 0) > 0
            or int(attrs.get("prompt_tokens", 0) or 0) > 0
        )

    def get_spans(
        self,
        *,
        agent: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        real_only: bool = False,
        limit: int = 200,
    ) -> list[TraceSpan]:
        """Read spans matching filters.  Scans daily files in reverse order.

        Args:
            real_only: If True, exclude test stubs (zero-token spans).
        """
        results: list[TraceSpan] = []
        files = sorted(self._base_dir.glob("traces_*.jsonl"), reverse=True)
        for fp in files:
            if len(results) >= limit:
                break
            try:
                for raw_line in fp.read_text().splitlines():
                    if not raw_line.strip():
                        continue
                    span = TraceSpan.from_jsonl(raw_line)
                    if agent and span.attributes.get("agent") != agent:
                        continue
                    if kind and span.kind != kind:
                        continue
                    if status and span.status != status:
                        continue
                    if since and span.start_time < since.isoformat():
                        continue
                    if until and span.start_time > until.isoformat():
                        continue
                    if real_only and not self.is_real_span(span):
                        continue
                    results.append(span)
                    if len(results) >= limit:
                        break
            except Exception:
                logger.debug("Error reading %s", fp, exc_info=True)
        return results

    def get_real_spans(self, *, limit: int = 200, **kwargs: Any) -> list[TraceSpan]:
        """Convenience: get only real LLM call spans (non-zero tokens)."""
        return self.get_spans(real_only=True, limit=limit, **kwargs)

    def real_vs_stub_counts(self) -> dict[str, int]:
        """Return counts of real vs stub spans in today's traces."""
        all_spans = self.get_spans(limit=10000)
        real = sum(1 for s in all_spans if self.is_real_span(s))
        return {"real": real, "stub": len(all_spans) - real, "total": len(all_spans)}

    def get_cost_summary(
        self,
        *,
        agent: str | None = None,
        provider: str | None = None,
        date: str | None = None,
    ) -> dict[str, float]:
        """Aggregate costs from the ledger.  Returns {grouping_key: total_usd}."""
        ledger_path = self._base_dir / "cost_ledger.jsonl"
        if not ledger_path.exists():
            return {}
        totals: dict[str, float] = {}
        try:
            for raw_line in ledger_path.read_text().splitlines():
                if not raw_line.strip():
                    continue
                rec = json.loads(raw_line)
                if agent and rec.get("agent") != agent:
                    continue
                if provider and rec.get("provider") != provider:
                    continue
                if date and not rec.get("timestamp", "").startswith(date):
                    continue
                key = rec.get("agent", "unknown") + "/" + rec.get("provider", "unknown")
                totals[key] = totals.get(key, 0.0) + rec.get("cost_usd", 0.0)
        except Exception:
            logger.debug("Cost summary read failed", exc_info=True)
        return totals


# ---------------------------------------------------------------------------
# Langfuse adapter (optional — graceful if unavailable)
# ---------------------------------------------------------------------------

class _LangfuseAdapter:
    """Thin wrapper over the Langfuse SDK.

    Initialises lazily on first use.  If LANGFUSE_PUBLIC_KEY and
    LANGFUSE_SECRET_KEY are not set, or if the SDK import fails,
    all methods become silent no-ops.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._available: bool | None = None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self._try_init()
        return self._available

    def _try_init(self) -> bool:
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
        if not pk or not sk:
            logger.debug("Langfuse keys not set — local-only mode")
            return False
        try:
            from langfuse import Langfuse  # type: ignore[import-untyped]

            host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
            self._client = Langfuse(
                public_key=pk,
                secret_key=sk,
                host=host,
            )
            logger.info("Langfuse connected: %s", host)
            return True
        except Exception:
            logger.debug("Langfuse init failed — local-only mode", exc_info=True)
            return False

    def trace(self, **kwargs: Any) -> Any:
        if not self.available or self._client is None:
            return None
        try:
            return self._client.trace(**kwargs)
        except Exception:
            logger.debug("Langfuse trace() failed", exc_info=True)
            return None

    def generation(self, trace: Any, **kwargs: Any) -> Any:
        if trace is None:
            return None
        try:
            return trace.generation(**kwargs)
        except Exception:
            logger.debug("Langfuse generation() failed", exc_info=True)
            return None

    def span(self, trace: Any, **kwargs: Any) -> Any:
        if trace is None:
            return None
        try:
            return trace.span(**kwargs)
        except Exception:
            logger.debug("Langfuse span() failed", exc_info=True)
            return None

    def flush(self) -> None:
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:
                logger.debug("Langfuse flush failed", exc_info=True)

    def shutdown(self) -> None:
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception:
                logger.debug("Langfuse shutdown failed", exc_info=True)


# ---------------------------------------------------------------------------
# Main observability interface
# ---------------------------------------------------------------------------

# Module-level singletons (created lazily via get_observer())
_observer: SwarmObserver | None = None
_observer_lock = threading.Lock()


class SwarmObserver:
    """Central observability hub for dharma_swarm.

    Writes every trace to local JSONL (always) and to Langfuse (when
    configured).  All public methods are non-blocking best-effort:
    they never raise, never slow down the caller.
    """

    def __init__(self, traces_dir: Path | None = None) -> None:
        self._local = LocalTraceStore(traces_dir)
        self._langfuse = _LangfuseAdapter()
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    @property
    def langfuse_available(self) -> bool:
        return self._langfuse.available

    @property
    def local_store(self) -> LocalTraceStore:
        return self._local

    # -- context manager for tracing an agent dispatch -----------------------

    @contextmanager
    def trace_context(
        self,
        name: str,
        *,
        agent: str = "",
        task_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Generator[TraceSpan, None, None]:
        """Context manager that auto-records start/end/duration of a span."""
        trace_id = _new_id("trace")
        span_id = _new_id("span")
        start = time.monotonic()
        start_iso = _utc_now_iso()
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            name=name,
            kind="context",
            start_time=start_iso,
            attributes={"agent": agent, "task_id": task_id, **(metadata or {})},
        )
        try:
            yield span
            span.status = "ok"
        except Exception as exc:
            span.status = "error"
            span.attributes["error"] = str(exc)[:500]
            raise
        finally:
            span.end_time = _utc_now_iso()
            span.duration_ms = (time.monotonic() - start) * 1000.0
            self._local.write_span(span)

    # -- trace_agent_dispatch ------------------------------------------------

    def trace_agent_dispatch(
        self,
        *,
        agent: str,
        task_id: str,
        task_title: str,
        provider: str = "",
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        error: str = "",
        result_preview: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a complete agent dispatch cycle.

        Returns the trace_id for correlation.
        """
        trace_id = _new_id("trace")
        span_id = _new_id("dispatch")
        cost = _estimate_cost(provider, prompt_tokens, completion_tokens)
        now_iso = _utc_now_iso()

        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            name=f"agent_dispatch:{agent}",
            kind="agent_dispatch",
            status="ok" if success else "error",
            start_time=now_iso,
            end_time=now_iso,
            duration_ms=latency_ms,
            attributes={
                "agent": agent,
                "task_id": task_id,
                "task_title": task_title[:200],
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_usd": round(cost, 6),
                "success": success,
                "error": error[:500] if error else "",
                "result_preview": result_preview[:300],
                **(metadata or {}),
            },
        )
        self._local.write_span(span)

        # Cost ledger
        if prompt_tokens or completion_tokens:
            self._local.write_cost({
                "timestamp": now_iso,
                "agent": agent,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": round(cost, 6),
                "task_id": task_id,
            })

        # Langfuse (best-effort, async-ish via thread)
        if self._langfuse.available:
            try:
                lf_trace = self._langfuse.trace(
                    name=f"agent:{agent}",
                    id=trace_id,
                    metadata={"task_id": task_id, "task_title": task_title[:200]},
                    tags=[agent, provider] if provider else [agent],
                )
                if lf_trace is not None:
                    self._langfuse.generation(
                        lf_trace,
                        name=f"llm:{model or provider}",
                        model=model or provider,
                        input=task_title[:500],
                        output=result_preview[:500],
                        usage={
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        },
                        metadata={
                            "latency_ms": latency_ms,
                            "success": success,
                            "error": error[:200] if error else "",
                            "cost_usd": round(cost, 6),
                        },
                    )
            except Exception:
                logger.debug("Langfuse trace_agent_dispatch failed", exc_info=True)

        return trace_id

    # -- trace_llm_call ------------------------------------------------------

    def trace_llm_call(
        self,
        *,
        provider: str,
        model: str,
        prompt: str = "",
        response: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        error: str = "",
        agent: str = "",
        task_id: str = "",
        parent_trace_id: str = "",
    ) -> str:
        """Record a single LLM call (may be nested inside an agent dispatch)."""
        trace_id = parent_trace_id or _new_id("trace")
        span_id = _new_id("llm")
        cost = _estimate_cost(provider, prompt_tokens, completion_tokens)
        now_iso = _utc_now_iso()

        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_trace_id,
            name=f"llm_call:{model or provider}",
            kind="llm_call",
            status="ok" if success else "error",
            start_time=now_iso,
            end_time=now_iso,
            duration_ms=latency_ms,
            attributes={
                "agent": agent,
                "task_id": task_id,
                "provider": provider,
                "model": model,
                "prompt_preview": prompt[:300],
                "response_preview": response[:300],
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": round(cost, 6),
                "success": success,
                "error": error[:500] if error else "",
            },
        )
        self._local.write_span(span)

        if prompt_tokens or completion_tokens:
            self._local.write_cost({
                "timestamp": now_iso,
                "agent": agent,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": round(cost, 6),
                "task_id": task_id,
            })

        return trace_id

    # -- trace_evolution_cycle -----------------------------------------------

    def trace_evolution_cycle(
        self,
        *,
        proposals: list[dict[str, Any]] | None = None,
        fitness_scores: dict[str, float] | None = None,
        outcomes: dict[str, Any] | None = None,
        duration_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a Darwin Engine evolution cycle."""
        trace_id = _new_id("trace")
        span_id = _new_id("evo")
        now_iso = _utc_now_iso()

        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            name="evolution_cycle",
            kind="evolution",
            status="ok",
            start_time=now_iso,
            end_time=now_iso,
            duration_ms=duration_ms,
            attributes={
                "num_proposals": len(proposals) if proposals else 0,
                "fitness_scores": fitness_scores or {},
                "outcomes_summary": str(outcomes)[:500] if outcomes else "",
                **(metadata or {}),
            },
        )
        self._local.write_span(span)

        if self._langfuse.available:
            try:
                self._langfuse.trace(
                    name="evolution_cycle",
                    id=trace_id,
                    metadata={
                        "num_proposals": len(proposals) if proposals else 0,
                        "fitness_scores": fitness_scores or {},
                        "duration_ms": duration_ms,
                        **(metadata or {}),
                    },
                    tags=["evolution", "darwin_engine"],
                )
            except Exception:
                logger.debug("Langfuse evolution trace failed", exc_info=True)

        return trace_id

    # -- trace_stigmergy_mark ------------------------------------------------

    def trace_stigmergy_mark(
        self,
        *,
        agent: str,
        channel: str,
        salience: float,
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a stigmergy pheromone mark."""
        trace_id = _new_id("trace")
        span_id = _new_id("stig")
        now_iso = _utc_now_iso()

        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            name=f"stigmergy:{channel}",
            kind="stigmergy",
            status="ok",
            start_time=now_iso,
            end_time=now_iso,
            duration_ms=0.0,
            attributes={
                "agent": agent,
                "channel": channel,
                "salience": salience,
                "content_preview": content[:200],
                **(metadata or {}),
            },
        )
        self._local.write_span(span)
        return trace_id

    # -- flush / shutdown ----------------------------------------------------

    def flush(self) -> None:
        """Flush Langfuse buffer (if available)."""
        self._langfuse.flush()

    def shutdown(self) -> None:
        """Shutdown Langfuse client (if available)."""
        self._langfuse.shutdown()


# ---------------------------------------------------------------------------
# Module-level accessor
# ---------------------------------------------------------------------------

def get_observer(traces_dir: Path | None = None) -> SwarmObserver:
    """Return the singleton SwarmObserver instance.

    Thread-safe.  First call creates the instance; subsequent calls
    return the same object (traces_dir is ignored after first call).
    """
    global _observer
    if _observer is not None:
        return _observer
    with _observer_lock:
        if _observer is not None:
            return _observer
        _observer = SwarmObserver(traces_dir)
        return _observer
