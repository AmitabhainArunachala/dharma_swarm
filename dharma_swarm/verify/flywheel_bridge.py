"""Bridge: dharma_verify reviews → trajectory collector → training flywheel.

Every PR review becomes a trajectory that feeds the self-training pipeline.
The scorer dimensions become fitness signals. Over time, the system learns
what good code looks like from its own review history.

This is the economic engine: reviews are both the PRODUCT (value to user)
and the TRAINING DATA (value to dharma_swarm's own evolution).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def record_review_trajectory(
    *,
    pr_id: str,
    diff_text: str,
    review_text: str,
    score: float,
    dimensions: dict[str, float],
    verdict: str,
    files_reviewed: list[str],
    model: str = "heuristic",
    tokens_used: int = 0,
    latency_ms: float = 0.0,
) -> str | None:
    """Record a PR review as a trajectory for the training flywheel.

    Returns the trajectory_id if successful, None on failure.
    Never raises — review delivery must not fail because telemetry fails.
    """
    try:
        from dharma_swarm.trajectory_collector import (
            Trajectory,
            TrajectoryChunk,
            TrajectoryCollector,
            TrajectoryOutcome,
        )

        collector = TrajectoryCollector()
        traj = collector.start_trajectory(
            agent_id="dharma_verify",
            task_id=f"review_{pr_id}",
            task_title=f"Review PR {pr_id}",
        )

        # The diff is the "prompt", the review is the "response"
        collector.add_chunk(
            traj.trajectory_id,
            TrajectoryChunk(
                agent_id="dharma_verify",
                task_id=f"review_{pr_id}",
                prompt=diff_text[:5000],  # Truncate for storage
                response=review_text[:3000],
                model=model,
                provider="dharma_verify",
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            ),
        )

        collector.complete_trajectory(
            traj.trajectory_id,
            TrajectoryOutcome(
                success=score >= 0.5,
                result_preview=f"Verdict: {verdict} (score: {score:.2f})",
                fitness_score=dimensions,
            ),
        )

        logger.info(
            "Recorded review trajectory %s for PR %s (score=%.2f)",
            traj.trajectory_id, pr_id, score,
        )
        return traj.trajectory_id

    except Exception as e:
        logger.warning("Failed to record review trajectory: %s", e)
        return None


def record_review_cost(
    *,
    pr_id: str,
    tokens_used: int,
    model: str,
    cost_usd: float = 0.0,
) -> None:
    """Record the economic cost of a review for the economic engine.

    Never raises — cost tracking must not block review delivery.
    """
    try:
        from dharma_swarm.economic_engine import EconomicEngine

        engine = EconomicEngine()
        engine.record_revenue_event(
            event_type="review",
            amount=0.0,  # Free tier for now
            description=f"PR {pr_id} review ({tokens_used} tokens, {model})",
            metadata={
                "pr_id": pr_id,
                "tokens_used": tokens_used,
                "model": model,
                "cost_usd": cost_usd,
            },
        )
    except ImportError:
        pass  # EconomicEngine may not exist yet
    except Exception as e:
        logger.warning("Failed to record review cost: %s", e)
