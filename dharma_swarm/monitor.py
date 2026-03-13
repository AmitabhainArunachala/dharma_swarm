"""System monitor -- swarm health tracking and anomaly detection.

Watches traces, detects drift, tracks agent health, provides
actionable health summaries, and performs pop-quiz liveness checks.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.traces import TraceEntry, TraceStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HealthStatus(str, Enum):
    """Overall health classification for agents or the swarm."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Anomaly(BaseModel):
    """A detected anomaly in swarm operations."""

    id: str = Field(default_factory=_new_id)
    detected_at: datetime = Field(default_factory=_utc_now)
    anomaly_type: str  # "failure_spike", "fitness_drift", "agent_silent", "throughput_drop"
    severity: str  # "low", "medium", "high"
    description: str
    related_traces: list[str] = Field(default_factory=list)


class AgentHealth(BaseModel):
    """Health summary for a single agent."""

    agent_name: str
    total_actions: int = 0
    failures: int = 0
    success_rate: float = 1.0
    last_seen: Optional[datetime] = None
    status: HealthStatus = HealthStatus.UNKNOWN


class HealthReport(BaseModel):
    """Full health report for the swarm."""

    timestamp: datetime = Field(default_factory=_utc_now)
    overall_status: HealthStatus = HealthStatus.UNKNOWN
    agent_health: list[AgentHealth] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    total_traces: int = 0
    traces_last_hour: int = 0
    failure_rate: float = 0.0
    mean_fitness: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_failure(entry: TraceEntry) -> bool:
    """Return True if *entry* represents a failed operation."""
    if entry.state == "failed":
        return True
    action_lower = entry.action.lower()
    return "fail" in action_lower or "error" in action_lower


