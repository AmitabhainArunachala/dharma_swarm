"""Data models for the Petri Dish experiment."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class TextSnippet(BaseModel):
    """A text snippet with ground truth labels."""

    text: str
    true_sentiment: str  # positive | negative | neutral
    true_topic: str      # technology | science | politics | culture | other
    true_urgency: str    # high | medium | low


class Classification(BaseModel):
    """An agent's classification of a single snippet."""

    sentiment: str = ""
    topic: str = ""
    urgency: str = ""
    confidence: float = 0.5
    raw_response: str = ""


class SnippetResult(BaseModel):
    """Classification result for one snippet with ground truth comparison."""

    snippet_text: str
    classification: Classification
    true_sentiment: str
    true_topic: str
    true_urgency: str
    sentiment_correct: bool = False
    topic_correct: bool = False
    urgency_correct: bool = False


class WorkerTrace(BaseModel):
    """Complete trace of one worker's performance in a cycle."""

    agent_name: str
    cycle_id: int
    generation: int
    results: list[SnippetResult] = Field(default_factory=list)
    sentiment_accuracy: float = 0.0
    topic_accuracy: float = 0.0
    urgency_accuracy: float = 0.0
    overall_accuracy: float = 0.0
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def compute_accuracy(self) -> None:
        """Compute accuracy scores from results."""
        if not self.results:
            return
        n = len(self.results)
        self.sentiment_accuracy = sum(r.sentiment_correct for r in self.results) / n
        self.topic_accuracy = sum(r.topic_correct for r in self.results) / n
        self.urgency_accuracy = sum(r.urgency_correct for r in self.results) / n
        self.overall_accuracy = (
            self.sentiment_accuracy + self.topic_accuracy + self.urgency_accuracy
        ) / 3.0


class Modification(BaseModel):
    """A specific change to an agent's behavioral DNA."""

    agent: str
    section: str
    action: str  # replace | append | delete
    old_text: str = ""
    new_text: str = ""
    rationale: str = ""


class ConsolidationResult(BaseModel):
    """Output of a consolidation cycle."""

    generation: int
    debate_transcript: list[dict[str, str]] = Field(default_factory=list)
    modifications: list[Modification] = Field(default_factory=list)
    pre_scores: dict[str, float] = Field(default_factory=dict)
    post_scores: dict[str, float] = Field(default_factory=dict)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class CycleMetrics(BaseModel):
    """Metrics for a single work cycle."""

    cycle_id: int
    generation: int
    agent_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    system_score: float = 0.0
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ExperimentReport(BaseModel):
    """Final experiment summary."""

    total_generations: int = 0
    total_work_cycles: int = 0
    total_consolidations: int = 0
    initial_system_score: float = 0.0
    final_system_score: float = 0.0
    improvement: float = 0.0
    score_trajectory: list[float] = Field(default_factory=list)
    all_modifications: list[Modification] = Field(default_factory=list)
    per_generation_scores: dict[int, float] = Field(default_factory=dict)
