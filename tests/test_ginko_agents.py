"""Tests for ginko_agents.py — Ginko fleet data model, persistence, fitness, fleet ops."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.runtime_provider import RuntimeProviderConfig
from dharma_swarm.ginko_agents import (
    DOMAIN_CREW,
    FLEET_SPEC,
    GinkoAgent,
    GinkoFleet,
    PARENT_AGENT,
    _LATENCY_CEILING_MS,
    _MAX_MEMORY_HISTORY,
    _MODEL_FALLBACKS,
    _append_fitness_snapshot,
    _append_task_log,
    _avg_latency_ms,
    _deserialize_agent,
    _ensure_agent_dirs,
    _identity_path,
    _load_agent_from_disk,
    _save_agent_to_disk,
    _serialize_agent,
    _success_rate,
    _utc_now,
    agent_task,
    best_agent_for_role,
    compute_agent_fitness,
    fleet_alpha_scan,
    fleet_analyze,
    fleet_consensus,
    fleet_fitness_ranking,
    fleet_health_check,
    fleet_macro_analysis,
    fleet_risk_check,
    fleet_sec_analysis,
    get_fleet_agent_names,
    get_parent_agent,
    is_domain_crew,
)


# ---------------------------------------------------------------------------
# FLEET_SPEC data integrity
# ---------------------------------------------------------------------------


class TestFleetSpec:
    def test_has_agents(self):
        assert len(FLEET_SPEC) >= 6

    def test_required_keys(self):
        required = {"name", "role", "model", "system_prompt"}
        for spec in FLEET_SPEC:
            missing = required - set(spec.keys())
            assert not missing, f"Agent spec '{spec.get('name', '?')}' missing: {missing}"

    def test_names_unique(self):
        names = [s["name"] for s in FLEET_SPEC]
        assert len(names) == len(set(names)), f"Duplicate names: {[n for n in names if names.count(n) > 1]}"

    def test_names_lowercase(self):
        for spec in FLEET_SPEC:
            assert spec["name"] == spec["name"].lower()

    def test_roles_not_empty(self):
        for spec in FLEET_SPEC:
            assert len(spec["role"]) > 3

    def test_models_have_slash(self):
        """Model IDs should be provider/model format."""
        for spec in FLEET_SPEC:
            assert "/" in spec["model"], f"Model for {spec['name']} missing provider prefix"

    def test_system_prompts_not_empty(self):
        for spec in FLEET_SPEC:
            assert len(spec["system_prompt"]) > 50, f"Prompt too short for {spec['name']}"

    def test_original_six_present(self):
        names = {s["name"] for s in FLEET_SPEC}
        for name in ("kimi", "deepseek", "nemotron", "glm", "sentinel", "scout"):
            assert name in names


class TestDomainCrew:
    def test_domain_crew_name(self):
        assert DOMAIN_CREW == "ginko"

    def test_parent_agent(self):
        assert get_parent_agent() == "strategist"
        assert PARENT_AGENT == "strategist"

    def test_is_domain_crew(self):
        assert is_domain_crew() is True

    def test_get_fleet_agent_names(self):
        names = get_fleet_agent_names()
        assert isinstance(names, list)
        assert len(names) == len(FLEET_SPEC)
        assert "kimi" in names


# ---------------------------------------------------------------------------
# GinkoAgent dataclass
# ---------------------------------------------------------------------------


class TestGinkoAgent:
    def test_creation_defaults(self):
        agent = GinkoAgent(name="test", role="tester", model="m/m", system_prompt="p")
        assert agent.name == "test"
        assert agent.status == "idle"
        assert agent.fitness == 0.5
        assert agent.tasks_completed == 0
        assert agent.tasks_failed == 0
        assert agent.total_tokens_used == 0
        assert agent.total_calls == 0
        assert agent.avg_quality == 0.0
        assert isinstance(agent.task_history, list)

    def test_created_at_is_iso(self):
        agent = GinkoAgent(name="t", role="r", model="m/m", system_prompt="p")
        assert "T" in agent.created_at  # ISO-8601 has T separator

    def test_serialization_roundtrip(self):
        agent = GinkoAgent(name="alice", role="analyst", model="m/m", system_prompt="sys")
        data = _serialize_agent(agent)
        restored = _deserialize_agent(data)
        assert restored.name == "alice"
        assert restored.role == "analyst"

    def test_deserialize_tolerates_extra_keys(self):
        data = {"name": "bob", "role": "r", "model": "m/m", "system_prompt": "p", "unknown_key": 42}
        agent = _deserialize_agent(data)
        assert agent.name == "bob"

    def test_deserialize_tolerates_missing_optional(self):
        data = {"name": "carol", "role": "r", "model": "m/m", "system_prompt": "p"}
        agent = _deserialize_agent(data)
        assert agent.status == "idle"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_ensure_agent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        _ensure_agent_dirs("alpha")
        assert (tmp_path / "agents" / "alpha").is_dir()
        assert (tmp_path / "agents" / "alpha" / "prompt_variants").is_dir()

    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        agent = GinkoAgent(name="x", role="r", model="m/m", system_prompt="hello")
        _save_agent_to_disk(agent)

        loaded = _load_agent_from_disk("x")
        assert loaded is not None
        assert loaded.name == "x"
        assert loaded.system_prompt == "hello"

        # Check active prompt file written
        prompt_path = tmp_path / "agents" / "x" / "prompt_variants" / "active.txt"
        assert prompt_path.exists()
        assert prompt_path.read_text() == "hello"

    def test_load_nonexistent_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        assert _load_agent_from_disk("nope") is None

    def test_legacy_migration(self, tmp_path, monkeypatch):
        """Loading from legacy flat file (agents/name.json) works."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", agents_dir)

        legacy_data = {"name": "hermes", "role": "coordinator", "model": "m/m", "system_prompt": "old"}
        (agents_dir / "hermes.json").write_text(json.dumps(legacy_data))

        loaded = _load_agent_from_disk("hermes")
        assert loaded is not None
        assert loaded.name == "hermes"
        assert loaded.role == "coordinator"

    def test_load_corrupt_json_returns_none(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", agents_dir)
        d = agents_dir / "bad"
        d.mkdir(parents=True)
        (d / "identity.json").write_text("{not valid json")
        assert _load_agent_from_disk("bad") is None

    def test_append_task_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        _append_task_log("loggy", {"task": "hello", "success": True})
        _append_task_log("loggy", {"task": "world", "success": False})

        log_path = tmp_path / "agents" / "loggy" / "task_log.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["task"] == "hello"

    def test_append_fitness_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        _append_fitness_snapshot("fitty", 0.85)

        path = tmp_path / "agents" / "fitty" / "fitness_history.jsonl"
        assert path.exists()
        entry = json.loads(path.read_text().strip())
        assert entry["fitness"] == 0.85


# ---------------------------------------------------------------------------
# Fitness calculation
# ---------------------------------------------------------------------------


class TestFitness:
    def _make_agent(self, **kw):
        defaults = {"name": "t", "role": "r", "model": "m/m", "system_prompt": "p"}
        defaults.update(kw)
        return GinkoAgent(**defaults)

    def test_success_rate_no_calls(self):
        agent = self._make_agent()
        assert _success_rate(agent) is None

    def test_success_rate_all_success(self):
        agent = self._make_agent(total_calls=10, tasks_completed=10)
        assert _success_rate(agent) == 1.0

    def test_success_rate_partial(self):
        agent = self._make_agent(total_calls=10, tasks_completed=7)
        assert _success_rate(agent) == 0.7

    def test_avg_latency_empty(self):
        agent = self._make_agent()
        assert _avg_latency_ms(agent) is None

    def test_avg_latency_with_history(self):
        agent = self._make_agent(
            task_history=[
                {"latency_ms": 100.0},
                {"latency_ms": 200.0},
                {"latency_ms": 300.0},
            ]
        )
        assert _avg_latency_ms(agent) == 200.0

    def test_avg_latency_skips_bad_entries(self):
        agent = self._make_agent(
            task_history=[
                {"latency_ms": 100.0},
                {"latency_ms": "bad"},
                {"no_latency": True},
                {"latency_ms": 0},  # zero is excluded
            ]
        )
        assert _avg_latency_ms(agent) == 100.0

    def test_fitness_new_agent(self):
        agent = self._make_agent()
        fitness = compute_agent_fitness(agent)
        # Default: 0.5 * 0.4 + 0.5 * 0.3 + 0.0 * 0.3 = 0.35
        assert abs(fitness - 0.35) < 0.01

    def test_fitness_perfect_agent(self):
        agent = self._make_agent(
            total_calls=100, tasks_completed=100, avg_quality=1.0,
            task_history=[{"latency_ms": 1.0}],  # very fast
        )
        fitness = compute_agent_fitness(agent)
        assert fitness > 0.9

    def test_fitness_terrible_agent(self):
        agent = self._make_agent(
            total_calls=100, tasks_completed=0, avg_quality=0.0,
            task_history=[{"latency_ms": _LATENCY_CEILING_MS * 2}],  # very slow
        )
        fitness = compute_agent_fitness(agent)
        assert fitness < 0.1

    def test_fitness_clamped_to_01(self):
        agent = self._make_agent(
            total_calls=1, tasks_completed=1, avg_quality=1.0,
            task_history=[{"latency_ms": 0.001}],
        )
        fitness = compute_agent_fitness(agent)
        assert 0.0 <= fitness <= 1.0


# ---------------------------------------------------------------------------
# GinkoFleet
# ---------------------------------------------------------------------------


class TestGinkoFleet:
    def test_fleet_creation(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        assert len(fleet.list_agents()) == len(FLEET_SPEC)

    def test_fleet_get_agent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        agent = fleet.get_agent("kimi")
        assert agent is not None
        assert agent.name == "kimi"

    def test_fleet_get_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        assert fleet.get_agent("nonexistent") is None

    def test_fleet_agent_names_sorted(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        names = fleet.agent_names()
        assert names == sorted(names)

    def test_fleet_save_agent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        agent = fleet.get_agent("kimi")
        agent.fitness = 0.99
        fleet.save_agent(agent)
        # Verify persisted
        reloaded = _load_agent_from_disk("kimi")
        assert reloaded.fitness == 0.99

    def test_fleet_summary_returns_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        summary = fleet.fleet_summary()
        assert "Dharmic Quant" in summary
        assert "kimi" in summary

    def test_fleet_preserves_existing_identity(self, tmp_path, monkeypatch):
        """If agent already exists on disk, fleet doesn't overwrite it."""
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", agents_dir)

        # Pre-create kimi with custom fitness
        _ensure_agent_dirs("kimi")
        custom = GinkoAgent(
            name="kimi", role="macro_oracle", model="custom/model",
            system_prompt="custom prompt", fitness=0.99,
        )
        _save_agent_to_disk(custom)

        fleet = GinkoFleet()
        loaded = fleet.get_agent("kimi")
        assert loaded.model == "custom/model"
        assert loaded.fitness == 0.99


# ---------------------------------------------------------------------------
# Fleet status / ranking
# ---------------------------------------------------------------------------


class TestFleetStatus:
    def _make_fleet(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        return GinkoFleet()

    def test_fitness_ranking(self, tmp_path, monkeypatch):
        fleet = self._make_fleet(tmp_path, monkeypatch)
        # Set different fitnesses
        a1 = fleet.get_agent("kimi")
        a1.fitness = 0.9
        fleet.save_agent(a1)
        a2 = fleet.get_agent("scout")
        a2.fitness = 0.1
        fleet.save_agent(a2)

        ranking = fleet_fitness_ranking(fleet)
        assert ranking[0][1] >= ranking[-1][1]  # descending

    def test_best_agent_for_role(self, tmp_path, monkeypatch):
        fleet = self._make_fleet(tmp_path, monkeypatch)
        best = best_agent_for_role(fleet, "macro_oracle")
        assert best is not None
        assert best.role == "macro_oracle"

    def test_best_agent_for_nonexistent_role(self, tmp_path, monkeypatch):
        fleet = self._make_fleet(tmp_path, monkeypatch)
        assert best_agent_for_role(fleet, "nonexistent_role") is None

    def test_fleet_health_check(self, tmp_path, monkeypatch):
        fleet = self._make_fleet(tmp_path, monkeypatch)
        health = fleet_health_check(fleet)
        assert health["agent_count"] == len(FLEET_SPEC)
        assert "total_calls" in health
        assert "avg_fitness" in health
        assert "agents_by_status" in health
        assert "warnings" in health
        assert "timestamp" in health

    def test_health_check_warnings_on_low_success(self, tmp_path, monkeypatch):
        fleet = self._make_fleet(tmp_path, monkeypatch)
        agent = fleet.get_agent("kimi")
        agent.total_calls = 10
        agent.tasks_completed = 1  # 10% success
        agent.fitness = 0.1
        fleet.save_agent(agent)

        health = fleet_health_check(fleet)
        assert len(health["warnings"]) >= 1


# ---------------------------------------------------------------------------
# agent_task (mocked API)
# ---------------------------------------------------------------------------


class TestAgentTask:
    @pytest.mark.asyncio
    async def test_agent_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        result = await agent_task(fleet, "nonexistent", "hello")
        assert result["success"] is False
        assert "not found" in result["response"]

    @pytest.mark.asyncio
    async def test_successful_task(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "Analysis complete: bullish outlook",
            "tokens": 150,
            "latency_ms": 500.0,
            "model": "moonshotai/kimi-k2.5",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await agent_task(fleet, "kimi", "analyze macro")

        assert result["success"] is True
        assert result["tokens"] == 150
        agent = fleet.get_agent("kimi")
        assert agent.total_calls == 1
        assert agent.tasks_completed == 1
        assert agent.status == "idle"

    @pytest.mark.asyncio
    async def test_failed_task_updates_counters(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "",
            "tokens": 0,
            "latency_ms": 100.0,
            "model": "moonshotai/kimi-k2.5",
            "error": True,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await agent_task(fleet, "kimi", "fail task")

        assert result["success"] is False
        agent = fleet.get_agent("kimi")
        assert agent.tasks_failed == 1

    @pytest.mark.asyncio
    async def test_task_history_bounded(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()
        agent = fleet.get_agent("kimi")
        # Pre-fill history near the limit
        agent.task_history = [{"task": f"t{i}", "latency_ms": 10.0} for i in range(_MAX_MEMORY_HISTORY)]
        fleet.save_agent(agent)

        mock_response = {
            "content": "done",
            "tokens": 10,
            "latency_ms": 50.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            await agent_task(fleet, "kimi", "one more")

        agent = fleet.get_agent("kimi")
        assert len(agent.task_history) <= _MAX_MEMORY_HISTORY


# ---------------------------------------------------------------------------
# fleet_analyze (mocked API)
# ---------------------------------------------------------------------------


class TestFleetAnalyze:
    @pytest.mark.asyncio
    async def test_parallel_dispatch(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "analysis result",
            "tokens": 50,
            "latency_ms": 100.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            results = await fleet_analyze(fleet, "test question", ["kimi", "scout"])

        assert "kimi" in results
        assert "scout" in results

    @pytest.mark.asyncio
    async def test_invalid_agent_in_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "ok",
            "tokens": 10,
            "latency_ms": 50.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            results = await fleet_analyze(fleet, "q", ["kimi", "nonexistent"])

        assert "nonexistent" in results
        assert "ERROR" in results["nonexistent"]
        assert "kimi" in results


# ---------------------------------------------------------------------------
# Fleet analysis pipelines (mocked)
# ---------------------------------------------------------------------------


class TestFleetPipelines:
    @pytest.mark.asyncio
    async def test_macro_analysis(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "Regime: BULL. Confidence: 70%.",
            "tokens": 100,
            "latency_ms": 200.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await fleet_macro_analysis(fleet, {"macro": {"fed_funds_rate": 5.25}})

        assert "consensus_regime" in result
        assert "agents" in result

    @pytest.mark.asyncio
    async def test_sec_analysis(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "Filing is bearish: rising costs, declining margins.",
            "tokens": 100,
            "latency_ms": 200.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await fleet_sec_analysis(fleet, {"risk_factors": "inflation risk", "management_discussion": "stable"})

        assert "findings" in result

    @pytest.mark.asyncio
    async def test_risk_check(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "PASS: BTC position within limits.",
            "tokens": 80,
            "latency_ms": 150.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await fleet_risk_check(
                fleet,
                {"total_value": 100000, "max_drawdown": 0.05, "open_positions": 3},
                [{"symbol": "BTC", "direction": "long", "confidence": 0.7}],
            )

        assert "risk_review" in result

    @pytest.mark.asyncio
    async def test_alpha_scan(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "Opportunity: ETH mean reversion setup.",
            "tokens": 60,
            "latency_ms": 120.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await fleet_alpha_scan(
                fleet,
                {"BTC": [60000.0, 61000.0, 62000.0], "ETH": [3000.0, 2900.0, 2800.0]},
                "bull",
            )

        assert "alpha_scan" in result
        assert result["agent"] == "scout"

    @pytest.mark.asyncio
    async def test_consensus(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_agents.AGENTS_DIR", tmp_path / "agents")
        fleet = GinkoFleet()

        mock_response = {
            "content": "YES. Confidence: 80%. Strong macro tailwinds.",
            "tokens": 40,
            "latency_ms": 100.0,
            "model": "m/m",
            "error": False,
        }
        with patch("dharma_swarm.ginko_agents._call_openrouter", new_callable=AsyncMock, return_value=mock_response):
            result = await fleet_consensus(fleet, "Should we go long BTC?")

        assert "votes" in result
        assert "majority" in result
        assert result["majority"] == "YES"


# ---------------------------------------------------------------------------
# Model fallbacks
# ---------------------------------------------------------------------------


class TestModelFallbacks:
    def test_fallback_dict_has_entries(self):
        assert len(_MODEL_FALLBACKS) >= 1

    def test_fallback_values_are_lists(self):
        for model, fallbacks in _MODEL_FALLBACKS.items():
            assert isinstance(fallbacks, list)
            assert all(isinstance(f, str) for f in fallbacks)

    def test_fallback_models_have_slash(self):
        for model, fallbacks in _MODEL_FALLBACKS.items():
            assert "/" in model
            for fb in fallbacks:
                assert "/" in fb


# ---------------------------------------------------------------------------
# _call_openrouter (mocked httpx)
# ---------------------------------------------------------------------------


class TestCallOpenRouter:
    @pytest.mark.asyncio
    async def test_no_available_providers(self, monkeypatch):
        from dharma_swarm.ginko_agents import _call_openrouter

        monkeypatch.setattr(
            "dharma_swarm.ginko_agents.preferred_runtime_provider_configs",
            lambda **kwargs: [],
        )
        result = await _call_openrouter("m/m", [{"role": "user", "content": "hi"}])
        assert result["error"] is True
        assert "No preferred providers available" in result["content"]

    @pytest.mark.asyncio
    async def test_timeout_handling(self, monkeypatch):
        import httpx
        from dharma_swarm.ginko_agents import _call_openrouter

        class _TimeoutProvider:
            async def complete(self, request):
                raise httpx.TimeoutException("timed out")

            async def close(self):
                return None

        monkeypatch.setattr(
            "dharma_swarm.ginko_agents.preferred_runtime_provider_configs",
            lambda **kwargs: [
                RuntimeProviderConfig(
                    provider=ProviderType.OLLAMA,
                    available=True,
                    default_model="ollama-local",
                )
            ],
        )
        monkeypatch.setattr(
            "dharma_swarm.ginko_agents.create_runtime_provider",
            lambda config: _TimeoutProvider(),
        )
        result = await _call_openrouter("m/m", [{"role": "user", "content": "hi"}])

        assert result["error"] is True
        assert "TIMEOUT" in result["content"] or "ERROR" in result["content"]

    @pytest.mark.asyncio
    async def test_prefers_ollama_then_nim_before_openrouter(self, monkeypatch):
        from dharma_swarm.ginko_agents import _call_openrouter

        calls: list[tuple[str, str]] = []

        class _FakeProvider:
            def __init__(self, label: str, *, fail: bool = False):
                self.label = label
                self.fail = fail

            async def complete(self, request):
                calls.append((self.label, request.model))
                if self.fail:
                    raise RuntimeError(f"{self.label} failed")
                return LLMResponse(content=f"{self.label} ok", model=request.model)

            async def close(self):
                return None

        monkeypatch.setattr(
            "dharma_swarm.ginko_agents.preferred_runtime_provider_configs",
            lambda **kwargs: [
                RuntimeProviderConfig(
                    provider=ProviderType.OLLAMA,
                    available=True,
                    default_model="ollama-local",
                ),
                RuntimeProviderConfig(
                    provider=ProviderType.NVIDIA_NIM,
                    available=True,
                    default_model="nim-local",
                ),
                RuntimeProviderConfig(
                    provider=ProviderType.OPENROUTER,
                    available=True,
                    default_model="openrouter-model",
                ),
            ],
        )
        monkeypatch.setattr(
            "dharma_swarm.ginko_agents.create_runtime_provider",
            lambda config: _FakeProvider(
                config.provider.value,
                fail=config.provider == ProviderType.OLLAMA,
            ),
        )

        result = await _call_openrouter("moonshotai/kimi-k2.5", [{"role": "user", "content": "hi"}])

        assert result["error"] is False
        assert result["content"] == "nvidia_nim ok"
        assert calls == [
            ("ollama", "ollama-local"),
            ("nvidia_nim", "nim-local"),
        ]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


class TestUtility:
    def test_utc_now_has_tz(self):
        now = _utc_now()
        assert now.tzinfo is not None
