"""Tests for bootstrap.py — NOW.json manifest generation and loading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import dharma_swarm.bootstrap as bmod
from dharma_swarm.bootstrap import (
    IDENTITY,
    _collect_evolution_state,
    _collect_kernel_spec,
    _collect_module_count,
    _collect_sleep_reports,
    _collect_stigmergy_state,
    _collect_test_state,
    generate_manifest,
    load_manifest,
    print_manifest,
)


# ---------------------------------------------------------------------------
# IDENTITY constant
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_identity_has_required_keys(self):
        assert "name" in IDENTITY
        assert "version" in IDENTITY
        assert "one_line" in IDENTITY
        assert "what_it_is" in IDENTITY
        assert "entry_points" in IDENTITY
        assert "key_modules" in IDENTITY

    def test_name_is_dharma_swarm(self):
        assert IDENTITY["name"] == "dharma_swarm"

    def test_version_format(self):
        parts = IDENTITY["version"].split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ---------------------------------------------------------------------------
# _collect_test_state
# ---------------------------------------------------------------------------


class TestCollectTestState:
    def test_success_parse(self):
        """Parses pytest --co output correctly."""
        class FakeResult:
            returncode = 0
            stdout = "4500 tests collected in 3.21s\n"
            stderr = ""

        with patch("dharma_swarm.bootstrap.subprocess.run", return_value=FakeResult()):
            state = _collect_test_state()

        assert state["tests_collected"] == 4500
        assert state["collection_ok"] is True
        assert state["errors"] == ""

    def test_failure_parse(self):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "ImportError: cannot import foo"

        with patch("dharma_swarm.bootstrap.subprocess.run", return_value=FakeResult()):
            state = _collect_test_state()

        assert state["collection_ok"] is False
        assert "ImportError" in state["errors"]

    def test_exception_handling(self):
        with patch("dharma_swarm.bootstrap.subprocess.run", side_effect=OSError("no pytest")):
            state = _collect_test_state()

        assert state["tests_collected"] == 0
        assert state["collection_ok"] is False
        assert "no pytest" in state["errors"]

    def test_empty_output(self):
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""

        with patch("dharma_swarm.bootstrap.subprocess.run", return_value=FakeResult()):
            state = _collect_test_state()

        assert state["tests_collected"] == 0


# ---------------------------------------------------------------------------
# _collect_evolution_state
# ---------------------------------------------------------------------------


class TestCollectEvolutionState:
    def test_no_archive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        state = _collect_evolution_state()
        assert state["archive_exists"] is False
        assert state["total_entries"] == 0

    def test_with_archive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        archive = tmp_path / ".dharma" / "evolution" / "archive.jsonl"
        archive.parent.mkdir(parents=True)
        entries = [
            {"id": "e1", "component": "foo.py", "change_type": "refactor", "status": "accepted", "created_at": "2026-03-22"},
            {"id": "e2", "component": "bar.py", "change_type": "feature", "status": "pending", "created_at": "2026-03-22"},
        ]
        archive.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

        state = _collect_evolution_state()
        assert state["archive_exists"] is True
        assert state["total_entries"] == 2
        assert state["last_entry"]["id"] == "e2"

    def test_corrupted_last_line(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        archive = tmp_path / ".dharma" / "evolution" / "archive.jsonl"
        archive.parent.mkdir(parents=True)
        archive.write_text('{"id":"good"}\nnot valid json\n', encoding="utf-8")

        state = _collect_evolution_state()
        assert state["total_entries"] == 2
        assert state["last_entry"] is None  # couldn't parse last line


# ---------------------------------------------------------------------------
# _collect_stigmergy_state
# ---------------------------------------------------------------------------


class TestCollectStigmergyState:
    def test_no_marks_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        state = _collect_stigmergy_state()
        assert state["marks_file_exists"] is False
        assert state["mark_count"] == 0

    def test_with_marks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        marks = tmp_path / ".dharma" / "stigmergy" / "marks.jsonl"
        marks.parent.mkdir(parents=True)
        marks.write_text('{"type":"pheromone"}\n{"type":"trail"}\n{"type":"alarm"}\n', encoding="utf-8")

        state = _collect_stigmergy_state()
        assert state["marks_file_exists"] is True
        assert state["mark_count"] == 3


# ---------------------------------------------------------------------------
# _collect_kernel_spec
# ---------------------------------------------------------------------------


class TestCollectKernelSpec:
    def test_no_spec_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "KERNEL_SPEC_PATH", tmp_path / "missing.md")
        state = _collect_kernel_spec()
        assert state["spec_exists"] is False
        assert state["crystal"] == ""

    def test_with_crystal(self, tmp_path, monkeypatch):
        spec = tmp_path / "KERNEL_CORE_SPEC.md"
        spec.write_text(
            "# Header\n\n"
            "## THE CRYSTAL\n\n"
            "> dharma_swarm is the unified telos engine.\n"
            "> It governs through gates.\n"
            ">\n"
            "> Every mutation is witnessed.\n\n"
            "## NEXT SECTION\n\n"
            "Other stuff.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(bmod, "KERNEL_SPEC_PATH", spec)

        state = _collect_kernel_spec()
        assert state["spec_exists"] is True
        assert "unified telos engine" in state["crystal"]
        assert "witnessed" in state["crystal"]
        assert "Other stuff" not in state["crystal"]


# ---------------------------------------------------------------------------
# _collect_module_count
# ---------------------------------------------------------------------------


class TestCollectModuleCount:
    def test_counts_py_files(self, tmp_path, monkeypatch):
        pkg = tmp_path / "dharma_swarm"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        (pkg / "swarm.py").touch()
        (pkg / "models.py").touch()
        (pkg / "not_python.txt").touch()

        monkeypatch.setattr(bmod, "DHARMA_SWARM", tmp_path)
        count = _collect_module_count()
        assert count == 3  # __init__.py + swarm.py + models.py


# ---------------------------------------------------------------------------
# _collect_sleep_reports
# ---------------------------------------------------------------------------


class TestCollectSleepReports:
    def test_no_reports_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        state = _collect_sleep_reports()
        assert state["last_report"] is None
        assert state["total_reports"] == 0

    def test_with_reports(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        reports_dir = tmp_path / ".dharma" / "sleep_reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report_001.json").write_text(
            json.dumps({"phases_completed": ["LIGHT", "DEEP"]}),
            encoding="utf-8",
        )
        (reports_dir / "report_002.json").write_text(
            json.dumps({"phases_completed": ["LIGHT", "DEEP", "REM"]}),
            encoding="utf-8",
        )

        state = _collect_sleep_reports()
        assert state["total_reports"] == 2
        assert state["last_report"] == "report_002.json"
        assert "REM" in state["last_phases"]


# ---------------------------------------------------------------------------
# generate_manifest
# ---------------------------------------------------------------------------


class TestGenerateManifest:
    def test_generates_valid_json(self, tmp_path, monkeypatch):
        """generate_manifest produces a valid JSON manifest."""
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        monkeypatch.setattr(bmod, "DHARMA_STATE", tmp_path / "state")
        monkeypatch.setattr(bmod, "NOW_PATH", tmp_path / "state" / "NOW.json")
        monkeypatch.setattr(bmod, "DHARMA_SWARM", tmp_path)
        monkeypatch.setattr(bmod, "KERNEL_SPEC_PATH", tmp_path / "missing.md")

        # Create minimal pkg dir for module count
        (tmp_path / "dharma_swarm").mkdir()
        (tmp_path / "dharma_swarm" / "init.py").touch()

        # Mock subprocess for test collection
        class FakeResult:
            returncode = 0
            stdout = "100 tests collected in 1.0s\n"
            stderr = ""

        with (
            patch("dharma_swarm.bootstrap.subprocess.run", return_value=FakeResult()),
            patch("dharma_swarm.bootstrap._collect_d3_state", return_value={}),
            patch("dharma_swarm.bootstrap._collect_d3_priorities", return_value=[]),
        ):
            manifest = generate_manifest()

        assert manifest["identity"]["name"] == "dharma_swarm"
        assert manifest["health"]["status"] in ("GREEN", "YELLOW", "RED")
        assert "_meta" in manifest
        assert "generated_at" in manifest["_meta"]

        # Verify file was written
        assert (tmp_path / "state" / "NOW.json").exists()
        on_disk = json.loads((tmp_path / "state" / "NOW.json").read_text())
        assert on_disk["identity"]["name"] == "dharma_swarm"

    def test_red_health_when_tests_fail(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "HOME", tmp_path)
        monkeypatch.setattr(bmod, "DHARMA_STATE", tmp_path / "state")
        monkeypatch.setattr(bmod, "NOW_PATH", tmp_path / "state" / "NOW.json")
        monkeypatch.setattr(bmod, "DHARMA_SWARM", tmp_path)
        monkeypatch.setattr(bmod, "KERNEL_SPEC_PATH", tmp_path / "missing.md")
        (tmp_path / "dharma_swarm").mkdir()

        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "collection error"

        with (
            patch("dharma_swarm.bootstrap.subprocess.run", return_value=FakeResult()),
            patch("dharma_swarm.bootstrap._collect_d3_state", return_value={}),
            patch("dharma_swarm.bootstrap._collect_d3_priorities", return_value=[]),
        ):
            manifest = generate_manifest()

        assert manifest["health"]["status"] == "RED"
        assert any("Test collection" in i for i in manifest["health"]["issues"])


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_load_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bmod, "NOW_PATH", tmp_path / "missing.json")
        assert load_manifest() is None

    def test_load_valid(self, tmp_path, monkeypatch):
        path = tmp_path / "NOW.json"
        path.write_text(json.dumps({"identity": {"name": "test"}}), encoding="utf-8")
        monkeypatch.setattr(bmod, "NOW_PATH", path)
        m = load_manifest()
        assert m is not None
        assert m["identity"]["name"] == "test"

    def test_load_corrupted(self, tmp_path, monkeypatch):
        path = tmp_path / "NOW.json"
        path.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(bmod, "NOW_PATH", path)
        assert load_manifest() is None


# ---------------------------------------------------------------------------
# print_manifest
# ---------------------------------------------------------------------------


class TestPrintManifest:
    def test_print_no_manifest(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(bmod, "NOW_PATH", tmp_path / "missing.json")
        print_manifest()
        out = capsys.readouterr().out
        assert "No manifest found" in out

    def test_print_with_manifest(self, capsys):
        manifest = {
            "identity": {"name": "dharma_swarm", "one_line": "test system"},
            "health": {"status": "GREEN", "issues": []},
            "state": {
                "tests": {"tests_collected": 100, "collection_ok": True},
                "evolution": {"total_entries": 5},
            },
            "dimensions": {
                "D1_codebase": "50 modules",
                "D2_knowledge": "100 marks",
                "D3_field": "10 entries",
            },
            "next_actions": [
                {"priority": "HIGH", "action": "Do something", "command": "dgc foo"},
            ],
            "_meta": {"generated_at": "2026-03-22T00:00:00Z", "generation_time_sec": 0.5},
            "kernel_crystal": "",
        }
        print_manifest(manifest)
        out = capsys.readouterr().out
        assert "dharma_swarm" in out
        assert "GREEN" in out
        assert "Do something" in out
