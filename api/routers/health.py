"""Health + anomaly detection endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from api.models import (
    AgentHealthOut,
    AnomalyOut,
    AnomalyListResponse,
    HealthOut,
    HealthResponse,
    RuntimeHealthOut,
    SwarmOverview,
    SwarmOverviewResponse,
)
from dharma_swarm.runtime_artifacts import build_runtime_health_payload
from dharma_swarm.runtime_paths import resolve_runtime_paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])
_RUNTIME_PATHS = resolve_runtime_paths()


def _get_deps():
    """Lazy-load dharma_swarm dependencies."""
    from api.main import get_swarm, get_trace_store, get_monitor
    return get_swarm(), get_trace_store(), get_monitor()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    _, trace_store, monitor = _get_deps()
    runtime_payload = build_runtime_health_payload(_RUNTIME_PATHS.state_root)
    try:
        report = await monitor.check_health()
        return HealthResponse(data=HealthOut(
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
            runtime=RuntimeHealthOut(**runtime_payload),
        ).model_dump())
    except Exception as e:
        return HealthResponse(
            data=HealthOut(
                overall_status="unknown",
                runtime=RuntimeHealthOut(**runtime_payload),
            ).model_dump(),
            error=str(e),
        )


@router.get("/health/anomalies", response_model=AnomalyListResponse)
async def get_anomalies(window_hours: float = 1) -> AnomalyListResponse:
    _, _, monitor = _get_deps()
    anomalies = await monitor.detect_anomalies(window_hours=window_hours)
    return AnomalyListResponse(data=[
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


@router.get("/overview", response_model=SwarmOverviewResponse)
async def overview() -> SwarmOverviewResponse:
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
        logger.debug("Failed to fetch swarm status for overview", exc_info=True)

    health_status = "unknown"
    try:
        report = await monitor.check_health()
        health_status = report.overall_status.value if hasattr(report.overall_status, 'value') else str(report.overall_status)
    except Exception:
        logger.debug("Failed to check health for overview", exc_info=True)

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
        logger.debug("Failed to load evolution archive for overview", exc_info=True)

    stig_density = 0
    try:
        from dharma_swarm.stigmergy import StigmergyStore
        stig = StigmergyStore()
        stig_density = stig.density()
    except Exception:
        logger.debug("Failed to read stigmergy density for overview", exc_info=True)

    return SwarmOverviewResponse(data=SwarmOverview(
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
