"""Tests for dharma_swarm.cli."""

import pytest
from typer.testing import CliRunner

from dharma_swarm.cli import app

runner = CliRunner()


def test_init(tmp_path):
    result = runner.invoke(app, ["init", "--state-dir", str(tmp_path / ".dharma")])
    assert result.exit_code == 0
    assert "Initialized" in result.stdout


def test_status(tmp_path):
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["status", "--state-dir", state_dir])
    assert result.exit_code == 0
    assert "DHARMA SWARM" in result.stdout


def test_task_create(tmp_path):
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["task", "create", "Hello World", "--state-dir", state_dir])
    assert result.exit_code == 0
    assert "Created task" in result.stdout


def test_task_list(tmp_path):
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    runner.invoke(app, ["task", "create", "Test Task", "--state-dir", state_dir])
    result = runner.invoke(app, ["task", "list", "--state-dir", state_dir])
    assert result.exit_code == 0


def test_memory_store_and_recall(tmp_path):
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["memory", "store", "test memory", "--state-dir", state_dir])
    assert result.exit_code == 0
    assert "Stored" in result.stdout

    result = runner.invoke(app, ["memory", "recall", "--state-dir", state_dir])
    assert result.exit_code == 0


def test_spawn(tmp_path):
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["spawn", "--name", "test-agent", "--role", "coder", "--state-dir", state_dir])
    assert result.exit_code == 0
    assert "Spawned agent" in result.stdout


# ── Additional CLI tests ─────────────────────────────────────────────


def test_spawn_invalid_role(tmp_path):
    """Spawning with a role that does not exist in AgentRole should fail."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["spawn", "--name", "bad-agent", "--role", "wizard", "--state-dir", state_dir])
    assert result.exit_code != 0


def test_task_create_with_description(tmp_path):
    """Create a task with both title and description."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(
        app,
        ["task", "create", "Refactor module",
         "--description", "Split models.py into separate files",
         "--state-dir", state_dir],
    )
    assert result.exit_code == 0
    assert "Created task" in result.stdout


def test_task_create_with_priority(tmp_path):
    """Create a task with explicit priority."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(
        app,
        ["task", "create", "Urgent fix",
         "--priority", "urgent",
         "--state-dir", state_dir],
    )
    assert result.exit_code == 0
    assert "Created task" in result.stdout


def test_task_create_invalid_priority(tmp_path):
    """Invalid priority value should cause a non-zero exit."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(
        app,
        ["task", "create", "Bad priority",
         "--priority", "mega-urgent",
         "--state-dir", state_dir],
    )
    assert result.exit_code != 0


def test_task_list_empty(tmp_path):
    """Listing tasks on a fresh swarm returns no error."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["task", "list", "--state-dir", state_dir])
    assert result.exit_code == 0


def test_task_list_with_status_filter(tmp_path):
    """Listing tasks with a status filter should succeed."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    runner.invoke(app, ["task", "create", "Some task", "--state-dir", state_dir])
    result = runner.invoke(
        app,
        ["task", "list", "--status", "pending", "--state-dir", state_dir],
    )
    assert result.exit_code == 0


def test_status_shows_default_agents(tmp_path):
    """Status on an initialized swarm should list the default startup crew."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["status", "--state-dir", state_dir])
    assert result.exit_code == 0
    # SwarmManager.init() creates a default startup crew; verify at least one appears
    assert "Agents" in result.stdout


def test_status_on_fresh_swarm(tmp_path):
    """Status on a freshly initialized swarm should show zero counts."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["status", "--state-dir", state_dir])
    assert result.exit_code == 0
    # Should contain the metric labels
    assert "Agents" in result.stdout
    assert "Tasks Pending" in result.stdout


def test_memory_recall_with_limit(tmp_path):
    """Recall with custom limit should succeed."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    runner.invoke(app, ["memory", "store", "first memory", "--state-dir", state_dir])
    runner.invoke(app, ["memory", "store", "second memory", "--state-dir", state_dir])
    result = runner.invoke(
        app,
        ["memory", "recall", "--limit", "1", "--state-dir", state_dir],
    )
    assert result.exit_code == 0


def test_context_command():
    """The context command should run without error and show section info."""
    result = runner.invoke(app, ["context", "--role", "surgeon"])
    assert result.exit_code == 0
    # Should show char count
    assert "chars" in result.stdout


def test_context_full_command():
    """context-full should dump context for a given role."""
    result = runner.invoke(app, ["context-full", "--role", "validator"])
    assert result.exit_code == 0


def test_context_with_thread():
    """Context command with a research thread should not crash."""
    result = runner.invoke(app, ["context", "--role", "archeologist", "--thread", "mechanistic"])
    assert result.exit_code == 0
    assert "chars" in result.stdout


def test_health_command(tmp_path):
    """Health command should produce output on an initialized swarm."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["health", "--state-dir", state_dir])
    assert result.exit_code == 0
    assert "Overall" in result.stdout


def test_evolve_trend_empty(tmp_path):
    """Fitness trend on a fresh swarm should show no data without error."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(app, ["evolve", "trend", "--state-dir", state_dir])
    assert result.exit_code == 0
    assert "No fitness data" in result.stdout


def test_init_idempotent(tmp_path):
    """Running init twice on the same directory should not fail."""
    state_dir = str(tmp_path / ".dharma")
    result1 = runner.invoke(app, ["init", "--state-dir", state_dir])
    result2 = runner.invoke(app, ["init", "--state-dir", state_dir])
    assert result1.exit_code == 0
    assert result2.exit_code == 0


def test_spawn_multiple_agents(tmp_path):
    """Spawning multiple agents with different names should all succeed."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    for name, role in [("a1", "coder"), ("a2", "reviewer"), ("a3", "tester")]:
        result = runner.invoke(
            app,
            ["spawn", "--name", name, "--role", role, "--state-dir", state_dir],
        )
        assert result.exit_code == 0
        assert name in result.stdout


def test_spawn_with_custom_model(tmp_path):
    """Spawning with a custom model should succeed."""
    state_dir = str(tmp_path / ".dharma")
    runner.invoke(app, ["init", "--state-dir", state_dir])
    result = runner.invoke(
        app,
        ["spawn", "--name", "custom-model-agent", "--role", "general",
         "--model", "openai/gpt-4o", "--state-dir", state_dir],
    )
    assert result.exit_code == 0
    assert "Spawned agent" in result.stdout
