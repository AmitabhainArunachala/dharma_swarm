"""Append-only experiment records for Darwin Engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.archive import FitnessScore
from dharma_swarm.execution_profile import EvidenceTier, PromotionState
from dharma_swarm.models import _new_id, _utc_now


class ExperimentRecord(BaseModel):
    """Canonical record of one Darwin experiment outcome."""

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    proposal_id: str = ""
    archive_entry_id: str = ""
    cycle_id: str | None = None
    component: str = ""
    change_type: str = ""
    description: str = ""
    parent_id: str | None = None
    execution_profile: str = "default"
    matched_pattern: str | None = None
    workspace: str | None = None
    test_command: str | None = None
    timeout: float | None = None
    evidence_tier: EvidenceTier = EvidenceTier.UNVALIDATED
    promotion_state: PromotionState = PromotionState.CANDIDATE
    risk_level: str = "medium"
    rollback_policy: str = "revert_patch"
    expected_metrics: list[str] = Field(default_factory=list)
    pass_rate: float = 0.0
    weighted_fitness: float = 0.0
    outcome: str = "archived"
    failure_class: str | None = None
    failure_signature: str | None = None
    test_results: dict[str, Any] = Field(default_factory=dict)
    fitness: FitnessScore = Field(default_factory=FitnessScore)
    agent_id: str = ""
    model: str = ""
    tokens_used: int = 0
    lessons: list[str] = Field(default_factory=list)


class ExperimentLog:
    """Append-only JSONL store for experiment records."""

    def __init__(self, path: Path | None = None) -> None:
        default = Path.home() / ".dharma" / "evolution" / "experiments.jsonl"
        self.path = path or default

    async def append(self, record: ExperimentRecord) -> str:
        """Append one experiment record and return its id."""
        import aiofiles

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "a") as handle:
            await handle.write(record.model_dump_json() + "\n")
        return record.id

    async def get_recent(self, limit: int = 20) -> list[ExperimentRecord]:
        """Return the most recent experiment records."""
        if not self.path.exists():
            return []
        import aiofiles

        records: list[ExperimentRecord] = []
        async with aiofiles.open(self.path, "r") as handle:
            async for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    if "fitness" in data and isinstance(data["fitness"], dict):
                        data["fitness"] = FitnessScore(**data["fitness"])
                    records.append(ExperimentRecord.model_validate(data))
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue
        records.sort(key=lambda record: record.timestamp, reverse=True)
        return records[:limit]
