"""Transcendence Protocol — coordinated diverse agents provably outperforming any individual.

The core engine that implements the three conditions:
1. Diversity of competence — agents from 2+ model families
2. Error decorrelation — independent parallel execution
3. Quality aggregation — temperature concentration / quality weighting

Based on:
- Zhang et al. "Transcendence" (NeurIPS 2024) — low-temp implicit majority voting
- Krogh & Vedelsby (1995) — E_ensemble = E_mean - E_diversity
- Abreu et al. (2025) — three modes: denoising, selection, generalization

Usage:
    protocol = TranscendenceProtocol(router=router, scorer=my_scorer)
    result = await protocol.execute(task, agent_configs)
    print(result.metrics.transcendence_margin)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.models import (
    ProviderType,
    _new_id,
    _utc_now,
)
from dharma_swarm.transcendence_aggregation import (
    majority_vote,
    quality_weighted_average,
    temperature_concentrate,
    softmax_select,
)
from dharma_swarm.transcendence_metrics import (
    behavioral_diversity,
    error_decorrelation,
    krogh_vedelsby_diversity,
    transcendence_margin as compute_transcendence_margin,
    aggregation_lift as compute_aggregation_lift,
    diversity_health,
)

logger = logging.getLogger(__name__)

_TRIALS_DIR = Path.home() / ".dharma" / "transcendence"


class TranscendenceMode(str, Enum):
    """Three modes of transcendence (Abreu et al. 2025)."""
    DENOISING = "denoising"       # Filter idiosyncratic errors
    SELECTION = "selection"        # Route to best agent per sub-problem
    GENERALIZATION = "generalization"  # Recombine beyond any single agent


class AggregationMethod(str, Enum):
    """Available aggregation mechanisms."""
    MAJORITY_VOTE = "majority_vote"
    QUALITY_WEIGHTED = "quality_weighted"
    TEMPERATURE_CONCENTRATE = "temperature_concentrate"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Configuration for one agent in a transcendence trial."""
    name: str
    provider: ProviderType
    model: str
    system_prompt: str = ""
    temperature: float = 0.7


class AgentOutput(BaseModel):
    """Output from a single agent."""
    agent_name: str
    provider: ProviderType
    model: str
    content: str
    probability: float | None = None  # For prediction tasks
    latency_ms: float = 0.0
    score: float | None = None  # Set after scoring
    error: float | None = None  # Set after scoring (lower = better)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscendenceMetrics(BaseModel):
    """Computed metrics for a transcendence trial."""
    behavioral_div: float = 0.0
    error_decorr: float = 0.0
    kv_diversity_term: float = 0.0
    transcendence_margin: float = 0.0
    aggregation_lift: float = 0.0
    best_individual_score: float = 0.0
    mean_individual_score: float = 0.0
    ensemble_score: float = 0.0
    n_agents: int = 0
    n_model_families: int = 0
    diversity_status: str = "unknown"


