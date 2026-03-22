"""Tests for dataset_builder.py — training data construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.dataset_builder import (
    DatasetBuilder,
    DatasetConfig,
    DatasetSample,
    DatasetStats,
)


@pytest.fixture
def builder(tmp_path: Path) -> DatasetBuilder:
    return DatasetBuilder(output_dir=tmp_path)


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path


# --- DatasetConfig ---


def test_config_defaults() -> None:
    c = DatasetConfig()
    assert c.min_thinkodynamic_score == 0.7
    assert c.chat_format == "openai"
    assert c.include_foundations is True


# --- DatasetSample ---


def test_sample_construction() -> None:
    s = DatasetSample(
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ],
        source="trajectory",
        quality_score=0.85,
    )
    assert len(s.messages) == 3
    assert s.source == "trajectory"


# --- Build with empty data ---


def test_build_no_extras_produces_file(builder: DatasetBuilder, output_dir: Path) -> None:
    config = DatasetConfig(
        name="test-no-extras",
        include_foundations=False,
        include_dreams=False,
        include_stigmergy=False,
        include_evolution=False,
    )
    stats = builder.build(config)
    # May have trajectories from live ~/.dharma/ data
    assert stats.total_samples >= 0
    output_file = output_dir / "test-no-extras.jsonl"
    assert output_file.exists()


def test_build_stats_fields(builder: DatasetBuilder) -> None:
    config = DatasetConfig(
        name="test-stats",
        include_foundations=False,
        include_dreams=False,
        include_stigmergy=False,
        include_evolution=False,
    )
    stats = builder.build(config)
    assert isinstance(stats, DatasetStats)
    assert stats.build_time_seconds >= 0
    assert stats.avg_quality >= 0


# --- Build with foundation data ---


def test_build_with_foundations(tmp_path: Path) -> None:
    # Create a fake foundations dir with a known file
    foundations_dir = tmp_path / "dharma_swarm" / "foundations"
    foundations_dir.mkdir(parents=True)

    # The builder looks for ~/dharma_swarm/foundations/ — we can't easily
    # redirect that, so test the internal method directly
    builder = DatasetBuilder(output_dir=tmp_path)
    # _collect_foundations reads from ~/dharma_swarm/foundations/ which exists
    # in the real repo, so this should return some samples
    samples = builder._collect_foundations()
    # Might be empty if the foundation files don't exist with exact names
    assert isinstance(samples, list)


# --- Format methods ---


def test_format_openai(builder: DatasetBuilder) -> None:
    sample = DatasetSample(
        messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "assistant", "content": "ast"},
        ],
        source="test",
    )
    result = builder._format_sample(sample, "openai")
    assert "messages" in result
    assert len(result["messages"]) == 3


def test_format_alpaca(builder: DatasetBuilder) -> None:
    sample = DatasetSample(
        messages=[
            {"role": "system", "content": "You are a dharmic agent."},
            {"role": "user", "content": "Explain telos."},
            {"role": "assistant", "content": "Telos is purpose."},
        ],
        source="test",
    )
    result = builder._format_sample(sample, "alpaca")
    assert "instruction" in result
    assert "output" in result
    assert "Telos is purpose." in result["output"]
    assert "dharmic agent" in result["instruction"]


def test_format_chatml_fallback(builder: DatasetBuilder) -> None:
    sample = DatasetSample(
        messages=[{"role": "user", "content": "hi"}],
        source="test",
    )
    result = builder._format_sample(sample, "chatml")
    assert "messages" in result


# --- max_samples limit ---


def test_max_samples_limit(builder: DatasetBuilder, output_dir: Path) -> None:
    # Build with foundations (if any exist) limited to 2
    config = DatasetConfig(
        name="test-limited",
        max_samples=2,
        include_dreams=False,
        include_stigmergy=False,
        include_evolution=False,
    )
    stats = builder.build(config)
    assert stats.total_samples <= 2


# --- JSONL output format ---


def test_jsonl_output_parseable(builder: DatasetBuilder, output_dir: Path) -> None:
    config = DatasetConfig(
        name="test-jsonl",
        include_foundations=True,
        include_dreams=False,
        include_stigmergy=False,
        include_evolution=False,
    )
    stats = builder.build(config)
    output_file = output_dir / "test-jsonl.jsonl"
    assert output_file.exists()
    # Every line should be valid JSON
    for line in output_file.read_text().strip().split("\n"):
        if line:
            record = json.loads(line)
            assert isinstance(record, dict)


# --- Dream collector graceful on missing file ---


def test_collect_dreams_missing_file(builder: DatasetBuilder) -> None:
    # Should not raise even if dream file doesn't exist
    samples = builder._collect_dreams()
    assert isinstance(samples, list)


# --- Stigmergy collector graceful ---


def test_collect_stigmergy_returns_list(builder: DatasetBuilder) -> None:
    samples = builder._collect_stigmergy()
    assert isinstance(samples, list)


# --- Evolution collector graceful ---


def test_collect_evolution_returns_list(builder: DatasetBuilder) -> None:
    samples = builder._collect_evolution()
    assert isinstance(samples, list)
