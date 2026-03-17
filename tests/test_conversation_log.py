"""Tests for the unified conversation logger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.conversation_log import (
    log_exchange,
    log_agent_turn,
    load_recent,
    load_promises,
    stats,
    _extract_promises,
)


class TestExtractPromises:
    def test_finds_will(self):
        text = "I will build this feature.\nSome other line."
        promises = _extract_promises(text)
        assert len(promises) == 1
        assert "I will build" in promises[0]

    def test_finds_let_me(self):
        text = "Let me check the configuration file."
        promises = _extract_promises(text)
        assert len(promises) == 1

    def test_finds_phase(self):
        text = "Phase 7 is the eval harness."
        promises = _extract_promises(text)
        assert len(promises) == 1

    def test_ignores_short_lines(self):
        text = "I will.\nOK."
        promises = _extract_promises(text)
        assert len(promises) == 0

    def test_empty_input(self):
        assert _extract_promises("") == []

    def test_caps_at_20(self):
        text = "\n".join(f"I will do thing number {i}" for i in range(30))
        promises = _extract_promises(text)
        assert len(promises) == 20


class TestLogExchange:
    def test_writes_to_daily_and_master(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange("user", "hello world", interface="test", session_id="s1")

        # Check daily log
        daily_files = list(tmp_path.glob("*.jsonl"))
        daily_files = [f for f in daily_files if f.name not in ("all.jsonl", "promises.jsonl")]
        assert len(daily_files) == 1
        entry = json.loads(daily_files[0].read_text().strip())
        assert entry["role"] == "user"
        assert entry["content"] == "hello world"
        assert entry["interface"] == "test"

        # Check master log
        master = tmp_path / "all.jsonl"
        assert master.exists()
        assert "hello world" in master.read_text()

    def test_extracts_promises_from_assistant(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange(
            "assistant",
            "I will implement the feature. Let me start now.",
            interface="test",
        )

        promises_file = tmp_path / "promises.jsonl"
        assert promises_file.exists()
        entry = json.loads(promises_file.read_text().strip())
        assert entry["type"] == "promises_detected"
        assert entry["count"] >= 1

    def test_no_promises_from_user(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange("user", "I will do something", interface="test")

        promises_file = tmp_path / "promises.jsonl"
        assert not promises_file.exists()

    def test_metadata_included(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange("user", "test", interface="api", metadata={"model": "opus"})

        master = tmp_path / "all.jsonl"
        entry = json.loads(master.read_text().strip())
        assert entry["metadata"]["model"] == "opus"


class TestLogAgentTurn:
    def test_agent_turn_logged(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_agent_turn(
            agent_id="architect",
            task_id="t-1",
            role="assistant",
            content="Task completed successfully",
            model="claude-opus",
        )

        master = tmp_path / "all.jsonl"
        entry = json.loads(master.read_text().strip())
        assert entry["interface"] == "agent"
        assert entry["metadata"]["agent_id"] == "architect"
        assert entry["metadata"]["model"] == "claude-opus"


class TestLoadRecent:
    def test_loads_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange("user", "msg1", interface="test")
        log_exchange("assistant", "reply1", interface="test")

        entries = load_recent(hours=1)
        assert len(entries) == 2

    def test_filters_by_role(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange("user", "msg1", interface="test")
        log_exchange("assistant", "reply1", interface="test")

        user_only = load_recent(hours=1, role="user")
        assert len(user_only) == 1
        assert user_only[0]["role"] == "user"

    def test_empty_when_no_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)
        assert load_recent() == []


class TestStats:
    def test_stats_shape(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.conversation_log.LOG_DIR", tmp_path)

        log_exchange("user", "hello", interface="tui", session_id="s1")
        log_exchange("assistant", "I will help you", interface="tui", session_id="s1")

        s = stats(hours=1)
        assert s["total_entries"] == 2
        assert s["by_role"]["user"] == 1
        assert s["by_role"]["assistant"] == 1
        assert s["by_interface"]["tui"] == 2
        assert s["unique_sessions"] >= 1
        assert s["promises_detected"] >= 1
