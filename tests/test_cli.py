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
