"""Strategy reinforcement through behavioral RL.

Extracts winning patterns from top trajectories and reinforces them by
promoting successful strategies into agent system prompts. This is NOT
gradient descent — it's evolutionary strategy selection at the behavioral
level, using trajectories scored by ThinkodynamicScorer.

The loop:
    1. Load completed trajectories (from TrajectoryCollector)
    2. Score them (ThinkodynamicScorer)
    3. Select top-K by UCB (exploit best + explore novel)
    4. Extract strategy patterns (prompt fragments, tool sequences)
    5. Inject winning patterns into agent configs (system_prompt)
    6. Next cycle: agents use reinforced strategies → new trajectories

Inspired by IPA's chunk-level credit assignment (arXiv:2512.24873)
but operating at the strategy level, not the weight level.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_STRATEGY_DIR = Path.home() / ".dharma" / "strategies"


# ---------------------------------------------------------------------------
# Strategy models
# ---------------------------------------------------------------------------


class StrategyPattern(BaseModel):
    """An extracted strategy pattern from successful trajectories."""

    pattern_id: str = ""
    name: str = ""
    description: str = ""
    source_trajectories: list[str] = Field(default_factory=list)
    prompt_fragment: str = ""  # The system prompt text to inject
    tool_sequence: list[str] = Field(default_factory=list)  # Tool-use pattern
    avg_fitness: float = 0.0
    avg_thinkodynamic: float = 0.0
    times_used: int = 0
    times_succeeded: int = 0
    ucb_score: float = 0.0
    created_at: float = Field(default_factory=time.time)
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.times_used == 0:
            return 0.0
        return self.times_succeeded / self.times_used

    @property
    def confidence(self) -> float:
        """Confidence in this strategy (more uses = more confident)."""
        return min(self.times_used / 10.0, 1.0)


class ReinforcementResult(BaseModel):
    """Result of a reinforcement cycle."""

    cycle_number: int = 0
    trajectories_evaluated: int = 0
    patterns_extracted: int = 0
    patterns_promoted: int = 0
    top_pattern: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


# ---------------------------------------------------------------------------
# UCB Selection
# ---------------------------------------------------------------------------


def ucb_score(
    avg_reward: float,
    times_selected: int,
    total_rounds: int,
    exploration_weight: float = 1.414,
) -> float:
    """Upper Confidence Bound score for strategy selection.

    Balances exploitation (high avg_reward) with exploration
    (less-tried strategies get a bonus).
    """
    if times_selected == 0:
        return float("inf")  # Always try untried strategies
    exploitation = avg_reward
    exploration = exploration_weight * math.sqrt(
        math.log(max(total_rounds, 1)) / times_selected
    )
    return exploitation + exploration


# ---------------------------------------------------------------------------
# Strategy Reinforcer
# ---------------------------------------------------------------------------


class StrategyReinforcer:
    """Extracts and promotes winning strategies from trajectories.

    Usage:
        reinforcer = StrategyReinforcer()

        # Run a reinforcement cycle
        result = reinforcer.reinforce_cycle(trajectories)

        # Get the best strategy fragments for an agent
        fragments = reinforcer.get_prompt_fragments(top_k=3)

        # Build a reinforced system prompt
        prompt = reinforcer.build_reinforced_prompt(base_prompt, top_k=3)
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._storage_dir = storage_dir or _STRATEGY_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._patterns: dict[str, StrategyPattern] = {}
        self._cycle_count: int = 0
        self._pattern_file = self._storage_dir / "patterns.jsonl"
        self._load_patterns()

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    # -- Core cycle --------------------------------------------------------

    def reinforce_cycle(
        self,
        trajectories: list[Any],
        min_thinkodynamic: float = 0.5,
        top_k: int = 5,
    ) -> ReinforcementResult:
        """Run one reinforcement cycle on completed trajectories.

        Args:
            trajectories: List of Trajectory objects (from TrajectoryCollector).
            min_thinkodynamic: Minimum thinkodynamic composite to consider.
            top_k: Number of top strategies to extract/reinforce.

        Returns:
            ReinforcementResult summarizing the cycle.
        """
        self._cycle_count += 1

        # 1. Score and filter trajectories
        scored = []
        for traj in trajectories:
            outcome = getattr(traj, "outcome", None)
            if outcome is None or not getattr(outcome, "success", False):
                continue

            # Get thinkodynamic score
            td_score = getattr(outcome, "thinkodynamic_score", None)
            if td_score is None:
                # Score it now
                try:
                    from dharma_swarm.thinkodynamic_scorer import ThinkodynamicScorer
                    scorer = ThinkodynamicScorer()
                    td = scorer.score_trajectory(traj)
                    composite = td.composite
                except Exception:
                    composite = 0.0
            else:
                composite = td_score.get("composite", 0.0) if isinstance(td_score, dict) else 0.0

            if composite >= min_thinkodynamic:
                scored.append((traj, composite))

        # 2. Sort by composite score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)
        top_trajectories = scored[:top_k]

        # 3. Extract patterns from top trajectories
        new_patterns = 0
        for traj, composite in top_trajectories:
            pattern = self._extract_pattern(traj, composite)
            if pattern:
                self._add_or_update_pattern(pattern)
                new_patterns += 1

        # 4. Recalculate UCB scores for all patterns
        for p in self._patterns.values():
            p.ucb_score = ucb_score(
                avg_reward=p.avg_thinkodynamic,
                times_selected=p.times_used,
                total_rounds=self._cycle_count,
            )

        # 5. Persist
        self._save_patterns()

        result = ReinforcementResult(
            cycle_number=self._cycle_count,
            trajectories_evaluated=len(trajectories),
            patterns_extracted=new_patterns,
            patterns_promoted=min(new_patterns, top_k),
            top_pattern=self._top_pattern_name(),
        )

        logger.info(
            "Reinforcement cycle %d: %d trajectories → %d patterns extracted",
            result.cycle_number,
            result.trajectories_evaluated,
            result.patterns_extracted,
        )
        return result

    # -- Strategy extraction -----------------------------------------------

    def _extract_pattern(self, trajectory: Any, composite: float) -> Optional[StrategyPattern]:
        """Extract a strategy pattern from a successful trajectory."""
        chunks = getattr(trajectory, "chunks", [])
        if not chunks:
            return None

        traj_id = getattr(trajectory, "trajectory_id", "unknown")
        task_title = getattr(trajectory, "task_title", "")

        # Extract the most informative prompt fragment
        # (the chunk with highest response quality, measured by length/density)
        best_chunk = max(chunks, key=lambda c: len(getattr(c, "response", "")))
        prompt_fragment = getattr(best_chunk, "prompt", "")[:500]
        response_preview = getattr(best_chunk, "response", "")[:300]

        # Extract tool-use sequence
        tool_sequence = []
        for chunk in chunks:
            model = getattr(chunk, "model", "")
            if model:
                tool_sequence.append(model)

        # Create a condensed strategy description
        description = (
            f"Strategy from task '{task_title[:80]}': "
            f"{len(chunks)} steps, thinkodynamic={composite:.2f}. "
            f"Key approach: {response_preview[:100]}..."
        )

        pattern = StrategyPattern(
            pattern_id=f"sp-{traj_id[:8]}-{int(time.time()) % 10000}",
            name=f"strategy-{task_title[:30]}".replace(" ", "-").lower(),
            description=description,
            source_trajectories=[traj_id],
            prompt_fragment=self._distill_prompt_fragment(chunks),
            tool_sequence=tool_sequence[:10],
            avg_fitness=composite,
            avg_thinkodynamic=composite,
            times_used=0,
            times_succeeded=0,
        )
        return pattern

    def _distill_prompt_fragment(self, chunks: list) -> str:
        """Distill the key instruction from successful chunks.

        Extracts the most actionable parts of prompts that led to
        high-quality responses. This becomes the injected strategy.
        """
        if not chunks:
            return ""

        # Collect all prompts from the trajectory
        prompts = [getattr(c, "prompt", "") for c in chunks if getattr(c, "prompt", "")]
        if not prompts:
            return ""

        # Take the first prompt (task setup) and last prompt (refinement)
        first = prompts[0][:200]
        last = prompts[-1][:200] if len(prompts) > 1 else ""

        fragment = f"[Reinforced strategy] Task pattern: {first}"
        if last and last != first:
            fragment += f"\nRefinement approach: {last}"

        return fragment[:500]

    # -- Pattern management ------------------------------------------------

    def _add_or_update_pattern(self, pattern: StrategyPattern) -> None:
        """Add a new pattern or update an existing one with similar name."""
        # Check for existing similar pattern
        existing = self._patterns.get(pattern.name)
        if existing:
            # Update with running average
            n = existing.times_used + 1
            existing.avg_thinkodynamic = (
                (existing.avg_thinkodynamic * existing.times_used + pattern.avg_thinkodynamic)
                / n
            )
            existing.avg_fitness = (
                (existing.avg_fitness * existing.times_used + pattern.avg_fitness)
                / n
            )
            existing.source_trajectories.extend(pattern.source_trajectories)
            existing.source_trajectories = existing.source_trajectories[-20:]  # Keep last 20
        else:
            self._patterns[pattern.name] = pattern

    def _top_pattern_name(self) -> Optional[str]:
        """Get the name of the highest-UCB pattern."""
        if not self._patterns:
            return None
        return max(self._patterns.values(), key=lambda p: p.ucb_score).name

    # -- Prompt building ---------------------------------------------------

    def get_top_patterns(self, top_k: int = 3) -> list[StrategyPattern]:
        """Get top-K patterns ranked by UCB score."""
        sorted_patterns = sorted(
            self._patterns.values(),
            key=lambda p: p.ucb_score,
            reverse=True,
        )
        return sorted_patterns[:top_k]

    def get_prompt_fragments(self, top_k: int = 3) -> list[str]:
        """Get prompt fragments from top-K patterns."""
        return [p.prompt_fragment for p in self.get_top_patterns(top_k) if p.prompt_fragment]

    def build_reinforced_prompt(
        self,
        base_prompt: str,
        top_k: int = 3,
    ) -> str:
        """Build a system prompt with reinforced strategy fragments.

        Args:
            base_prompt: The agent's original system prompt.
            top_k: Number of top strategy fragments to inject.

        Returns:
            Augmented system prompt with strategy fragments appended.
        """
        fragments = self.get_prompt_fragments(top_k)
        if not fragments:
            return base_prompt

        strategy_section = "\n\n## Reinforced Strategies (from successful trajectories)\n"
        for i, frag in enumerate(fragments, 1):
            strategy_section += f"\n### Strategy {i}\n{frag}\n"

        return base_prompt + strategy_section

    def record_outcome(
        self,
        pattern_name: str,
        success: bool,
    ) -> None:
        """Record the outcome of using a strategy pattern."""
        pattern = self._patterns.get(pattern_name)
        if pattern:
            pattern.times_used += 1
            if success:
                pattern.times_succeeded += 1
            pattern.last_used = time.time()

    # -- Persistence -------------------------------------------------------

    def _save_patterns(self) -> None:
        """Save all patterns to JSONL."""
        try:
            with open(self._pattern_file, "w") as f:
                for p in self._patterns.values():
                    f.write(p.model_dump_json() + "\n")
        except OSError:
            logger.warning("Failed to save strategy patterns", exc_info=True)

    def _load_patterns(self) -> None:
        """Load patterns from JSONL."""
        if not self._pattern_file.exists():
            return
        try:
            with open(self._pattern_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        p = StrategyPattern.model_validate_json(line)
                        self._patterns[p.name] = p
                    except Exception:
                        continue
            logger.debug("Loaded %d strategy patterns", len(self._patterns))
        except OSError:
            logger.warning("Failed to load strategy patterns", exc_info=True)

    def stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        return {
            "total_patterns": len(self._patterns),
            "cycle_count": self._cycle_count,
            "top_pattern": self._top_pattern_name(),
            "avg_success_rate": (
                sum(p.success_rate for p in self._patterns.values())
                / max(len(self._patterns), 1)
            ),
        }
