"""Active inference engine — Friston P10 embodiment.

Implements the Free Energy Principle for dharma_swarm agents:

    F = Complexity - Accuracy   (variational free energy)
    G = Risk + Ambiguity        (expected free energy, for planning)

Each agent maintains a generative model: beliefs about expected task
outcomes parameterized as (mean, precision) per task_type.  Before
executing a task the engine emits a *prediction*; after execution it
computes *prediction error* and updates beliefs via precision-weighted
learning.  The orchestrator uses Expected Free Energy (EFE) to route
tasks to agents that minimize expected surprise.

Integration points:
    agent_runner.py  — predict() before run_task, observe() after
    orchestrator.py  — expected_free_energy() in _select_idle_agent
    signal_bus.py    — prediction_error signals for strange loop

Ground: PILLAR_06_FRISTON.md §2 Engineering Implications
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Belief:
    """Gaussian belief: (mean, precision) about expected outcome quality.

    Precision = inverse variance = confidence.  High precision = narrow
    distribution = strong belief.  PILLAR_06 §1.6.
    """
    mean: float = 0.5        # expected quality [0,1]
    precision: float = 1.0   # confidence (inverse variance); starts low
    observation_count: int = 0

    def variance(self) -> float:
        return 1.0 / max(self.precision, 1e-6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": round(self.mean, 6),
            "precision": round(self.precision, 6),
            "observation_count": self.observation_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Belief:
        return cls(
            mean=float(d.get("mean", 0.5)),
            precision=float(d.get("precision", 1.0)),
            observation_count=int(d.get("observation_count", 0)),
        )


@dataclass
class Prediction:
    """Emitted before task execution — the agent's expectation."""
    agent_id: str
    task_id: str
    task_type: str
    predicted_quality: float      # E[quality] from generative model
    predicted_precision: float    # confidence in prediction
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "predicted_quality": round(self.predicted_quality, 6),
            "predicted_precision": round(self.predicted_precision, 6),
            "timestamp": self.timestamp,
        }


@dataclass
class PredictionError:
    """Computed after task execution — surprise signal."""
    agent_id: str
    task_id: str
    task_type: str
    predicted_quality: float
    observed_quality: float
    error: float                  # observed - predicted
    precision_weighted_error: float  # precision * error (learning signal)
    free_energy: float            # F for this observation
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "predicted_quality": round(self.predicted_quality, 6),
            "observed_quality": round(self.observed_quality, 6),
            "error": round(self.error, 6),
            "precision_weighted_error": round(self.precision_weighted_error, 6),
            "free_energy": round(self.free_energy, 6),
            "timestamp": self.timestamp,
        }


@dataclass
class GenerativeModel:
    """Per-agent generative model — beliefs about task outcome quality.

    Maps task_type → Belief.  The "default" key covers unknown types.
    Prior preferences (§1.5): preferred observations = high quality (1.0).
    """
    agent_id: str
    beliefs: dict[str, Belief] = field(default_factory=dict)
    # Prior preference: what the agent WANTS to observe (telos alignment)
    preferred_quality: float = 1.0   # moksha = 1.0 always
    # Global model complexity penalty (Occam factor)
    complexity_weight: float = 0.01
    # Learning rate for belief updates
    learning_rate: float = 0.1
    # Minimum precision floor (prevents infinite variance)
    min_precision: float = 0.1
    # Maximum precision ceiling (prevents overconfidence)
    max_precision: float = 50.0

    def get_belief(self, task_type: str) -> Belief:
        """Return belief for task_type, creating default if absent."""
        if task_type not in self.beliefs:
            self.beliefs[task_type] = Belief(mean=0.5, precision=1.0)
        return self.beliefs[task_type]

    def model_complexity(self) -> float:
        """KL divergence of beliefs from prior (uniform).

        Complexity = how far the model has drifted from maximum entropy.
        Simpler models (closer to prior) have lower complexity.
        PILLAR_06 §1.1: F = Complexity - Accuracy.
        """
        if not self.beliefs:
            return 0.0
        total_kl = 0.0
        prior_mean = 0.5
        prior_precision = 1.0
        for belief in self.beliefs.values():
            # KL divergence between two Gaussians
            # KL(q||p) = 0.5 * (precision_p/precision_q + precision_q*(mean_q - mean_p)^2/precision_p - 1 + ln(precision_q/precision_p))
            ratio = prior_precision / max(belief.precision, 1e-6)
            mean_diff_sq = (belief.mean - prior_mean) ** 2
            kl = 0.5 * (
                ratio
                + belief.precision * mean_diff_sq / max(prior_precision, 1e-6)
                - 1.0
                + math.log(max(belief.precision, 1e-6) / max(prior_precision, 1e-6))
            )
            total_kl += max(kl, 0.0)
        return total_kl

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "preferred_quality": self.preferred_quality,
            "complexity_weight": self.complexity_weight,
            "learning_rate": self.learning_rate,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GenerativeModel:
        beliefs = {
            k: Belief.from_dict(v)
            for k, v in d.get("beliefs", {}).items()
        }
        return cls(
            agent_id=d.get("agent_id", ""),
            beliefs=beliefs,
            preferred_quality=float(d.get("preferred_quality", 1.0)),
            complexity_weight=float(d.get("complexity_weight", 0.01)),
            learning_rate=float(d.get("learning_rate", 0.1)),
        )


