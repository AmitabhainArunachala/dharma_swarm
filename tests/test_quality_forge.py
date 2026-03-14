"""Tests for dharma_swarm.quality_forge -- the self-scoring strange loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.archive import FitnessScore
from dharma_swarm.models import ForgeScore
from dharma_swarm.quality_forge import QualityForge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_PYTHON = '''\
"""A simple module for testing."""


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}"


class Calculator:
    """Basic calculator."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
'''


@pytest.fixture()
def forge() -> QualityForge:
    """Return a default QualityForge instance."""
    return QualityForge()


@pytest.fixture()
def simple_py(tmp_path: Path) -> Path:
    """Write a simple Python file and return its path."""
    p = tmp_path / "simple.py"
    p.write_text(SIMPLE_PYTHON, encoding="utf-8")
    return p


@pytest.fixture()
def empty_py(tmp_path: Path) -> Path:
    """Write an empty Python file and return its path."""
    p = tmp_path / "empty.py"
    p.write_text("", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScoreArtifact:
    """Tests for QualityForge.score_artifact."""

    def test_score_artifact_basic(self, forge: QualityForge, simple_py: Path) -> None:
        """Score a known Python file and verify ForgeScore fields are valid."""
        score = forge.score_artifact(simple_py)

        assert isinstance(score, ForgeScore)
        assert score.stars >= 0.0
        assert score.yosemite >= 5.0
        assert score.dharmic >= 0.0
        assert score.efficiency >= 0.0
        assert score.elegance_sub >= 0.0
        assert score.behavioral_sub >= 0.0
        assert score.timestamp is not None

    def test_score_empty_file(self, forge: QualityForge, empty_py: Path) -> None:
        """Empty file should be handled gracefully without raising."""
        score = forge.score_artifact(empty_py)
        assert isinstance(score, ForgeScore)
        # Empty file still gets a valid score object
        assert score.stars >= 0.0

    def test_score_nonexistent_file(self, forge: QualityForge, tmp_path: Path) -> None:
        """Non-existent path should raise FileNotFoundError."""
        missing = tmp_path / "does_not_exist.py"
        with pytest.raises(FileNotFoundError):
            forge.score_artifact(missing)

    def test_elegance_sub_range(self, forge: QualityForge, simple_py: Path) -> None:
        """elegance_sub must be in [0, 1]."""
        score = forge.score_artifact(simple_py)
        assert 0.0 <= score.elegance_sub <= 1.0

    def test_behavioral_sub_range(self, forge: QualityForge, simple_py: Path) -> None:
        """behavioral_sub must be in [0, 1]."""
        score = forge.score_artifact(simple_py)
        assert 0.0 <= score.behavioral_sub <= 1.0

    def test_stars_range(self, forge: QualityForge, simple_py: Path) -> None:
        """stars must be in [0, 10]."""
        score = forge.score_artifact(simple_py)
        assert 0.0 <= score.stars <= 10.0

    def test_yosemite_range(self, forge: QualityForge, simple_py: Path) -> None:
        """yosemite must be in [5.0, 5.15]."""
        score = forge.score_artifact(simple_py)
        assert 5.0 <= score.yosemite <= 5.15

    def test_dharmic_range(self, forge: QualityForge, simple_py: Path) -> None:
        """dharmic must be in [0, 10]."""
        score = forge.score_artifact(simple_py)
        assert 0.0 <= score.dharmic <= 10.0

    def test_gate_pass_contributes(self, forge: QualityForge, simple_py: Path) -> None:
        """Gate pass should contribute positively to stars.

        A benign Python file should not trigger AHIMSA/SATYA/CONSENT blocks,
        so gate_pass should be 1.0 and stars should reflect the gate
        contribution (0.3 * 1.0 * 10 = 3.0 minimum from gate alone).
        """
        score = forge.score_artifact(simple_py)
        # Gate contributes 0.3 * gate_pass * 10. With gate_pass=1.0
        # the gate alone adds 3.0 to stars. Combined with elegance and
        # behavioral, total should exceed 3.0.
        assert score.stars >= 3.0


class TestSelfScore:
    """Tests for QualityForge.self_score."""

    def test_self_score(self, forge: QualityForge) -> None:
        """self_score() should return a valid ForgeScore for quality_forge.py."""
        score = forge.self_score()
        assert isinstance(score, ForgeScore)
        assert score.stars > 0.0
        assert score.elegance_sub > 0.0

    def test_eigenform_stability(self, forge: QualityForge) -> None:
        """self_score() called twice must return identical scores (deterministic)."""
        score_a = forge.self_score()
        score_b = forge.self_score()
        assert score_a.stars == score_b.stars
        assert score_a.yosemite == score_b.yosemite
        assert score_a.dharmic == score_b.dharmic
        assert score_a.efficiency == score_b.efficiency
        assert score_a.elegance_sub == score_b.elegance_sub
        assert score_a.behavioral_sub == score_b.behavioral_sub


class TestNeedsEvolution:
    """Tests for QualityForge.needs_evolution."""

    def test_needs_evolution_below_threshold(self, forge: QualityForge) -> None:
        """ForgeScore with stars < threshold should need evolution."""
        low_score = ForgeScore(stars=3.0, yosemite=5.0, dharmic=2.0)
        assert forge.needs_evolution(low_score) is True

    def test_needs_evolution_above_threshold(self, forge: QualityForge) -> None:
        """ForgeScore with stars >= threshold should not need evolution."""
        high_score = ForgeScore(stars=8.0, yosemite=5.1, dharmic=7.0)
        assert forge.needs_evolution(high_score) is False

    def test_needs_evolution_at_threshold(self) -> None:
        """Stars exactly at threshold should not need evolution."""
        forge = QualityForge(threshold=6.0)
        exact_score = ForgeScore(stars=6.0)
        assert forge.needs_evolution(exact_score) is False


class TestToFitnessScore:
    """Tests for QualityForge.to_fitness_score."""

    def test_to_fitness_score(self, forge: QualityForge) -> None:
        """FitnessScore projection should correctly map forge dimensions."""
        fs = ForgeScore(
            stars=7.0,
            yosemite=5.1,
            dharmic=6.0,
            efficiency=50.0,
            elegance_sub=0.85,
            behavioral_sub=0.7,
        )
        fit = forge.to_fitness_score(fs)

        assert isinstance(fit, FitnessScore)
        assert fit.correctness == pytest.approx(0.7, abs=1e-6)
        assert fit.dharmic_alignment == pytest.approx(0.6, abs=1e-6)
        assert fit.elegance == pytest.approx(0.85, abs=1e-6)
        assert fit.efficiency == pytest.approx(0.5, abs=1e-6)
        assert fit.safety == pytest.approx(1.0, abs=1e-6)

    def test_to_fitness_score_low_dharmic(self, forge: QualityForge) -> None:
        """When dharmic < 5.0, safety should scale proportionally."""
        fs = ForgeScore(stars=5.0, dharmic=3.0)
        fit = forge.to_fitness_score(fs)
        assert fit.safety == pytest.approx(0.6, abs=1e-6)
