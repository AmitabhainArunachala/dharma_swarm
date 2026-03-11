"""Lean experiment-memory analysis for Darwin Engine."""

from __future__ import annotations

from collections import Counter
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
    component_mutation_bias: dict[str, float] = Field(default_factory=dict)
    profile_mutation_bias: dict[str, float] = Field(default_factory=dict)
    failure_classes: dict[str, int] = Field(default_factory=dict)
    failure_signatures: dict[str, int] = Field(default_factory=dict)
    caution_components: list[str] = Field(default_factory=list)
    avoidance_hints: list[str] = Field(default_factory=list)
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
        failure_classes, failure_signatures = self._failure_patterns(records)
        component_mutation_bias = self._mutation_bias_map(
            component_scores,
            caution_components=set(caution_components),
        )
        profile_mutation_bias = self._mutation_bias_map(profile_scores)
        avoidance_hints = self._build_avoidance_hints(
            failure_classes=failure_classes,
            failure_signatures=failure_signatures,
            caution_components=caution_components,
        )
        recommended_strategy = self._recommend_strategy(
            overall_score=overall_score,
            avg_weighted_fitness=avg_weighted_fitness,
            caution_components=caution_components,
            failure_classes=failure_classes,
        )
        lessons = self._build_lessons(
            records=records,
            component_scores=component_scores,
            profile_scores=profile_scores,
            caution_components=caution_components,
            avoidance_hints=avoidance_hints,
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
            component_mutation_bias=component_mutation_bias,
            profile_mutation_bias=profile_mutation_bias,
            failure_classes=failure_classes,
            failure_signatures=failure_signatures,
            caution_components=caution_components,
            avoidance_hints=avoidance_hints,
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

    def _failure_patterns(
        self,
        records: list[ExperimentRecord],
    ) -> tuple[dict[str, int], dict[str, int]]:
        failure_classes: Counter[str] = Counter()
        failure_signatures: Counter[str] = Counter()
        for record in records:
            failure_class = self._infer_failure_class(record)
            if failure_class is None:
                continue
            failure_classes[failure_class] += 1
            failure_signature = self._infer_failure_signature(record, failure_class)
            if failure_signature:
                failure_signatures[failure_signature] += 1
        return dict(failure_classes), dict(failure_signatures)

    def _infer_failure_class(self, record: ExperimentRecord) -> str | None:
        explicit = (record.failure_class or "").strip().lower()
        if explicit:
            return explicit

        if record.test_results.get("rolled_back"):
            return "rollback"
        exit_code = record.test_results.get("exit_code")
        if exit_code not in (None, 0):
            return "test_failure"
        if record.pass_rate < 1.0:
            return "test_failure"
        if record.weighted_fitness < 0.35:
            return "low_fitness"
        return None

    def _infer_failure_signature(
        self,
        record: ExperimentRecord,
        failure_class: str,
    ) -> str | None:
        explicit = (record.failure_signature or "").strip().lower()
        if explicit:
            return explicit

        if failure_class == "rollback":
            return "rollback:apply_or_test"
        if failure_class == "test_failure":
            exit_code = record.test_results.get("exit_code")
            if exit_code not in (None, 0):
                return f"test_failure:exit_{int(exit_code)}"
            return "test_failure:pass_rate_drop"
        if failure_class == "low_fitness":
            return "low_fitness:weak_total_score"
        return None

    @staticmethod
    def _mutation_bias(score: float, *, caution: bool = False) -> float:
        if score >= 0.8:
            bias = 1.15
        elif score >= 0.65:
            bias = 1.05
        elif score <= 0.25:
            bias = 0.7
        elif score <= 0.4:
            bias = 0.85
        else:
            bias = 1.0
        if caution:
            bias = min(bias, 0.8)
        return round(max(0.65, min(1.2, bias)), 3)

    def _mutation_bias_map(
        self,
        scores: dict[str, float],
        *,
        caution_components: set[str] | None = None,
    ) -> dict[str, float]:
        caution_components = caution_components or set()
        return {
            key: self._mutation_bias(score, caution=key in caution_components)
            for key, score in scores.items()
        }

    @staticmethod
    def _recommend_strategy(
        *,
        overall_score: float,
        avg_weighted_fitness: float,
        caution_components: list[str],
        failure_classes: dict[str, int],
    ) -> str | None:
        if failure_classes.get("rollback", 0) >= 2 or failure_classes.get("gate_block", 0) >= 2:
            return "backtrack"
        if overall_score < 0.3:
            return "backtrack"
        if overall_score > 0.7 and avg_weighted_fitness > 0.55:
            return "exploit"
        if caution_components or overall_score < 0.55:
            return "explore"
        return None

    @staticmethod
    def _build_avoidance_hints(
        *,
        failure_classes: dict[str, int],
        failure_signatures: dict[str, int],
        caution_components: list[str],
    ) -> list[str]:
        hints: list[str] = []
        repeated_signatures = sorted(
            failure_signatures.items(),
            key=lambda item: (-item[1], item[0]),
        )
        for signature, count in repeated_signatures:
            if count < 2:
                continue
            hints.append(
                f"Avoid repeating {signature.replace(':', ' / ')} ({count} recent hits)."
            )
            if len(hints) >= 2:
                break
        if not hints and failure_classes:
            worst_class = max(failure_classes, key=failure_classes.get)
            hints.append(
                f"Recent weak spot is {worst_class.replace('_', ' ')}; keep changes more reversible."
            )
        if caution_components:
            hints.append(
                f"Treat {', '.join(caution_components[:2])} as fragile until validation quality improves."
            )
        return hints[:3]

    @staticmethod
    def _build_lessons(
        *,
        records: list[ExperimentRecord],
        component_scores: dict[str, float],
        profile_scores: dict[str, float],
        caution_components: list[str],
        avoidance_hints: list[str],
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
        lessons.extend(avoidance_hints[:2])
        if not lessons and records:
            lessons.append("Recent experiment memory is neutral; keep mutations bounded.")
        return lessons[:3]
