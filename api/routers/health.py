"""Health + anomaly detection endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.models import (
    AgentHealthOut,
    AnomalyOut,
    ApiResponse,
    HealthOut,
    SwarmOverview,
)

router = APIRouter(prefix="/api", tags=["health"])


def _get_deps():
    """Lazy-load dharma_swarm dependencies."""
    from api.main import get_swarm, get_trace_store, get_monitor
    return get_swarm(), get_trace_store(), get_monitor()


@router.get("/health")
async def health_check() -> ApiResponse:
    _, trace_store, monitor = _get_deps()
    try:
        report = await monitor.check_health()
        return ApiResponse(data=HealthOut(
            overall_status=report.overall_status.value if hasattr(report.overall_status, 'value') else str(report.overall_status),
            agent_health=[
                AgentHealthOut(
                    agent_name=ah.agent_name,
                    total_actions=ah.total_actions,
                    failures=ah.failures,
                    success_rate=ah.success_rate,
                    last_seen=str(ah.last_seen) if ah.last_seen else None,
                    status=ah.status.value if hasattr(ah.status, 'value') else str(ah.status),
                )
                for ah in report.agent_health
            ],
            anomalies=[
                AnomalyOut(
                    id=a.id,
                    detected_at=str(a.detected_at),
                    anomaly_type=a.anomaly_type,
                    severity=a.severity,
                    description=a.description,
                    related_traces=a.related_traces,
                )
                for a in report.anomalies
            ],
            total_traces=report.total_traces,
            traces_last_hour=report.traces_last_hour,
            failure_rate=report.failure_rate,
            mean_fitness=report.mean_fitness,
        ).model_dump())
    except Exception as e:
        return ApiResponse(data=HealthOut(overall_status="unknown").model_dump(), error=str(e))


@router.get("/health/anomalies")
async def get_anomalies(window_hours: float = 1) -> ApiResponse:
    _, _, monitor = _get_deps()
    anomalies = await monitor.detect_anomalies(window_hours=window_hours)
    return ApiResponse(data=[
        AnomalyOut(
            id=a.id,
            detected_at=str(a.detected_at),
            anomaly_type=a.anomaly_type,
            severity=a.severity,
            description=a.description,
            related_traces=a.related_traces,
        ).model_dump()
        for a in anomalies
    ])


@router.get("/overview")
async def overview() -> ApiResponse:
    """Combined swarm overview for the dashboard L1."""
    swarm, trace_store, monitor = _get_deps()

    agent_count = 0
    tasks_pending = 0
    tasks_running = 0
    tasks_completed = 0
    tasks_failed = 0
    uptime = 0.0

    try:
        status = await swarm.status()
        agent_count = len(status.agents)
        tasks_pending = status.tasks_pending
        tasks_running = status.tasks_running
        tasks_completed = status.tasks_completed
        tasks_failed = status.tasks_failed
        uptime = status.uptime_seconds
    except Exception:
        pass

    health_status = "unknown"
    try:
        report = await monitor.check_health()
        health_status = report.overall_status.value if hasattr(report.overall_status, 'value') else str(report.overall_status)
    except Exception:
        pass

    mean_fitness = 0.0
    evolution_entries = 0
    try:
        from dharma_swarm.archive import EvolutionArchive
        archive = EvolutionArchive()
        await archive.load()
        entries = await archive.list_entries()
        evolution_entries = len(entries)
        if entries:
            fitnesses = [e.fitness.weighted() for e in entries]
            mean_fitness = sum(fitnesses) / len(fitnesses)
    except Exception:
        pass

    stig_density = 0
    try:
        from dharma_swarm.stigmergy import StigmergyStore
        stig = StigmergyStore()
        stig_density = stig.density()
    except Exception:
        pass

    return ApiResponse(data=SwarmOverview(
        agent_count=agent_count,
        task_count=tasks_pending + tasks_running + tasks_completed + tasks_failed,
        tasks_pending=tasks_pending,
        tasks_running=tasks_running,
        tasks_completed=tasks_completed,
        tasks_failed=tasks_failed,
        mean_fitness=round(mean_fitness, 4),
        uptime_seconds=uptime,
        health_status=health_status,
        stigmergy_density=stig_density,
        evolution_entries=evolution_entries,
    ).model_dump())
