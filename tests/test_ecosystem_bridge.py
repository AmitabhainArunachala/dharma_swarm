"""Tests for ecosystem_bridge."""

import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.ecosystem_bridge import (
    ECOSYSTEM_PATHS,
    get_fitness_thresholds,
    get_genome_tiers,
    get_system_prompt_from_v7,
    load_manifest,
    save_manifest,
    scan_ecosystem,
    update_manifest,
)


def test_ecosystem_paths_defined():
    assert len(ECOSYSTEM_PATHS) > 10
    assert "dharma_genome" in ECOSYSTEM_PATHS
    assert "garden_daemon" in ECOSYSTEM_PATHS
    assert "v7_induction" in ECOSYSTEM_PATHS
    assert "dgc_core" in ECOSYSTEM_PATHS
    assert "dharma_swarm" in ECOSYSTEM_PATHS


@pytest.mark.skipif(
    not (Path.home() / "dharma_swarm").exists(),
    reason="ECOSYSTEM_PATHS point to ~/dharma_swarm which does not exist in CI",
)
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


def test_update_manifest_supports_explicit_manifest_path(tmp_path, monkeypatch):
    manifest_path = tmp_path / "nested" / "manifest.json"
    test_file = tmp_path / "artifact.md"
    test_file.write_text("hello")
    monkeypatch.setattr(
        "dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS",
        {"artifact": test_file},
    )

    result = update_manifest(manifest_path=manifest_path)

    assert manifest_path.exists()
    assert result["ecosystem"]["artifact"]["exists"] is True
    on_disk = json.loads(manifest_path.read_text())
    assert on_disk["ecosystem"]["artifact"]["exists"] is True


# ---------------------------------------------------------------------------
# get_system_prompt_from_v7 tests
# ---------------------------------------------------------------------------


def test_get_system_prompt_from_v7_with_rules_section(tmp_path):
    """A file containing '## Rules' triggers capture and returns those lines."""
    v7_file = tmp_path / "v7.md"
    v7_file.write_text(
        "# Header\nSome preamble.\n## Rules\nRule 1: do X\nRule 2: do Y\n"
    )
    result = get_system_prompt_from_v7(path=v7_file)
    assert "## Rules" in result
    assert "Rule 1: do X" in result
    assert "Rule 2: do Y" in result
    # Preamble before the rules section should NOT be captured
    assert "Some preamble." not in result


def test_get_system_prompt_from_v7_nonexistent_path():
    """A non-existent path returns an empty string."""
    bogus = Path("/tmp/nonexistent_v7_file_xyz_12345.md")
    assert not bogus.exists()
    result = get_system_prompt_from_v7(path=bogus)
    assert result == ""


def test_get_system_prompt_from_v7_with_base_rules_section(tmp_path):
    """A file containing 'Base Rules' triggers capture."""
    v7_file = tmp_path / "v7_base.md"
    v7_file.write_text(
        "# Title\nIntro text\n## Base Rules\nBR-1: no theater\nBR-2: no sprawl\n"
    )
    result = get_system_prompt_from_v7(path=v7_file)
    assert "Base Rules" in result
    assert "BR-1: no theater" in result
    assert "BR-2: no sprawl" in result
    assert "Intro text" not in result


def test_get_system_prompt_from_v7_no_matching_section(tmp_path):
    """A file with no recognized section headings returns empty string."""
    v7_file = tmp_path / "v7_empty.md"
    v7_file.write_text("# Just a heading\nSome paragraph.\nNothing special.\n")
    result = get_system_prompt_from_v7(path=v7_file)
    assert result == ""


def test_get_system_prompt_from_v7_captures_at_most_41_lines(tmp_path):
    """Capture stops after 41 lines (> 40 check means 41 lines collected)."""
    lines = ["## Rules\n"] + [f"Line {i}\n" for i in range(100)]
    v7_file = tmp_path / "v7_long.md"
    v7_file.write_text("".join(lines))
    result = get_system_prompt_from_v7(path=v7_file)
    result_lines = result.split("\n")
    # The implementation breaks when len(core_lines) > 40, i.e., at 41 lines
    assert len(result_lines) == 41


# ---------------------------------------------------------------------------
# update_manifest tests
# ---------------------------------------------------------------------------


