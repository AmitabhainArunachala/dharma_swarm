"""Tests for the absorbed ecosystem_map module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_ecosystem_map_imports():
    """ecosystem_map.py can be imported."""
    from dharma_swarm.ecosystem_map import ECOSYSTEM, get_context_for, check_health
    assert isinstance(ECOSYSTEM, dict)
    assert callable(get_context_for)
    assert callable(check_health)


def test_ecosystem_has_domains():
    """ECOSYSTEM contains the expected domains."""
    from dharma_swarm.ecosystem_map import ECOSYSTEM
    expected_core = {"research", "content", "ops", "identity", "vault", "foundations"}
    assert expected_core.issubset(set(ECOSYSTEM.keys()))
    assert "jagat_kalyan" in ECOSYSTEM


def test_get_context_for_all():
    """get_context_for('all') returns context with all domains."""
    from dharma_swarm.ecosystem_map import get_context_for
    ctx = get_context_for("all")
    assert "RESEARCH" in ctx
    assert "OPS" in ctx
    assert "IDENTITY" in ctx


def test_get_context_for_single_domain():
    """get_context_for with a single domain returns only that domain."""
    from dharma_swarm.ecosystem_map import get_context_for
    ctx = get_context_for("research")
    assert "RESEARCH" in ctx
    assert "VAULT" not in ctx.upper().split("RESEARCH")[0]  # vault shouldn't appear before research


def test_get_context_for_invalid():
    """get_context_for with invalid domain returns error message."""
    from dharma_swarm.ecosystem_map import get_context_for
    ctx = get_context_for("nonexistent")
    assert "Unknown domain" in ctx


def test_check_health_returns_counts():
    """check_health returns ok and missing counts."""
    from dharma_swarm.ecosystem_map import check_health
    h = check_health()
    assert "ok" in h
    assert "missing" in h
    assert "details" in h
    assert isinstance(h["ok"], int)
    assert isinstance(h["missing"], int)
    assert isinstance(h["details"], dict)
    assert h["ok"] + h["missing"] > 0  # should have at least some paths


def test_check_health_details_are_missing():
    """Only missing paths appear in details."""
    from dharma_swarm.ecosystem_map import check_health
    h = check_health()
    for path_str, desc in h["details"].items():
        assert "MISSING" in desc
        p = Path(path_str).expanduser()
        assert not p.exists()
