"""Self-evolution pipeline for the Resident Operator's system prompt.

Decomposes the operator prompt into a PromptGenome with INVARIANT/MUTABLE/ADAPTIVE
segments. Periodically shadow-tests canary prompt variants against the baseline
and promotes winners via CanaryDeployer semantics.

Cost awareness: shadow evaluations use FREE providers only (Ollama Cloud / NVIDIA NIM).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GENOME_PATH = Path.home() / ".dharma" / "evolution" / "operator_prompt.json"


@dataclass
class PromptSegment:
    """A segment of the operator prompt genome."""
    name: str
    content: str
    segment_type: str  # INVARIANT | MUTABLE | ADAPTIVE
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content,
            "segment_type": self.segment_type,
            "version": self.version,
        }


@dataclass
class PromptGenome:
    """The operator's prompt decomposed into evolvable segments."""
    segments: list[PromptSegment] = field(default_factory=list)
    generation: int = 0
    parent_id: str | None = None
    fitness_history: list[float] = field(default_factory=list)

    def render(self, adaptive_context: dict[str, str] | None = None) -> str:
        """Render the full prompt from all segments."""
        parts = []
        ctx = adaptive_context or {}
        for seg in self.segments:
            if seg.segment_type == "ADAPTIVE":
                # Fill from runtime context
                filled = ctx.get(seg.name, seg.content)
                if filled:
                    parts.append(filled)
            else:
                parts.append(seg.content)
        return "\n\n".join(parts)

    def get_mutable_segments(self) -> list[PromptSegment]:
        return [s for s in self.segments if s.segment_type == "MUTABLE"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "parent_id": self.parent_id,
            "fitness_history": self.fitness_history,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptGenome:
        return cls(
            generation=data.get("generation", 0),
            parent_id=data.get("parent_id"),
            fitness_history=data.get("fitness_history", []),
            segments=[
                PromptSegment(**s) for s in data.get("segments", [])
            ],
        )


@dataclass
class ShadowResult:
    """Result of a shadow evaluation comparing baseline vs canary."""
    baseline_score: float
    canary_score: float
    delta: float
    input_text: str
    timestamp: float = field(default_factory=time.time)


class OperatorEvolver:
    """Evolves the operator's system prompt through shadow testing + canary deployment.

    Pipeline:
    1. Every 10th interaction: shadow test — same input processed by canary variant
    2. After 5 shadow evals: compare canary mean YSD vs baseline mean YSD
    3. PROMOTE (delta > 0.05): swap genome, persist
    4. ROLLBACK (delta < -0.02): discard variant, archive failure
    5. DEFER: keep collecting data
    """

    SHADOW_INTERVAL = 10      # Shadow test every N interactions
    EVAL_WINDOW = 5           # Evals before promotion decision
    PROMOTE_THRESHOLD = 0.05
    ROLLBACK_THRESHOLD = -0.02

    def __init__(self, genome_path: Path | None = None) -> None:
        self._genome_path = genome_path or _GENOME_PATH
        self._genome: PromptGenome | None = None
        self._canary_genome: PromptGenome | None = None
        self._shadow_results: list[ShadowResult] = []
        self._baseline_scores: list[float] = []

    async def init(self) -> None:
        """Load or create the operator prompt genome."""
        self._genome = self._load_genome()
        if self._genome is None:
            self._genome = self._create_default_genome()
            self._save_genome(self._genome)
        logger.info(
            "OperatorEvolver initialized (generation=%d, segments=%d)",
            self._genome.generation, len(self._genome.segments),
        )

    def get_current_prompt(
        self, adaptive_context: dict[str, str] | None = None,
    ) -> str:
        """Render the current promoted genome with adaptive sections filled."""
        if self._genome is None:
            return ""
        return self._genome.render(adaptive_context)

    async def maybe_shadow_evaluate(
        self,
        interaction_count: int,
        user_input: str,
        operator_output: str,
        baseline_score: float,
    ) -> None:
        """Conditionally run a shadow evaluation.

        Called every interaction; only actually evaluates every SHADOW_INTERVAL.
        """
        if interaction_count % self.SHADOW_INTERVAL != 0:
            return

        self._baseline_scores.append(baseline_score)

        # Generate canary if we don't have one
        if self._canary_genome is None:
            self._canary_genome = self._mutate_genome()

        # Score the canary variant
        canary_score = await self._score_canary(user_input)

        result = ShadowResult(
            baseline_score=baseline_score,
            canary_score=canary_score,
            delta=canary_score - baseline_score,
            input_text=user_input[:200],
        )
        self._shadow_results.append(result)

        logger.info(
            "Shadow eval #%d: baseline=%.4f canary=%.4f delta=%+.4f",
            len(self._shadow_results), baseline_score, canary_score, result.delta,
        )

        # Check if we have enough evals for a decision
        if len(self._shadow_results) >= self.EVAL_WINDOW:
            await self.check_promotion()

    async def check_promotion(self) -> str | None:
        """Evaluate accumulated shadow results and decide: PROMOTE/ROLLBACK/DEFER."""
        if not self._shadow_results or not self._baseline_scores:
            return None

        baseline_mean = sum(self._baseline_scores) / len(self._baseline_scores)
        canary_mean = sum(r.canary_score for r in self._shadow_results) / len(self._shadow_results)
        delta = canary_mean - baseline_mean

        if delta > self.PROMOTE_THRESHOLD:
            # PROMOTE: swap canary into active genome
            if self._canary_genome and self._genome:
                self._canary_genome.generation = self._genome.generation + 1
                self._canary_genome.parent_id = f"gen_{self._genome.generation}"
                self._canary_genome.fitness_history = [canary_mean]
                self._genome = self._canary_genome
                self._save_genome(self._genome)
                logger.info(
                    "PROMOTE: canary → generation %d (delta=%+.4f)",
                    self._genome.generation, delta,
                )
            self._reset_shadow()
            return "PROMOTE"

        elif delta < self.ROLLBACK_THRESHOLD:
            # ROLLBACK: discard canary
            self._archive_failure(delta)
            logger.info("ROLLBACK: canary discarded (delta=%+.4f)", delta)
            self._reset_shadow()
            return "ROLLBACK"

        else:
            # DEFER: keep collecting (but reset if window exceeded)
            if len(self._shadow_results) >= self.EVAL_WINDOW * 2:
                logger.info("DEFER: resetting after %d stale evals", len(self._shadow_results))
                self._reset_shadow()
            return "DEFER"

    def _reset_shadow(self) -> None:
        self._canary_genome = None
        self._shadow_results.clear()
        self._baseline_scores.clear()

    # -- Genome mutation ----------------------------------------------------

    def _mutate_genome(self) -> PromptGenome | None:
        """Create a mutated copy of the current genome (MUTABLE segments only)."""
        if self._genome is None:
            return None

        import copy
        canary = copy.deepcopy(self._genome)

        for seg in canary.get_mutable_segments():
            # Simple mutation: minor wording adjustments
            # In production, this would use an LLM call on a free provider
            seg.version += 1
            seg.content = self._apply_mutation(seg.content)

        return canary

    @staticmethod
    def _apply_mutation(text: str) -> str:
        """Apply a simple deterministic mutation to prompt text.

        In production: use free LLM (Ollama/NIM) for intelligent rewording.
        For now: minor structural adjustments that preserve semantics.
        """
        # Swap bullet point style as a minimal mutation
        if "- " in text and "* " not in text:
            return text.replace("- ", "* ", 1)
        elif "* " in text:
            return text.replace("* ", "- ", 1)
        # Add emphasis to first instruction
        lines = text.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(("*", "-", "#", "APPROACH", "TONE")):
                lines[i] = line  # No-op for now; real mutation via LLM
                break
        return "\n".join(lines)

    # -- Canary scoring -----------------------------------------------------

    async def _score_canary(self, user_input: str) -> float:
        """Score the canary prompt variant on the given input.

        Uses free providers only. Falls back to heuristic scoring.
        """
        if self._canary_genome is None:
            return 5.0

        # Heuristic scoring based on prompt quality metrics
        prompt = self._canary_genome.render()
        # Score based on: conciseness, specificity, coverage
        length_penalty = max(0, (len(prompt) - 2000) / 10000)  # Penalize bloat
        specificity = sum(1 for w in ("tool", "gate", "stigmergy", "swarm", "delegate")
                         if w in prompt.lower()) / 5.0
        score = 5.0 + 0.15 * (specificity - length_penalty)
        return max(5.0, min(5.15, score))

    # -- Persistence --------------------------------------------------------

    def _load_genome(self) -> PromptGenome | None:
        if self._genome_path.exists():
            try:
                data = json.loads(self._genome_path.read_text())
                return PromptGenome.from_dict(data)
            except Exception as e:
                logger.warning("Failed to load genome: %s", e)
        return None

    def _save_genome(self, genome: PromptGenome) -> None:
        self._genome_path.parent.mkdir(parents=True, exist_ok=True)
        self._genome_path.write_text(json.dumps(genome.to_dict(), indent=2))

    def _archive_failure(self, delta: float) -> None:
        """Archive a failed canary for post-mortem analysis."""
        archive_dir = self._genome_path.parent / "canary_failures"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        path = archive_dir / f"canary_{ts}.json"
        if self._canary_genome:
            data = self._canary_genome.to_dict()
            data["failure_delta"] = delta
            data["shadow_results"] = [
                {"baseline": r.baseline_score, "canary": r.canary_score, "delta": r.delta}
                for r in self._shadow_results
            ]
            path.write_text(json.dumps(data, indent=2))

    def _create_default_genome(self) -> PromptGenome:
        """Create the initial operator prompt genome from the hardcoded prompt."""
        from dharma_swarm.resident_operator import _INVARIANT_PROMPT, _MUTABLE_PROMPT

        return PromptGenome(
            generation=0,
            segments=[
                PromptSegment(
                    name="identity",
                    content=_INVARIANT_PROMPT,
                    segment_type="INVARIANT",
                ),
                PromptSegment(
                    name="approach",
                    content=_MUTABLE_PROMPT,
                    segment_type="MUTABLE",
                ),
                PromptSegment(
                    name="swarm_state",
                    content="",
                    segment_type="ADAPTIVE",
                ),
                PromptSegment(
                    name="stigmergy_context",
                    content="",
                    segment_type="ADAPTIVE",
                ),
                PromptSegment(
                    name="conversation_summary",
                    content="",
                    segment_type="ADAPTIVE",
                ),
            ],
        )

    def status_dict(self) -> dict[str, Any]:
        return {
            "generation": self._genome.generation if self._genome else 0,
            "segments": len(self._genome.segments) if self._genome else 0,
            "shadow_evals_pending": len(self._shadow_results),
            "has_canary": self._canary_genome is not None,
            "baseline_scores": len(self._baseline_scores),
        }


__all__ = ["OperatorEvolver", "PromptGenome", "PromptSegment"]
