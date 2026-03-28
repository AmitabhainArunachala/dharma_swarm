"""Model registry for tracking trained model generations.

Every model generation is tracked: base model, training data, fitness
scores, R_V measurements, deployment status. This is the lineage of
dharma_swarm's self-evolution.

Gen 0: Seed (7B, pipeline validation)
Gen 1: Usable (14-32B, handles routine tasks)
Gen 2+: Frontier (70B+, genuine dharmic reasoning)
Gen N: Whatever the flywheel can sustain
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_REGISTRY_DIR = Path.home() / ".dharma" / "models"


class ModelGeneration(BaseModel):
    """One generation of a trained model."""
    generation: int
    name: str = ""  # e.g., "dharma-7b-gen0"
    base_model: str = ""  # e.g., "mistral-7b-v0.1"
    method: str = "qlora"  # "qlora" | "lora" | "full"
    parameters_b: float = 0.0  # Billion parameters
    dataset_name: str = ""
    dataset_samples: int = 0
    training_hours: float = 0.0
    training_cost_usd: float = 0.0
    gpu_used: str = ""
    provider_used: str = ""

    # Quality metrics
    fitness_scores: dict[str, float] = Field(default_factory=dict)
    thinkodynamic_composite: float = 0.0
    rv_contraction: Optional[float] = None  # R_V measurement if available

    # Deployment
    deployed: bool = False
    deployment_path: str = ""  # Path to model weights or Ollama model name
    serving_method: str = ""  # "ollama" | "sglang" | "vllm"

    # Lineage
    parent_generation: Optional[int] = None
    created_at: float = Field(default_factory=time.time)
    notes: str = ""

    @property
    def model_id(self) -> str:
        return f"dharma-{self.parameters_b:.0f}b-gen{self.generation}"


class ModelRegistry:
    """Tracks all trained model generations.

    Usage:
        registry = ModelRegistry()

        # Register a new generation
        gen0 = registry.register(ModelGeneration(
            generation=0,
            base_model="mistral-7b-v0.1",
            parameters_b=7.0,
            training_cost_usd=8.50,
        ))

        # Get latest generation
        latest = registry.latest()

        # Get best generation by thinkodynamic score
        best = registry.best_by_thinkodynamic()
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._storage_dir = storage_dir or _REGISTRY_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._generations: dict[int, ModelGeneration] = {}
        self._registry_file = self._storage_dir / "registry.json"
        self._load()

    @property
    def generation_count(self) -> int:
        return len(self._generations)

    def register(self, model: ModelGeneration) -> ModelGeneration:
        """Register a new model generation."""
        if not model.name:
            model.name = model.model_id
        self._generations[model.generation] = model
        self._save()
        logger.info(
            "Registered model gen %d: %s (%s, %.0fB params, $%.2f)",
            model.generation, model.name, model.base_model,
            model.parameters_b, model.training_cost_usd,
        )
        return model

    def get(self, generation: int) -> Optional[ModelGeneration]:
        """Get a specific generation."""
        return self._generations.get(generation)

    def latest(self) -> Optional[ModelGeneration]:
        """Get the latest (highest number) generation."""
        if not self._generations:
            return None
        return self._generations[max(self._generations.keys())]

    def latest_deployed(self) -> Optional[ModelGeneration]:
        """Get the latest deployed generation."""
        deployed = [g for g in self._generations.values() if g.deployed]
        if not deployed:
            return None
        return max(deployed, key=lambda g: g.generation)

    def best_by_thinkodynamic(self) -> Optional[ModelGeneration]:
        """Get the generation with highest thinkodynamic composite score."""
        scored = [g for g in self._generations.values() if g.thinkodynamic_composite > 0]
        if not scored:
            return None
        return max(scored, key=lambda g: g.thinkodynamic_composite)

    def total_training_cost(self) -> float:
        """Total USD spent on training across all generations."""
        return sum(g.training_cost_usd for g in self._generations.values())

    def lineage(self) -> list[dict[str, Any]]:
        """Return the generation lineage for display."""
        return [
            {
                "gen": g.generation,
                "name": g.name,
                "base": g.base_model,
                "params_b": g.parameters_b,
                "cost": g.training_cost_usd,
                "thinkodynamic": g.thinkodynamic_composite,
                "rv": g.rv_contraction,
                "deployed": g.deployed,
            }
            for g in sorted(self._generations.values(), key=lambda g: g.generation)
        ]

    def _save(self) -> None:
        try:
            data = {
                str(k): v.model_dump()
                for k, v in self._generations.items()
            }
            self._registry_file.write_text(json.dumps(data, indent=2))
        except OSError:
            logger.warning("Failed to save model registry", exc_info=True)

    def _load(self) -> None:
        if not self._registry_file.exists():
            return
        try:
            data = json.loads(self._registry_file.read_text())
            for k, v in data.items():
                self._generations[int(k)] = ModelGeneration.model_validate(v)
            logger.debug("Loaded %d model generations", len(self._generations))
        except Exception:
            logger.warning("Failed to load model registry", exc_info=True)
