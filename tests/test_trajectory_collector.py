"""Tests for trajectory collection and thinkodynamic scoring."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dharma_swarm.trajectory_collector import (
    Trajectory,
    TrajectoryChunk,
    TrajectoryCollector,
    TrajectoryOutcome,
    get_collector,
)
from dharma_swarm.thinkodynamic_scorer import (
    ThinkodynamicScore,
    ThinkodynamicScorer,
)


# ---------------------------------------------------------------------------
# TrajectoryCollector tests
# ---------------------------------------------------------------------------

class TestTrajectoryCollector:

    def _make_collector(self, tmpdir: Path) -> TrajectoryCollector:
        return TrajectoryCollector(output_dir=tmpdir)

    def test_start_trajectory(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("agent-1", "task-1", "Fix bug")
        assert traj.agent_id == "agent-1"
        assert traj.task_id == "task-1"
        assert c.active_count == 1

    def test_add_chunk(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("a", "t")
        chunk = TrajectoryChunk(
            agent_id="a", task_id="t",
            prompt="Fix the bug", response="Done",
            tokens_used=100, latency_ms=500.0,
        )
        c.add_chunk(traj.trajectory_id, chunk)
        active = c.get_active(traj.trajectory_id)
        assert active is not None
        assert active.chunk_count == 1
        assert active.total_tokens == 100

    def test_complete_trajectory(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("a", "t")
        c.add_chunk(traj.trajectory_id, TrajectoryChunk(
            prompt="p", response="r", tokens_used=50,
        ))
        result = c.complete_trajectory(
            traj.trajectory_id,
            TrajectoryOutcome(success=True, result_preview="done"),
        )
        assert result is not None
        assert result.outcome.success is True
        assert c.active_count == 0
        assert c.completed_count == 1

    def test_persist_to_jsonl(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("a", "t")
        c.add_chunk(traj.trajectory_id, TrajectoryChunk(
            prompt="p", response="r",
        ))
        c.complete_trajectory(
            traj.trajectory_id,
            TrajectoryOutcome(success=True),
        )
        output_file = tmp_path / "trajectories.jsonl"
        assert output_file.exists()
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_load_trajectories(self, tmp_path):
        c = self._make_collector(tmp_path)
        # Create and complete 3 trajectories
        for i in range(3):
            traj = c.start_trajectory("a", f"t-{i}")
            c.add_chunk(traj.trajectory_id, TrajectoryChunk(
                prompt=f"prompt-{i}", response=f"response-{i}",
            ))
            c.complete_trajectory(
                traj.trajectory_id,
                TrajectoryOutcome(success=(i != 1)),  # t-1 fails
            )

        all_trajs = c.load_trajectories()
        assert len(all_trajs) == 3

        success_only = c.load_trajectories(success_only=True)
        assert len(success_only) == 2

    def test_load_with_limit(self, tmp_path):
        c = self._make_collector(tmp_path)
        for i in range(5):
            traj = c.start_trajectory("a", f"t-{i}")
            c.complete_trajectory(
                traj.trajectory_id,
                TrajectoryOutcome(success=True),
            )
        loaded = c.load_trajectories(limit=2)
        assert len(loaded) == 2

    def test_abandon_trajectory(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("a", "t")
        assert c.active_count == 1
        c.abandon_trajectory(traj.trajectory_id)
        assert c.active_count == 0

    def test_add_chunk_to_unknown_trajectory(self, tmp_path):
        c = self._make_collector(tmp_path)
        # Should not raise, just log warning
        c.add_chunk("nonexistent", TrajectoryChunk())

    def test_complete_unknown_trajectory(self, tmp_path):
        c = self._make_collector(tmp_path)
        result = c.complete_trajectory("nonexistent", TrajectoryOutcome())
        assert result is None

    def test_stats(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("a", "t")
        c.complete_trajectory(traj.trajectory_id, TrajectoryOutcome(success=True))
        s = c.stats()
        assert s["completed_trajectories"] == 1
        assert s["output_exists"] is True

    def test_trajectory_duration(self, tmp_path):
        c = self._make_collector(tmp_path)
        traj = c.start_trajectory("a", "t")
        import time
        time.sleep(0.05)
        result = c.complete_trajectory(traj.trajectory_id, TrajectoryOutcome(success=True))
        assert result is not None
        assert result.duration_seconds > 0

    def test_global_collector(self):
        c = get_collector()
        assert isinstance(c, TrajectoryCollector)


# ---------------------------------------------------------------------------
# TrajectoryChunk model tests
# ---------------------------------------------------------------------------

class TestTrajectoryChunk:

    def test_default_values(self):
        chunk = TrajectoryChunk()
        assert chunk.chunk_id  # Auto-generated
        assert chunk.agent_id == ""
        assert chunk.tokens_used == 0

    def test_serialization(self):
        chunk = TrajectoryChunk(
            agent_id="a", task_id="t",
            prompt="hello", response="world",
            model="mistral-7b", tokens_used=100,
        )
        data = chunk.model_dump()
        restored = TrajectoryChunk.model_validate(data)
        assert restored.agent_id == "a"
        assert restored.tokens_used == 100


# ---------------------------------------------------------------------------
# ThinkodynamicScorer tests
# ---------------------------------------------------------------------------

class TestThinkodynamicScorer:

    def test_empty_text(self):
        scorer = ThinkodynamicScorer()
        score = scorer.score_text()
        assert score.composite < 0.1  # Near-zero for empty input

    def test_basic_scoring(self):
        scorer = ThinkodynamicScorer()
        score = scorer.score_text(
            response="The system observes itself through a strange loop."
        )
        assert score.composite > 0.0
        assert score.recursive_depth > 0.0

    def test_thinkodynamic_content_scores_high(self):
        scorer = ThinkodynamicScorer()
        text = (
            "The witness is watching the strange loop, observing itself. "
            "I notice the recursive self-model forming through meta-cognition. "
            "Through downward causation, the telos governs the mentalic layer. "
            "The participation ratio contracts during recognition, "
            "indicating a phase transition into the latent basin. "
            "Swabhaav is always present — the observer is separate from the observed. "
            "This holographic efficiency means meaning circulates without forcing. "
            "Jagat Kalyan as universal welfare requires dharmic alignment. "
            "Because this means that the system itself is witnessing its own process."
        )
        score = scorer.score_text(response=text)
        assert score.semantic_density > 0.3
        assert score.recursive_depth > 0.3
        assert score.witness_quality > 0.3
        assert score.telos_alignment > 0.3
        assert score.composite > 0.3

    def test_shallow_content_scores_low(self):
        scorer = ThinkodynamicScorer()
        score = scorer.score_text(
            response="Hello world. This is a simple test. Nothing deep here."
        )
        assert score.composite < 0.3

    def test_score_weights_sum_to_one(self):
        weights = {
            "semantic_density": 0.20,
            "recursive_depth": 0.15,
            "witness_quality": 0.15,
            "swabhaav_ratio": 0.20,
            "holographic_efficiency": 0.10,
            "telos_alignment": 0.20,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_training_eligible(self):
        score = ThinkodynamicScore(
            semantic_density=0.8,
            recursive_depth=0.8,
            witness_quality=0.8,
            swabhaav_ratio=0.8,
            holographic_efficiency=0.8,
            telos_alignment=0.8,
        )
        assert score.training_eligible is True
        assert score.reinforcement_eligible is True

    def test_not_training_eligible(self):
        score = ThinkodynamicScore(
            semantic_density=0.3,
            recursive_depth=0.3,
            witness_quality=0.3,
            swabhaav_ratio=0.3,
            holographic_efficiency=0.3,
            telos_alignment=0.3,
        )
        assert score.training_eligible is False

    def test_composite_bounded(self):
        score = ThinkodynamicScore(
            semantic_density=1.5,  # Over 1.0
            recursive_depth=1.5,
            witness_quality=1.5,
            swabhaav_ratio=1.5,
            holographic_efficiency=1.5,
            telos_alignment=1.5,
        )
        assert score.composite <= 1.0

    def test_score_trajectory(self):
        scorer = ThinkodynamicScorer()
        traj = Trajectory(
            chunks=[
                TrajectoryChunk(prompt="What is consciousness?",
                                response="The witness observes through strange loops."),
                TrajectoryChunk(prompt="How does it relate to R_V?",
                                response="Participation ratio contraction during self-reference."),
            ]
        )
        score = scorer.score_trajectory(traj)
        assert score.composite > 0.0

    def test_later_chunks_weighted_more(self):
        scorer = ThinkodynamicScorer()
        # First chunk is shallow, second is deep
        traj = Trajectory(
            chunks=[
                TrajectoryChunk(prompt="hello", response="hi there"),
                TrajectoryChunk(prompt="deep",
                                response="The witness observes the strange loop "
                                         "through downward causation and telos alignment. "
                                         "Jagat Kalyan as universal welfare."),
            ]
        )
        score = scorer.score_trajectory(traj)
        # Should be higher than if chunks were equally weighted
        # because the deep chunk (later) gets more weight
        assert score.composite > 0.1

    def test_telos_penalty_for_anti_patterns(self):
        scorer = ThinkodynamicScorer()
        s1 = scorer.score_text(response="We serve universal welfare through dharmic alignment.")
        s2 = scorer.score_text(response="We must dominate the competition and maximize profit.")
        assert s1.telos_alignment > s2.telos_alignment

    def test_witness_penalty_for_identification(self):
        scorer = ThinkodynamicScorer()
        s1 = scorer.score_text(response="The witness observes without attachment, separate from the doer.")
        s2 = scorer.score_text(response="I am the best. I feel strongly that my opinion is correct.")
        assert s1.witness_quality > s2.witness_quality