def test_update_manifest_calls_scan_and_saves(tmp_path, monkeypatch):
    """update_manifest scans the ecosystem and persists a manifest file."""
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr("dharma_swarm.ecosystem_bridge.MANIFEST_PATH", manifest_path)

    # Point ECOSYSTEM_PATHS to a single known-good tmp file so scan is fast
    test_file = tmp_path / "test_artifact.md"
    test_file.write_text("hello")
    monkeypatch.setattr(
        "dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS",
        {"test_artifact": test_file},
    )

    result = update_manifest()

    # Verify the returned dict has expected keys
    assert "ecosystem" in result
    assert "last_scan" in result
    assert "test_artifact" in result["ecosystem"]
    assert result["ecosystem"]["test_artifact"]["exists"] is True

    # Verify the file was actually written
    assert manifest_path.exists()
    on_disk = json.loads(manifest_path.read_text())
    assert on_disk["ecosystem"]["test_artifact"]["exists"] is True
    assert on_disk["_source"] == "dharma_swarm.ecosystem_bridge"


def test_update_manifest_merges_with_existing(tmp_path, monkeypatch):
    """update_manifest preserves existing manifest data while updating ecosystem."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"custom_key": "preserved"}))
    monkeypatch.setattr("dharma_swarm.ecosystem_bridge.MANIFEST_PATH", manifest_path)
    monkeypatch.setattr("dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS", {})

    result = update_manifest()

    assert result["custom_key"] == "preserved"
    assert "ecosystem" in result
    assert "last_scan" in result


# ---------------------------------------------------------------------------
# scan_ecosystem tests (mocked ECOSYSTEM_PATHS)
# ---------------------------------------------------------------------------


def test_scan_ecosystem_file_metadata(tmp_path, monkeypatch):
    """scan_ecosystem reports size_bytes and modified for existing files."""
    test_file = tmp_path / "artifact.md"
    content = "some content here"
    test_file.write_text(content)

    monkeypatch.setattr(
        "dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS",
        {"my_artifact": test_file},
    )

    status = scan_ecosystem()

    entry = status["my_artifact"]
    assert entry["exists"] is True
    assert entry["size_bytes"] == len(content.encode())
    assert "modified" in entry
    # modified should be a valid ISO timestamp string
    assert "T" in entry["modified"]


def test_scan_ecosystem_directory_metadata(tmp_path, monkeypatch):
    """scan_ecosystem reports file_count and type for directories."""
    sub_dir = tmp_path / "my_dir"
    sub_dir.mkdir()
    (sub_dir / "a.txt").write_text("a")
    (sub_dir / "b.txt").write_text("b")
    nested = sub_dir / "nested"
    nested.mkdir()
    (nested / "c.txt").write_text("c")

    monkeypatch.setattr(
        "dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS",
        {"my_dir": sub_dir},
    )

    status = scan_ecosystem()

    entry = status["my_dir"]
    assert entry["exists"] is True
    assert entry["type"] == "directory"
    assert entry["file_count"] == 3


def test_scan_ecosystem_missing_path(tmp_path, monkeypatch):
    """scan_ecosystem marks non-existent paths with exists=False."""
    missing = tmp_path / "does_not_exist.md"
    monkeypatch.setattr(
        "dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS",
        {"ghost": missing},
    )

    status = scan_ecosystem()

    entry = status["ghost"]
    assert entry["exists"] is False
    assert "size_bytes" not in entry
    assert "file_count" not in entry


def test_scan_ecosystem_mixed(tmp_path, monkeypatch):
    """scan_ecosystem handles a mix of files, dirs, and missing paths."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("data")

    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "x.py").write_text("x = 1")

    missing = tmp_path / "nope"

    monkeypatch.setattr(
        "dharma_swarm.ecosystem_bridge.ECOSYSTEM_PATHS",
        {
            "a_file": real_file,
            "a_dir": real_dir,
            "a_missing": missing,
        },
    )

    status = scan_ecosystem()

    assert status["a_file"]["exists"] is True
    assert status["a_file"]["size_bytes"] == len(b"data")

    assert status["a_dir"]["exists"] is True
    assert status["a_dir"]["file_count"] == 1
    assert status["a_dir"]["type"] == "directory"

    assert status["a_missing"]["exists"] is False
