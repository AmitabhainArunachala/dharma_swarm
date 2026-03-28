"""Conductor Wake Cycle Efficiency Loop.

Simulates 60 minutes of conductor heartbeats. Measures "waste" as
heartbeat cycles where the conductor wakes but has no work to do.
Iterates wake_interval tuning until waste approaches zero.

Convergence criterion: waste_ratio < 0.05 (less than 5% idle wakes)
Max iterations: 30
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from tools.loop_templates.progress_protocol import LoopProgressTracker, ProgressSnapshot
except ImportError:  # pragma: no cover - direct script fallback
    from progress_protocol import LoopProgressTracker, ProgressSnapshot

STATE_DIR = Path.home() / ".dharma"
OVERNIGHT_DIR = STATE_DIR / "overnight"
LOG_FILE = OVERNIGHT_DIR / "conductor_efficiency.jsonl"

# Simulation defaults
SIMULATION_MINUTES: float = 60.0
INITIAL_WAKE_INTERVAL: float = 60.0  # seconds


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class LoopConfig:
    """Configuration for the conductor efficiency loop."""

    max_iterations: int = 30
    convergence_threshold: float = 0.05  # waste_ratio target
    simulation_minutes: float = SIMULATION_MINUTES
    initial_wake_interval: float = INITIAL_WAKE_INTERVAL
    min_wake_interval: float = 5.0   # floor: never poll faster than 5s
    max_wake_interval: float = 600.0  # ceiling: never sleep longer than 10min
    max_avg_latency: float = 120.0
    max_missed_work: int = 0
    log_dir: Path = field(default_factory=lambda: OVERNIGHT_DIR)
    work_arrival_seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["log_dir"] = str(self.log_dir)
        return d


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


@dataclass
class SimulationResult:
    """Result of a single 60-minute simulation."""

    wake_interval: float
    total_wakes: int
    productive_wakes: int
    idle_wakes: int
    waste_ratio: float
    work_items_completed: int
    work_items_missed: int
    avg_response_latency: float  # seconds between work arriving and being picked up


@dataclass
class IterationResult:
    """Result of a single optimization iteration."""

    iteration: int
    wake_interval_tested: float
    simulation: dict[str, Any]
    waste_ratio: float
    best_waste_ratio: float
    best_interval: float
    search_low: float
    search_high: float
    converged: bool
    elapsed_seconds: float
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Work arrival model
# ---------------------------------------------------------------------------


def generate_work_schedule(
    duration_seconds: float,
    seed: int = 42,
) -> list[float]:
    """Generate a realistic work arrival schedule.

    Models work arriving in bursts (Poisson process with time-varying rate).
    Returns sorted list of timestamps (in seconds) when work items arrive.

    Work pattern:
    - Base rate: ~1 item every 3-5 minutes
    - Burst periods: ~1 item every 30-60 seconds for 2-5 minutes
    - Quiet periods: no work for 5-15 minutes
    """
    rng = random.Random(seed)
    arrivals: list[float] = []
    t = 0.0

    while t < duration_seconds:
        # Decide current regime
        regime = rng.random()

        if regime < 0.2:
            # Quiet period: 5-15 minutes
            quiet_duration = rng.uniform(300, 900)
            t += quiet_duration
        elif regime < 0.4:
            # Burst period: 2-5 minutes of frequent work
            burst_end = t + rng.uniform(120, 300)
            while t < burst_end and t < duration_seconds:
                arrivals.append(t)
                t += rng.expovariate(1.0 / rng.uniform(30, 60))
        else:
            # Normal: one item, then wait 3-5 minutes
            arrivals.append(t)
            t += rng.expovariate(1.0 / rng.uniform(180, 300))

    return sorted(a for a in arrivals if a < duration_seconds)


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------


def simulate_conductor(
    wake_interval: float,
    work_schedule: list[float],
    duration_seconds: float,
) -> SimulationResult:
    """Simulate a conductor running for the given duration.

    The conductor wakes every wake_interval seconds. If work has arrived
    since the last wake, the wake is productive. Otherwise, it is idle.

    Args:
        wake_interval: Seconds between conductor wake cycles.
        work_schedule: Sorted list of work arrival timestamps (seconds).
        duration_seconds: Total simulation duration in seconds.

    Returns:
        SimulationResult with efficiency metrics.
    """
    total_wakes = 0
    productive_wakes = 0
    idle_wakes = 0
    work_completed = 0
    response_latencies: list[float] = []

    # Track which work items have been consumed
    work_idx = 0
    t = wake_interval  # First wake after one interval

    while t <= duration_seconds:
        total_wakes += 1

        # Collect all work that arrived since last wake
        items_available = 0
        while work_idx < len(work_schedule) and work_schedule[work_idx] <= t:
            arrival = work_schedule[work_idx]
            latency = t - arrival
            response_latencies.append(latency)
            items_available += 1
            work_idx += 1

        if items_available > 0:
            productive_wakes += 1
            work_completed += items_available
        else:
            idle_wakes += 1

        t += wake_interval

    # Work items that arrived but were never picked up (after last wake)
    work_missed = len(work_schedule) - work_idx

    waste_ratio = idle_wakes / total_wakes if total_wakes > 0 else 0.0
    avg_latency = (
        sum(response_latencies) / len(response_latencies)
        if response_latencies else 0.0
    )

    return SimulationResult(
        wake_interval=round(wake_interval, 2),
        total_wakes=total_wakes,
        productive_wakes=productive_wakes,
        idle_wakes=idle_wakes,
        waste_ratio=round(waste_ratio, 4),
        work_items_completed=work_completed,
        work_items_missed=work_missed,
        avg_response_latency=round(avg_latency, 2),
    )


# ---------------------------------------------------------------------------
# JSONL logging
# ---------------------------------------------------------------------------


def _log_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a JSON record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _composite_loss(sim: SimulationResult, cfg: LoopConfig) -> float:
    """Combine waste, misses, and latency into a single optimization target."""
    miss_penalty = sim.work_items_missed * 2.0
    latency_penalty = sim.avg_response_latency / max(cfg.max_avg_latency, 1.0)
    return round(sim.waste_ratio + miss_penalty + latency_penalty, 6)


def _service_level_met(sim: SimulationResult, cfg: LoopConfig) -> bool:
    """True when wake tuning does not sacrifice responsiveness."""
    return (
        sim.work_items_missed <= cfg.max_missed_work
        and sim.avg_response_latency <= cfg.max_avg_latency
    )


def _next_best_task(sim: SimulationResult, cfg: LoopConfig) -> tuple[str, list[str]]:
    """Bounded next step recommendation for the operator."""
    notes: list[str] = []
    if sim.work_items_missed > cfg.max_missed_work:
        notes.append("Service-level failure: work items were missed.")
        return "Shorten the wake interval until missed work returns to zero.", notes
    if sim.avg_response_latency > cfg.max_avg_latency:
        notes.append("Average pickup latency exceeded the service-level target.")
        return "Shorten the wake interval and replay the same schedule.", notes
    if sim.waste_ratio >= cfg.convergence_threshold:
        notes.append("Idle wake ratio is still above target.")
        return "Keep shortening the wake interval until idle wakes fall below the threshold.", notes
    notes.append("Current interval satisfies both waste and service constraints.")
    return "Try a slightly longer interval and verify service levels remain intact.", notes


# ---------------------------------------------------------------------------
# Core loop -- binary search on wake_interval
# ---------------------------------------------------------------------------


async def run(
    config: LoopConfig | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> list[IterationResult]:
    """Run the conductor efficiency optimization loop.

    Uses binary search on wake_interval to find the longest interval
    that keeps waste_ratio below the convergence threshold.
    Longer intervals are preferred because they reduce resource usage.

    Args:
        config: Loop configuration. Uses defaults if None.
        shutdown_event: Set this event to trigger graceful shutdown.

    Returns:
        List of IterationResult for each completed iteration.
    """
    cfg = config or LoopConfig()
    shutdown = shutdown_event or asyncio.Event()

    log_path = cfg.log_dir / "conductor_efficiency.jsonl"
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    duration_seconds = cfg.simulation_minutes * 60.0

    # Pre-generate work schedule (deterministic for reproducibility)
    work_schedule = generate_work_schedule(duration_seconds, seed=cfg.work_arrival_seed)

    results: list[IterationResult] = []
    best_waste_ratio = 1.0
    best_interval = cfg.initial_wake_interval
    best_loss = float("inf")
    best_converged = False
    tracker = LoopProgressTracker("conductor_efficiency", cfg.log_dir)

    # Binary search bounds
    search_low = cfg.min_wake_interval
    search_high = cfg.max_wake_interval

    # Log config at start
    _log_jsonl(log_path, {
        "event": "loop_start",
        "config": cfg.to_dict(),
        "work_items_total": len(work_schedule),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    tracker.start(
        objective="Minimize wasted conductor wakes without missing work or violating latency targets.",
        config=cfg.to_dict(),
    )

    logger.info(
        "Conductor efficiency loop starting: max_iter=%d, threshold=%.3f, "
        "sim_minutes=%.0f, work_items=%d",
        cfg.max_iterations, cfg.convergence_threshold,
        cfg.simulation_minutes, len(work_schedule),
    )

    for iteration in range(1, cfg.max_iterations + 1):
        if shutdown.is_set():
            logger.info("Shutdown requested at iteration %d", iteration)
            break

        t0 = time.monotonic()

        # Binary search: test the midpoint
        test_interval = (search_low + search_high) / 2.0

        # Run simulation (offload to thread to avoid blocking the event loop)
        sim = await asyncio.to_thread(
            simulate_conductor,
            test_interval,
            work_schedule,
            duration_seconds,
        )

        waste = sim.waste_ratio
        service_ok = _service_level_met(sim, cfg)
        converged = waste < cfg.convergence_threshold and service_ok
        loss = _composite_loss(sim, cfg)

        # Update best
        if loss < best_loss:
            best_loss = loss
        if service_ok and waste < best_waste_ratio:
            best_waste_ratio = waste
            best_interval = test_interval
        if converged:
            best_converged = True

        # Binary search logic:
        # We only accept longer sleeps when service levels are intact and waste is acceptable.
        if not service_ok or waste >= cfg.convergence_threshold:
            search_high = test_interval
        else:
            search_low = test_interval

        elapsed = time.monotonic() - t0

        iter_result = IterationResult(
            iteration=iteration,
            wake_interval_tested=round(test_interval, 2),
            simulation=asdict(sim),
            waste_ratio=waste,
            best_waste_ratio=round(best_waste_ratio, 4),
            best_interval=round(best_interval, 2),
            search_low=round(search_low, 2),
            search_high=round(search_high, 2),
            converged=converged,
            elapsed_seconds=round(elapsed, 4),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        results.append(iter_result)
        _log_jsonl(log_path, {"event": "iteration", **iter_result.to_dict()})
        next_best_task, notes = _next_best_task(sim, cfg)
        tracker.record(ProgressSnapshot(
            loop_name="conductor_efficiency",
            objective="Tune conductor wake intervals for low waste and acceptable responsiveness.",
            status="converged" if converged else ("service_violation" if not service_ok else "running"),
            iteration=iteration,
            target_metric={
                "waste_ratio": cfg.convergence_threshold,
                "max_avg_latency": cfg.max_avg_latency,
                "max_missed_work": cfg.max_missed_work,
            },
            current_metric={
                "waste_ratio": sim.waste_ratio,
                "avg_response_latency": sim.avg_response_latency,
                "work_items_missed": sim.work_items_missed,
                "composite_loss": loss,
            },
            best_metric={
                "best_waste_ratio": round(best_waste_ratio, 4),
                "best_interval": round(best_interval, 2),
                "best_loss": best_loss,
            },
            verifier={
                "passed": converged,
                "service_level_met": service_ok,
            },
            artifact_delta={
                "metrics_updated": 3,
                "interval_tested": round(test_interval, 2),
            },
            next_best_task=next_best_task,
            progress_delta=round(max(1.0 - loss, 0.0), 6),
            notes=notes,
        ))

        logger.info(
            "Iteration %d/%d: interval=%.1fs, waste=%.4f (best=%.4f @ %.1fs), "
            "wakes=%d (prod=%d, idle=%d), search=[%.1f, %.1f]",
            iteration, cfg.max_iterations,
            test_interval, waste, best_waste_ratio, best_interval,
            sim.total_wakes, sim.productive_wakes, sim.idle_wakes,
            search_low, search_high,
        )

        # Stop if search range is narrow enough (within 1 second)
        if (search_high - search_low) < 1.0:
            logger.info(
                "Search converged: interval range [%.1f, %.1f] < 1s",
                search_low, search_high,
            )
            break

    # Log summary
    summary = {
        "event": "loop_end",
        "total_iterations": len(results),
        "best_waste_ratio": round(best_waste_ratio, 4),
        "best_interval": round(best_interval, 2),
        "converged": best_converged,
        "best_loss": best_loss,
        "final_search_range": [round(search_low, 2), round(search_high, 2)],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _log_jsonl(log_path, summary)
    tracker.finish(summary)
    logger.info("Loop complete: %s", json.dumps(summary, indent=2))

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    """Entry point for direct execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    config = LoopConfig()
    shutdown = asyncio.Event()

    import signal as _signal

    def _handle_signal(sig: int, frame: Any) -> None:
        logger.info("Signal %d received, shutting down gracefully...", sig)
        shutdown.set()

    _signal.signal(_signal.SIGINT, _handle_signal)
    _signal.signal(_signal.SIGTERM, _handle_signal)

    await run(config=config, shutdown_event=shutdown)


if __name__ == "__main__":
    asyncio.run(_main())