def _entries_in_window(
    entries: list[TraceEntry], now: datetime, hours: float
) -> list[TraceEntry]:
    """Return entries whose timestamp falls within *hours* before *now*."""
    cutoff = now - timedelta(hours=hours)
    return [e for e in entries if e.timestamp >= cutoff]


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class SystemMonitor:
    """Monitors swarm health via TraceStore analysis.

    All public methods are async to match the TraceStore interface.
    The monitor is pure analysis -- it never mutates the trace store.
    """

    def __init__(self, trace_store: TraceStore) -> None:
        self._store = trace_store

    # -- public API ----------------------------------------------------------

    async def check_health(self) -> HealthReport:
        """Run a full health scan and return a report.

        Combines agent health, anomaly detection, throughput, and
        fitness metrics into a single actionable report.
        """
        all_entries = await self._store.get_recent(limit=10_000)
        if not all_entries:
            return HealthReport(overall_status=HealthStatus.UNKNOWN)

        now = _utc_now()
        last_hour = _entries_in_window(all_entries, now, hours=1)

        # Failure rate across all entries
        total = len(all_entries)
        failures = sum(1 for e in all_entries if _is_failure(e))
        failure_rate = failures / total if total else 0.0

        # Mean fitness
        fitness_values = [
            e.fitness.weighted()
            for e in all_entries
            if e.fitness is not None
        ]
        mean_fitness: Optional[float] = None
        if fitness_values:
            mean_fitness = statistics.mean(fitness_values)

        # Per-agent health
        agents = await self._all_agent_health(all_entries, now)

        # Anomalies (from last hour)
        anomalies = self._detect_anomalies_from(all_entries, now, window_hours=1)

        # Overall status
        has_high = any(a.severity == "high" for a in anomalies)
        has_medium = any(a.severity == "medium" for a in anomalies)

        if failure_rate > 0.5 or has_high:
            overall = HealthStatus.CRITICAL
        elif failure_rate > 0.2 or has_medium:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return HealthReport(
            overall_status=overall,
            agent_health=agents,
            anomalies=anomalies,
            total_traces=total,
            traces_last_hour=len(last_hour),
            failure_rate=failure_rate,
            mean_fitness=mean_fitness,
        )

    async def detect_anomalies(self, window_hours: float = 1) -> list[Anomaly]:
        """Detect anomalies in the recent *window_hours* of traces."""
        all_entries = await self._store.get_recent(limit=10_000)
        now = _utc_now()
        return self._detect_anomalies_from(all_entries, now, window_hours)

    async def agent_health(self, agent_name: str) -> AgentHealth:
        """Return health summary for a single agent."""
        all_entries = await self._store.get_recent(limit=10_000)
        agent_entries = [e for e in all_entries if e.agent == agent_name]

        if not agent_entries:
            return AgentHealth(agent_name=agent_name)

        failures = sum(1 for e in agent_entries if _is_failure(e))
        total = len(agent_entries)
        success_rate = 1.0 - (failures / total) if total else 1.0

        # Last seen
        latest = max(agent_entries, key=lambda e: e.timestamp)

        # Status based on success rate
        if total == 0:
            status = HealthStatus.UNKNOWN
        elif success_rate < 0.5:
            status = HealthStatus.CRITICAL
        elif success_rate < 0.8:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return AgentHealth(
            agent_name=agent_name,
            total_actions=total,
            failures=failures,
            success_rate=success_rate,
            last_seen=latest.timestamp,
            status=status,
        )

    async def fitness_drift(self, window_hours: float = 24) -> Optional[float]:
        """Compute a simple fitness trend slope over *window_hours*.

        Returns a positive number if fitness is improving, negative if
        degrading, or ``None`` if there are fewer than 2 data points.
        Uses least-squares linear regression on (elapsed_seconds, fitness).
        """
        all_entries = await self._store.get_recent(limit=10_000)
        now = _utc_now()
        window = _entries_in_window(all_entries, now, window_hours)

        points: list[tuple[float, float]] = []
        for e in window:
            if e.fitness is not None:
                elapsed = (e.timestamp - (now - timedelta(hours=window_hours))).total_seconds()
                points.append((elapsed, e.fitness.weighted()))

        if len(points) < 2:
            return None

        # Simple linear regression slope
        n = len(points)
        sum_x = sum(p[0] for p in points)
        sum_y = sum(p[1] for p in points)
        sum_xy = sum(p[0] * p[1] for p in points)
        sum_x2 = sum(p[0] ** 2 for p in points)
        denom = n * sum_x2 - sum_x ** 2
        if abs(denom) < 1e-12:
            return 0.0
        return (n * sum_xy - sum_x * sum_y) / denom

    async def throughput(self, window_hours: float = 1) -> dict[str, int]:
        """Return action counts within *window_hours*, keyed by action name."""
        all_entries = await self._store.get_recent(limit=10_000)
        now = _utc_now()
        window = _entries_in_window(all_entries, now, window_hours)
        counter: Counter[str] = Counter()
        for e in window:
            counter[e.action] += 1
        return dict(counter)

    # -- private helpers -----------------------------------------------------

    async def _all_agent_health(
        self, entries: list[TraceEntry], now: datetime
    ) -> list[AgentHealth]:
        """Build health summaries for every agent seen in *entries*."""
        by_agent: defaultdict[str, list[TraceEntry]] = defaultdict(list)
        for e in entries:
            by_agent[e.agent].append(e)

        result: list[AgentHealth] = []
        for name, agent_entries in sorted(by_agent.items()):
            total = len(agent_entries)
            failures = sum(1 for e in agent_entries if _is_failure(e))
            success_rate = 1.0 - (failures / total) if total else 1.0
            latest = max(agent_entries, key=lambda e: e.timestamp)

            if success_rate < 0.5:
                status = HealthStatus.CRITICAL
            elif success_rate < 0.8:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            result.append(
                AgentHealth(
                    agent_name=name,
                    total_actions=total,
                    failures=failures,
                    success_rate=success_rate,
                    last_seen=latest.timestamp,
                    status=status,
                )
            )
        return result

    def _detect_anomalies_from(
        self,
        all_entries: list[TraceEntry],
        now: datetime,
        window_hours: float,
    ) -> list[Anomaly]:
        """Core anomaly detection logic (sync, operates on pre-fetched data)."""
        anomalies: list[Anomaly] = []
        window = _entries_in_window(all_entries, now, window_hours)

        # --- failure_spike ---
        if window:
            fail_count = sum(1 for e in window if _is_failure(e))
            fail_rate = fail_count / len(window)
            if fail_rate > 0.3:
                failed_ids = [e.id for e in window if _is_failure(e)]
                anomalies.append(
                    Anomaly(
                        anomaly_type="failure_spike",
                        severity="high",
                        description=(
                            f"Failure rate {fail_rate:.0%} exceeds 30% threshold "
                            f"({fail_count}/{len(window)} traces)"
                        ),
                        related_traces=failed_ids,
                    )
                )

        # --- agent_silent ---
        # Agents seen before the window but not in it
        window_agents = {e.agent for e in window}
        window_ids = {e.id for e in window}
        pre_window_agents = {e.agent for e in all_entries if e.id not in window_ids}
        silent_agents = pre_window_agents - window_agents
        for agent_name in sorted(silent_agents):
            anomalies.append(
                Anomaly(
                    anomaly_type="agent_silent",
                    severity="medium",
                    description=(
                        f"Agent '{agent_name}' was active before the window "
                        f"but has no traces in the last {window_hours}h"
                    ),
                )
            )

        # --- throughput_drop ---
        # Compare current window to the previous window of same size
        prev_start = now - timedelta(hours=window_hours * 2)
        prev_end = now - timedelta(hours=window_hours)
        prev_window = [
            e for e in all_entries
            if prev_start <= e.timestamp < prev_end
        ]
        if prev_window and window:
            if len(window) < len(prev_window) * 0.5:
                anomalies.append(
                    Anomaly(
                        anomaly_type="throughput_drop",
                        severity="low",
                        description=(
                            f"Throughput dropped to {len(window)} traces from "
                            f"{len(prev_window)} in the previous window "
                            f"(<50% of prior period)"
                        ),
                    )
                )

        # --- fitness_regression ---
        # Check if last 3 fitness values (chronological) are monotonically decreasing.
        # all_entries may be newest-first, so sort by timestamp before extracting.
        chrono_with_fitness = sorted(
            [e for e in all_entries if e.fitness is not None],
            key=lambda e: e.timestamp,
        )
        fitness_values = [e.fitness.weighted() for e in chrono_with_fitness if e.fitness is not None]
        if len(fitness_values) >= 3:
            last_3 = fitness_values[-3:]
            if last_3[0] > last_3[1] > last_3[2]:
                anomalies.append(
                    Anomaly(
                        anomaly_type="fitness_regression",
                        severity="medium",
                        description=(
                            f"Fitness monotonically decreasing over last 3 entries: "
                            f"{last_3[0]:.3f} -> {last_3[1]:.3f} -> {last_3[2]:.3f}"
                        ),
                    )
                )

        return anomalies

    async def liveness_check(
        self,
        agent_name: str,
        provider: Any,
        challenge: str = "What is your current role and task?",
        expected_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Inject a test prompt into a running agent to verify behavioral correctness.

        Implements the Devin pop-quiz pattern: periodically verify that agents
        are operating correctly by comparing responses against expected baselines.

        Args:
            agent_name: Name of the agent being tested.
            provider: LLM provider with async ``complete()`` method.
            challenge: The test prompt to send.
            expected_keywords: Words that should appear in the response.
                Defaults to [agent_name].

        Returns:
            Dict with 'passed' (bool), 'response' (str), 'keywords_found' (list),
            and 'agent_name'.
        """
        if provider is None:
            return {
                "passed": False,
                "agent_name": agent_name,
                "response": "",
                "reason": "No provider attached",
            }

        from dharma_swarm.models import LLMRequest

        request = LLMRequest(
            model="mock",
            messages=[{"role": "user", "content": f"POP QUIZ: {challenge}"}],
            system=f"You are agent '{agent_name}'. Answer the question briefly and accurately.",
            max_tokens=200,
            temperature=0.0,
        )

        try:
            response = await provider.complete(request)
            content = response.content.lower()

            expected = expected_keywords or [agent_name.lower()]
            found = [kw for kw in expected if kw.lower() in content]
            passed = len(found) > 0

            # Log the check as a trace
            await self._store.log_entry(
                TraceEntry(
                    agent=agent_name,
                    action="liveness_check",
                    state="passed" if passed else "failed",
                    metadata={
                        "challenge": challenge,
                        "keywords_found": found,
                        "keywords_expected": expected,
                        "response_preview": response.content[:200],
                    },
                )
            )

            logger.info(
                "Liveness check for %s: %s (found %d/%d keywords)",
                agent_name,
                "PASSED" if passed else "FAILED",
                len(found),
                len(expected),
            )

            return {
                "passed": passed,
                "agent_name": agent_name,
                "response": response.content[:200],
                "keywords_found": found,
                "keywords_expected": expected,
            }
        except Exception as exc:
            logger.warning("Liveness check failed for %s: %s", agent_name, exc)
            return {
                "passed": False,
                "agent_name": agent_name,
                "response": "",
                "reason": str(exc),
            }

    async def batch_liveness_check(
        self,
        agents: dict[str, Any],
        challenge: str = "What is your current role and task?",
    ) -> list[dict[str, Any]]:
        """Run liveness checks on multiple agents.

        Args:
            agents: Mapping of agent_name to provider instance.
            challenge: The test prompt to send to each agent.

        Returns:
            List of liveness check results, one per agent.
        """
        results: list[dict[str, Any]] = []
        for agent_name, provider in agents.items():
            result = await self.liveness_check(
                agent_name=agent_name,
                provider=provider,
                challenge=challenge,
            )
            results.append(result)
        return results

    async def detect_fitness_regression(
        self,
        archive: Any,
        n: int = 3,
    ) -> list[Anomaly]:
        """Check the evolution archive for monotonically decreasing fitness.

        Fetches the last *n* entries from *archive* (an EvolutionArchive)
        and emits a medium-severity ``fitness_regression`` anomaly if their
        weighted fitness values are strictly monotonically decreasing.

        Args:
            archive: An EvolutionArchive instance.
            n: Number of recent entries to inspect (default 3).

        Returns:
            A list containing zero or one Anomaly.
        """
        if archive is None:
            return []

        try:
            latest = await archive.get_latest(n=n)
        except Exception:
            logger.warning("Failed to read evolution archive for fitness regression check")
            return []

        if len(latest) < n:
            return []

        # get_latest returns newest-first; reverse to chronological order
        chrono = list(reversed(latest))
        values = [e.fitness.weighted() for e in chrono]

        # Check strict monotonic decrease
        if all(values[i] > values[i + 1] for i in range(len(values) - 1)):
            formatted = " -> ".join(f"{v:.3f}" for v in values)
            return [
                Anomaly(
                    anomaly_type="fitness_regression",
                    severity="medium",
                    description=(
                        f"Fitness monotonically decreasing over last {n} "
                        f"archive entries: {formatted}"
                    ),
                )
            ]

        return []

    @staticmethod
    def bridge_summary(bridge: Any) -> dict:
        """Summarize a ResearchBridge state.

        Extracts measurement count, correlation statistics, and per-group
        summaries from a ResearchBridge instance.

        Args:
            bridge: A ResearchBridge instance (or None).

        Returns:
            Dict with status, measurement_count, correlation stats
            (pearson_r, spearman_rho, n, contraction_recognition_overlap),
            and group_summary.
        """
        if bridge is None:
            return {"status": "not_initialized"}
        try:
            result: dict[str, Any] = {
                "status": "active",
                "type": type(bridge).__name__,
                "measurement_count": bridge.measurement_count,
            }

            correlation = bridge.compute_correlation()
            result["correlation"] = {
                "n": correlation.n,
                "pearson_r": correlation.pearson_r,
                "spearman_rho": correlation.spearman_rho,
                "contraction_recognition_overlap": correlation.contraction_recognition_overlap,
                "summary": correlation.summary,
            }

            result["group_summary"] = bridge.group_summary()

            return result
        except Exception:
            return {"status": "error"}
