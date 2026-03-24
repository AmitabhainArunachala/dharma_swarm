"""Training flywheel — orchestration glue for the self-training pipeline.

Connects the 8 orphaned pipeline modules into a single async loop:

    trajectory_collector (LIVE, 120+ trajectories)
    → thinkodynamic_scorer (score quality)
    → strategy_reinforcer (UCB pattern selection)
    → dataset_builder (build training JSONL)
    → resource_scout (GPU procurement)
    → economic_engine (budget check)
    → model_registry (track generations)
    → docker_sandbox + sandbox_monitor (container governance)

Three sub-cycles with different cadences:
    1. Reinforcement (every 30 min) — score trajectories, extract strategy patterns
    2. Dataset build (every 6 hours) — accumulate high-quality samples into JSONL
    3. Training readiness (every 12 hours) — check budget, recommend GPU, log readiness

Designed to run as loop #10 in orchestrate_live.py. Follows the same async
pattern: shutdown_event, asyncio.wait_for, lazy imports, _log().

Inspired by Alibaba ALE's ROLL (arXiv:2512.24873) but governed by
thinkodynamic gates — the system trains BECAUSE governance approves,
not despite it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HOME = Path.home()
STATE_DIR = HOME / ".dharma"

# Sub-cycle intervals (seconds)
REINFORCE_INTERVAL = 1800    # 30 minutes
DATASET_INTERVAL = 21600     # 6 hours
READINESS_INTERVAL = 43200   # 12 hours

# Thresholds
MIN_TRAJECTORIES_FOR_REINFORCE = 5
MIN_TRAJECTORIES_FOR_DATASET = 20
MIN_THINKODYNAMIC_FOR_TRAINING = 0.7


def _log(system: str, msg: str) -> None:
    """Log with UTC timestamp — matches orchestrate_live pattern."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{system}] {msg}"
    print(line, flush=True)
    logger.info("[%s] %s", system, msg)


# ---------------------------------------------------------------------------
# Flywheel state — tracks cycle counts and last-run timestamps
# ---------------------------------------------------------------------------