class TranscendenceTask(BaseModel):
    """A task for the transcendence protocol."""
    id: str = Field(default_factory=_new_id)
    prompt: str
    task_type: str = "general"  # "prediction", "classification", "general"
    ground_truth: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnsembleResult(BaseModel):
    """Result of a transcendence trial."""
    id: str = Field(default_factory=_new_id)
    task: TranscendenceTask
    agent_outputs: list[AgentOutput]
    ensemble_output: str
    ensemble_probability: float | None = None
    aggregation_method: AggregationMethod
    metrics: TranscendenceMetrics
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    transcended: bool = False  # True if ensemble beat best individual


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class TranscendenceProtocol:
    """The engine that produces transcendence through diversity.

    Takes a task, fans out to N diverse agents, aggregates outputs
    via quality-weighted mechanisms, and measures whether the ensemble
    outperforms any individual.
    """

    def __init__(
        self,
        call_fn: Callable[[AgentConfig, str], Awaitable[str]],
        scorer: Callable[[str, TranscendenceTask], float] | None = None,
        aggregation: AggregationMethod = AggregationMethod.QUALITY_WEIGHTED,
        temperature: float = 0.5,
        persist: bool = True,
    ) -> None:
        """
        Args:
            call_fn: Async function that calls an agent and returns text.
                     Signature: (config, prompt) -> str
            scorer: Scores an output against the task. Higher = better.
                    If None, uses length as a trivial proxy.
            aggregation: Default aggregation method.
            temperature: Concentration parameter for temperature methods.
            persist: Whether to save trial results to disk.
        """
        self._call_fn = call_fn
        self._scorer = scorer or self._default_scorer
        self._aggregation = aggregation
        self._temperature = temperature
        self._persist = persist

    async def execute(
        self,
        task: TranscendenceTask,
        agents: Sequence[AgentConfig],
        *,
        aggregation: AggregationMethod | None = None,
        temperature: float | None = None,
    ) -> EnsembleResult:
        """Execute a transcendence trial.

        Args:
            task: The task to solve.
            agents: Agent configurations (must span 2+ model families).
            aggregation: Override default aggregation method.
            temperature: Override default temperature.

        Returns:
            EnsembleResult with metrics showing whether transcendence occurred.
        """
        method = aggregation or self._aggregation
        temp = temperature if temperature is not None else self._temperature

        # Validate diversity
        families = {a.provider for a in agents}
        if len(families) < 2:
            logger.warning(
                "Transcendence trial with < 2 model families (%s). "
                "Error decorrelation may be insufficient.",
                families,
            )

        # Fan out: independent parallel execution
        outputs = await self._fan_out(task, agents)

        # Score each output individually
        for out in outputs:
            out.score = self._scorer(out.content, task)
            out.error = 1.0 - out.score  # Higher score = lower error

        # Aggregate
        ensemble_text, ensemble_prob = self._aggregate(outputs, method, temp)

        # Score ensemble
        ensemble_score = self._scorer(ensemble_text, task)

        # Compute metrics
        individual_scores = [o.score for o in outputs if o.score is not None]
        individual_errors = [o.error for o in outputs if o.error is not None]
        contents = [o.content for o in outputs]

        best_ind = max(individual_scores) if individual_scores else 0.0
        mean_ind = (
            sum(individual_scores) / len(individual_scores)
            if individual_scores
            else 0.0
        )
        ensemble_error = 1.0 - ensemble_score

        kv_div = krogh_vedelsby_diversity(individual_errors, ensemble_error)
        t_margin = compute_transcendence_margin(ensemble_score, best_ind)
        a_lift = compute_aggregation_lift(ensemble_score, mean_ind)
        b_div = behavioral_diversity(contents)
        e_decorr = error_decorrelation(individual_errors)
        d_health = diversity_health(b_div, e_decorr, kv_div)

        metrics = TranscendenceMetrics(
            behavioral_div=b_div,
            error_decorr=e_decorr,
            kv_diversity_term=kv_div,
            transcendence_margin=t_margin,
            aggregation_lift=a_lift,
            best_individual_score=best_ind,
            mean_individual_score=mean_ind,
            ensemble_score=ensemble_score,
            n_agents=len(outputs),
            n_model_families=len(families),
            diversity_status=str(d_health.get("status", "unknown")),
        )

        result = EnsembleResult(
            task=task,
            agent_outputs=outputs,
            ensemble_output=ensemble_text,
            ensemble_probability=ensemble_prob,
            aggregation_method=method,
            metrics=metrics,
            transcended=t_margin > 0,
        )

        if self._persist:
            self._save_trial(result)

        if result.transcended:
            logger.info(
                "TRANSCENDENCE achieved: margin=%.4f, diversity=%.4f, agents=%d",
                t_margin, b_div, len(outputs),
            )
        else:
            logger.info(
                "No transcendence: margin=%.4f, diversity=%.4f, agents=%d",
                t_margin, b_div, len(outputs),
            )

        return result

    async def _fan_out(
        self,
        task: TranscendenceTask,
        agents: Sequence[AgentConfig],
    ) -> list[AgentOutput]:
        """Call all agents in parallel. Independent execution."""

        async def _call_one(cfg: AgentConfig) -> AgentOutput:
            t0 = time.monotonic()
            try:
                content = await self._call_fn(cfg, task.prompt)
            except Exception as exc:
                logger.warning("Agent %s failed: %s", cfg.name, exc)
                content = ""
            latency = (time.monotonic() - t0) * 1000

            # Extract probability if this is a prediction task
            prob = self._extract_probability(content) if task.task_type == "prediction" else None

            return AgentOutput(
                agent_name=cfg.name,
                provider=cfg.provider,
                model=cfg.model,
                content=content,
                probability=prob,
                latency_ms=latency,
            )

        results = await asyncio.gather(*[_call_one(cfg) for cfg in agents])
        return [r for r in results if r.content]  # Drop failed agents

    def _aggregate(
        self,
        outputs: list[AgentOutput],
        method: AggregationMethod,
        temperature: float,
    ) -> tuple[str, float | None]:
        """Aggregate agent outputs using the selected method.

        Returns (ensemble_text, ensemble_probability_or_None).
        """
        if not outputs:
            return ("", None)

        # For prediction tasks with probabilities (only when task IS a prediction)
        probs = [o.probability for o in outputs if o.probability is not None]
        scores = [o.score or 0.5 for o in outputs]

        # Only use probability aggregation if MOST agents returned probabilities
        # (more than half) — otherwise treat as text
        is_prediction = len(probs) > len(outputs) / 2

        if is_prediction and probs and method in (
            AggregationMethod.QUALITY_WEIGHTED,
            AggregationMethod.TEMPERATURE_CONCENTRATE,
        ):
            if method == AggregationMethod.QUALITY_WEIGHTED:
                ens_prob = quality_weighted_average(probs, scores)
            else:
                ens_prob = temperature_concentrate(probs, scores, temperature)

            # Text output summarizes the ensemble probability
            ens_text = f"Ensemble probability: {ens_prob:.4f}"
            return (ens_text, ens_prob)

        # For discrete choices (majority vote)
        if method == AggregationMethod.MAJORITY_VOTE:
            choices = [o.content.strip() for o in outputs]
            winner, _share = majority_vote(choices, scores)
            return (winner, None)

        # Default: quality-weighted selection of best output
        weights = softmax_select(scores, temperature)
        best_idx = max(range(len(weights)), key=lambda i: weights[i])
        return (outputs[best_idx].content, None)

    @staticmethod
    def _extract_probability(text: str) -> float | None:
        """Try to extract a probability from agent output text.

        Only matches EXPLICIT probability declarations, not arbitrary numbers.
        """
        import re
        # Only match explicit probability/confidence declarations
        patterns = [
            r'(?:probability|prob|confidence|estimate|likelihood)(?:\s+is)?[:\s=]+(\d*\.?\d+)',
            r'(\d+)%\s*(?:probability|confidence|likely|chance)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                val = float(match.group(1))
                if val > 1.0:
                    val = val / 100.0  # Convert percentage
                if 0.0 <= val <= 1.0:
                    return val
        return None

    @staticmethod
    def _default_scorer(content: str, _task: TranscendenceTask) -> float:
        """Trivial scorer: longer, non-empty content scores higher."""
        if not content:
            return 0.0
        return min(len(content) / 1000.0, 1.0)

    def _save_trial(self, result: EnsembleResult) -> None:
        """Persist trial result to JSONL."""
        try:
            _TRIALS_DIR.mkdir(parents=True, exist_ok=True)
            path = _TRIALS_DIR / "trials.jsonl"
            record = {
                "id": result.id,
                "task_id": result.task.id,
                "task_type": result.task.task_type,
                "n_agents": result.metrics.n_agents,
                "n_families": result.metrics.n_model_families,
                "transcended": result.transcended,
                "transcendence_margin": result.metrics.transcendence_margin,
                "aggregation_lift": result.metrics.aggregation_lift,
                "behavioral_diversity": result.metrics.behavioral_div,
                "kv_diversity_term": result.metrics.kv_diversity_term,
                "ensemble_score": result.metrics.ensemble_score,
                "best_individual": result.metrics.best_individual_score,
                "method": result.aggregation_method.value,
                "timestamp": result.timestamp,
            }
            with open(path, "a") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.warning("Failed to persist trial: %s", exc)
