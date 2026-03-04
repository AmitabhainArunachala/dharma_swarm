"""Tests for ecosystem_bridge."""

import json
import tempfile
from pathlib import Path

from dharma_swarm.ecosystem_bridge import (
    ECOSYSTEM_PATHS,
    get_fitness_thresholds,
    get_genome_tiers,
    load_manifest,
    save_manifest,
    scan_ecosystem,
)


def test_ecosystem_paths_defined():
    assert len(ECOSYSTEM_PATHS) > 10
    assert "dharma_genome" in ECOSYSTEM_PATHS
    assert "garden_daemon" in ECOSYSTEM_PATHS
    assert "v7_induction" in ECOSYSTEM_PATHS
    assert "dgc_core" in ECOSYSTEM_PATHS
    assert "dharma_swarm" in ECOSYSTEM_PATHS


def test_scan_ecosystem():
    status = scan_ecosystem()
    assert isinstance(status, dict)
    assert "dharma_swarm" in status
    # dharma_swarm should exist since we're running from it
    assert status["dharma_swarm"]["exists"] is True


def test_fitness_thresholds():
    t = get_fitness_thresholds()
    assert t["minimum_fitness"] == 0.6
    assert t["crown_jewel_threshold"] == 0.85
    assert t["max_daily_contributions"] == 4
    assert t["heartbeat_hours"] == 6


def test_genome_tiers():
    tiers = get_genome_tiers()
    assert "tier_a_hard" in tiers
    assert "tier_b_descriptors" in tiers
    assert len(tiers["tier_a_hard"]) == 6
    assert len(tiers["tier_b_descriptors"]) == 5
    assert "transmission" in tiers["tier_a_hard"]
    assert "witness_stance" in tiers["tier_b_descriptors"]


def test_manifest_roundtrip(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr("dharma_swarm.ecosystem_bridge.MANIFEST_PATH", manifest_path)

    assert load_manifest() == {}

    save_manifest({"test": "data", "version": 1})
    loaded = load_manifest()
    assert loaded["test"] == "data"
    assert loaded["version"] == 1
    assert "_updated" in loaded
    assert "_source" in loaded
