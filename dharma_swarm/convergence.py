"""Plateau and convergence detection for Darwin Engine."""

from __future__ import annotations

from statistics import pvariance

from pydantic import BaseModel, Field


class ConvergenceConfig(BaseModel):
    """Configuration for convergence and restart detection."""

    window_size: int = 20
    variance_threshold: float = 0.01
    improvement_threshold: float = 0.05
    restart_mutation_multiplier: float = 2.0
    restart_duration: int = 10


class ConvergenceState(BaseModel):
    """Current convergence-tracking state."""

    fitness_history: list[float] = Field(default_factory=list)
    converged: bool = False
    plateau_detected: bool = False
    restart_cycles_remaining: int = 0
    last_variance: float = 0.0
    last_improvement: float = 0.0


class ConvergenceDetector:
    """Detect plateaus and open a bounded restart window."""

    def __init__(self, config: ConvergenceConfig | None = None) -> None:
        self.config = config or ConvergenceConfig()
        self.state = ConvergenceState()

    def update(self, best_fitness: float) -> bool:
        """Record a cycle result and trigger restart mode if plateaued."""
        if self.state.restart_cycles_remaining > 0:
            self.state.restart_cycles_remaining -= 1

        self.state.fitness_history.append(float(best_fitness))
        if len(self.state.fitness_history) < self.config.window_size:
            return False

        recent = self.state.fitness_history[-self.config.window_size :]
        self.state.last_variance = (
            pvariance(recent) if len(recent) > 1 else 0.0
        )
        self.state.converged = self.state.last_variance < self.config.variance_threshold

        prior = self.state.fitness_history[: -self.config.window_size]
        if prior:
            best_before = max(prior)
            best_recent = max(recent)
            self.state.last_improvement = best_recent - best_before
        else:
            self.state.last_improvement = max(recent) - min(recent)

        self.state.plateau_detected = (
            self.state.last_improvement < self.config.improvement_threshold
        )

        if (
            self.state.converged
            and self.state.plateau_detected
            and self.state.restart_cycles_remaining == 0
        ):
            self.state.restart_cycles_remaining = self.config.restart_duration
            return True
        return False

    def is_restart_active(self) -> bool:
        """Return whether restart parameters should currently be active."""
        return self.state.restart_cycles_remaining > 0

    def get_restart_mutation_rate(self, base_rate: float) -> float:
        """Amplify mutation rate during restart windows."""
        if self.is_restart_active():
            return float(base_rate) * self.config.restart_mutation_multiplier
        return float(base_rate)
