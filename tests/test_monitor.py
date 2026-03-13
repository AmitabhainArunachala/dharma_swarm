"""Tests for dharma_swarm.monitor -- SystemMonitor, health tracking, anomaly detection."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.models import _utc_now
from dharma_swarm.monitor import (
    AgentHealth,
    Anomaly,
    HealthReport,
    HealthStatus,
    SystemMonitor,
    _entries_in_window,
    _is_failure,
)
from dharma_swarm.traces import TraceEntry, TraceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Fixed reference point for pure-helper tests (no store interaction).
_FIXED = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def trace_dir(tmp_path: Path) -> Path:
    """Return a fresh temporary directory for a TraceStore."""
    return tmp_path / "traces"


@pytest.fixture
async def store(trace_dir: Path) -> TraceStore:
    """Return an initialised TraceStore pointed at *trace_dir*."""
    s = TraceStore(base_path=trace_dir)
    await s.init()
    return s


@pytest.fixture
async def monitor(store: TraceStore) -> SystemMonitor:
    """Return a SystemMonitor backed by a fresh store."""
    return SystemMonitor(store)


def _make_entry(
    agent: str = "test-agent",
    action: str = "test_action",
    state: str = "active",
    timestamp: datetime | None = None,
    fitness: FitnessScore | None = None,
    **kw,
) -> TraceEntry:
    """Shorthand for building test trace entries with known timestamps."""
    entry = TraceEntry(agent=agent, action=action, state=state, fitness=fitness, **kw)
    if timestamp is not None:
        entry.timestamp = timestamp
    return entry


# ---------------------------------------------------------------------------
# HealthStatus enum
# ---------------------------------------------------------------------------


def test_health_status_values():
    assert HealthStatus.HEALTHY == "healthy"
    assert HealthStatus.DEGRADED == "degraded"
    assert HealthStatus.CRITICAL == "critical"
    assert HealthStatus.UNKNOWN == "unknown"


def test_health_status_is_string():
    assert isinstance(HealthStatus.HEALTHY, str)


# ---------------------------------------------------------------------------
# Anomaly model
# ---------------------------------------------------------------------------


def test_anomaly_defaults():
    a = Anomaly(anomaly_type="failure_spike", severity="high", description="test")
    assert len(a.id) == 16
    assert a.related_traces == []
    assert a.detected_at is not None


def test_anomaly_with_traces():
    a = Anomaly(
        anomaly_type="agent_silent",
        severity="medium",
        description="gone",
        related_traces=["abc", "def"],
    )
    assert a.related_traces == ["abc", "def"]


# ---------------------------------------------------------------------------
# AgentHealth model
# ---------------------------------------------------------------------------


def test_agent_health_defaults():
    h = AgentHealth(agent_name="alpha")
    assert h.total_actions == 0
    assert h.failures == 0
    assert h.success_rate == 1.0
    assert h.last_seen is None
    assert h.status == HealthStatus.UNKNOWN


# ---------------------------------------------------------------------------
# HealthReport model
# ---------------------------------------------------------------------------


def test_health_report_defaults():
    r = HealthReport()
    assert r.overall_status == HealthStatus.UNKNOWN
    assert r.agent_health == []
    assert r.anomalies == []
    assert r.total_traces == 0
    assert r.mean_fitness is None


# ---------------------------------------------------------------------------
# _is_failure helper
# ---------------------------------------------------------------------------


def test_is_failure_by_state():
    e = _make_entry(state="failed")
    assert _is_failure(e) is True


def test_is_failure_by_action_fail():
    e = _make_entry(action="task_failed")
    assert _is_failure(e) is True


def test_is_failure_by_action_error():
    e = _make_entry(action="runtime_error")
    assert _is_failure(e) is True


def test_is_failure_active_state():
    e = _make_entry(state="active", action="task_completed")
    assert _is_failure(e) is False


def test_is_failure_case_insensitive():
    e = _make_entry(action="FATAL_ERROR_OCCURRED")
    assert _is_failure(e) is True


# ---------------------------------------------------------------------------
# _entries_in_window helper
# ---------------------------------------------------------------------------


def test_entries_in_window_filters():
    entries = [
        _make_entry(timestamp=_FIXED - timedelta(hours=3)),
        _make_entry(timestamp=_FIXED - timedelta(minutes=30)),
        _make_entry(timestamp=_FIXED - timedelta(minutes=5)),
    ]
    result = _entries_in_window(entries, _FIXED, hours=1)
    assert len(result) == 2


def test_entries_in_window_empty():
    result = _entries_in_window([], _FIXED, hours=1)
    assert result == []


def test_entries_in_window_none_in_range():
    entries = [_make_entry(timestamp=_FIXED - timedelta(hours=5))]
    result = _entries_in_window(entries, _FIXED, hours=1)
    assert result == []


# ---------------------------------------------------------------------------
# check_health -- empty store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_empty_store(monitor: SystemMonitor):
    report = await monitor.check_health()
    assert report.overall_status == HealthStatus.UNKNOWN
    assert report.total_traces == 0
    assert report.anomalies == []


# ---------------------------------------------------------------------------
# check_health -- healthy swarm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_healthy(store: TraceStore, monitor: SystemMonitor):
    for i in range(10):
        await store.log_entry(
            _make_entry(agent="alpha", action="task_completed", state="done")
        )
    report = await monitor.check_health()
    assert report.overall_status == HealthStatus.HEALTHY
    assert report.total_traces == 10
    assert report.failure_rate == 0.0


# ---------------------------------------------------------------------------
# check_health -- degraded (>20% failure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_degraded(store: TraceStore, monitor: SystemMonitor):
    # 7 ok + 3 failed = 30% failure → degraded (>20%, not >50%)
    for i in range(7):
        await store.log_entry(_make_entry(agent="a", action="ok"))
    for i in range(3):
        await store.log_entry(_make_entry(agent="a", action="ok", state="failed"))
    report = await monitor.check_health()
    assert report.overall_status in (HealthStatus.DEGRADED, HealthStatus.CRITICAL)
    assert report.failure_rate == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# check_health -- critical (>50% failure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_critical_failure_rate(
    store: TraceStore, monitor: SystemMonitor
):
    for i in range(3):
        await store.log_entry(_make_entry(agent="a", action="ok"))
    for i in range(7):
        await store.log_entry(_make_entry(agent="a", action="ok", state="failed"))
    report = await monitor.check_health()
    assert report.overall_status == HealthStatus.CRITICAL
    assert report.failure_rate == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# check_health -- mean fitness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_mean_fitness(store: TraceStore, monitor: SystemMonitor):
    f1 = FitnessScore(correctness=1.0, dharmic_alignment=1.0, performance=1.0, utilization=1.0, economic_value=1.0, elegance=1.0, efficiency=1.0, safety=1.0)
    f2 = FitnessScore(correctness=0.5, dharmic_alignment=0.5, performance=0.5, utilization=0.5, economic_value=0.5, elegance=0.5, efficiency=0.5, safety=0.5)
    await store.log_entry(_make_entry(fitness=f1))
    await store.log_entry(_make_entry(fitness=f2))
    report = await monitor.check_health()
    assert report.mean_fitness is not None
    assert report.mean_fitness == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_check_health_no_fitness(store: TraceStore, monitor: SystemMonitor):
    await store.log_entry(_make_entry())
    report = await monitor.check_health()
    assert report.mean_fitness is None


# ---------------------------------------------------------------------------
# detect_anomalies -- failure_spike
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anomaly_failure_spike(store: TraceStore, monitor: SystemMonitor):
    # 4 failed out of 5 = 80% failure rate
    for i in range(4):
        await store.log_entry(_make_entry(action="task_failed"))
    await store.log_entry(_make_entry(action="task_ok"))
    anomalies = await monitor.detect_anomalies(window_hours=1)
    spike = [a for a in anomalies if a.anomaly_type == "failure_spike"]
    assert len(spike) == 1
    assert spike[0].severity == "high"
    assert len(spike[0].related_traces) == 4


@pytest.mark.asyncio
async def test_no_anomaly_below_threshold(store: TraceStore, monitor: SystemMonitor):
    # 2 failed out of 10 = 20% < 30% threshold
    for i in range(8):
        await store.log_entry(_make_entry(action="ok"))
    for i in range(2):
        await store.log_entry(_make_entry(action="task_failed"))
    anomalies = await monitor.detect_anomalies(window_hours=1)
    spike = [a for a in anomalies if a.anomaly_type == "failure_spike"]
    assert len(spike) == 0


# ---------------------------------------------------------------------------
# detect_anomalies -- agent_silent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anomaly_agent_silent(store: TraceStore, monitor: SystemMonitor):
    now = _utc_now()
    # Agent "old-bot" was active 2 hours ago but not in the last hour
    await store.log_entry(
        _make_entry(agent="old-bot", action="pulse", timestamp=now - timedelta(hours=2))
    )
    # Agent "active-bot" is active now
    await store.log_entry(
        _make_entry(agent="active-bot", action="pulse", timestamp=now)
    )
    anomalies = await monitor.detect_anomalies(window_hours=1)
    silent = [a for a in anomalies if a.anomaly_type == "agent_silent"]
    assert len(silent) == 1
    assert "old-bot" in silent[0].description
    assert silent[0].severity == "medium"


@pytest.mark.asyncio
async def test_no_silent_when_agent_active(store: TraceStore, monitor: SystemMonitor):
    await store.log_entry(_make_entry(agent="bot"))
    anomalies = await monitor.detect_anomalies(window_hours=1)
    silent = [a for a in anomalies if a.anomaly_type == "agent_silent"]
    assert len(silent) == 0


# ---------------------------------------------------------------------------
# detect_anomalies -- throughput_drop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anomaly_throughput_drop(store: TraceStore, monitor: SystemMonitor):
    now = _utc_now()
    # 10 entries in the previous window (1-2 hours ago)
    for i in range(10):
        await store.log_entry(
            _make_entry(timestamp=now - timedelta(hours=1, minutes=30))
        )
    # Only 2 in the current window (last hour) -- 20% of previous
    for i in range(2):
        await store.log_entry(
            _make_entry(timestamp=now - timedelta(minutes=5))
        )
    anomalies = await monitor.detect_anomalies(window_hours=1)
    drop = [a for a in anomalies if a.anomaly_type == "throughput_drop"]
    assert len(drop) == 1
    assert drop[0].severity == "low"


@pytest.mark.asyncio
async def test_no_throughput_drop_when_stable(
    store: TraceStore, monitor: SystemMonitor
):
    now = _utc_now()
    for i in range(5):
        await store.log_entry(
            _make_entry(timestamp=now - timedelta(hours=1, minutes=30))
        )
    for i in range(5):
        await store.log_entry(
            _make_entry(timestamp=now - timedelta(minutes=5))
        )
    anomalies = await monitor.detect_anomalies(window_hours=1)
    drop = [a for a in anomalies if a.anomaly_type == "throughput_drop"]
    assert len(drop) == 0


# ---------------------------------------------------------------------------
# detect_anomalies -- empty store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anomalies_empty_store(monitor: SystemMonitor):
    anomalies = await monitor.detect_anomalies()
    assert anomalies == []


# ---------------------------------------------------------------------------
# agent_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_health_unknown_agent(monitor: SystemMonitor):
    h = await monitor.agent_health("nobody")
    assert h.agent_name == "nobody"
    assert h.status == HealthStatus.UNKNOWN
    assert h.total_actions == 0


@pytest.mark.asyncio
async def test_agent_health_healthy_agent(store: TraceStore, monitor: SystemMonitor):
    for i in range(10):
        await store.log_entry(_make_entry(agent="alpha", action="pulse"))
    h = await monitor.agent_health("alpha")
    assert h.status == HealthStatus.HEALTHY
    assert h.total_actions == 10
    assert h.failures == 0
    assert h.success_rate == 1.0
    assert h.last_seen is not None


@pytest.mark.asyncio
async def test_agent_health_degraded_agent(
    store: TraceStore, monitor: SystemMonitor
):
    # 7 ok + 3 failed = 70% success = DEGRADED (<80%)
    for i in range(7):
        await store.log_entry(_make_entry(agent="beta", action="ok"))
    for i in range(3):
        await store.log_entry(_make_entry(agent="beta", action="ok", state="failed"))
    h = await monitor.agent_health("beta")
    assert h.status == HealthStatus.DEGRADED
    assert h.failures == 3
    assert h.success_rate == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_agent_health_critical_agent(
    store: TraceStore, monitor: SystemMonitor
):
    # 2 ok + 8 failed = 20% success = CRITICAL (<50%)
    for i in range(2):
        await store.log_entry(_make_entry(agent="gamma", action="ok"))
    for i in range(8):
        await store.log_entry(_make_entry(agent="gamma", action="ok", state="failed"))
    h = await monitor.agent_health("gamma")
    assert h.status == HealthStatus.CRITICAL
    assert h.failures == 8
    assert h.success_rate == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# fitness_drift
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fitness_drift_no_data(monitor: SystemMonitor):
    result = await monitor.fitness_drift()
    assert result is None


@pytest.mark.asyncio
async def test_fitness_drift_single_point(store: TraceStore, monitor: SystemMonitor):
    f = FitnessScore(correctness=0.8, dharmic_alignment=0.8, elegance=0.8, efficiency=0.8, safety=0.8)
    await store.log_entry(_make_entry(fitness=f))
    result = await monitor.fitness_drift()
    assert result is None


@pytest.mark.asyncio
async def test_fitness_drift_improving(store: TraceStore, monitor: SystemMonitor):
    now = _utc_now()
    # Older entry with low fitness, newer with high
    f_low = FitnessScore(correctness=0.2, dharmic_alignment=0.2, elegance=0.2, efficiency=0.2, safety=0.2)
    f_high = FitnessScore(correctness=0.9, dharmic_alignment=0.9, elegance=0.9, efficiency=0.9, safety=0.9)
    await store.log_entry(
        _make_entry(fitness=f_low, timestamp=now - timedelta(hours=12))
    )
    await store.log_entry(
        _make_entry(fitness=f_high, timestamp=now - timedelta(minutes=5))
    )
    result = await monitor.fitness_drift(window_hours=24)
    assert result is not None
    assert result > 0  # positive slope = improving


@pytest.mark.asyncio
async def test_fitness_drift_degrading(store: TraceStore, monitor: SystemMonitor):
    now = _utc_now()
    f_high = FitnessScore(correctness=0.9, dharmic_alignment=0.9, elegance=0.9, efficiency=0.9, safety=0.9)
    f_low = FitnessScore(correctness=0.1, dharmic_alignment=0.1, elegance=0.1, efficiency=0.1, safety=0.1)
    await store.log_entry(
        _make_entry(fitness=f_high, timestamp=now - timedelta(hours=12))
    )
    await store.log_entry(
        _make_entry(fitness=f_low, timestamp=now - timedelta(minutes=5))
    )
    result = await monitor.fitness_drift(window_hours=24)
    assert result is not None
    assert result < 0  # negative slope = degrading


# ---------------------------------------------------------------------------
# throughput
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throughput_empty(monitor: SystemMonitor):
    result = await monitor.throughput()
    assert result == {}


@pytest.mark.asyncio
async def test_throughput_counts_actions(store: TraceStore, monitor: SystemMonitor):
    await store.log_entry(_make_entry(action="pulse"))
    await store.log_entry(_make_entry(action="pulse"))
    await store.log_entry(_make_entry(action="task_completed"))
    result = await monitor.throughput(window_hours=1)
    assert result["pulse"] == 2
    assert result["task_completed"] == 1


@pytest.mark.asyncio
async def test_throughput_excludes_old(store: TraceStore, monitor: SystemMonitor):
    now = _utc_now()
    await store.log_entry(
        _make_entry(action="old_action", timestamp=now - timedelta(hours=5))
    )
    await store.log_entry(_make_entry(action="new_action", timestamp=now))
    result = await monitor.throughput(window_hours=1)
    assert "old_action" not in result
    assert result.get("new_action", 0) == 1


# ---------------------------------------------------------------------------
# check_health -- agent_health list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_agent_list(store: TraceStore, monitor: SystemMonitor):
    await store.log_entry(_make_entry(agent="alice", action="pulse"))
    await store.log_entry(_make_entry(agent="bob", action="pulse"))
    report = await monitor.check_health()
    names = [h.agent_name for h in report.agent_health]
    assert "alice" in names
    assert "bob" in names


# ---------------------------------------------------------------------------
# check_health -- critical from high anomaly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_critical_from_anomaly(
    store: TraceStore, monitor: SystemMonitor
):
    # All traces fail → high anomaly → CRITICAL
    for i in range(5):
        await store.log_entry(_make_entry(state="failed"))
    report = await monitor.check_health()
    assert report.overall_status == HealthStatus.CRITICAL
    spike = [a for a in report.anomalies if a.anomaly_type == "failure_spike"]
    assert len(spike) == 1


# ---------------------------------------------------------------------------
# check_health -- degraded from medium anomaly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_degraded_from_silent_agent(
    store: TraceStore, monitor: SystemMonitor
):
    now = _utc_now()
    # One agent only active before the window → medium anomaly → DEGRADED
    await store.log_entry(
        _make_entry(agent="ghost", action="pulse", timestamp=now - timedelta(hours=2))
    )
    await store.log_entry(_make_entry(agent="alive", action="pulse", timestamp=now))
    report = await monitor.check_health()
    assert report.overall_status == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# Integration: multiple anomalies at once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_anomalies(store: TraceStore, monitor: SystemMonitor):
    now = _utc_now()
    # Previous window: many entries from agent "old"
    for i in range(10):
        await store.log_entry(
            _make_entry(
                agent="old", action="pulse",
                timestamp=now - timedelta(hours=1, minutes=30),
            )
        )
    # Current window: few entries, all failures, from agent "new"
    for i in range(2):
        await store.log_entry(
            _make_entry(agent="new", action="task_failed", timestamp=now)
        )
    anomalies = await monitor.detect_anomalies(window_hours=1)
    types = {a.anomaly_type for a in anomalies}
    # Should detect failure spike, silent agent, and throughput drop
    assert "failure_spike" in types
    assert "agent_silent" in types
    assert "throughput_drop" in types


# ---------------------------------------------------------------------------
# JSON roundtrip for report models
# ---------------------------------------------------------------------------


def test_health_report_json_roundtrip():
    r = HealthReport(
        overall_status=HealthStatus.HEALTHY,
        total_traces=42,
        failure_rate=0.05,
        mean_fitness=0.85,
    )
    data = r.model_dump_json()
    r2 = HealthReport.model_validate_json(data)
    assert r2.overall_status == HealthStatus.HEALTHY
    assert r2.total_traces == 42
    assert r2.failure_rate == pytest.approx(0.05)


def test_anomaly_json_roundtrip():
    a = Anomaly(
        anomaly_type="fitness_drift",
        severity="low",
        description="trending down",
        related_traces=["id1", "id2"],
    )
    data = a.model_dump_json()
    a2 = Anomaly.model_validate_json(data)
    assert a2.anomaly_type == "fitness_drift"
    assert a2.related_traces == ["id1", "id2"]


# ---------------------------------------------------------------------------
# detect_fitness_regression -- evolution archive based
# ---------------------------------------------------------------------------


def _make_archive_entry(fitness_val: float, ts_offset_hours: float = 0.0) -> ArchiveEntry:
    """Build an ArchiveEntry with uniform fitness at *fitness_val*."""
    from dharma_swarm.models import _utc_now as _now

    ts = _now() - timedelta(hours=ts_offset_hours)
    return ArchiveEntry(
        component="test",
        change_type="test",
        description="test entry",
        fitness=FitnessScore(
            correctness=fitness_val,
            dharmic_alignment=fitness_val,
            performance=fitness_val,
            utilization=fitness_val,
            economic_value=fitness_val,
            elegance=fitness_val,
            efficiency=fitness_val,
            safety=fitness_val,
        ),
        timestamp=ts.isoformat(),
    )


@pytest.mark.asyncio
async def test_fitness_regression_detected(monitor: SystemMonitor):
    """Three monotonically decreasing fitness entries should trigger anomaly."""
    # get_latest returns newest-first, so order: high ts first, low ts last
    entries = [
        _make_archive_entry(0.3, ts_offset_hours=0),   # newest (lowest fitness)
        _make_archive_entry(0.6, ts_offset_hours=1),   # middle
        _make_archive_entry(0.9, ts_offset_hours=2),   # oldest (highest fitness)
    ]
    archive = AsyncMock()
    archive.get_latest = AsyncMock(return_value=entries)

    anomalies = await monitor.detect_fitness_regression(archive, n=3)
    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "fitness_regression"
    assert anomalies[0].severity == "medium"
    assert "0.900" in anomalies[0].description
    assert "0.300" in anomalies[0].description


@pytest.mark.asyncio
async def test_fitness_regression_not_triggered_improving(monitor: SystemMonitor):
    """Improving fitness should not trigger the anomaly."""
    entries = [
        _make_archive_entry(0.9, ts_offset_hours=0),
        _make_archive_entry(0.6, ts_offset_hours=1),
        _make_archive_entry(0.3, ts_offset_hours=2),
    ]
    archive = AsyncMock()
    archive.get_latest = AsyncMock(return_value=entries)

    anomalies = await monitor.detect_fitness_regression(archive, n=3)
    assert len(anomalies) == 0


@pytest.mark.asyncio
async def test_fitness_regression_not_triggered_flat(monitor: SystemMonitor):
    """Equal fitness values should not trigger the anomaly."""
    entries = [
        _make_archive_entry(0.5, ts_offset_hours=0),
        _make_archive_entry(0.5, ts_offset_hours=1),
        _make_archive_entry(0.5, ts_offset_hours=2),
    ]
    archive = AsyncMock()
    archive.get_latest = AsyncMock(return_value=entries)

    anomalies = await monitor.detect_fitness_regression(archive, n=3)
    assert len(anomalies) == 0


@pytest.mark.asyncio
async def test_fitness_regression_insufficient_entries(monitor: SystemMonitor):
    """Fewer than n entries should return no anomalies."""
    entries = [_make_archive_entry(0.5)]
    archive = AsyncMock()
    archive.get_latest = AsyncMock(return_value=entries)

    anomalies = await monitor.detect_fitness_regression(archive, n=3)
    assert len(anomalies) == 0


@pytest.mark.asyncio
async def test_fitness_regression_none_archive(monitor: SystemMonitor):
    """None archive should return empty list."""
    anomalies = await monitor.detect_fitness_regression(None)
    assert anomalies == []


# ---------------------------------------------------------------------------
# bridge_summary
# ---------------------------------------------------------------------------


def test_bridge_summary_none():
    result = SystemMonitor.bridge_summary(None)
    assert result == {"status": "not_initialized"}


def test_bridge_summary_with_real_bridge():
    """Verify bridge_summary extracts meaningful data from a ResearchBridge."""
    from dharma_swarm.bridge import ResearchBridge

    bridge = ResearchBridge(data_path=Path("/tmp/test_bridge_summary.jsonl"))
    result = SystemMonitor.bridge_summary(bridge)

    assert result["status"] == "active"
    assert result["type"] == "ResearchBridge"
    assert result["measurement_count"] == 0
    assert "correlation" in result
    assert result["correlation"]["n"] == 0
    assert result["correlation"]["pearson_r"] is None
    assert "group_summary" in result
    assert result["group_summary"] == {}


def test_bridge_summary_error_handling():
    """An object that raises on attribute access should return error status."""

    class BrokenBridge:
        @property
        def measurement_count(self):
            raise RuntimeError("broken")

    result = SystemMonitor.bridge_summary(BrokenBridge())
    assert result["status"] == "error"
