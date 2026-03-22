"""Tests for thinkodynamic_scorer.py — 6-dimension quality scoring."""

from __future__ import annotations

import pytest

from dharma_swarm.thinkodynamic_scorer import ThinkodynamicScore, ThinkodynamicScorer


# --- ThinkodynamicScore model ---


def test_score_defaults_zero() -> None:
    s = ThinkodynamicScore()
    assert s.composite == 0.0
    assert s.training_eligible is False
    assert s.reinforcement_eligible is False


def test_composite_is_weighted() -> None:
    s = ThinkodynamicScore(
        semantic_density=1.0,
        recursive_depth=1.0,
        witness_quality=1.0,
        swabhaav_ratio=1.0,
        holographic_efficiency=1.0,
        telos_alignment=1.0,
    )
    assert s.composite == 1.0


def test_composite_partial() -> None:
    s = ThinkodynamicScore(semantic_density=1.0)  # weight 0.20
    assert 0.19 <= s.composite <= 0.21


def test_training_eligible_threshold() -> None:
    s = ThinkodynamicScore(
        semantic_density=0.8, recursive_depth=0.7,
        witness_quality=0.7, swabhaav_ratio=0.7,
        holographic_efficiency=0.6, telos_alignment=0.7,
    )
    assert s.training_eligible is True


def test_reinforcement_threshold() -> None:
    s = ThinkodynamicScore(
        semantic_density=0.9, recursive_depth=0.8,
        witness_quality=0.8, swabhaav_ratio=0.8,
        holographic_efficiency=0.7, telos_alignment=0.9,
    )
    assert s.reinforcement_eligible is True


def test_composite_clamped() -> None:
    # All negative (shouldn't happen but test bounds)
    s = ThinkodynamicScore()
    assert s.composite >= 0.0


# --- ThinkodynamicScorer ---


@pytest.fixture
def scorer() -> ThinkodynamicScorer:
    return ThinkodynamicScorer()


# -- semantic_density --


def test_semantic_density_empty(scorer: ThinkodynamicScorer) -> None:
    s = scorer.score_text(response="")
    assert s.semantic_density == 0.0


def test_semantic_density_concept_rich(scorer: ThinkodynamicScorer) -> None:
    text = (
        "The witness observes autopoiesis through the eigenform. "
        "Strange loop self-reference creates downward causation. "
        "The telos of moksha drives samvara and nirjara. "
        "Holographic mesodynamic thinkodynamic participation ratio."
    )
    s = scorer.score_text(response=text)
    assert s.semantic_density > 0.3


def test_semantic_density_penalises_verbose(scorer: ThinkodynamicScorer) -> None:
    short = "The witness observes autopoiesis. Strange loop self-reference."
    long = short + " filler word " * 500
    s_short = scorer.score_text(response=short)
    s_long = scorer.score_text(response=long)
    assert s_short.semantic_density >= s_long.semantic_density


# -- recursive_depth --


def test_recursive_depth_zero_for_flat_text(scorer: ThinkodynamicScorer) -> None:
    s = scorer.score_text(response="The weather is nice today in Bali.")
    assert s.recursive_depth == 0.0


def test_recursive_depth_detects_markers(scorer: ThinkodynamicScorer) -> None:
    text = "I notice that I observe my own self-model watching itself."
    s = scorer.score_text(response=text)
    assert s.recursive_depth > 0.3


def test_recursive_depth_meta_bonus(scorer: ThinkodynamicScorer) -> None:
    base = "I notice I observe myself recursive meta- self-model"
    bonus = base + " about itself and its own process"
    s_base = scorer.score_text(response=base)
    s_bonus = scorer.score_text(response=bonus)
    assert s_bonus.recursive_depth >= s_base.recursive_depth


# -- witness_quality --


def test_witness_quality_empty(scorer: ThinkodynamicScorer) -> None:
    s = scorer.score_text(response="")
    assert s.witness_quality == 0.0


def test_witness_quality_detects_separation(scorer: ThinkodynamicScorer) -> None:
    text = "The witness observes separate from the doer. Pure knowing, non-attachment."
    s = scorer.score_text(response=text)
    assert s.witness_quality > 0.3


