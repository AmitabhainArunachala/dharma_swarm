"""Tests for dharma_swarm.hypnagogic -- Dream Journal Processor."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.hypnagogic import (
    _format_dreams_for_journal,
    _load_recent_dreams,
    _persist_journal,
    process_recent_dreams,
)


# ---------------------------------------------------------------------------
# _format_dreams_for_journal
# ---------------------------------------------------------------------------


def test_format_dreams_empty():
    result = _format_dreams_for_journal([])
    assert result == ""


def test_format_dreams_single():
    dreams = [
        {
            "resonance_type": "structural_isomorphism",
            "description": "A deep connection found",
            "salience": 0.85,
            "source_files": ["/home/user/file_a.md", "/home/user/file_b.md"],
            "evidence_fragments": ["fragment 1", "fragment 2"],
            "reasoning": "The dream texture here",
        }
    ]
    result = _format_dreams_for_journal(dreams)
    assert "DREAM 1" in result
    assert "structural_isomorphism" in result
    assert "0.85" in result
    assert "file_a.md" in result
    assert "fragment 1" in result
    assert "dream texture" in result.lower() or "Dream texture" in result


def test_format_dreams_multiple():
    dreams = [
        {
            "resonance_type": "cross_domain_bridge",
            "description": "Bridge A",
            "salience": 0.90,
            "source_files": ["a.md"],
        },
        {
            "resonance_type": "recursive_echo",
            "description": "Echo B",
            "salience": 0.75,
            "source_files": ["b.md"],
        },
    ]
    result = _format_dreams_for_journal(dreams)
    assert "DREAM 1" in result
    assert "DREAM 2" in result
    assert "Bridge A" in result
    assert "Echo B" in result


# ---------------------------------------------------------------------------
# _load_recent_dreams
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_recent_dreams_no_file(tmp_path: Path):
    with patch("dharma_swarm.hypnagogic._DREAM_FILE", tmp_path / "nope.jsonl"):
        result = await _load_recent_dreams(hours_back=8, min_salience=0.5, max_dreams=10)
        assert result == []


@pytest.mark.asyncio
async def test_load_recent_dreams_filters_by_salience(tmp_path: Path):
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    entries = [
        {"timestamp": now.isoformat(), "salience": 0.9, "description": "high"},
        {"timestamp": now.isoformat(), "salience": 0.3, "description": "low"},
        {"timestamp": now.isoformat(), "salience": 0.8, "description": "medium"},
    ]
    dream_file.write_text("\n".join(json.dumps(e) for e in entries))

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        result = await _load_recent_dreams(hours_back=8, min_salience=0.7, max_dreams=10)
        assert len(result) == 2
        # Sorted by salience descending
        assert result[0]["salience"] == 0.9
        assert result[1]["salience"] == 0.8


@pytest.mark.asyncio
async def test_load_recent_dreams_filters_by_time(tmp_path: Path):
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=24)
    entries = [
        {"timestamp": now.isoformat(), "salience": 0.9, "description": "recent"},
        {"timestamp": old.isoformat(), "salience": 0.9, "description": "old"},
    ]
    dream_file.write_text("\n".join(json.dumps(e) for e in entries))

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        result = await _load_recent_dreams(hours_back=8, min_salience=0.5, max_dreams=10)
        assert len(result) == 1
        assert result[0]["description"] == "recent"


@pytest.mark.asyncio
async def test_load_recent_dreams_caps_at_max(tmp_path: Path):
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    entries = [
        {"timestamp": now.isoformat(), "salience": 0.9 - i * 0.01, "description": f"d{i}"}
        for i in range(20)
    ]
    dream_file.write_text("\n".join(json.dumps(e) for e in entries))

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        result = await _load_recent_dreams(hours_back=8, min_salience=0.5, max_dreams=5)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# _persist_journal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_journal(tmp_path: Path):
    journal_dir = tmp_path / "journal"
    with patch("dharma_swarm.hypnagogic._JOURNAL_DIR", journal_dir):
        ts = datetime(2026, 3, 7, 10, 30, tzinfo=timezone.utc)
        path = await _persist_journal("Test journal content", [{"x": 1}], ts)

        assert path.exists()
        text = path.read_text()
        assert "Dream Journal" in text
        assert "Test journal content" in text
        assert "1 dreams processed" in text

        # Latest file should also exist
        latest = journal_dir / "LATEST_JOURNAL.md"
        assert latest.exists()
        assert latest.read_text() == text


# ---------------------------------------------------------------------------
# process_recent_dreams (integration, mocked LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_no_api_keys():
    with patch.dict("os.environ", {}, clear=True):
        # Remove any keys that might be set
        for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
            if k in __import__("os").environ:
                del __import__("os").environ[k]
        result = await process_recent_dreams()
        assert "error" in result or result.get("status") in ("no_dreams", "error")


@pytest.mark.asyncio
async def test_process_no_dreams(tmp_path: Path):
    with patch("dharma_swarm.hypnagogic._DREAM_FILE", tmp_path / "nope.jsonl"):
        with patch.dict("os.environ", {}, clear=True):
            result = await process_recent_dreams()
            assert result["status"] == "no_dreams"


@pytest.mark.asyncio
async def test_process_openrouter_success(tmp_path: Path):
    # Create dream file with recent high-salience dream
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    entry = {
        "timestamp": now.isoformat(),
        "salience": 0.9,
        "description": "A profound connection",
        "resonance_type": "structural_isomorphism",
        "source_files": ["a.md"],
    }
    dream_file.write_text(json.dumps(entry))

    journal_dir = tmp_path / "journal"

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        with patch("dharma_swarm.hypnagogic._JOURNAL_DIR", journal_dir):
            with patch(
                "dharma_swarm.hypnagogic.complete_via_preferred_runtime_providers",
                new=AsyncMock(
                    return_value=(
                        LLMResponse(
                            content="The dream speaks of convergence...",
                            model="nim-local",
                        ),
                        SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
                    )
                ),
            ):
                result = await process_recent_dreams()
                assert result["status"] == "ok"
                assert result["dreams_processed"] == 1
                assert "convergence" in result["preview"]


@pytest.mark.asyncio
async def test_process_openrouter_empty_choices(tmp_path: Path):
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    entry = {"timestamp": now.isoformat(), "salience": 0.9, "description": "x"}
    dream_file.write_text(json.dumps(entry))

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        with patch(
            "dharma_swarm.hypnagogic.complete_via_preferred_runtime_providers",
            new=AsyncMock(
                return_value=(
                    LLMResponse(content="", model="nim-local"),
                    SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
                )
            ),
        ):
            result = await process_recent_dreams()
            assert result["status"] in ("empty", "error")


@pytest.mark.asyncio
async def test_process_openrouter_http_error(tmp_path: Path):
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    entry = {"timestamp": now.isoformat(), "salience": 0.9, "description": "x"}
    dream_file.write_text(json.dumps(entry))

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        with patch(
            "dharma_swarm.hypnagogic.complete_via_preferred_runtime_providers",
            new=AsyncMock(side_effect=RuntimeError("OpenRouter error 429: Rate limited")),
        ):
            result = await process_recent_dreams()
            assert result["status"] == "error"
            assert "429" in result.get("error", "")


@pytest.mark.asyncio
async def test_process_openrouter_network_error(tmp_path: Path):
    dream_file = tmp_path / "dreams.jsonl"
    now = datetime.now(timezone.utc)
    entry = {"timestamp": now.isoformat(), "salience": 0.9, "description": "x"}
    dream_file.write_text(json.dumps(entry))

    with patch("dharma_swarm.hypnagogic._DREAM_FILE", dream_file):
        with patch(
            "dharma_swarm.hypnagogic.complete_via_preferred_runtime_providers",
            new=AsyncMock(side_effect=ConnectionError("network down")),
        ):
            result = await process_recent_dreams()
            assert result["status"] == "error"
            assert "ConnectionError" in result.get("error", "")
