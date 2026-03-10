"""Lean experiment-memory analysis for Darwin Engine."""

from __future__ import annotations

from statistics import mean

from pydantic import BaseModel, Field

from dharma_swarm.execution_profile import PromotionState
from dharma_swarm.experiment_log import ExperimentRecord


class ExperimentMemorySnapshot(BaseModel):
    """Condensed memory over recent Darwin experiments."""

    records_considered: int = 0
    overall_score: float = 0.0
    avg_weighted_fitness: float = 0.0
    recommended_strategy: str | None = None
    confidence: float = 0.0
    parent_scores: dict[str, float] = Field(default_factory=dict)
    component_scores: dict[str, float] = Field(default_factory=dict)
    profile_scores: dict[str, float] = Field(default_factory=dict)
    caution_components: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)


class ExperimentMemory:
    """Analyze recent experiment history into selection and strategy signals."""

    _PROMOTION_SCORES = {
        PromotionState.CANDIDATE.value: 0.0,
        PromotionState.PROBE_PASS.value: 0.25,
        PromotionState.LOCAL_PASS.value: 0.5,
        PromotionState.COMPONENT_PASS.value: 0.75,
        PromotionState.SYSTEM_PASS.value: 1.0,
        PromotionState.PROMOTED.value: 1.0,
    }

    def analyze(self, records: list[ExperimentRecord]) -> ExperimentMemorySnapshot:
        """Summarize recent experiment outcomes into compact guidance."""
        if not records:
            return ExperimentMemorySnapshot()

        record_scores = [self._record_score(record) for record in records]
        overall_score = mean(record_scores)
        avg_weighted_fitness = mean(record.weighted_fitness for record in records)
        confidence = min(1.0, len(records) / 12.0)

        parent_scores = self._aggregate(records, key="parent_id")
        component_scores = self._aggregate(records, key="component")
        profile_scores = self._aggregate(records, key="execution_profile")
        caution_components = self._caution_components(records)
        recommended_strategy = self._recommend_strategy(
            overall_score=overall_score,
            avg_weighted_fitness=avg_weighted_fitness,
            caution_components=caution_components,
        )
        lessons = self._build_lessons(
            records=records,
            component_scores=component_scores,
            profile_scores=profile_scores,
            caution_components=caution_components,
        )

        return ExperimentMemorySnapshot(
            records_considered=len(records),
            overall_score=overall_score,
            avg_weighted_fitness=avg_weighted_fitness,
            recommended_strategy=recommended_strategy,
            confidence=confidence,
            parent_scores=parent_scores,
            component_scores=component_scores,
            profile_scores=profile_scores,
            caution_components=caution_components,
            lessons=lessons,
        )

    def _record_score(self, record: ExperimentRecord) -> float:
        promotion_score = self._PROMOTION_SCORES.get(
            record.promotion_state.value
            if hasattr(record.promotion_state, "value")
            else str(record.promotion_state),
            0.0,
        )
        pass_score = max(0.0, min(1.0, float(record.pass_rate)))
        fitness_score = max(0.0, min(1.0, float(record.weighted_fitness)))
        return (0.5 * promotion_score) + (0.3 * pass_score) + (0.2 * fitness_score)

    def _aggregate(
        self,
        records: list[ExperimentRecord],
        *,
        key: str,
    ) -> dict[str, float]:
        buckets: dict[str, list[float]] = {}
        for record in records:
            value = getattr(record, key, None)
            if not value:
                continue
            buckets.setdefault(str(value), []).append(self._record_score(record))
        return {
            bucket: mean(scores)
            for bucket, scores in buckets.items()
        }

    def _caution_components(self, records: list[ExperimentRecord]) -> list[str]:
        grouped: dict[str, list[float]] = {}
        for record in records:
            grouped.setdefault(record.component, []).append(self._record_score(record))
        return sorted(
            component
            for component, scores in grouped.items()
            if len(scores) >= 2 and mean(scores) < 0.35
        )

    @staticmethod
    def _recommend_strategy(
        *,
        overall_score: float,
        avg_weighted_fitness: float,
        caution_components: list[str],
    ) -> str | None:
        if overall_score < 0.3:
            return "backtrack"
        if overall_score > 0.7 and avg_weighted_fitness > 0.55:
            return "exploit"
        if caution_components or overall_score < 0.55:
            return "explore"
        return None

    @staticmethod
    def _build_lessons(
        *,
        records: list[ExperimentRecord],
        component_scores: dict[str, float],
        profile_scores: dict[str, float],
        caution_components: list[str],
    ) -> list[str]:
        lessons: list[str] = []
        if caution_components:
            lessons.append(
                f"Caution on {', '.join(caution_components[:2])}: repeated weak experiment outcomes."
            )
        if profile_scores:
            best_profile = max(profile_scores, key=profile_scores.get)
            lessons.append(
                f"Profile {best_profile} is strongest recently (score {profile_scores[best_profile]:.2f})."
            )
        if component_scores:
            best_component = max(component_scores, key=component_scores.get)
            lessons.append(
                f"Lineage around {best_component} is currently producing the best outcomes."
            )
        if not lessons and records:
            lessons.append("Recent experiment memory is neutral; keep mutations bounded.")
        return lessons[:3]
