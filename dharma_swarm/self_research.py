"""Automated introspection over evaluation history."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from uuid import uuid4

from dharma_swarm.evaluator import OutputEvaluation, OutputEvaluator

RESEARCH_QUESTIONS = [
    "Which provider/model combination produces the highest quality outputs for code tasks?",
    "Which agent roles consistently produce actionable outputs versus noise?",
    "Do longer outputs improve quality, or is there a diminishing returns curve?",
    "Which task classes benefit most from premium models?",
]


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass(slots=True)
class Hypothesis:
    """Candidate system-level claim to validate with historical data."""

    id: str
    question: str
    rationale: str
    task_type: str = "general"
    models: tuple[str, ...] = ()
    expected_winner: str | None = None
    evidence_count: int = 0


@dataclass(slots=True)
class Experiment:
    """A concrete evaluation plan for a hypothesis."""

    id: str
    hypothesis_id: str
    question: str
    task_type: str
    metric: str
    control_model: str | None
    candidate_model: str | None
    sample_size: int
    methodology: str


@dataclass(slots=True)
class ExperimentResult:
    """Outcome of an applied or retrospective experiment."""

    hypothesis_id: str
    question: str
    winner: str | None
    delta: float
    confidence: float
    sample_sizes: dict[str, int] = field(default_factory=dict)
    conclusion: str = ""


@dataclass(slots=True)
class ConfigChange:
    """Suggested config mutation derived from evidence."""

    target: str
    key: str
    value: str
    reason: str


class SelfResearcher:
    """Generate and test hypotheses using persisted output evaluations."""

    def __init__(self, *, evaluations_path=None) -> None:
        self._evaluator = OutputEvaluator(evaluations_path=evaluations_path)

    async def load_evaluations(self) -> list[OutputEvaluation]:
        return await self._evaluator.read_all()

    async def generate_hypotheses(self, evaluations: list[OutputEvaluation]) -> list[Hypothesis]:
        """Propose system hypotheses grounded in quality history."""

        if not evaluations:
            return []

        by_task_type: defaultdict[str, list[OutputEvaluation]] = defaultdict(list)
        for evaluation in evaluations:
            by_task_type[evaluation.task_type].append(evaluation)

        hypotheses: list[Hypothesis] = []
        for task_type, entries in sorted(by_task_type.items()):
            by_model: defaultdict[str, list[OutputEvaluation]] = defaultdict(list)
            for entry in entries:
                by_model[entry.model].append(entry)
            ranked = sorted(
                (
                    (
                        model,
                        len(model_entries),
                        sum(item.quality_score for item in model_entries) / len(model_entries),
                    )
                    for model, model_entries in by_model.items()
                    if len(model_entries) >= 2
                ),
                key=lambda item: (-item[2], -item[1], item[0]),
            )
            if len(ranked) >= 2:
                winner, count, winner_score = ranked[0]
                runner_up, _, runner_up_score = ranked[1]
                delta = winner_score - runner_up_score
                if delta >= 0.05:
                    hypotheses.append(
                        Hypothesis(
                            id=_new_id(),
                            question=f"{winner} outperforms {runner_up} for {task_type} tasks.",
                            rationale=(
                                f"Historical quality delta is {delta:.3f} over {count} scored outputs."
                            ),
                            task_type=task_type,
                            models=(winner, runner_up),
                            expected_winner=winner,
                            evidence_count=count,
                        )
                    )

        lengthy = [entry for entry in evaluations if entry.token_count >= 180]
        concise = [entry for entry in evaluations if 0 < entry.token_count < 180]
        if lengthy and concise:
            lengthy_mean = sum(entry.quality_score for entry in lengthy) / len(lengthy)
            concise_mean = sum(entry.quality_score for entry in concise) / len(concise)
            if abs(lengthy_mean - concise_mean) >= 0.05:
                hypotheses.append(
                    Hypothesis(
                        id=_new_id(),
                        question="Longer outputs do not always improve quality.",
                        rationale=(
                            f"Historical delta between long and concise outputs is "
                            f"{abs(lengthy_mean - concise_mean):.3f}."
                        ),
                        task_type="general",
                        models=(),
                        expected_winner="concise" if concise_mean >= lengthy_mean else "long",
                        evidence_count=min(len(lengthy), len(concise)),
                    )
                )

        return hypotheses

    async def design_experiment(self, hypothesis: Hypothesis) -> Experiment:
        """Translate a hypothesis into a repeatable experiment design."""

        control_model = hypothesis.models[1] if len(hypothesis.models) >= 2 else None
        candidate_model = hypothesis.models[0] if hypothesis.models else None
        return Experiment(
            id=_new_id(),
            hypothesis_id=hypothesis.id,
            question=hypothesis.question,
            task_type=hypothesis.task_type,
            metric="quality_score",
            control_model=control_model,
            candidate_model=candidate_model,
            sample_size=max(4, min(20, hypothesis.evidence_count)),
            methodology=(
                "Use matched historical tasks when available. If evidence is thin, "
                "run paired tasks with identical prompts and score outputs with the evaluator."
            ),
        )

    async def run_experiment(
        self,
        experiment: Experiment,
        evaluations: list[OutputEvaluation] | None = None,
    ) -> ExperimentResult:
        """Execute a retrospective experiment against historical evaluation data."""

        rows = evaluations if evaluations is not None else await self.load_evaluations()
        filtered = [row for row in rows if row.task_type == experiment.task_type]
        if experiment.candidate_model:
            candidate_rows = [row for row in filtered if row.model == experiment.candidate_model]
        else:
            candidate_rows = filtered
        control_rows = (
            [row for row in filtered if row.model == experiment.control_model]
            if experiment.control_model
            else []
        )

        candidate_mean = (
            sum(row.quality_score for row in candidate_rows) / len(candidate_rows)
            if candidate_rows
            else 0.0
        )
        control_mean = (
            sum(row.quality_score for row in control_rows) / len(control_rows)
            if control_rows
            else 0.0
        )
        delta = candidate_mean - control_mean
        total_samples = len(candidate_rows) + len(control_rows)
        confidence = min(1.0, total_samples / max(1, experiment.sample_size * 2))
        winner = None
        if candidate_rows and (not control_rows or candidate_mean >= control_mean):
            winner = experiment.candidate_model
        elif control_rows:
            winner = experiment.control_model

        if experiment.control_model and control_rows:
            conclusion = (
                f"{winner} leads {experiment.task_type} outputs by {abs(delta):.3f} "
                f"quality points across {total_samples} samples."
            )
        else:
            conclusion = (
                f"Observed {len(candidate_rows)} historical samples for "
                f"{experiment.candidate_model or experiment.task_type}."
            )

        return ExperimentResult(
            hypothesis_id=experiment.hypothesis_id,
            question=experiment.question,
            winner=winner,
            delta=delta,
            confidence=confidence,
            sample_sizes={
                str(experiment.candidate_model or "candidate"): len(candidate_rows),
                str(experiment.control_model or "control"): len(control_rows),
            },
            conclusion=conclusion,
        )

    async def apply_learnings(self, result: ExperimentResult) -> list[ConfigChange]:
        """Turn a validated result into configuration suggestions."""

        if result.confidence < 0.5 or not result.winner:
            return []

        return [
            ConfigChange(
                target="routing_preferences",
                key="preferred_model",
                value=result.winner,
                reason=(
                    f"{result.question} Historical evidence shows a {result.delta:+.3f} "
                    f"quality delta at confidence {result.confidence:.2f}."
                ),
            )
        ]