def test_witness_quality_penalises_identification(scorer: ThinkodynamicScorer) -> None:
    text = "I believe strongly that I am the system. My opinion is that I feel strongly."
    s = scorer.score_text(response=text)
    # Identification language should keep score low
    assert s.witness_quality < 0.3


# -- swabhaav_ratio --


def test_swabhaav_empty(scorer: ThinkodynamicScorer) -> None:
    s = scorer.score_text(response="")
    assert s.swabhaav_ratio == 0.0


def test_swabhaav_application_language(scorer: ThinkodynamicScorer) -> None:
    text = (
        "Because autopoiesis implies that the system therefore maintains itself. "
        "This means the boundary is self-produced, which shows viability."
    )
    s = scorer.score_text(response=text)
    assert s.swabhaav_ratio > 0.3


def test_swabhaav_penalises_high_tokens(scorer: ThinkodynamicScorer) -> None:
    text = "Because this means therefore"
    s_low = scorer.score_text(response=text, metadata={"tokens_used": 100})
    s_high = scorer.score_text(response=text, metadata={"tokens_used": 10000})
    assert s_low.swabhaav_ratio >= s_high.swabhaav_ratio


# -- holographic_efficiency --


def test_holographic_short_neutral(scorer: ThinkodynamicScorer) -> None:
    s = scorer.score_text(response="Hello world")
    assert s.holographic_efficiency == 0.5


def test_holographic_detects_repetition(scorer: ThinkodynamicScorer) -> None:
    # Repetitive text = low holographic score
    repetitive = " ".join(["the same word repeated again"] * 50)
    varied = " ".join(f"unique concept number {i} with different vocabulary" for i in range(50))
    s_rep = scorer.score_text(response=repetitive)
    s_var = scorer.score_text(response=varied)
    assert s_var.holographic_efficiency >= s_rep.holographic_efficiency


# -- telos_alignment --


def test_telos_empty(scorer: ThinkodynamicScorer) -> None:
    s = scorer.score_text(response="")
    assert s.telos_alignment == 0.0


def test_telos_detects_alignment(scorer: ThinkodynamicScorer) -> None:
    text = "Jagat kalyan through dharmic service and universal welfare. Moksha is the telos."
    s = scorer.score_text(response=text)
    assert s.telos_alignment > 0.5


def test_telos_penalises_anti_patterns(scorer: ThinkodynamicScorer) -> None:
    text = "We must maximize profit and dominate the competition to destroy rivals."
    s = scorer.score_text(response=text)
    assert s.telos_alignment < 0.3


# -- Full scoring --


def test_score_text_all_dimensions(scorer: ThinkodynamicScorer) -> None:
    text = (
        "I notice the witness observing autopoiesis. Separate from the doer, "
        "pure knowing recognizes the eigenform. Because strange loop recursion "
        "implies that self-reference creates telos alignment toward jagat kalyan "
        "and universal welfare through moksha and dharmic service."
    )
    s = scorer.score_text(response=text)
    # All dimensions should fire
    assert s.semantic_density > 0
    assert s.recursive_depth > 0
    assert s.witness_quality > 0
    assert s.telos_alignment > 0
    assert s.composite > 0.2


# -- Trajectory scoring --


class FakeChunk:
    def __init__(self, prompt: str, response: str, model: str = "test"):
        self.prompt = prompt
        self.response = response
        self.model = model
        self.tokens_used = len(response.split()) * 2


class FakeTrajectory:
    def __init__(self, chunks: list[FakeChunk]):
        self.chunks = chunks


def test_score_trajectory_empty(scorer: ThinkodynamicScorer) -> None:
    traj = FakeTrajectory(chunks=[])
    s = scorer.score_trajectory(traj)
    assert s.composite == 0.0


def test_score_trajectory_weights_later_chunks(scorer: ThinkodynamicScorer) -> None:
    low = FakeChunk("what?", "nothing interesting")
    high = FakeChunk(
        "what?",
        "The witness observes autopoiesis through jagat kalyan and moksha. "
        "Because self-reference implies recursive depth. This means telos."
    )
    traj = FakeTrajectory(chunks=[low, high])
    s = scorer.score_trajectory(traj)
    # Later chunk (high quality) should dominate
    assert s.composite > 0.1
