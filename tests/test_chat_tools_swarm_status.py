import pytest

from api.chat_tools import exec_swarm_status
from dharma_swarm.monitor import HealthReport, HealthStatus
from dharma_swarm.traces import TraceEntry


class _FakeAgent:
    def __init__(self, name: str, status: str = "running") -> None:
        self.id = name
        self.name = name
        self.role = "tester"
        self.status = status
        self.current_task = None
        self.started_at = None
        self.last_heartbeat = None
        self.turns_used = 0
        self.tasks_completed = 0


class _FakeSwarmStatus:
    def __init__(self) -> None:
        self.agents = [_FakeAgent("alpha"), _FakeAgent("beta", status="idle")]
        self.tasks_running = 1
        self.tasks_completed = 2
        self.tasks_failed = 0
        self.tasks_pending = 0
        self.uptime_seconds = 12.0


class _FakeSwarm:
    async def status(self):
        return _FakeSwarmStatus()


class _FakeMonitor:
    async def check_health(self):
        return HealthReport(
            overall_status=HealthStatus.DEGRADED,
            total_traces=2,
            traces_last_hour=2,
            failure_rate=0.5,
            mean_fitness=None,
            anomalies=[],
        )


class _FakeTraceStore:
    async def get_recent(self, limit: int = 20):
        return [
            TraceEntry(agent="alpha", action="pulse", state="running"),
            TraceEntry(agent="beta", action="task_completed", state="done"),
        ]


class _FakeApiMain:
    @staticmethod
    def get_swarm():
        return _FakeSwarm()

    @staticmethod
    def get_monitor():
        return _FakeMonitor()

    @staticmethod
    def get_trace_store():
        return _FakeTraceStore()


@pytest.mark.asyncio
async def test_exec_swarm_status_handles_none_mean_fitness_and_trace_agent(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "api.main", _FakeApiMain)

    result = await exec_swarm_status({"include_traces": True, "include_anomalies": True})

    assert "Health: degraded" in result
    assert "mean_fitness=n/a" in result
    assert "alpha — pulse → running" in result
    assert "beta — task_completed → done" in result
    assert "Health error:" not in result
    assert "Traces error:" not in result
