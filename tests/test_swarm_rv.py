"""Tests for dharma_swarm.swarm_rv -- SwarmRV behavioral contraction measurement."""

from collections import Counter
from pathlib import Path

import pytest

from dharma_swarm.swarm_rv import (
    ContractionLevel,
    SwarmRV,
    SwarmRVReading,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shared_dir(tmp_path: Path) -> Path:
    """Create and return a temporary shared notes directory."""
    d = tmp_path / "shared"
    d.mkdir()
    return d


@pytest.fixture
def rv(shared_dir: Path) -> SwarmRV:
    """Return a SwarmRV pointed at the temporary shared directory."""
    return SwarmRV(shared_dir=shared_dir)


def _write_note(shared_dir: Path, name: str, content: str) -> Path:
    """Write a note file in the shared directory.

    Note filenames must match the ``*_notes.md`` glob pattern used
    by SwarmRV._read_notes().
    """
    fpath = shared_dir / name
    fpath.write_text(content, encoding="utf-8")
    return fpath


# ---------------------------------------------------------------------------
# test_extract_topics_basic
# ---------------------------------------------------------------------------


def test_extract_topics_basic(rv: SwarmRV):
    """Verify topic extraction from simple text returns meaningful words."""
    text = (
        "The participation_ratio measures geometric contraction "
        "in the transformer value space. Activation patching at "
        "layer twenty-seven validates the causal mechanism."
    )
    topics = rv._extract_topics(text)
    assert isinstance(topics, list)
    assert len(topics) > 0
    # All returned topics should be lowercase strings of at least 4 chars
    for topic in topics:
        assert isinstance(topic, str)
        assert len(topic) >= 4
        assert topic == topic.lower()


# ---------------------------------------------------------------------------
# test_extract_topics_filters_stopwords
# ---------------------------------------------------------------------------


def test_extract_topics_filters_stopwords(rv: SwarmRV):
    """Verify stopwords are removed from topic extraction."""
    # Text composed almost entirely of stopwords
    text = "the is a an to in for of and or but it its this that with from be"
    topics = rv._extract_topics(text)
    # None of the stopwords should appear
    assert len(topics) == 0


def test_extract_topics_filters_domain_stopwords(rv: SwarmRV):
    """Verify domain-specific stopwords (file, path, agent, etc.) are filtered."""
    text = "file path note notes agent agents swarm dharma system data task"
    topics = rv._extract_topics(text)
    # Domain stopwords should all be filtered
    assert "file" not in topics
    assert "path" not in topics
    assert "agent" not in topics
    assert "notes" not in topics


# ---------------------------------------------------------------------------
# test_participation_ratio_uniform
# ---------------------------------------------------------------------------


def test_participation_ratio_uniform(rv: SwarmRV):
    """Uniform distribution should give PR close to 1.0."""
    # 10 topics each appearing exactly once -> maximally uniform
    counts = Counter({"alpha": 1, "beta": 1, "gamma": 1, "delta": 1, "epsilon": 1})
    pr = rv._compute_participation_ratio(counts)
    assert pr == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# test_participation_ratio_concentrated
# ---------------------------------------------------------------------------


def test_participation_ratio_concentrated(rv: SwarmRV):
    """All weight on one topic should give PR at the minimum (1/N normalized)."""
    counts = Counter({"dominant": 1000, "rare_a": 1, "rare_b": 1, "rare_c": 1})
    pr = rv._compute_participation_ratio(counts)
    # With one dominant topic, PR should be low (close to 1/N)
    assert pr < 0.5


def test_participation_ratio_empty(rv: SwarmRV):
    """Empty counter should return 0.0."""
    pr = rv._compute_participation_ratio(Counter())
    assert pr == 0.0


# ---------------------------------------------------------------------------
# test_compute_similarity_identical
# ---------------------------------------------------------------------------


def test_compute_similarity_identical(rv: SwarmRV):
    """Identical topic lists should give similarity = 1.0."""
    topics = ["contraction", "geometric", "value", "space", "measurement"]
    similarity = rv._compute_similarity([topics, topics])
    assert similarity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# test_compute_similarity_disjoint
# ---------------------------------------------------------------------------


def test_compute_similarity_disjoint(rv: SwarmRV):
    """No overlap should give similarity = 0.0."""
    list_a = ["alpha", "beta", "gamma"]
    list_b = ["delta", "epsilon", "zeta"]
    similarity = rv._compute_similarity([list_a, list_b])
    assert similarity == pytest.approx(0.0)


def test_compute_similarity_single_list(rv: SwarmRV):
    """Fewer than 2 lists should return 0.0."""
    similarity = rv._compute_similarity([["alpha", "beta"]])
    assert similarity == 0.0


def test_compute_similarity_partial_overlap(rv: SwarmRV):
    """Partial overlap should give a value between 0 and 1."""
    list_a = ["alpha", "beta", "gamma"]
    list_b = ["beta", "gamma", "delta"]
    similarity = rv._compute_similarity([list_a, list_b])
    assert 0.0 < similarity < 1.0


# ---------------------------------------------------------------------------
# test_measure_with_notes
# ---------------------------------------------------------------------------


def test_measure_with_notes(rv: SwarmRV, shared_dir: Path):
    """Create shared dir with note files, verify measurement returns valid reading."""
    # Write several note files with overlapping content
    for i in range(5):
        _write_note(
            shared_dir,
            f"agent_{i}_notes.md",
            f"# Agent {i} Notes\n"
            f"The participation_ratio shows geometric contraction.\n"
            f"Layer analysis reveals activation patching mechanism {i}.\n"
            f"Behavioral transfer confirmed at threshold {i * 0.1:.1f}.\n",
        )

    reading = rv.measure(window=10)
    assert isinstance(reading, SwarmRVReading)
    assert reading.window_size == 5
    assert 0.0 <= reading.topic_pr <= 1.0
    assert 0.0 <= reading.similarity <= 1.0
    assert 0.0 <= reading.exploration_ratio <= 1.0
    assert isinstance(reading.contraction_level, ContractionLevel)
    assert isinstance(reading.is_productive, bool)
    assert isinstance(reading.top_topics, list)


# ---------------------------------------------------------------------------
# test_measure_empty_dir
# ---------------------------------------------------------------------------


def test_measure_empty_dir(rv: SwarmRV):
    """No notes should return a default reading."""
    reading = rv.measure()
    assert reading.window_size == 0
    assert reading.topic_pr == 1.0
    assert reading.similarity == 0.0
    assert reading.exploration_ratio == 1.0
    assert reading.contraction_level == ContractionLevel.STABLE
    assert reading.is_productive is True
    assert reading.top_topics == []


# ---------------------------------------------------------------------------
# test_contraction_levels
# ---------------------------------------------------------------------------


def test_contraction_collapsed(rv: SwarmRV):
    """Low PR + high similarity -> COLLAPSED."""
    level = rv._assess_contraction(topic_pr=0.1, similarity=0.8, exploration_ratio=0.0)
    assert level == ContractionLevel.COLLAPSED


def test_contraction_contracting(rv: SwarmRV):
    """Moderate PR or moderate similarity -> CONTRACTING."""
    level = rv._assess_contraction(topic_pr=0.25, similarity=0.3, exploration_ratio=0.2)
    assert level == ContractionLevel.CONTRACTING


def test_contraction_expanding(rv: SwarmRV):
    """High PR + high exploration -> EXPANDING."""
    level = rv._assess_contraction(topic_pr=0.7, similarity=0.2, exploration_ratio=0.5)
    assert level == ContractionLevel.EXPANDING


def test_contraction_stable(rv: SwarmRV):
    """Moderate PR with low exploration -> STABLE."""
    level = rv._assess_contraction(topic_pr=0.5, similarity=0.3, exploration_ratio=0.1)
    assert level == ContractionLevel.STABLE


# ---------------------------------------------------------------------------
# test_summary_format
# ---------------------------------------------------------------------------


def test_summary_format(rv: SwarmRV, shared_dir: Path):
    """Verify summary() returns a string with key information."""
    # Write at least one note so there's something to measure
    _write_note(
        shared_dir,
        "researcher_notes.md",
        "The geometric_signature shows value_space contraction.\n"
        "Participation_ratio is dropping across sessions.\n",
    )

    summary = rv.summary()
    assert isinstance(summary, str)
    assert "Colony state:" in summary
    assert "PR=" in summary
    assert "similarity=" in summary
    assert "notes in window" in summary


def test_summary_empty(rv: SwarmRV):
    """Summary on empty dir should still produce valid string."""
    summary = rv.summary()
    assert isinstance(summary, str)
    assert "STABLE" in summary
    assert "0 notes in window" in summary


# ---------------------------------------------------------------------------
# Productivity assessment
# ---------------------------------------------------------------------------


def test_productive_contraction(rv: SwarmRV):
    """Contraction with productive words -> is_productive=True."""
    is_prod = rv._assess_productivity(
        ContractionLevel.CONTRACTING,
        ["The solution was confirmed and verified. Fixed and shipped."],
    )
    assert is_prod is True


def test_stuck_contraction(rv: SwarmRV):
    """Contraction with stuck words -> is_productive=False."""
    is_prod = rv._assess_productivity(
        ContractionLevel.CONTRACTING,
        ["Still stuck in a loop. Error after error. Bug is unknown. Confused again."],
    )
    assert is_prod is False


def test_expanding_always_productive(rv: SwarmRV):
    """Expanding state is always productive regardless of words."""
    is_prod = rv._assess_productivity(
        ContractionLevel.EXPANDING,
        ["stuck broken loop error failing"],
    )
    assert is_prod is True
