"""Tests for the Foreman — Focused Quality Forge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dharma_swarm.foreman import (
    FOREMAN_DIR,
    PROJECTS_FILE,
    ProjectEntry,
    add_project,
    find_weakest_dimension,
    format_status,
    generate_task,
    get_active_projects,
    load_projects,
    run_cycle,
    save_projects,
    score_all_dimensions,
    foreman_run_fn,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_foreman(tmp_path, monkeypatch):
    """Redirect foreman storage to tmp_path."""
    foreman_dir = tmp_path / "foreman"
    foreman_dir.mkdir()
    monkeypatch.setattr("dharma_swarm.foreman.FOREMAN_DIR", foreman_dir)
    monkeypatch.setattr("dharma_swarm.foreman.PROJECTS_FILE", foreman_dir / "projects.json")
    monkeypatch.setattr("dharma_swarm.foreman.CYCLES_FILE", foreman_dir / "cycles.jsonl")
    return foreman_dir


@pytest.fixture
def isolated_iteration(tmp_path, monkeypatch):
    """Redirect iteration depth storage so advise cycles stay hermetic."""
    iteration_dir = tmp_path / "iteration"
    iteration_dir.mkdir()
    monkeypatch.setattr("dharma_swarm.iteration_depth.ITERATION_DIR", iteration_dir)
    monkeypatch.setattr("dharma_swarm.iteration_depth.INITIATIVES_FILE", iteration_dir / "initiatives.jsonl")
    monkeypatch.setattr("dharma_swarm.iteration_depth.QUEUE_FILE", iteration_dir / "queue.jsonl")
    return iteration_dir


@pytest.fixture
def sample_repo(tmp_path):
    """Create a small Python repo with known quality profile."""
    pkg = tmp_path / "sample_project"
    pkg.mkdir()
    src = pkg / "src"
    src.mkdir()
    (src / "__init__.py").write_text('"""Sample package."""\n')

    # Source file WITH docstrings and error handling
    (src / "core.py").write_text('''\
"""Core module."""


def process(data: list[int]) -> int:
    """Process data and return sum of positives."""
    if not isinstance(data, list):
        raise TypeError("data must be a list")
    try:
        return sum(x for x in data if x > 0)
    except Exception as e:
        raise RuntimeError(f"processing failed: {e}") from e


def transform(value: str) -> str:
    """Transform a string value."""
    return value.upper()
''')

    # Source file WITHOUT docstrings or error handling
    (src / "helpers.py").write_text('''\
def add(a, b):
    return a + b


def multiply(a, b):
    return a * b
''')

    # Test file
    tests = pkg / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_core.py").write_text('''\
"""Tests for core module."""

from src.core import process


def test_process():
    assert process([1, 2, -3]) == 3


def test_process_empty():
    assert process([]) == 0
''')

    return pkg


@pytest.fixture
def empty_repo(tmp_path):
    """An empty directory registered as a project."""
    d = tmp_path / "empty_project"
    d.mkdir()
    return d


# ── Registry CRUD ────────────────────────────────────────────────────


class TestRegistryCRUD:
    def test_empty_registry(self):
        projects = load_projects()
        assert projects == []

    def test_add_and_load(self, sample_repo):
        entry = add_project(str(sample_repo), name="sample")
        assert entry.name == "sample"
        assert entry.path == str(sample_repo)
        assert entry.active is True

        loaded = load_projects()
        assert len(loaded) == 1
        assert loaded[0].name == "sample"
        assert loaded[0].path == str(sample_repo)

    def test_deduplicates_by_path(self, sample_repo):
        add_project(str(sample_repo), name="first")
        add_project(str(sample_repo), name="second")
        loaded = load_projects()
        assert len(loaded) == 1
        assert loaded[0].name == "second"

    def test_add_multiple_projects(self, sample_repo, empty_repo):
        add_project(str(sample_repo), name="sample")
        add_project(str(empty_repo), name="empty")
        loaded = load_projects()
        assert len(loaded) == 2
        names = {p.name for p in loaded}
        assert names == {"sample", "empty"}

    def test_add_nonexistent_path_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Not a directory"):
            add_project(str(tmp_path / "does_not_exist"))

    def test_save_and_load_roundtrip(self, sample_repo):
        entries = [
            ProjectEntry(
                name="test",
                path=str(sample_repo),
                test_command="pytest",
                exclude=["vendor"],
                dimensions={"has_tests": 0.5},
            )
        ]
        save_projects(entries)
        loaded = load_projects()
        assert len(loaded) == 1
        assert loaded[0].test_command == "pytest"
        assert loaded[0].exclude == ["vendor"]
        assert loaded[0].dimensions == {"has_tests": 0.5}

    def test_get_active_projects(self, sample_repo, empty_repo):
        add_project(str(sample_repo), name="active")
        add_project(str(empty_repo), name="inactive")
        # Deactivate one
        projects = load_projects()
        projects[1].active = False
        save_projects(projects)

        active = get_active_projects()
        assert len(active) == 1
        assert active[0].name == "active"

    def test_corrupt_json_returns_empty(self, isolated_foreman):
        (isolated_foreman / "projects.json").write_text("NOT JSON")
        assert load_projects() == []


# ── Quality Dimension Scoring ────────────────────────────────────────


class TestDimensionScoring:
    def test_has_tests_nonzero(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = score_all_dimensions(entry)
        assert dims["has_tests"] > 0.0
        assert dims["has_tests"] <= 1.0

    def test_tests_pass_no_command(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = score_all_dimensions(entry)
        assert dims["tests_pass"] == 0.0  # No test_command set

    def test_tests_pass_uses_shell_aware_tokenization(self, sample_repo, monkeypatch):
        captured: dict[str, object] = {}

        def _fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["cwd"] = kwargs["cwd"]
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr("dharma_swarm.foreman.subprocess.run", _fake_run)
        entry = ProjectEntry(
            name="sample",
            path=str(sample_repo),
            test_command='python -m pytest -k "process empty"',
        )

        dims = score_all_dimensions(entry)

        assert dims["tests_pass"] == 1.0
        assert captured["argv"] == ["python", "-m", "pytest", "-k", "process empty"]
        assert captured["cwd"] == str(sample_repo)

    def test_error_handling_partial(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = score_all_dimensions(entry)
        # core.py has try/raise, helpers.py doesn't; __init__.py is trivial
        assert 0.0 < dims["error_handling"] < 1.0

    def test_documented_partial(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = score_all_dimensions(entry)
        # core.py is fully documented, helpers.py has zero docstrings
        assert 0.0 < dims["documented"] < 1.0

    def test_edge_cases_partial(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = score_all_dimensions(entry)
        # test_core.py has test_process → "process" is covered
        # but add, multiply, transform are not
        assert 0.0 <= dims["edge_cases_covered"] <= 1.0

    def test_all_dimensions_present(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = score_all_dimensions(entry)
        expected_keys = {"has_tests", "tests_pass", "error_handling", "documented", "edge_cases_covered"}
        assert set(dims.keys()) == expected_keys
        for v in dims.values():
            assert isinstance(v, float)
            assert 0.0 <= v <= 1.0

    def test_empty_repo_returns_zeros(self, empty_repo):
        entry = ProjectEntry(name="empty", path=str(empty_repo))
        dims = score_all_dimensions(entry)
        assert dims["has_tests"] == 0.0


# ── Weakest Dimension ────────────────────────────────────────────────


class TestFindWeakest:
    def test_finds_minimum(self):
        dims = {
            "has_tests": 0.5,
            "tests_pass": 0.0,
            "error_handling": 0.3,
            "documented": 0.8,
            "edge_cases_covered": 0.1,
        }
        assert find_weakest_dimension(dims) == "tests_pass"

    def test_single_dimension(self):
        dims = {"has_tests": 0.5}
        assert find_weakest_dimension(dims) == "has_tests"

    def test_all_equal(self):
        dims = {
            "has_tests": 0.5,
            "tests_pass": 0.5,
            "error_handling": 0.5,
            "documented": 0.5,
            "edge_cases_covered": 0.5,
        }
        # Any is fine, just check it returns one
        result = find_weakest_dimension(dims)
        assert result in dims


# ── Task Generation ──────────────────────────────────────────────────


class TestGenerateTask:
    def test_has_tests_task(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = {"has_tests": 0.2, "tests_pass": 0.5, "error_handling": 0.5, "documented": 0.5, "edge_cases_covered": 0.5}
        task = generate_task(entry, "has_tests", dims)
        assert task["dimension"] == "has_tests"
        assert task["score"] == 0.2
        assert "sample" in task["task"]
        assert "targets" in task

    def test_tests_pass_task(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo), test_command="pytest")
        dims = {"has_tests": 0.5, "tests_pass": 0.0, "error_handling": 0.5, "documented": 0.5, "edge_cases_covered": 0.5}
        task = generate_task(entry, "tests_pass", dims)
        assert task["dimension"] == "tests_pass"
        assert task["priority"] == 1.0  # Broken tests = top priority

    def test_error_handling_task(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = {"has_tests": 0.5, "tests_pass": 0.5, "error_handling": 0.1, "documented": 0.5, "edge_cases_covered": 0.5}
        task = generate_task(entry, "error_handling", dims)
        assert task["dimension"] == "error_handling"
        assert "targets" in task

    def test_documented_task(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = {"has_tests": 0.5, "tests_pass": 0.5, "error_handling": 0.5, "documented": 0.1, "edge_cases_covered": 0.5}
        task = generate_task(entry, "documented", dims)
        assert task["dimension"] == "documented"
        assert "docstring" in task["task"].lower() or "Docstring" in task["task"]

    def test_edge_cases_task(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = {"has_tests": 0.5, "tests_pass": 0.5, "error_handling": 0.5, "documented": 0.5, "edge_cases_covered": 0.0}
        task = generate_task(entry, "edge_cases_covered", dims)
        assert task["dimension"] == "edge_cases_covered"
        assert "edge" in task["task"].lower()

    def test_task_has_required_fields(self, sample_repo):
        entry = ProjectEntry(name="sample", path=str(sample_repo))
        dims = {"has_tests": 0.2, "tests_pass": 0.5, "error_handling": 0.5, "documented": 0.5, "edge_cases_covered": 0.5}
        task = generate_task(entry, "has_tests", dims)
        assert "dimension" in task
        assert "score" in task
        assert "task" in task
        assert "acceptance_criteria" in task
        assert "priority" in task


# ── Forge Cycle ──────────────────────────────────────────────────────


class TestRunCycle:
    def test_observe_cycle_no_projects(self):
        report = run_cycle(level="observe")
        assert report.level == "observe"
        assert report.per_project == []

    def test_observe_cycle_with_project(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        report = run_cycle(level="observe")
        assert len(report.per_project) == 1
        result = report.per_project[0]
        assert result["name"] == "sample"
        assert result["grade"] in ("A", "B", "C", "D", "F")
        assert "dimensions" in result
        assert "weakest_dimension" in result
        assert "task" in result

    def test_observe_does_not_queue(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        report = run_cycle(level="observe")
        result = report.per_project[0]
        assert "queued" not in result

    def test_project_filter(self, sample_repo, empty_repo):
        add_project(str(sample_repo), name="sample")
        add_project(str(empty_repo), name="empty")
        report = run_cycle(level="observe", project_filter="sample")
        assert len(report.per_project) == 1
        assert report.per_project[0]["name"] == "sample"

    def test_cycle_updates_registry(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        run_cycle(level="observe")

        projects = load_projects()
        assert len(projects) == 1
        p = projects[0]
        assert p.last_scan is not None
        assert p.last_grade is not None
        assert p.last_score is not None
        assert len(p.dimensions) > 0

    def test_cycle_persists_to_jsonl(self, sample_repo, isolated_foreman):
        add_project(str(sample_repo), name="sample")
        run_cycle(level="observe")
        cycles_file = isolated_foreman / "cycles.jsonl"
        assert cycles_file.exists()
        lines = cycles_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert "cycle_id" in data
        assert data["level"] == "observe"

    def test_skip_tests_flag(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        report = run_cycle(level="observe", skip_tests=True)
        result = report.per_project[0]
        # tests_pass should be 0.0 (default) when skipped
        assert result["dimensions"]["tests_pass"] == 0.0

    def test_skip_tests_does_not_execute_test_command(self, sample_repo, monkeypatch):
        add_project(str(sample_repo), name="sample", test_command="pytest -q")

        def _should_not_run(*args, **kwargs):
            raise AssertionError("test command should not run when skip_tests=True")

        monkeypatch.setattr("dharma_swarm.foreman.subprocess.run", _should_not_run)

        report = run_cycle(level="observe", skip_tests=True)
        assert report.per_project[0]["dimensions"]["tests_pass"] == 0.0

    def test_missing_project_dir_skipped(self, tmp_path, isolated_foreman):
        """A registered project whose directory is gone is skipped."""
        entries = [ProjectEntry(name="ghost", path=str(tmp_path / "gone"))]
        save_projects(entries)
        report = run_cycle(level="observe")
        assert len(report.per_project) == 0

    def test_advise_cycle_deduplicates_existing_pending_task(self, sample_repo, isolated_iteration):
        from dharma_swarm.iteration_depth import CompoundingQueue

        add_project(str(sample_repo), name="sample")

        first = run_cycle(level="advise")
        second = run_cycle(level="advise")

        queue = CompoundingQueue()
        queue.load()

        pending = queue.get_pending()
        assert len(pending) == 1
        assert first.per_project[0]["queued"] is True
        assert first.per_project[0]["queue_status"] == "queued"
        assert first.queue_depth == 1
        assert second.per_project[0]["queued"] is False
        assert second.per_project[0]["queue_status"] == "already_pending"
        assert second.queue_depth == 1


# ── Display ──────────────────────────────────────────────────────────


class TestFormatStatus:
    def test_empty_status(self):
        output = format_status()
        assert "No projects registered" in output

    def test_status_with_projects(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        run_cycle(level="observe")
        output = format_status()
        assert "sample" in output
        assert "Foreman Quality Forge" in output

    def test_status_shows_dimensions(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        run_cycle(level="observe")
        output = format_status()
        assert "has_tests" in output
        assert "WEAKEST" in output


# ── Cron Integration ─────────────────────────────────────────────────


class TestForemanRunFn:
    def test_observe_level(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        success, output, error = foreman_run_fn({"prompt": "observe"})
        assert success is True
        assert error is None
        assert "sample" in output

    def test_invalid_level_defaults_to_advise(self, sample_repo):
        """Invalid level in job should default to advise."""
        add_project(str(sample_repo), name="sample")
        # advise requires iteration_depth — mock it
        with patch("dharma_swarm.foreman.run_cycle") as mock_cycle:
            from dharma_swarm.foreman import CycleReport
            mock_cycle.return_value = CycleReport(level="advise", per_project=[])
            success, output, error = foreman_run_fn({"prompt": "garbage"})
            assert success is True
            mock_cycle.assert_called_once_with(level="advise", skip_tests=False)

    def test_empty_prompt_defaults(self, sample_repo):
        add_project(str(sample_repo), name="sample")
        with patch("dharma_swarm.foreman.run_cycle") as mock_cycle:
            from dharma_swarm.foreman import CycleReport
            mock_cycle.return_value = CycleReport(level="advise", per_project=[])
            foreman_run_fn({"prompt": ""})
            mock_cycle.assert_called_once_with(level="advise", skip_tests=False)
