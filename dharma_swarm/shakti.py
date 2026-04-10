"""Shakti perception layer -- creative autonomy at every level.

Four energies from Sri Aurobindo mapped to computational perception.
Each agent carries a Shakti loop that scans for emergent patterns,
proposes local actions, and escalates system-level observations.

The four energies:
  - **Maheshwari**: Vision, architecture, strategic direction.
  - **Mahakali**: Force, decisive action, breakthrough.
  - **Mahalakshmi**: Harmony, beauty, integration.
  - **Mahasaraswati**: Precision, correctness, meticulous detail.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.stigmergy import StigmergyStore

# ---------------------------------------------------------------------------
# Energy taxonomy
# ---------------------------------------------------------------------------


class ShaktiEnergy(str, Enum):
    """The four Shaktis -- creative energies governing perception."""

    MAHESHWARI = "maheshwari"
    MAHAKALI = "mahakali"
    MAHALAKSHMI = "mahalakshmi"
    MAHASARASWATI = "mahasaraswati"
    KRIYA = "kriya"
    JNANA = "jnana"
    ICCHA = "iccha"

    def __str__(self) -> str:
        return self.value


_ENERGY_KEYWORDS: dict[ShaktiEnergy, frozenset[str]] = {
    ShaktiEnergy.MAHESHWARI: frozenset({
        "vision", "pattern", "architecture", "design", "direction",
        "strategy", "purpose", "telos", "emergence", "possibility",
    }),
    ShaktiEnergy.MAHAKALI: frozenset({
        "force", "action", "execute", "deploy", "speed",
        "urgency", "breakthrough", "destroy", "clear", "decisive",
    }),
    ShaktiEnergy.MAHALAKSHMI: frozenset({
        "harmony", "balance", "beauty", "elegant", "integrate",
        "flow", "rhythm", "proportion", "grace", "coherence",
    }),
    ShaktiEnergy.MAHASARASWATI: frozenset({
        "precision", "detail", "exact", "correct", "careful",
        "thorough", "meticulous", "accurate", "validate", "verify",
    }),
}


# ---------------------------------------------------------------------------
# Perception model
# ---------------------------------------------------------------------------


class ShaktiPerception(BaseModel):
    """A single observation through the Shakti lens."""

    id: str = Field(default_factory=_new_id)
    observation: str
    connection: str
    energy: ShaktiEnergy
    proposal: str | None = None
    impact_level: str = "local"  # "local" | "module" | "system"
    salience: float = 0.5
    timestamp: datetime = Field(default_factory=_utc_now)

    def __init__(self, *args: Any, **data: Any) -> None:
        if args:
            names = ("energy", "observation", "file_path", "impact", "salience", "connections")
            if len(args) > len(names):
                raise TypeError(
                    f"ShaktiPerception accepts at most {len(names)} positional arguments"
                )
            for name, value in zip(names, args, strict=False):
                data.setdefault(name, value)
        super().__init__(**data)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if not normalized.get("connection") and normalized.get("file_path"):
            normalized["connection"] = normalized["file_path"]
        if not normalized.get("connection"):
            normalized["connection"] = "system"
        if "impact" in normalized and "impact_level" not in normalized:
            normalized["impact_level"] = normalized["impact"]
        return normalized

    @property
    def file_path(self) -> str:
        return self.connection

    @property
    def impact(self) -> str:
        return self.impact_level


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_energy(observation: str) -> ShaktiEnergy:
    """Classify an observation into a Shakti energy via keyword matching.

    Lowercases the observation and counts keyword hits for each energy.
    Returns the energy with the most matches.  Defaults to MAHASARASWATI
    (precision as the conservative fallback).
    """
    words = observation.lower().split()
    word_set = set(words)

    best_energy = ShaktiEnergy.MAHASARASWATI
    best_count = 0

    for energy, keywords in _ENERGY_KEYWORDS.items():
        count = len(word_set & keywords)
        if count > best_count:
            best_count = count
            best_energy = energy

    return best_energy


# ---------------------------------------------------------------------------
# Shakti Loop
# ---------------------------------------------------------------------------


class ShaktiLoop:
    """Perception loop wired into a stigmergy store.

    Scans hot paths and high-salience marks, classifies them into
    Shakti energies, and returns structured perceptions.  Local
    perceptions can be proposed immediately; module/system-level
    ones are escalated for orchestration.
    """

    def __init__(
        self,
        stigmergy: StigmergyStore,
        context_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._stigmergy = stigmergy
        self._context_fn = context_fn

    # -- perceive ------------------------------------------------------------

    async def perceive(
        self,
        current_context: str = "",
        agent_role: str = "general",
    ) -> list[ShaktiPerception]:
        """Scan stigmergy for emergent patterns and return perceptions."""
        perceptions: list[ShaktiPerception] = []

        # Hot paths (files with heavy recent activity)
        hot = await self._stigmergy.hot_paths(window_hours=24)
        for path, count in hot:
            obs = f"Hot path: {path} ({count} touches)"
            energy = classify_energy(obs)
            impact = "system" if count > 10 else "module" if count > 5 else "local"
            salience = min(count / 20.0, 1.0)
            perceptions.append(ShaktiPerception(
                observation=obs,
                connection=path,
                energy=energy,
                impact_level=impact,
                salience=salience,
            ))

        # High-salience marks
        salient_marks = await self._stigmergy.high_salience(threshold=0.7)
        for mark in salient_marks:
            obs = f"High salience: {mark.observation}"
            energy = classify_energy(obs)
            perceptions.append(ShaktiPerception(
                observation=obs,
                connection=mark.file_path,
                energy=energy,
                impact_level="module",
                salience=mark.salience,
            ))

        return perceptions

    # -- propose / escalate --------------------------------------------------

    async def propose_local(self, perception: ShaktiPerception) -> dict[str, str] | None:
        """Return a local proposal dict, or None if not local impact."""
        if perception.impact_level != "local":
            return None
        return {
            "type": "local",
            "perception_id": perception.id,
            "proposal": perception.proposal or perception.observation,
            "energy": perception.energy.value,
        }

    async def escalate(self, perception: ShaktiPerception) -> dict[str, str | None]:
        """Escalate a module/system perception for orchestration."""
        return {
            "type": "escalation",
            "perception_id": perception.id,
            "impact": perception.impact_level,
            "observation": perception.observation,
            "proposal": perception.proposal,
            "energy": perception.energy.value,
        }


# ---------------------------------------------------------------------------
# System-prompt hook
# ---------------------------------------------------------------------------

SHAKTI_HOOK = """SHAKTI PERCEPTION: Before completing your task, spend 30 seconds scanning:
- What pattern did you notice that wasn't in your task description?
- What connection exists between what you just did and something else in the system?
- What wants to emerge that nobody asked for?
Leave a stigmergic mark with your observation. If salience > 0.7, propose it."""
