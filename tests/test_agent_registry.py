"""Tests for agent_registry.py — JIKOKU paper trail, fitness, prompt evolution, budgets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.agent_registry import (
    DAILY_BUDGET_USD,
    MODEL_PRICING,
    WEEKLY_BUDGET_USD,
    AgentIdentity,
    AgentRegistry,
    _append_jsonl,
    _jikoku,
    _lookup_price_per_token,
    _read_json,
    _read_jsonl,
    _utc_now,
    _write_json,
    get_registry,
)


# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------


class TestTimeUtils:
    def test_utc_now_has_tzinfo(self):
        now = _utc_now()
        assert now.tzinfo is not None

    def test_jikoku_returns_iso_string(self):
        ts = _jikoku()
        assert "T" in ts
        assert "+" in ts or "Z" in ts  # timezone info present


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


class TestFileIO:
    def test_read_json_valid(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        result = _read_json(f)
        assert result == {"key": "value"}

    def test_read_json_missing(self, tmp_path):
        result = _read_json(tmp_path / "missing.json")
        assert result is None

    def test_read_json_corrupt(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        result = _read_json(f)
        assert result is None

    def test_write_json_creates_dirs(self, tmp_path):
        f = tmp_path / "sub" / "deep" / "file.json"
        _write_json(f, {"hello": "world"})
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["hello"] == "world"

    def test_write_json_atomic(self, tmp_path):
        """Verify tmp file is cleaned up (atomic rename)."""
        f = tmp_path / "atomic.json"
        _write_json(f, {"a": 1})
        assert f.exists()
        assert not f.with_suffix(".tmp").exists()

    def test_append_jsonl(self, tmp_path):
        f = tmp_path / "log.jsonl"
        _append_jsonl(f, {"entry": 1})
        _append_jsonl(f, {"entry": 2})
        lines = f.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["entry"] == 1
        assert json.loads(lines[1])["entry"] == 2

    def test_read_jsonl(self, tmp_path):
        f = tmp_path / "log.jsonl"
        f.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
        entries = _read_jsonl(f)
        assert len(entries) == 2

    def test_read_jsonl_skips_bad_lines(self, tmp_path):
        f = tmp_path / "log.jsonl"
        f.write_text('{"a":1}\nnot json\n{"a":3}\n', encoding="utf-8")
        entries = _read_jsonl(f)
        assert len(entries) == 2

    def test_read_jsonl_empty(self, tmp_path):
        f = tmp_path / "log.jsonl"
        f.write_text("", encoding="utf-8")
        assert _read_jsonl(f) == []

    def test_read_jsonl_missing(self, tmp_path):
        assert _read_jsonl(tmp_path / "missing.jsonl") == []


# ---------------------------------------------------------------------------
# Price lookup
# ---------------------------------------------------------------------------


class TestPriceLookup:
    def test_exact_match(self):
        price = _lookup_price_per_token("moonshotai/kimi-k2.5")
        assert price == MODEL_PRICING["moonshotai/kimi-k2.5"]

    def test_free_model(self):
        price = _lookup_price_per_token("nvidia/llama-3.1-nemotron-70b-instruct:free")
        assert price == 0.0

    def test_unknown_model_returns_zero(self):
        price = _lookup_price_per_token("totally-unknown-model-xyz")
        assert price == 0.0

    def test_substring_match(self):
        # "kimi-k2.5" should match via substring
        price = _lookup_price_per_token("kimi-k2.5")
        assert price > 0


# ---------------------------------------------------------------------------
# AgentIdentity dataclass
# ---------------------------------------------------------------------------


class TestAgentIdentityDataclass:
    def test_to_dict(self):
        ident = AgentIdentity(
            name="test", role="coder", model="gpt-4",
            system_prompt="You code.",
        )
        d = ident.to_dict()
        assert d["name"] == "test"
        assert d["role"] == "coder"
        assert d["model"] == "gpt-4"
        assert isinstance(d["task_history"], list)

    def test_from_dict(self):
        d = {
            "name": "test", "role": "coder", "model": "gpt-4",
            "system_prompt": "hi", "tasks_completed": 5,
        }
        ident = AgentIdentity.from_dict(d)
        assert ident.name == "test"
        assert ident.tasks_completed == 5

    def test_from_dict_ignores_unknown(self):
        d = {
            "name": "test", "role": "coder", "model": "gpt-4",
            "system_prompt": "hi", "unknown_field": True,
        }
        ident = AgentIdentity.from_dict(d)
        assert ident.name == "test"
        assert not hasattr(ident, "unknown_field") or "unknown_field" not in ident.to_dict()


# ---------------------------------------------------------------------------
# AgentRegistry — registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_creates_files(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        data = reg.register_agent("alice", "coder", "gpt-4", "You code.")

        assert data["name"] == "alice"
        assert (tmp_path / "agents" / "alice" / "identity.json").exists()
        assert (tmp_path / "agents" / "alice" / "prompt_variants" / "active.txt").exists()
        assert (tmp_path / "agents" / "alice" / "prompt_variants" / "gen_0.txt").exists()

    def test_register_idempotent(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        d1 = reg.register_agent("alice", "coder", "gpt-4", "prompt v1")
        d2 = reg.register_agent("alice", "reviewer", "gpt-3.5", "prompt v2")
        # Second call returns existing, doesn't overwrite
        assert d1["role"] == d2["role"]
        assert d2["system_prompt"] == "prompt v1"

    def test_register_creates_evolution_log(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("bob", "tester", "llama", "Test all things.")
        log = _read_jsonl(tmp_path / "agents" / "bob" / "prompt_variants" / "evolution_log.jsonl")
        assert len(log) == 1
        assert log[0]["generation"] == 0
        assert log[0]["reason"] == "initial registration"


# ---------------------------------------------------------------------------
# AgentRegistry — loading and listing
# ---------------------------------------------------------------------------


class TestLoadAndList:
    def test_load_registered(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        data = reg.load_agent("alice")
        assert data is not None
        assert data["name"] == "alice"

    def test_load_missing(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        assert reg.load_agent("nonexistent") is None

    def test_list_agents(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p1")
        reg.register_agent("bob", "tester", "gpt-4", "p2")
        agents = reg.list_agents()
        names = [a["name"] for a in agents]
        assert "alice" in names
        assert "bob" in names
        # Sorted by name
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------


class TestLegacyMigration:
    def test_load_migrates_legacy(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        # Write legacy flat file
        legacy = agents_dir / "oldbot.json"
        legacy.write_text(json.dumps({
            "name": "oldbot", "role": "general", "model": "gpt-4",
            "system_prompt": "I am old.", "task_history": [{"task": "t1"}],
        }), encoding="utf-8")

        reg = AgentRegistry(agents_dir=agents_dir)
        data = reg.load_agent("oldbot")
        assert data is not None
        assert data["name"] == "oldbot"

        # Verify migration happened
        assert (agents_dir / "oldbot" / "identity.json").exists()
        assert (agents_dir / "oldbot" / "task_log.jsonl").exists()
        assert legacy.with_suffix(".json.bak").exists()

    def test_migrate_all_legacy(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        for name in ("a1", "a2"):
            (agents_dir / f"{name}.json").write_text(json.dumps({
                "name": name, "role": "r", "model": "m", "system_prompt": "s",
            }), encoding="utf-8")

        reg = AgentRegistry(agents_dir=agents_dir)
        migrated = reg.migrate_all_legacy()
        assert set(migrated) == {"a1", "a2"}


# ---------------------------------------------------------------------------
# Task logging
# ---------------------------------------------------------------------------


class TestTaskLogging:
    def test_log_task_creates_entry(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        reg.log_task("alice", "fix bug", success=True, tokens=500, latency_ms=3000.0)

        entries = _read_jsonl(tmp_path / "agents" / "alice" / "task_log.jsonl")
        assert len(entries) == 1
        assert entries[0]["success"] is True
        assert entries[0]["tokens"] == 500

    def test_log_task_updates_counters(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        reg.log_task("alice", "task1", success=True, tokens=100, latency_ms=1000.0)
        reg.log_task("alice", "task2", success=False, tokens=200, latency_ms=2000.0)

        data = reg.load_agent("alice")
        assert data["tasks_completed"] == 1
        assert data["tasks_failed"] == 1
        assert data["total_tokens_used"] == 300
        assert data["total_calls"] == 2

    def test_log_task_caps_history(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        for i in range(60):
            reg.log_task("alice", f"task_{i}", success=True, tokens=1, latency_ms=1.0)

        data = reg.load_agent("alice")
        assert len(data["task_history"]) <= 50

    def test_log_task_computes_cost(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "moonshotai/kimi-k2.5", "prompt")
        reg.log_task("alice", "task", success=True, tokens=1_000_000, latency_ms=5000.0)

        entries = _read_jsonl(tmp_path / "agents" / "alice" / "task_log.jsonl")
        assert entries[0]["cost_usd"] > 0


# ---------------------------------------------------------------------------
# Fitness computation
# ---------------------------------------------------------------------------


class TestFitness:
    def test_no_tasks_fitness(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        fitness = reg.get_agent_fitness("alice")
        assert fitness["success_rate"] == 0.0
        assert fitness["composite_fitness"] == 0.0
        assert fitness["total_calls"] == 0

    def test_fitness_with_tasks(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        # 3 successes, 1 failure
        for i in range(3):
            reg.log_task("alice", f"ok_{i}", success=True, tokens=100, latency_ms=3000.0)
        reg.log_task("alice", "fail", success=False, tokens=100, latency_ms=3000.0)

        fitness = reg.get_agent_fitness("alice")
        assert fitness["success_rate"] == 0.75
        assert fitness["total_calls"] == 4
        assert fitness["composite_fitness"] > 0

    def test_speed_score_fast(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        reg.log_task("alice", "fast", success=True, tokens=10, latency_ms=1000.0)
        fitness = reg.get_agent_fitness("alice")
        assert fitness["speed_score"] == 1.0  # under ceiling

    def test_speed_score_slow(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        reg.log_task("alice", "slow", success=True, tokens=10, latency_ms=200_000.0)
        fitness = reg.get_agent_fitness("alice")
        assert fitness["speed_score"] == 0.0  # over floor

    def test_update_fitness_history(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "prompt")
        reg.log_task("alice", "t", success=True, tokens=10, latency_ms=1000.0)
        reg.update_fitness_history("alice")

        history = reg.get_fitness_history("alice")
        assert len(history) == 1
        assert "composite_fitness" in history[0]


# ---------------------------------------------------------------------------
# Prompt evolution
# ---------------------------------------------------------------------------


class TestPromptEvolution:
    def test_get_prompt_variant_active(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "Original prompt.")
        prompt = reg.get_prompt_variant("alice")
        assert prompt == "Original prompt."

    def test_evolve_prompt(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "v1 prompt")
        reg.evolve_prompt("alice", "v2 prompt", "performance improvement")

        # Active prompt updated
        assert reg.get_prompt_variant("alice") == "v2 prompt"

        # Identity updated
        data = reg.load_agent("alice")
        assert data["prompt_generation"] == 1
        assert data["system_prompt"] == "v2 prompt"

        # Evolution log has 2 entries (initial + evolution)
        log = reg.get_prompt_history("alice")
        assert len(log) == 2
        assert log[1]["reason"] == "performance improvement"

        # Old gen preserved
        assert (tmp_path / "agents" / "alice" / "prompt_variants" / "gen_0.txt").exists()
        assert (tmp_path / "agents" / "alice" / "prompt_variants" / "gen_1.txt").exists()

    def test_evolve_prompt_unregistered_raises(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        with pytest.raises(ValueError, match="unregistered"):
            reg.evolve_prompt("ghost", "new prompt", "reason")

    def test_multiple_evolutions(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "v0")
        reg.evolve_prompt("alice", "v1", "reason1")
        reg.evolve_prompt("alice", "v2", "reason2")

        data = reg.load_agent("alice")
        assert data["prompt_generation"] == 2
        assert reg.get_prompt_variant("alice") == "v2"

        log = reg.get_prompt_history("alice")
        assert len(log) == 3  # gen_0 + gen_1 + gen_2


# ---------------------------------------------------------------------------
# Fleet operations
# ---------------------------------------------------------------------------


class TestFleetOperations:
    def test_get_fleet_fitness(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        reg.register_agent("bob", "tester", "gpt-4", "p")
        reg.log_task("alice", "t", success=True, tokens=10, latency_ms=1000.0)

        fleet = reg.get_fleet_fitness()
        assert len(fleet) == 2
        # Sorted by composite_fitness descending
        assert fleet[0]["composite_fitness"] >= fleet[1]["composite_fitness"]

    def test_get_fleet_summary(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        reg.log_task("alice", "t", success=True, tokens=100, latency_ms=1000.0)

        summary = reg.get_fleet_summary()
        assert summary["total_agents"] == 1
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 100


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


class TestBudgetTracking:
    def test_daily_spend_zero(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        assert reg.get_daily_spend("alice") == 0.0

    def test_weekly_spend_zero(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        assert reg.get_weekly_spend("alice") == 0.0

    def test_check_budget_ok(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        status = reg.check_budget("alice")
        assert status["status"] == "OK"
        assert status["daily_remaining"] == DAILY_BUDGET_USD
        assert status["weekly_remaining"] == WEEKLY_BUDGET_USD

    def test_is_budget_exceeded_false(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        assert reg.is_budget_exceeded("alice") is False

    def test_format_budget_report(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        reg.register_agent("alice", "coder", "gpt-4", "p")
        report = reg.format_budget_report()
        assert "GINKO BUDGET REPORT" in report
        assert "alice" in report

    def test_format_budget_report_empty(self, tmp_path):
        reg = AgentRegistry(agents_dir=tmp_path / "agents")
        report = reg.format_budget_report()
        assert "No registered agents" in report


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestFactory:
    def test_get_registry_default(self, tmp_path):
        reg = get_registry(agents_dir=tmp_path / "agents")
        assert isinstance(reg, AgentRegistry)
        assert reg.agents_dir == tmp_path / "agents"