# ---------------------------------------------------------------------------
# Active Inference Engine
# ---------------------------------------------------------------------------

class ActiveInferenceEngine:
    """Manages generative models for all agents and computes free energy.

    Singleton-ish: get via ``get_engine(state_dir)``.

    The engine is the computational heart of Friston P10 embodiment:
    - predict(): emit prediction from generative model before task
    - observe(): compute prediction error and update beliefs after task
    - expected_free_energy(): score agent-task pairings for routing
    - free_energy(): compute current F for an agent (system health)
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = (state_dir or Path.home() / ".dharma") / "active_inference"
        self._models: dict[str, GenerativeModel] = {}
        self._loaded = False

    # -- Model management ---------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._state_dir.mkdir(parents=True, exist_ok=True)
        models_file = self._state_dir / "generative_models.json"
        if models_file.is_file():
            try:
                data = json.loads(models_file.read_text(encoding="utf-8"))
                for agent_id, model_data in data.items():
                    self._models[agent_id] = GenerativeModel.from_dict(model_data)
                logger.debug("Loaded %d generative models", len(self._models))
            except Exception:
                logger.warning("Failed to load generative models", exc_info=True)
        self._loaded = True

    def _persist(self) -> None:
        """Persist all generative models to disk. Best-effort."""
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            models_file = self._state_dir / "generative_models.json"
            data = {aid: m.to_dict() for aid, m in self._models.items()}
            tmp = models_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(models_file)
        except Exception:
            logger.debug("Failed to persist generative models", exc_info=True)

    def get_model(self, agent_id: str) -> GenerativeModel:
        """Get or create a generative model for an agent."""
        self._ensure_loaded()
        if agent_id not in self._models:
            self._models[agent_id] = GenerativeModel(agent_id=agent_id)
        return self._models[agent_id]

    # -- Core operations ----------------------------------------------------

    def predict(
        self,
        agent_id: str,
        task_id: str,
        task_type: str = "general",
    ) -> Prediction:
        """Emit prediction from generative model before task execution.

        PILLAR_06 §1.2: The prediction drives the action. The model IS
        the purpose.

        Returns:
            Prediction with expected quality and precision.
        """
        model = self.get_model(agent_id)
        belief = model.get_belief(task_type)
        return Prediction(
            agent_id=agent_id,
            task_id=task_id,
            task_type=task_type,
            predicted_quality=belief.mean,
            predicted_precision=belief.precision,
        )

    def observe(
        self,
        prediction: Prediction,
        observed_quality: float,
        *,
        persist: bool = True,
    ) -> PredictionError:
        """Compute prediction error and update beliefs after task execution.

        PILLAR_06 §1.1: Minimizing F means simultaneously making your
        model accurate and your model simple.

        The belief update uses precision-weighted learning:
            new_mean = old_mean + learning_rate * precision_weight * error
            new_precision += observation_precision (grows with data)

        Args:
            prediction: The prediction emitted before task.
            observed_quality: Actual quality score [0, 1].
            persist: Whether to persist updated model to disk.

        Returns:
            PredictionError with surprise signal and updated free energy.
        """
        observed_quality = max(0.0, min(1.0, float(observed_quality)))
        model = self.get_model(prediction.agent_id)
        belief = model.get_belief(prediction.task_type)

        # Raw prediction error
        error = observed_quality - prediction.predicted_quality

        # Precision-weighted prediction error (the learning signal)
        # Higher precision = error matters more = faster learning
        precision_weight = belief.precision / (belief.precision + 1.0)
        pw_error = precision_weight * error

        # -- Belief update (perceptual inference, §1.2) --
        # Mean update: shift toward observation, weighted by learning rate
        belief.mean = _clamp01(
            belief.mean + model.learning_rate * pw_error
        )

        # Precision update: grows with observations (confidence increases)
        # but capped to prevent overconfidence
        observation_precision = 1.0  # each observation adds 1 unit
        belief.precision = min(
            belief.precision + observation_precision * model.learning_rate,
            model.max_precision,
        )
        belief.precision = max(belief.precision, model.min_precision)
        belief.observation_count += 1

        # -- Free energy computation --
        # F = Complexity - Accuracy
        # Accuracy: -log p(o|s) ≈ squared prediction error (Gaussian)
        accuracy = -(error ** 2)  # negative because F = Complexity - Accuracy
        complexity = model.complexity_weight * model.model_complexity()
        free_energy = complexity - accuracy  # lower is better

        pe = PredictionError(
            agent_id=prediction.agent_id,
            task_id=prediction.task_id,
            task_type=prediction.task_type,
            predicted_quality=prediction.predicted_quality,
            observed_quality=observed_quality,
            error=error,
            precision_weighted_error=pw_error,
            free_energy=free_energy,
        )

        # Persist and log
        if persist:
            self._persist()
        self._log_prediction_error(pe)

        return pe

    def expected_free_energy(
        self,
        agent_id: str,
        task_type: str = "general",
    ) -> float:
        """Compute Expected Free Energy (EFE) for an agent-task pairing.

        G = Risk + Ambiguity   (PILLAR_06 §1.2)

        Risk:     E[KL(predicted || preferred)] — how far predicted
                  outcome is from what the agent WANTS to observe.
        Ambiguity: H[p(o|s)] — uncertainty about the outcome.

        Lower EFE = better match. The orchestrator should route tasks
        to agents that minimize EFE.

        Returns:
            Expected free energy (lower is better).
        """
        model = self.get_model(agent_id)
        belief = model.get_belief(task_type)

        # Risk: KL divergence between predicted outcome and preferred outcome
        # For Gaussians: simplified to squared distance + variance ratio
        mean_diff = belief.mean - model.preferred_quality
        risk = mean_diff ** 2 + belief.variance()

        # Ambiguity: entropy of predicted outcome distribution
        # H[N(mu, sigma^2)] = 0.5 * ln(2*pi*e*sigma^2)
        ambiguity = 0.5 * math.log(2 * math.pi * math.e * belief.variance())

        # Exploration bonus: agents with fewer observations get lower EFE
        # (encourages exploring uncertain agents)
        exploration_bonus = 0.0
        if belief.observation_count < 5:
            exploration_bonus = -0.1 * (5 - belief.observation_count)

        return risk + ambiguity + exploration_bonus

    def free_energy(self, agent_id: str) -> float:
        """Compute total variational free energy for an agent.

        F = Complexity - Accuracy (averaged over all task types).
        Low F = well-calibrated agent. High F = model-world divergence.

        This is a health metric: agents with rising F are degrading.
        """
        model = self.get_model(agent_id)
        if not model.beliefs:
            return 0.0

        complexity = model.complexity_weight * model.model_complexity()

        # Average accuracy across all beliefs
        total_accuracy = 0.0
        count = 0
        for belief in model.beliefs.values():
            if belief.observation_count > 0:
                # Accuracy: how close mean is to preferred
                diff = belief.mean - model.preferred_quality
                total_accuracy += -(diff ** 2)
                count += 1

        avg_accuracy = total_accuracy / max(count, 1)
        return complexity - avg_accuracy

    def agent_summary(self, agent_id: str) -> dict[str, Any]:
        """Summary of an agent's generative model for diagnostics."""
        model = self.get_model(agent_id)
        return {
            "agent_id": agent_id,
            "free_energy": round(self.free_energy(agent_id), 4),
            "model_complexity": round(model.model_complexity(), 4),
            "belief_count": len(model.beliefs),
            "total_observations": sum(
                b.observation_count for b in model.beliefs.values()
            ),
            "beliefs": {
                k: {
                    "mean": round(v.mean, 3),
                    "precision": round(v.precision, 3),
                    "variance": round(v.variance(), 4),
                    "observations": v.observation_count,
                }
                for k, v in model.beliefs.items()
            },
        }

    def system_free_energy(self) -> dict[str, Any]:
        """System-wide free energy summary across all agents."""
        self._ensure_loaded()
        agent_fes: dict[str, float] = {}
        for agent_id in self._models:
            agent_fes[agent_id] = round(self.free_energy(agent_id), 4)
        total = sum(agent_fes.values())
        return {
            "total_free_energy": round(total, 4),
            "agent_count": len(agent_fes),
            "per_agent": agent_fes,
            "mean_free_energy": round(
                total / max(len(agent_fes), 1), 4
            ),
        }

    # -- Helpers ------------------------------------------------------------

    def _log_prediction_error(self, pe: PredictionError) -> None:
        """Append prediction error to JSONL log for trajectory analysis."""
        try:
            log_file = self._state_dir / "prediction_errors.jsonl"
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(pe.to_dict()) + "\n")
        except Exception:
            logger.debug("Failed to log prediction error", exc_info=True)

    def reset_agent(self, agent_id: str) -> None:
        """Reset an agent's generative model to prior."""
        self._ensure_loaded()
        self._models.pop(agent_id, None)
        self._persist()


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_engine: ActiveInferenceEngine | None = None


def get_engine(state_dir: Path | None = None) -> ActiveInferenceEngine:
    """Get or create the singleton ActiveInferenceEngine."""
    global _engine
    if _engine is None:
        _engine = ActiveInferenceEngine(state_dir=state_dir)
    return _engine


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))
