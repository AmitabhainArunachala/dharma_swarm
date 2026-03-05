"""Canary deployment evaluation for swarm evolution entries.

Compares canary fitness against an entry's baseline fitness and decides
whether to PROMOTE, ROLLBACK, or DEFER the change.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from dharma_swarm.archive import EvolutionArchive


# ---------------------------------------------------------------------------
# Decision enum
# ---------------------------------------------------------------------------


class CanaryDecision(str, Enum):
    """Outcome of a canary evaluation."""

    PROMOTE = "promote"
    ROLLBACK = "rollback"
    DEFER = "defer"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class CanaryConfig(BaseModel):
    """Thresholds governing canary decisions.

    Attributes:
        promote_threshold: Minimum positive delta to trigger promotion.
        rollback_threshold: Maximum negative delta before rollback fires.
        min_observations: Minimum observation count (reserved for future use).
    """

    promote_threshold: float = 0.05
    rollback_threshold: float = -0.02
    min_observations: int = 1


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


class CanaryResult(BaseModel):
    """Detailed outcome of a single canary evaluation."""

    decision: CanaryDecision
    baseline_fitness: float
    canary_fitness: float
    delta: float
    reason: str


# ---------------------------------------------------------------------------
# Deployer
# ---------------------------------------------------------------------------


class CanaryDeployer:
    """Evaluate canary fitness against archive baselines.

    Args:
        archive: The evolution archive containing baseline entries.
        config: Optional canary configuration; uses defaults if omitted.
    """

    def __init__(
        self,
        archive: EvolutionArchive,
        config: CanaryConfig | None = None,
    ) -> None:
        self._archive = archive
        self._config = config or CanaryConfig()

    async def evaluate_canary(
        self, entry_id: str, canary_fitness: float
    ) -> CanaryResult:
        """Compare *canary_fitness* against the baseline for *entry_id*.

        Args:
            entry_id: Archive entry to use as baseline.
            canary_fitness: Observed fitness of the canary deployment.

        Returns:
            A ``CanaryResult`` encoding the decision and supporting data.

        Raises:
            KeyError: If *entry_id* is not present in the archive.
        """
        entry = await self._archive.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"Entry {entry_id!r} not found in archive")

        baseline_fitness = entry.fitness.weighted()
        delta = canary_fitness - baseline_fitness

        if delta > self._config.promote_threshold:
            decision = CanaryDecision.PROMOTE
            reason = (
                f"Delta {delta:+.4f} exceeds promote threshold "
                f"{self._config.promote_threshold}"
            )
        elif delta < self._config.rollback_threshold:
            decision = CanaryDecision.ROLLBACK
            reason = (
                f"Delta {delta:+.4f} below rollback threshold "
                f"{self._config.rollback_threshold}"
            )
        else:
            decision = CanaryDecision.DEFER
            reason = (
                f"Delta {delta:+.4f} within neutral zone "
                f"[{self._config.rollback_threshold}, "
                f"{self._config.promote_threshold}]"
            )

        return CanaryResult(
            decision=decision,
            baseline_fitness=baseline_fitness,
            canary_fitness=canary_fitness,
            delta=delta,
            reason=reason,
        )

    async def promote(self, entry_id: str) -> bool:
        """Mark *entry_id* as promoted in the archive.

        Returns:
            True if the entry was found and updated, False otherwise.
        """
        entry = await self._archive.get_entry(entry_id)
        if entry is None:
            return False
        await self._archive.update_status(entry_id, "promoted")
        return True

    async def rollback(
        self, entry_id: str, reason: str = "Canary check failed"
    ) -> bool:
        """Mark *entry_id* as rolled back in the archive.

        Returns:
            True if the entry was found and updated, False otherwise.
        """
        return await self._archive.rollback_entry(entry_id, reason)
