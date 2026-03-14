"""Tests for the Build Engine — autonomous code improvement."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dharma_swarm.build_engine import (
    BuildTask,
    BuildResult,
    build_prompt,
    execute_task,
    validate_result,
    run_build_cycle,
    build_run_fn,
    _hermes_available,
    _git_stash,
    _git_stash_pop,
    _git_diff_files,
    _git_reset_hard,
    _git_commit,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def sample_task(tmp_path):
    """A BuildTask pointing at a tmp git repo."""
    repo = tmp_path / "test_project"
    repo.mkdir()
    (repo / "main.py").write_text("def hello():\n    return 'hello'\n")
    (repo / "test_main.py").write_text(
        "from main import hello\ndef test_hello():\n    assert hello() == 'hello'\n"
    )
    # Init git repo
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return BuildTask(
        queue_item_id="q1",
        initiative_id="init1",
        task="Add docstrings to all functions",
        project_name="test_project",
        project_path=str(repo),
        dimension="documented",
        targets=["main.py"],
        acceptance_criteria="All public functions have docstrings",
        test_command="python3 -m pytest test_main.py",
    )


@pytest.fixture
def git_repo(tmp_path):
    """A bare git repo for testing git operations."""
    repo = tmp_path / "git_test"
    repo.mkdir()
    (repo / "file.py").write_text("x = 1\n")
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return repo


# ── Prompt Builder ───────────────────────────────────────────────────


class TestBuildPrompt:
    def test_returns_two_strings(self, sample_task):
        system, user = build_prompt(sample_task)
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_contains_project(self, sample_task):
        system, _ = build_prompt(sample_task)
        assert "test_project" in system
        assert sample_task.project_path in system

    def test_user_prompt_contains_task(self, sample_task):
        _, user = build_prompt(sample_task)
        assert "Add docstrings" in user
        assert "documented" in user
        assert "main.py" in user

    def test_acceptance_criteria_in_prompt(self, sample_task):
        _, user = build_prompt(sample_task)
        assert "docstrings" in user.lower()

    def test_test_command_in_system(self, sample_task):
        system, _ = build_prompt(sample_task)
        assert "python3 -m pytest" in system

    def test_no_targets(self, sample_task):
        sample_task.targets = []
        _, user = build_prompt(sample_task)
        assert "TARGET FILES" not in user


# ── Dry Run ──────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_succeeds(self, sample_task):
        result = execute_task(sample_task, dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert "DRY RUN" in result.agent_output

    def test_dry_run_no_files_changed(self, sample_task):
        result = execute_task(sample_task, dry_run=True)
        assert result.files_changed == []
        assert result.committed is False

    def test_dry_run_fast(self, sample_task):
        result = execute_task(sample_task, dry_run=True)
        assert result.duration_seconds < 1.0


# ── Git Safety ───────────────────────────────────────────────────────


class TestGitSafety:
    def test_stash_clean_repo(self, git_repo):
        # Clean repo → nothing to stash
        had_stash = _git_stash(str(git_repo))
        assert had_stash is False

    def test_stash_dirty_repo(self, git_repo):
        # Modify a tracked file (untracked files aren't stashed by default)
        (git_repo / "file.py").write_text("x = 999\n")
        had_stash = _git_stash(str(git_repo))
        assert had_stash is True
        # File should be reverted after stash
        assert (git_repo / "file.py").read_text() == "x = 1\n"
        # Pop it back
        _git_stash_pop(str(git_repo))
        assert (git_repo / "file.py").read_text() == "x = 999\n"

    def test_diff_files_clean(self, git_repo):
        files = _git_diff_files(str(git_repo))
        assert files == []

    def test_diff_files_dirty(self, git_repo):
        (git_repo / "file.py").write_text("x = 2\n")
        files = _git_diff_files(str(git_repo))
        assert "file.py" in files

    def test_reset_hard(self, git_repo):
        (git_repo / "file.py").write_text("x = 999\n")
        (git_repo / "junk.py").write_text("junk\n")
        _git_reset_hard(str(git_repo))
        assert (git_repo / "file.py").read_text() == "x = 1\n"
        assert not (git_repo / "junk.py").exists()

    def test_commit(self, git_repo):
        (git_repo / "file.py").write_text("x = 2\n")
        ok = _git_commit(str(git_repo), "test commit\n\nCo-Authored-By: Oz <oz-agent@warp.dev>")
        assert ok is True
        # Verify commit
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=git_repo,
        )
        assert "test commit" in result.stdout


# ── Validation ───────────────────────────────────────────────────────


class TestValidation:
    def test_passing_tests(self, sample_task):
        result = validate_result(sample_task.project_path, sample_task.test_command)
        assert result is True

    def test_failing_tests(self, sample_task):
        # Break the test
        repo = Path(sample_task.project_path)
        (repo / "test_main.py").write_text(
            "def test_fail():\n    assert False\n"
        )
        result = validate_result(sample_task.project_path, sample_task.test_command)
        assert result is False

    def test_no_test_command(self, tmp_path):
        # No tests at all → pytest finds nothing, exits 5 (no tests collected)
        # which is non-zero → returns False
        result = validate_result(str(tmp_path))
        assert result is False


# ── Execute Task (mocked agent) ──────────────────────────────────────


class TestExecuteTask:
    def test_hermes_unavailable_returns_error(self, sample_task):
        with patch("dharma_swarm.build_engine._hermes_available", return_value=False):
            result = execute_task(sample_task, dry_run=False)
            assert result.success is False
            assert "not available" in result.error

    def test_agent_success_tests_pass(self, sample_task):
        def mock_spawn(prompt, system_prompt, project_path):
            # Simulate agent adding a docstring
            p = Path(project_path) / "main.py"
            p.write_text('def hello():\n    """Say hello."""\n    return "hello"\n')
            return "Added docstring to hello()"

        with patch("dharma_swarm.build_engine._hermes_available", return_value=True), \
             patch("dharma_swarm.build_engine._spawn_agent", side_effect=mock_spawn):
            result = execute_task(sample_task, dry_run=False)
            assert result.success is True
            assert result.tests_passed is True
            assert result.committed is True
            assert len(result.files_changed) > 0

    def test_agent_success_tests_fail_rollback(self, sample_task):
        def mock_spawn(prompt, system_prompt, project_path):
            # Simulate agent breaking code
            p = Path(project_path) / "main.py"
            p.write_text("def hello():\n    return 'WRONG'\n")
            return "Changed hello to return WRONG"

        with patch("dharma_swarm.build_engine._hermes_available", return_value=True), \
             patch("dharma_swarm.build_engine._spawn_agent", side_effect=mock_spawn):
            result = execute_task(sample_task, dry_run=False)
            assert result.success is False
            assert result.tests_passed is False
            assert result.committed is False
            assert "rolled back" in result.error

            # Verify rollback actually happened
            content = (Path(sample_task.project_path) / "main.py").read_text()
            assert "hello" in content
            # Original content should be restored
            assert "WRONG" not in content

    def test_agent_exception_rollback(self, sample_task):
        with patch("dharma_swarm.build_engine._hermes_available", return_value=True), \
             patch("dharma_swarm.build_engine._spawn_agent", side_effect=RuntimeError("boom")):
            result = execute_task(sample_task, dry_run=False)
            assert result.success is False
            assert "boom" in result.error


# ── Build Cycle ──────────────────────────────────────────────────────


class TestBuildCycle:
    def test_empty_queue(self, tmp_path, monkeypatch):
        """No tasks → empty results."""
        from dharma_swarm import iteration_depth
        iter_dir = tmp_path / "iteration"
        monkeypatch.setattr(iteration_depth, "ITERATION_DIR", iter_dir)
        monkeypatch.setattr(iteration_depth, "INITIATIVES_FILE", iter_dir / "initiatives.jsonl")
        monkeypatch.setattr(iteration_depth, "QUEUE_FILE", iter_dir / "queue.jsonl")

        results = run_build_cycle(dry_run=True)
        assert results == []


# ── Cron Integration ─────────────────────────────────────────────────


class TestBuildRunFn:
    def test_dry_run_default(self):
        with patch("dharma_swarm.build_engine.run_build_cycle", return_value=[]) as mock:
            success, output, error = build_run_fn({"prompt": ""})
            assert success is True
            mock.assert_called_once_with(dry_run=True)

    def test_live_mode(self):
        with patch("dharma_swarm.build_engine.run_build_cycle", return_value=[]) as mock:
            success, output, error = build_run_fn({"prompt": "live"})
            assert success is True
            mock.assert_called_once_with(dry_run=False)

    def test_error_handling(self):
        with patch("dharma_swarm.build_engine.run_build_cycle", side_effect=RuntimeError("fail")):
            success, output, error = build_run_fn({"prompt": ""})
            assert success is False
            assert "fail" in error


# ── Hermes Available Check ───────────────────────────────────────────


class TestHermesAvailable:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert _hermes_available() is False

    def test_no_hermes_dir(self, monkeypatch):
        monkeypatch.setattr("dharma_swarm.build_engine.HERMES_DIR", Path("/nonexistent"))
        assert _hermes_available() is False


# ── Quality Re-score Fields ──────────────────────────────────────────


class TestQualityRescore:
    def test_build_result_has_quality_fields(self, sample_task):
        result = BuildResult(
            task=sample_task,
            success=True,
            quality_before=0.4,
            quality_after=0.6,
            quality_delta=0.2,
        )
        assert result.quality_before == 0.4
        assert result.quality_after == 0.6
        assert result.quality_delta == 0.2

    def test_quality_fields_default_none(self, sample_task):
        result = BuildResult(task=sample_task, success=True)
        assert result.quality_before is None
        assert result.quality_after is None
        assert result.quality_delta is None

    def test_dry_run_no_quality_delta(self, sample_task):
        result = execute_task(sample_task, dry_run=True)
        assert result.quality_delta is None

    def test_quality_delta_computed_on_success(self, sample_task, tmp_path, monkeypatch):
        """After a successful live run with a registered project, quality_delta is set."""
        # Register the project in foreman so re-scoring can find it
        from dharma_swarm import foreman
        foreman_dir = tmp_path / "foreman"
        foreman_dir.mkdir()
        monkeypatch.setattr(foreman, "FOREMAN_DIR", foreman_dir)
        monkeypatch.setattr(foreman, "PROJECTS_FILE", foreman_dir / "projects.json")
        monkeypatch.setattr(foreman, "CYCLES_FILE", foreman_dir / "cycles.jsonl")
        monkeypatch.setattr(foreman, "HISTORY_FILE", foreman_dir / "history.jsonl")
        foreman.add_project(
            sample_task.project_path,
            name=sample_task.project_name,
            test_command=sample_task.test_command,
        )
        # Run a cycle to establish baseline scores
        foreman.run_cycle(level="observe")

        def mock_spawn(prompt, system_prompt, project_path):
            p = Path(project_path) / "main.py"
            p.write_text('def hello():\n    """Say hello."""\n    return "hello"\n')
            return "Added docstring"

        with patch("dharma_swarm.build_engine._hermes_available", return_value=True), \
             patch("dharma_swarm.build_engine._spawn_agent", side_effect=mock_spawn):
            result = execute_task(sample_task, dry_run=False)
            assert result.success is True
            assert result.committed is True
            assert result.quality_before is not None
            assert result.quality_after is not None
            assert result.quality_delta is not None
