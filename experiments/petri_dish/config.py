"""Configuration for the Petri Dish experiment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class PetriDishConfig(BaseModel):
    """All tunables for a petri dish run."""

    # --- LLM ---
    worker_model: str | list[str] = Field(
        default=[
            "openrouter/free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
        description="Model or fallback models for worker agents",
    )
    # Use a different model family for genuine perspective diversity
    consolidator_alpha_model: str | list[str] = Field(
        default=[
            "openrouter/free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
        ],
        description="Model or fallback models for consolidator alpha (thesis)",
    )
    consolidator_beta_model: str | list[str] = Field(
        default=[
            "openrouter/free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
        description="Model or fallback models for consolidator beta (antithesis)",
    )
    worker_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    consolidator_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=256, le=8192)

    # --- Cycle parameters ---
    work_cycles_per_generation: int = Field(
        default=3, ge=1, le=10,
        description="Work cycles before each consolidation",
    )
    total_generations: int = Field(
        default=4, ge=1, le=20,
        description="Total consolidation cycles to run",
    )
    batch_size: int = Field(
        default=12, ge=4, le=40,
        description="Text snippets per work cycle",
    )
    debate_rounds: int = Field(
        default=3, ge=1, le=7,
        description="Rounds in contrarian debate (2 turns per round)",
    )

    # --- Paths ---
    state_dir: Path = Field(
        default=Path(__file__).parent / "state",
        description="Root directory for runtime state",
    )

    # --- Provider ---
    api_key_env: str = Field(
        default="OPENROUTER_API_KEY",
        description="Environment variable holding the API key",
    )

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(f"{self.api_key_env} not set")
        return key

    @property
    def dna_dir(self) -> Path:
        return self.state_dir / "dna"

    @property
    def dna_archive_dir(self) -> Path:
        return self.state_dir / "dna_archive"

    @property
    def traces_dir(self) -> Path:
        return self.state_dir / "traces"

    @property
    def metrics_dir(self) -> Path:
        return self.state_dir / "metrics"

    @property
    def debates_dir(self) -> Path:
        return self.state_dir / "debates"
