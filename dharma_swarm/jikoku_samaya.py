"""
JIKOKU SAMAYA — Computational Efficiency Protocol
A burning pledge to account for every moment of compute.

From 5% utilization → 50% = 10x efficiency gain, zero hardware.

NOT about R_V contraction (that's separate research).
THIS is about: span tracing, pramāda detection, kaizen loops.
"""

import logging
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Rotate JIKOKU_LOG.jsonl when it exceeds this size (bytes).
_LOG_ROTATION_BYTES = 50 * 1024 * 1024  # 50 MB
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
import asyncio

@dataclass
class JikokuSpan:
    """
    Single span in the JIKOKU trace.

    [JIKOKU:START] and [JIKOKU:END] pairs create measured duration.
    Categories: boot | orient | execute.* | api_call | file_op | update | interrupt
    """
    span_id: str
    category: str
    intent: str  # What this span is trying to accomplish
    ts_start: str
    ts_end: Optional[str] = None
    duration_sec: Optional[float] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        """Serialize to JSONL format (one line per span)"""
        return json.dumps(asdict(self))

    @classmethod
    def from_jsonl(cls, line: str) -> 'JikokuSpan':
        """Deserialize from JSONL"""
        return cls(**json.loads(line))


class JikokuTracer:
    """
    Span-level tracer for computational efficiency.

    Usage:
        tracer = JikokuTracer()

        # Method 1: Context manager
        with tracer.span("api_call", "Fetch from Anthropic API"):
            response = anthropic_client.messages.create(...)

        # Method 2: Manual
        span_id = tracer.start("execute.llm_call", "Generate code mutation")
        # ... do work ...
        tracer.end(span_id)

    Review every 7 sessions for kaizen (continuous improvement).
    """

    VALID_CATEGORIES = {
        'boot', 'orient',
        'execute.llm_call', 'execute.tool_use', 'execute.code_gen',
        'api_call', 'file_op', 'update', 'interrupt'
    }

    def __init__(self, log_path: Optional[Path] = None, session_id: Optional[str] = None):
        self.log_path = log_path or Path.home() / ".dharma" / "jikoku" / "JIKOKU_LOG.jsonl"
        self._logging_disabled = False
        self._logging_error: Optional[str] = None
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._logging_disabled = True
            self._logging_error = str(exc)
        self.session_id = session_id or f"session-{int(time.time() * 1000)}"
        self.active_spans: Dict[str, JikokuSpan] = {}
        self._span_counter = 0
        self._rotation_check_counter = 0

    def _maybe_rotate(self) -> None:
        """Rotate log file if it exceeds _LOG_ROTATION_BYTES.

        Checked every 100 writes to avoid stat() on every span.
        """
        self._rotation_check_counter += 1
        if self._rotation_check_counter % 100 != 0:
            return
        try:
            if self.log_path.exists() and self.log_path.stat().st_size > _LOG_ROTATION_BYTES:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                rotated = self.log_path.with_name(f"JIKOKU_LOG.{stamp}.jsonl")
                self.log_path.rename(rotated)
                logger.info("JIKOKU log rotated → %s", rotated.name)
        except Exception:
            logger.debug("JIKOKU log rotation failed", exc_info=True)

    def _generate_span_id(self) -> str:
        """Generate unique span ID"""
        self._span_counter += 1
        timestamp = int(time.time() * 1000)
        return f"{self.session_id}-span-{self._span_counter}-{timestamp}"

    def _now_iso(self) -> str:
        """Current time in ISO 8601 UTC format"""
        return datetime.now(timezone.utc).isoformat()

    def start(
        self,
        category: str,
        intent: str,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **metadata
    ) -> str:
        """
        Start a new span.

        Args:
            category: boot | orient | execute.* | api_call | file_op | update | interrupt
            intent: Human-readable description of what this span does
            agent_id: Which agent is executing (if applicable)
            task_id: Which task this span belongs to (if applicable)
            **metadata: Additional span metadata

        Returns:
            span_id: Use this to end() the span
        """
        if category not in self.VALID_CATEGORIES:
            # Allow execute.* wildcard
            if not (category.startswith('execute.') and category != 'execute.'):
                raise ValueError(
                    f"Invalid category '{category}'. "
                    f"Must be one of {self.VALID_CATEGORIES} or execute.*"
                )

        span = JikokuSpan(
            span_id=self._generate_span_id(),
            category=category,
            intent=intent,
            ts_start=self._now_iso(),
            session_id=self.session_id,
            agent_id=agent_id,
            task_id=task_id,
            metadata=metadata
        )

        self.active_spans[span.span_id] = span
        return span.span_id

    def end(self, span_id: str, **extra_metadata) -> JikokuSpan:
        """
        End an active span and write to JIKOKU_LOG.jsonl.

        Args:
            span_id: ID returned by start()
            **extra_metadata: Additional metadata to merge in

        Returns:
            The completed span
        """
        if span_id not in self.active_spans:
            raise ValueError(f"Span '{span_id}' not found in active spans")

        span = self.active_spans.pop(span_id)
        span.ts_end = self._now_iso()

        # Calculate duration
        start_dt = datetime.fromisoformat(span.ts_start)
        end_dt = datetime.fromisoformat(span.ts_end)
        span.duration_sec = (end_dt - start_dt).total_seconds()

        # Merge extra metadata
        span.metadata.update(extra_metadata)

        # Append to JIKOKU_LOG.jsonl. Tracing must never break the caller.
        if not self._logging_disabled:
            self._maybe_rotate()
            try:
                with open(self.log_path, 'a') as f:
                    f.write(span.to_jsonl() + '\n')
            except OSError as exc:
                self._logging_disabled = True
                self._logging_error = str(exc)
                span.metadata.setdefault("log_write_error", str(exc))

        return span

    @contextmanager
    def span(
        self,
        category: str,
        intent: str,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **metadata
    ):
        """
        Context manager for span tracing.

        Usage:
            with tracer.span("api_call", "Call Anthropic API"):
                response = client.messages.create(...)
        """
        span_id = self.start(category, intent, agent_id, task_id, **metadata)
        try:
            yield span_id
        finally:
            self.end(span_id)

    def get_session_spans(self, session_id: Optional[str] = None) -> List[JikokuSpan]:
        """Get all spans for a specific session (or current session if None)"""
        target_session = session_id or self.session_id
        if not self.log_path.exists():
            return []

        spans = []
        with open(self.log_path) as f:
            for line in f:
                span = JikokuSpan.from_jsonl(line.strip())
                if span.session_id == target_session:
                    spans.append(span)
        return spans

    def kaizen_report_for_session(self, session_id: str) -> Dict[str, Any]:
        """Generate kaizen report for a specific session.

        Similar to kaizen_report() but for a single session only.
        Used for comparing before/after performance in fitness evaluation.

        Args:
            session_id: The session ID to analyze

        Returns:
            Report dict with wall_clock_sec, utilization_pct, etc.
            Returns {"error": "..."} if session not found.
        """
        if not self.log_path.exists():
            return {"error": "No JIKOKU log found"}

        # Get spans for this session
        spans = [
            JikokuSpan.from_jsonl(line.strip())
            for line in open(self.log_path)
            if JikokuSpan.from_jsonl(line.strip()).session_id == session_id
        ]

        if not spans:
            return {"error": f"No spans found for session {session_id}"}

        # Calculate metrics
        total_duration = sum(s.duration_sec for s in spans if s.duration_sec)

        # Wall clock time (first start to last end)
        start_times = [datetime.fromisoformat(s.ts_start) for s in spans]
        end_times = [datetime.fromisoformat(s.ts_end) for s in spans if s.ts_end]

        if not end_times:
            wall_clock = 0
        else:
            wall_clock = (max(end_times) - min(start_times)).total_seconds()

        # Utilization ratio
        utilization = (total_duration / wall_clock * 100) if wall_clock > 0 else 0

        # Category breakdown
        category_stats = {}
        for span in spans:
            if span.duration_sec is None:
                continue
            if span.category not in category_stats:
                category_stats[span.category] = {'count': 0, 'total_sec': 0.0}
            category_stats[span.category]['count'] += 1
            category_stats[span.category]['total_sec'] += span.duration_sec

        return {
            'session_id': session_id,
            'total_spans': len(spans),
            'total_compute_sec': total_duration,
            'wall_clock_sec': wall_clock,
            'utilization_pct': utilization,
            'idle_pct': 100 - utilization,
            'category_breakdown': category_stats,
        }

    def kaizen_report(self, last_n_sessions: int = 7) -> Dict[str, Any]:
        """
        Generate kaizen (continuous improvement) report.

        Reviews last N sessions for:
        - Total compute time vs wall clock time
        - Idle ratio (pramāda detection)
        - Category breakdown
        - Longest spans (optimization targets)

        Run every 7 sessions as per protocol.
        """
        if not self.log_path.exists():
            return {"error": "No JIKOKU log found"}

        # Load all spans
        all_spans = []
        with open(self.log_path) as f:
            for line in f:
                all_spans.append(JikokuSpan.from_jsonl(line.strip()))

        # Get unique sessions, take last N
        sessions = sorted(set(s.session_id for s in all_spans))
        target_sessions = set(sessions[-last_n_sessions:])

        # Filter to target sessions
        spans = [s for s in all_spans if s.session_id in target_sessions]

        if not spans:
            return {"error": "No spans in target sessions"}

        # Calculate metrics
        total_duration = sum(s.duration_sec for s in spans if s.duration_sec)

        # Wall clock time (first start to last end)
        start_times = [datetime.fromisoformat(s.ts_start) for s in spans]
        end_times = [datetime.fromisoformat(s.ts_end) for s in spans if s.ts_end]

        if not end_times:
            wall_clock = 0
        else:
            wall_clock = (max(end_times) - min(start_times)).total_seconds()

        # Utilization ratio
        utilization = (total_duration / wall_clock * 100) if wall_clock > 0 else 0

        # Category breakdown
        category_stats = {}
        for span in spans:
            if span.duration_sec is None:
                continue
            if span.category not in category_stats:
                category_stats[span.category] = {'count': 0, 'total_sec': 0.0}
            category_stats[span.category]['count'] += 1
            category_stats[span.category]['total_sec'] += span.duration_sec

        # Longest spans (optimization targets)
        longest = sorted(
            [s for s in spans if s.duration_sec],
            key=lambda s: s.duration_sec,
            reverse=True
        )[:10]

        return {
            'sessions_analyzed': len(target_sessions),
            'total_spans': len(spans),
            'total_compute_sec': total_duration,
            'wall_clock_sec': wall_clock,
            'utilization_pct': utilization,
            'idle_pct': 100 - utilization,  # Pramāda (heedlessness)
            'category_breakdown': category_stats,
            'optimization_targets': [
                {
                    'span_id': s.span_id,
                    'category': s.category,
                    'intent': s.intent,
                    'duration_sec': s.duration_sec
                }
                for s in longest
            ],
            'kaizen_goals': self._generate_kaizen_goals(utilization, category_stats)
        }

    def _generate_kaizen_goals(
        self,
        current_utilization: float,
        category_stats: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Generate improvement goals based on current metrics"""
        goals = []

        # Utilization goal
        if current_utilization < 50:
            goals.append(
                f"INCREASE UTILIZATION: {current_utilization:.1f}% → 50% "
                f"(potential {50/current_utilization if current_utilization > 0 else float('inf'):.1f}x gain)"
            )

        # Category-specific goals
        for cat, stats in sorted(
            category_stats.items(),
            key=lambda x: x[1]['total_sec'],
            reverse=True
        )[:3]:
            pct = (stats['total_sec'] / sum(s['total_sec'] for s in category_stats.values())) * 100
            goals.append(
                f"OPTIMIZE {cat}: {stats['count']} spans, {stats['total_sec']:.1f}s ({pct:.1f}%)"
            )

        return goals


# Global tracer instance
_global_tracer: Optional[JikokuTracer] = None

def get_global_tracer() -> JikokuTracer:
    """Get or create global JIKOKU tracer"""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = JikokuTracer()
    return _global_tracer

def init_tracer(log_path: Optional[Path] = None, session_id: Optional[str] = None):
    """Initialize global tracer with custom config"""
    global _global_tracer
    _global_tracer = JikokuTracer(log_path, session_id)
    return _global_tracer


# Convenience functions
def jikoku_span(category: str, intent: str, **metadata):
    """Decorator/context manager for span tracing"""
    return get_global_tracer().span(category, intent, **metadata)

def jikoku_start(category: str, intent: str, **metadata) -> str:
    """Start a span"""
    return get_global_tracer().start(category, intent, **metadata)

def jikoku_end(span_id: str, **metadata) -> JikokuSpan:
    """End a span"""
    return get_global_tracer().end(span_id, **metadata)

def jikoku_kaizen(last_n_sessions: int = 7) -> Dict[str, Any]:
    """Generate kaizen report"""
    return get_global_tracer().kaizen_report(last_n_sessions)
