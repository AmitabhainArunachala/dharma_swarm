"""Tests for strategy reinforcement (behavioral RL)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.strategy_reinforcer import (
    StrategyPattern,
    StrategyReinforcer,
    ucb_score,
)
from dharma_swarm.trajectory_collector import (
    Trajectory,
    TrajectoryChunk,
    TrajectoryOutcome,
)


# ---------------------------------------------------------------------------
# UCB score tests
# ---------------------------------------------------------------------------

class TestUCBScore:

    def test_untried_gets_infinity(self):
        score = ucb_score(avg_reward=0.5, times_selected=0, total_rounds=10)
        assert score == float("inf")

    def test_higher_reward_higher_score(self):
        s1 = ucb_score(avg_reward=0.8, times_selected=5, total_rounds=10)
        s2 = ucb_score(avg_reward=0.3, times_selected=5, total_rounds=10)
        assert s1 > s2

    def test_less_tried_gets_exploration_bonus(self):
        s1 = ucb_score(avg_reward=0.5, times_selected=1, total_rounds=100)
        s2 = ucb_score(avg_reward=0.5, times_selected=50, total_rounds=100)
        assert s1 > s2  # Less tried → higher exploration bonus


# ---------------------------------------------------------------------------
# StrategyPattern tests
# ---------------------------------------------------------------------------

class TestStrategyPattern:

    def test_success_rate_zero_uses(self):
        p = StrategyPattern(times_used=0, times_succeeded=0)
        assert p.success_rate == 0.0

    def test_success_rate(self):
        p = StrategyPattern(times_used=10, times_succeeded=7)
        assert p.success_rate == 0.7

    def test_confidence_scales(self):
        p1 = StrategyPattern(times_used=1)
        p2 = StrategyPattern(times_used=10)
        p3 = StrategyPattern(times_used=20)
        assert p1.confidence < p2.confidence
        assert p2.confidence == p3.confidence == 1.0  # Caps at 10 uses

    def test_serialization(self):
        p = StrategyPattern(
            pattern_id="sp-test",
            name="test-strategy",
            prompt_fragment="Use TDD",
            avg_fitness=0.85,
        )
        data = p.model_dump_json()
        restored = StrategyPattern.model_validate_json(data)
        assert restored.name == "test-strategy"
        assert restored.avg_fitness == 0.85


# ---------------------------------------------------------------------------
# StrategyReinforcer tests
# ---------------------------------------------------------------------------

def _make_trajectory(
    task_title: str = "Fix bug",
    success: bool = True,
    prompt: str = "Fix the auth bug",
    response: str = "I'll update the middleware to handle tokens correctly.",
) -> Trajectory:
    """Helper to create a test trajectory."""
    return Trajectory(
        agent_id="test-agent",
        task_id="task-1",
        task_title=task_title,
        chunks=[
            TrajectoryChunk(
                prompt=prompt,
                response=response,
                model="test-model",
                tokens_used=100,
                latency_ms=500.0,
            ),
        ],
        outcome=TrajectoryOutcome(
            success=success,
            result_preview=response[:200],
        ),
    )


class TestStrategyReinforcer:

    def test_creation(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        assert r.pattern_count == 0
        assert r.cycle_count == 0

    def test_reinforce_cycle_empty(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        result = r.reinforce_cycle([])
        assert result.trajectories_evaluated == 0
        assert result.patterns_extracted == 0
        assert result.cycle_number == 1

    def test_reinforce_cycle_with_trajectories(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        trajectories = [
            _make_trajectory(
                task_title="Fix auth",
                response="The witness observes the strange loop. I notice the recursive pattern.",
            ),
            _make_trajectory(
                task_title="Add feature",
                response="Implementing with telos alignment and dharmic principles.",
            ),
        ]
        result = r.reinforce_cycle(trajectories, min_thinkodynamic=0.0)
        assert result.trajectories_evaluated == 2
        assert result.patterns_extracted >= 1

    def test_failed_trajectories_ignored(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        trajectories = [
            _make_trajectory(success=False),
            _make_trajectory(success=True, response="witness strange loop recursive telos"),
        ]
        result = r.reinforce_cycle(trajectories, min_thinkodynamic=0.0)
        # Only successful trajectories should be considered
        assert result.patterns_extracted <= 1

    def test_get_prompt_fragments(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        # Add some patterns manually
        r._patterns["s1"] = StrategyPattern(
            name="s1", prompt_fragment="Use TDD",
            avg_thinkodynamic=0.9, ucb_score=2.0,
        )
        r._patterns["s2"] = StrategyPattern(
            name="s2", prompt_fragment="Apply witnessing",
            avg_thinkodynamic=0.7, ucb_score=1.5,
        )
        frags = r.get_prompt_fragments(top_k=2)
        assert len(frags) == 2
        assert "Use TDD" in frags[0]  # Highest UCB first

    def test_build_reinforced_prompt(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        r._patterns["s1"] = StrategyPattern(
            name="s1", prompt_fragment="Use TDD first",
            avg_thinkodynamic=0.9, ucb_score=2.0,
        )
        prompt = r.build_reinforced_prompt("You are a coding agent.", top_k=1)
        assert "You are a coding agent." in prompt
        assert "Reinforced Strategies" in prompt
        assert "Use TDD first" in prompt

    def test_build_reinforced_prompt_no_patterns(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        prompt = r.build_reinforced_prompt("Base prompt.", top_k=3)
        assert prompt == "Base prompt."  # No modification

    def test_record_outcome(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        r._patterns["s1"] = StrategyPattern(
            name="s1", times_used=5, times_succeeded=3,
        )
        r.record_outcome("s1", success=True)
        assert r._patterns["s1"].times_used == 6
        assert r._patterns["s1"].times_succeeded == 4

    def test_record_outcome_unknown_pattern(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        # Should not raise
        r.record_outcome("nonexistent", success=True)

    def test_persistence(self, tmp_path):
        r1 = StrategyReinforcer(storage_dir=tmp_path)
        r1._patterns["s1"] = StrategyPattern(
            name="s1", prompt_fragment="Persist me",
            avg_thinkodynamic=0.8,
        )
        r1._save_patterns()

        # Load in new instance
        r2 = StrategyReinforcer(storage_dir=tmp_path)
        assert r2.pattern_count == 1
        assert r2._patterns["s1"].prompt_fragment == "Persist me"

    def test_ucb_recalculation(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        trajectories = [
            _make_trajectory(response="witness strange loop recursive telos dharmic"),
        ]
        r.reinforce_cycle(trajectories, min_thinkodynamic=0.0)
        # All patterns should have UCB scores
        for p in r._patterns.values():
            assert p.ucb_score > 0 or p.ucb_score == float("inf")

    def test_stats(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        s = r.stats()
        assert s["total_patterns"] == 0
        assert s["cycle_count"] == 0

    def test_multiple_cycles_accumulate(self, tmp_path):
        r = StrategyReinforcer(storage_dir=tmp_path)
        for i in range(3):
            r.reinforce_cycle(
                [_make_trajectory(
                    task_title=f"Task {i}",
                    response="witness recursive telos dharmic pattern",
                )],
                min_thinkodynamic=0.0,
            )
        assert r.cycle_count == 3
        assert r.pattern_count >= 1