@dataclass
class FlywheelState:
    """Persistent state for the training flywheel."""
    reinforce_cycles: int = 0
    dataset_builds: int = 0
    readiness_checks: int = 0
    total_trajectories_scored: int = 0
    total_patterns_extracted: int = 0
    last_reinforce: float = 0.0
    last_dataset_build: float = 0.0
    last_readiness_check: float = 0.0
    last_dataset_path: str = ""
    training_ready: bool = False
    recommended_gpu: str = ""
    recommended_budget: float = 0.0

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot for logging / API."""
        return {
            "reinforce_cycles": self.reinforce_cycles,
            "dataset_builds": self.dataset_builds,
            "readiness_checks": self.readiness_checks,
            "total_trajectories_scored": self.total_trajectories_scored,
            "total_patterns_extracted": self.total_patterns_extracted,
            "last_dataset_path": self.last_dataset_path,
            "training_ready": self.training_ready,
            "recommended_gpu": self.recommended_gpu,
            "recommended_budget": self.recommended_budget,
        }


# ---------------------------------------------------------------------------
# Sub-cycle 1: Strategy reinforcement (every 30 min)
# ---------------------------------------------------------------------------


def _run_reinforcement(state: FlywheelState) -> dict[str, Any]:
    """Load recent trajectories, score them, extract winning strategies.

    Synchronous — called from the async loop via run_in_executor if needed,
    but fast enough to run inline (no LLM calls, pure heuristic scoring).
    """
    from dharma_swarm.trajectory_collector import get_collector
    from dharma_swarm.strategy_reinforcer import StrategyReinforcer

    collector = get_collector()
    trajectories = collector.load_trajectories(success_only=True, limit=50)

    if len(trajectories) < MIN_TRAJECTORIES_FOR_REINFORCE:
        return {
            "skipped": True,
            "reason": f"only {len(trajectories)} trajectories (need {MIN_TRAJECTORIES_FOR_REINFORCE})",
        }

    reinforcer = StrategyReinforcer()
    result = reinforcer.reinforce_cycle(
        trajectories,
        min_thinkodynamic=0.3,  # Lower bar for pattern extraction
        top_k=5,
    )

    state.reinforce_cycles += 1
    state.total_trajectories_scored += result.trajectories_evaluated
    state.total_patterns_extracted += result.patterns_extracted
    state.last_reinforce = time.time()

    return {
        "skipped": False,
        "cycle": result.cycle_number,
        "evaluated": result.trajectories_evaluated,
        "patterns_extracted": result.patterns_extracted,
        "top_pattern": result.top_pattern,
        "total_patterns": reinforcer.pattern_count,
    }


# ---------------------------------------------------------------------------
# Sub-cycle 2: Dataset building (every 6 hours)
# ---------------------------------------------------------------------------


def _run_dataset_build(state: FlywheelState) -> dict[str, Any]:
    """Build a training dataset from accumulated trajectories + foundations."""
    from dharma_swarm.dataset_builder import DatasetBuilder, DatasetConfig

    gen_number = state.dataset_builds
    config = DatasetConfig(
        name=f"dharma-gen{gen_number}",
        min_thinkodynamic_score=MIN_THINKODYNAMIC_FOR_TRAINING,
        include_foundations=True,
        include_dreams=True,
        include_stigmergy=True,
        include_evolution=True,
        chat_format="openai",
    )

    builder = DatasetBuilder()
    stats = builder.build(config)

    if stats.total_samples < MIN_TRAJECTORIES_FOR_DATASET:
        return {
            "skipped": True,
            "reason": f"only {stats.total_samples} samples (need {MIN_TRAJECTORIES_FOR_DATASET})",
            "samples": stats.total_samples,
        }

    state.dataset_builds += 1
    state.last_dataset_build = time.time()
    state.last_dataset_path = stats.output_path

    return {
        "skipped": False,
        "dataset": config.name,
        "total_samples": stats.total_samples,
        "by_source": stats.by_source,
        "avg_quality": round(stats.avg_quality, 3),
        "output_path": stats.output_path,
        "build_time": round(stats.build_time_seconds, 1),
    }


# ---------------------------------------------------------------------------
# Sub-cycle 3: Training readiness check (every 12 hours)
# ---------------------------------------------------------------------------


def _run_readiness_check(state: FlywheelState) -> dict[str, Any]:
    """Check if budget allows training and recommend GPU configuration."""
    from dharma_swarm.economic_engine import EconomicEngine
    from dharma_swarm.resource_scout import ResourceScout
    from dharma_swarm.model_registry import ModelRegistry

    registry = ModelRegistry()
    scout = ResourceScout()
    economy = EconomicEngine()

    # Determine next generation number
    latest = registry.latest()
    next_gen = (latest.generation + 1) if latest else 0

    # Get budget
    econ_snapshot = economy.snapshot()
    training_budget = econ_snapshot.budget.training

    # Get recommendation
    if training_budget <= 0:
        state.training_ready = False
        return {
            "skipped": False,
            "ready": False,
            "reason": "no training budget allocated",
            "next_gen": next_gen,
            "training_budget": training_budget,
        }

    recommendation = scout.recommend_for_generation(
        gen=next_gen,
        budget_usd=training_budget,
    )

    state.readiness_checks += 1
    state.last_readiness_check = time.time()
    state.training_ready = recommendation.fits_in_budget
    state.recommended_gpu = recommendation.recommended_gpu or ""
    state.recommended_budget = recommendation.estimated_cost_usd

    result = {
        "skipped": False,
        "ready": recommendation.fits_in_budget,
        "next_gen": next_gen,
        "model_size_b": recommendation.model_size_b,
        "method": recommendation.method,
        "estimated_hours": round(recommendation.estimated_hours, 1),
        "estimated_cost": round(recommendation.estimated_cost_usd, 2),
        "training_budget": training_budget,
        "recommended_gpu": recommendation.recommended_gpu,
        "recommended_provider": recommendation.recommended_provider,
        "total_training_cost_so_far": round(registry.total_training_cost(), 2),
    }

    if recommendation.fits_in_budget and state.last_dataset_path:
        result["action"] = (
            f"READY TO TRAIN gen{next_gen}: "
            f"{recommendation.model_size_b:.0f}B via {recommendation.method} "
            f"on {recommendation.recommended_gpu} "
            f"(~${recommendation.estimated_cost_usd:.2f}, "
            f"~{recommendation.estimated_hours:.1f}h). "
            f"Dataset: {state.last_dataset_path}"
        )

    return result


# ---------------------------------------------------------------------------
# Main async loop — runs as task #10 in orchestrate_live.py
# ---------------------------------------------------------------------------


async def run_training_flywheel_loop(shutdown_event: asyncio.Event) -> None:
    """The training flywheel async loop.

    Runs three sub-cycles at different cadences:
    - Reinforcement every 30 min
    - Dataset build every 6 hours
    - Readiness check every 12 hours

    All sub-cycles are synchronous (no LLM calls) so they run inline
    without blocking the event loop significantly.
    """
    # Initial delay — let swarm, pulse, and other systems boot first
    await asyncio.sleep(60)

    _log("flywheel", "Training flywheel starting")
    _log("flywheel", f"  Reinforce interval: {REINFORCE_INTERVAL}s")
    _log("flywheel", f"  Dataset interval: {DATASET_INTERVAL}s")
    _log("flywheel", f"  Readiness interval: {READINESS_INTERVAL}s")

    state = FlywheelState()
    tick = 0

    while not shutdown_event.is_set():
        tick += 1
        now = time.time()

        # --- Eval verdict gate: check system health before reinforcing ---
        _fw_gate_ok = True
        try:
            import json as _fwj
            from datetime import datetime as _fwdt, timezone as _fwtz
            _fw_verdict_path = (
                STATE_DIR / "overnight"
                / _fwdt.now(_fwtz.utc).strftime("%Y-%m-%d")
                / "verdict.json"
            )
            if _fw_verdict_path.exists():
                _fw_vdata = _fwj.loads(_fw_verdict_path.read_text())
                if _fw_vdata.get("verdict") == "rollback":
                    _fw_gate_ok = False
                    _log("flywheel", "PAUSED: overnight ROLLBACK — skipping reinforcement")
        except Exception:
            pass

        # --- Sub-cycle 1: Strategy reinforcement ---
        if now - state.last_reinforce >= REINFORCE_INTERVAL and _fw_gate_ok:
            try:
                result = _run_reinforcement(state)
                if result.get("skipped"):
                    _log("flywheel", f"Reinforce skipped: {result.get('reason')}")
                else:
                    _log(
                        "flywheel",
                        f"Reinforce cycle {result['cycle']}: "
                        f"{result['evaluated']} trajectories → "
                        f"{result['patterns_extracted']} new patterns "
                        f"(total: {result['total_patterns']})",
                    )
            except Exception as e:
                _log("flywheel", f"Reinforce error: {e}")

        # --- Sub-cycle 2: Dataset building ---
        if now - state.last_dataset_build >= DATASET_INTERVAL:
            try:
                result = _run_dataset_build(state)
                if result.get("skipped"):
                    _log("flywheel", f"Dataset build skipped: {result.get('reason')}")
                else:
                    _log(
                        "flywheel",
                        f"Dataset built: {result['dataset']} — "
                        f"{result['total_samples']} samples, "
                        f"avg quality {result['avg_quality']}, "
                        f"{result['build_time']}s",
                    )
            except Exception as e:
                _log("flywheel", f"Dataset build error: {e}")

        # --- Sub-cycle 3: Training readiness ---
        if now - state.last_readiness_check >= READINESS_INTERVAL:
            try:
                result = _run_readiness_check(state)
                if result.get("ready"):
                    _log(
                        "flywheel",
                        f"TRAINING READY: {result.get('action', 'check logs')}",
                    )
                else:
                    _log(
                        "flywheel",
                        f"Training not ready: {result.get('reason', 'budget insufficient')} "
                        f"(gen{result['next_gen']}, budget=${result['training_budget']:.2f})",
                    )
            except Exception as e:
                _log("flywheel", f"Readiness check error: {e}")

        # Log flywheel heartbeat every 10 ticks
        if tick % 10 == 0:
            _log("flywheel", f"Heartbeat: {state.snapshot()}")

        # Sleep until next check — use the shortest interval
        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=REINFORCE_INTERVAL
            )
            break
        except asyncio.TimeoutError:
            pass

    _log("flywheel", f"Training flywheel stopped (state: {state.snapshot()})")


# ---------------------------------------------------------------------------
# Standalone entry point (for testing outside orchestrator)
# ---------------------------------------------------------------------------


def get_flywheel_state() -> FlywheelState:
    """Get current flywheel state (for API / status endpoints)."""
    # In production, this would read from shared state or the running loop.
    # For now, return a fresh state that callers can populate.
    return FlywheelState()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )
    event = asyncio.Event()
    try:
        asyncio.run(run_training_flywheel_loop(event))
    except KeyboardInterrupt:
        event.set()
