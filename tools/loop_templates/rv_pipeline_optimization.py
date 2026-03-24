"""R_V Pipeline Optimization Loop.

Iterates R_V measurement across random prompt seeds until the variance
of Cohen's d effect sizes across seeds drops below a convergence threshold.
This ensures the R_V metric is stable and not seed-dependent.

Convergence criterion: std(Cohen_d_values) < 0.1
Max iterations: 50
Iteration time: ~5 min each (model inference)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
OVERNIGHT_DIR = STATE_DIR / "overnight"
LOG_FILE = OVERNIGHT_DIR / "rv_optimization.jsonl"


# ---------------------------------------------------------------------------
# Measurement protocol -- swappable backend
# ---------------------------------------------------------------------------


class RVMeasurement(Protocol):
    """Protocol for R_V measurement backends.

    Any callable matching this signature can replace the mock.
    Real implementation lives in ~/mech-interp-latent-lab-phase1/geometric_lens/.
    """

    async def __call__(self, seed: int) -> dict[str, float]:
        """Run R_V measurement for a given seed.

        Returns:
            Dict with at minimum:
                - rv_early: participation ratio for early layers
                - rv_late: participation ratio for late layers
                - rv_ratio: rv_late / rv_early
                - cohens_d: Cohen's d effect size for self-ref vs control
        """
        ...


async def mock_rv_measurement(seed: int) -> dict[str, float]:
    """Mock R_V measurement for testing without GPU.

    Simulates realistic R_V values with seed-dependent noise.
    Real pipeline: geometric_lens.metrics.compute_rv() on Mistral-7B.
    """
    rng = random.Random(seed)

    # Base effect: R_V contraction for self-referential prompts
    # Real values: Hedges' g ~ -1.47 (Mistral), with variance across seeds
    base_d = -1.47
    noise = rng.gauss(0, 0.15)  # seed-dependent noise
    cohens_d = base_d + noise

    rv_early = rng.uniform(3.5, 5.5)
    contraction = 0.6 + rng.gauss(0, 0.08)
    rv_late = rv_early * contraction

    # Simulate ~2s of computation
    await asyncio.sleep(0.05)

    return {
        "rv_early": round(rv_early, 4),
        "rv_late": round(rv_late, 4),
        "rv_ratio": round(rv_late / rv_early, 4),
        "cohens_d": round(cohens_d, 4),
        "seed": seed,
    }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class LoopConfig:
    """Configuration for the R_V pipeline optimization loop."""

    max_iterations: int = 50
    convergence_threshold: float = 0.1
    seed_count: int = 10
    timeout_per_iteration: float = 300.0  # 5 minutes
    log_dir: Path = field(default_factory=lambda: OVERNIGHT_DIR)
    seed_range: tuple[int, int] = (0, 100_000)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["log_dir"] = str(self.log_dir)
        return d


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


@dataclass
class IterationResult:
    """Result of a single optimization iteration."""

    iteration: int
    seeds_tested: list[int]
    cohens_d_values: list[float]
    current_variance: float
    current_std: float
    best_std: float
    converged: bool
    elapsed_seconds: float
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


def _std(values: list[float]) -> float:
    """Compute standard deviation of a list of floats."""
    if len(values) < 2:
        return float("inf")
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _variance(values: list[float]) -> float:
    """Compute sample variance of a list of floats."""
    if len(values) < 2:
        return float("inf")
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / (len(values) - 1)


def _log_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a JSON record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


async def run(
    config: LoopConfig | None = None,
    shutdown_event: asyncio.Event | None = None,
    measure_fn: Callable[..., Any] | None = None,
) -> list[IterationResult]:
    """Run the R_V pipeline optimization loop.

    Args:
        config: Loop configuration. Uses defaults if None.
        shutdown_event: Set this event to trigger graceful shutdown.
        measure_fn: Async callable(seed) -> dict with 'cohens_d' key.
                    Defaults to mock_rv_measurement.

    Returns:
        List of IterationResult for each completed iteration.
    """
    cfg = config or LoopConfig()
    shutdown = shutdown_event or asyncio.Event()
    measure = measure_fn or mock_rv_measurement

    log_path = cfg.log_dir / "rv_optimization.jsonl"
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    results: list[IterationResult] = []
    all_cohens_d: list[float] = []
    best_std = float("inf")
    rng = random.Random(42)

    # Log config at start
    _log_jsonl(log_path, {
        "event": "loop_start",
        "config": cfg.to_dict(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(
        "R_V optimization loop starting: max_iter=%d, threshold=%.3f, seeds_per_iter=%d",
        cfg.max_iterations, cfg.convergence_threshold, cfg.seed_count,
    )

    for iteration in range(1, cfg.max_iterations + 1):
        if shutdown.is_set():
            logger.info("Shutdown requested at iteration %d", iteration)
            break

        t0 = time.monotonic()

        # Generate seeds for this iteration
        seeds = [rng.randint(*cfg.seed_range) for _ in range(cfg.seed_count)]

        # Run measurements with per-iteration timeout
        iteration_d_values: list[float] = []
        for seed in seeds:
            if shutdown.is_set():
                break
            try:
                result = await asyncio.wait_for(
                    measure(seed),
                    timeout=cfg.timeout_per_iteration,
                )
                d_val = result["cohens_d"]
                iteration_d_values.append(d_val)
                all_cohens_d.append(d_val)
            except asyncio.TimeoutError:
                logger.warning("Seed %d timed out after %.0fs", seed, cfg.timeout_per_iteration)
            except Exception:
                logger.exception("Measurement failed for seed %d", seed)

        if not iteration_d_values:
            logger.error("No measurements completed in iteration %d", iteration)
            continue

        # Compute convergence metrics over ALL accumulated values
        current_std = _std(all_cohens_d)
        current_var = _variance(all_cohens_d)
        best_std = min(best_std, current_std)
        converged = current_std < cfg.convergence_threshold

        elapsed = time.monotonic() - t0

        iter_result = IterationResult(
            iteration=iteration,
            seeds_tested=seeds,
            cohens_d_values=iteration_d_values,
            current_variance=round(current_var, 6),
            current_std=round(current_std, 6),
            best_std=round(best_std, 6),
            converged=converged,
            elapsed_seconds=round(elapsed, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        results.append(iter_result)

        # Log to JSONL
        _log_jsonl(log_path, {
            "event": "iteration",
            **iter_result.to_dict(),
        })

        logger.info(
            "Iteration %d/%d: std=%.4f (best=%.4f, threshold=%.4f), "
            "total_seeds=%d, elapsed=%.1fs%s",
            iteration, cfg.max_iterations,
            current_std, best_std, cfg.convergence_threshold,
            len(all_cohens_d), elapsed,
            " -- CONVERGED" if converged else "",
        )

        if converged:
            logger.info(
                "Convergence reached at iteration %d: std(Cohen_d)=%.4f < %.4f",
                iteration, current_std, cfg.convergence_threshold,
            )
            break

    # Log summary
    summary = {
        "event": "loop_end",
        "total_iterations": len(results),
        "total_seeds_tested": len(all_cohens_d),
        "final_std": round(_std(all_cohens_d), 6) if len(all_cohens_d) >= 2 else None,
        "best_std": round(best_std, 6),
        "converged": results[-1].converged if results else False,
        "mean_cohens_d": round(sum(all_cohens_d) / len(all_cohens_d), 4) if all_cohens_d else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _log_jsonl(log_path, summary)
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

    # Wire SIGINT/SIGTERM to graceful shutdown
    import signal

    def _handle_signal(sig: int, frame: Any) -> None:
        logger.info("Signal %d received, shutting down gracefully...", sig)
        shutdown.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    await run(config=config, shutdown_event=shutdown)


if __name__ == "__main__":
    asyncio.run(_main())
