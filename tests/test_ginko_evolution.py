"""Tests for ginko_evolution.py — Darwin Engine prompt evolution for Ginko fleet."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.ginko_evolution import (
    FLEET_AGENTS,
    MUTATION_MODEL,
    PromptTournament,
    PromptVariant,
    _append_jsonl,
    _compute_fitness_from_log,
    _read_json,
    _read_jsonl,
    _sha256,
    format_tournament_report,
)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestSha256:
    def test_returns_12_chars(self):
        result = _sha256("hello")
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert _sha256("test") == _sha256("test")

    def test_different_inputs(self):
        assert _sha256("a") != _sha256("b")


class TestReadJsonl:
    def test_reads_entries(self, tmp_path):
        p = tmp_path / "data.jsonl"
        p.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")
        entries = _read_jsonl(p)
        assert len(entries) == 2
        assert entries[0]["a"] == 1

    def test_skips_blank_lines(self, tmp_path):
        p = tmp_path / "data.jsonl"
        p.write_text('{"a": 1}\n\n{"b": 2}\n\n', encoding="utf-8")
        assert len(_read_jsonl(p)) == 2

    def test_skips_invalid_json(self, tmp_path):
        p = tmp_path / "data.jsonl"
        p.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
        entries = _read_jsonl(p)
        assert len(entries) == 2

    def test_missing_file(self, tmp_path):
        assert _read_jsonl(tmp_path / "nope.jsonl") == []


class TestAppendJsonl:
    def test_appends(self, tmp_path):
        p = tmp_path / "out.jsonl"
        _append_jsonl(p, {"x": 1})
        _append_jsonl(p, {"y": 2})
        entries = _read_jsonl(p)
        assert len(entries) == 2

    def test_creates_parent(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "out.jsonl"
        _append_jsonl(p, {"z": 3})
        assert p.exists()


class TestReadJson:
    def test_reads_file(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        data = _read_json(p)
        assert data is not None
        assert data["key"] == "value"

    def test_missing_file(self, tmp_path):
        assert _read_json(tmp_path / "nope.json") is None

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        assert _read_json(p) is None


# ---------------------------------------------------------------------------
# PromptVariant
# ---------------------------------------------------------------------------


class TestPromptVariant:
    def test_construction(self):
        v = PromptVariant(
            text="You are a trader.",
            generation=0,
            parent_hash=None,
            fitness_score=0.5,
        )
        assert v.text == "You are a trader."
        assert v.generation == 0
        assert v.active is False

    def test_to_dict(self):
        v = PromptVariant("t", 1, "abc123", 0.7, created_at="2024-01-01", active=True)
        d = v.to_dict()
        assert d["generation"] == 1
        assert d["active"] is True

    def test_from_dict(self):
        d = {
            "text": "prompt",
            "generation": 2,
            "parent_hash": "xyz",
            "fitness_score": 0.8,
            "created_at": "2024-01-01",
            "active": False,
            "extra_field": "ignored",
        }
        v = PromptVariant.from_dict(d)
        assert v.generation == 2
        assert v.fitness_score == 0.8

    def test_from_dict_minimal(self):
        d = {"text": "x", "generation": 0, "parent_hash": None, "fitness_score": 0.0}
        v = PromptVariant.from_dict(d)
        assert v.text == "x"


# ---------------------------------------------------------------------------
# Fitness computation
# ---------------------------------------------------------------------------


class TestComputeFitnessFromLog:
    def _setup_agent(self, tmp_path, name, task_entries=None, identity=None):
        """Create agent dir with optional task_log.jsonl and identity.json."""
        agent_dir = tmp_path / name
        agent_dir.mkdir(parents=True, exist_ok=True)
        if task_entries is not None:
            log_path = agent_dir / "task_log.jsonl"
            with log_path.open("w", encoding="utf-8") as f:
                for entry in task_entries:
                    f.write(json.dumps(entry) + "\n")
        if identity is not None:
            (agent_dir / "identity.json").write_text(
                json.dumps(identity), encoding="utf-8"
            )

    def test_from_task_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)
        self._setup_agent(tmp_path, "kimi", task_entries=[
            {"success": True, "latency_ms": 2000.0, "quality": 0.8},
            {"success": True, "latency_ms": 3000.0, "quality": 0.7},
            {"success": False, "latency_ms": 10000.0, "quality": 0.3},
        ])
        result = _compute_fitness_from_log("kimi")
        assert result["name"] == "kimi"
        assert result["total_calls"] == 3
        assert abs(result["success_rate"] - 2 / 3) < 0.01
        assert result["composite_fitness"] > 0

    def test_from_identity_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)
        self._setup_agent(tmp_path, "scout", identity={
            "total_calls": 10,
            "tasks_completed": 8,
            "avg_quality": 0.75,
            "fitness": 0.65,
        })
        result = _compute_fitness_from_log("scout")
        assert result["total_calls"] == 10
        assert result["success_rate"] == 0.8
        assert result["composite_fitness"] == 0.65

    def test_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)
        (tmp_path / "ghost").mkdir()
        result = _compute_fitness_from_log("ghost")
        assert result["total_calls"] == 0
        assert result["composite_fitness"] == 0.0

    def test_speed_score_fast(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)
        # All calls under 5s -> speed score = 1.0
        self._setup_agent(tmp_path, "fast", task_entries=[
            {"success": True, "latency_ms": 1000.0, "quality": 0.9},
            {"success": True, "latency_ms": 2000.0, "quality": 0.9},
        ])
        result = _compute_fitness_from_log("fast")
        # composite = 1.0*0.4 + 1.0*0.3 + 0.9*0.3 = 0.97
        assert result["composite_fitness"] >= 0.95

    def test_speed_score_slow(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)
        # All calls over 120s -> speed score = 0.0
        self._setup_agent(tmp_path, "slow", task_entries=[
            {"success": True, "latency_ms": 200_000.0, "quality": 0.5},
        ])
        result = _compute_fitness_from_log("slow")
        # composite = 1.0*0.4 + 0.0*0.3 + 0.5*0.3 = 0.55
        assert abs(result["composite_fitness"] - 0.55) < 0.01


# ---------------------------------------------------------------------------
# PromptTournament
# ---------------------------------------------------------------------------


class TestPromptTournament:
    def _setup_fleet(self, tmp_path, agents=None, with_task_logs=True):
        """Create a fleet of agents with identity.json and optional task logs."""
        if agents is None:
            agents = ["alpha", "beta", "gamma", "delta", "epsilon"]
        for i, name in enumerate(agents):
            agent_dir = tmp_path / name
            agent_dir.mkdir(parents=True, exist_ok=True)
            identity = {
                "name": name,
                "system_prompt": f"You are {name}, a financial analyst.",
                "prompt_generation": 0,
                "total_calls": 10 + i * 5,
                "tasks_completed": 8 + i * 3,
            }
            (agent_dir / "identity.json").write_text(
                json.dumps(identity), encoding="utf-8"
            )
            # Create prompt variants dir
            prompt_dir = agent_dir / "prompt_variants"
            prompt_dir.mkdir()
            (prompt_dir / "active.txt").write_text(
                identity["system_prompt"], encoding="utf-8"
            )
            (prompt_dir / "gen_0.txt").write_text(
                identity["system_prompt"], encoding="utf-8"
            )
            if with_task_logs:
                log_path = agent_dir / "task_log.jsonl"
                # Varying fitness: later agents are fitter
                quality = 0.3 + i * 0.15
                entries = [
                    {"success": True, "latency_ms": 3000.0, "quality": quality},
                    {"success": i > 1, "latency_ms": 5000.0, "quality": quality - 0.1},
                ]
                with log_path.open("w", encoding="utf-8") as f:
                    for e in entries:
                        f.write(json.dumps(e) + "\n")

    def test_discover_agents(self, tmp_path):
        self._setup_fleet(tmp_path, ["a", "b", "c"])
        t = PromptTournament(agents_dir=tmp_path)
        agents = t._discover_agents()
        assert set(agents) == {"a", "b", "c"}

    def test_discover_no_agents(self, tmp_path):
        t = PromptTournament(agents_dir=tmp_path / "empty")
        assert t._discover_agents() == []

    def test_load_current_prompt(self, tmp_path):
        self._setup_fleet(tmp_path, ["kimi"])
        t = PromptTournament(agents_dir=tmp_path)
        prompt = t._load_current_prompt("kimi")
        assert "kimi" in prompt

    def test_load_prompt_fallback_to_identity(self, tmp_path):
        agent_dir = tmp_path / "test"
        agent_dir.mkdir()
        (agent_dir / "identity.json").write_text(
            json.dumps({"system_prompt": "fallback prompt"}), encoding="utf-8"
        )
        t = PromptTournament(agents_dir=tmp_path)
        assert t._load_current_prompt("test") == "fallback prompt"

    def test_get_current_generation(self, tmp_path):
        self._setup_fleet(tmp_path, ["kimi"])
        t = PromptTournament(agents_dir=tmp_path)
        assert t._get_current_generation("kimi") == 0

    def test_save_variant(self, tmp_path):
        self._setup_fleet(tmp_path, ["kimi"])
        t = PromptTournament(agents_dir=tmp_path)
        variant = t._save_variant(
            agent_name="kimi",
            new_prompt="Improved prompt for kimi agent.",
            generation=1,
            parent_hash="abc123",
            fitness=0.5,
            reason="test_mutation",
        )
        assert variant.generation == 1
        assert variant.active is True
        # Check files written
        assert (tmp_path / "kimi" / "prompt_variants" / "gen_1.txt").exists()
        assert (tmp_path / "kimi" / "prompt_variants" / "active.txt").read_text() == "Improved prompt for kimi agent."
        # Check evolution log
        evo_log = tmp_path / "kimi" / "prompt_variants" / "evolution_log.jsonl"
        assert evo_log.exists()
        entries = [json.loads(line) for line in evo_log.read_text().strip().split("\n")]
        assert entries[0]["generation"] == 1
        assert entries[0]["reason"] == "test_mutation"

    def test_get_prompt_lineage(self, tmp_path):
        self._setup_fleet(tmp_path, ["kimi"])
        t = PromptTournament(agents_dir=tmp_path)
        # Save a second generation
        t._save_variant("kimi", "Gen 1 prompt", 1, "hash0", 0.6, "test")
        lineage = t.get_prompt_lineage("kimi")
        assert len(lineage) >= 2
        assert lineage[0].generation == 0
        assert lineage[-1].generation == 1

    def test_get_prompt_lineage_empty(self, tmp_path):
        t = PromptTournament(agents_dir=tmp_path)
        assert t.get_prompt_lineage("nonexistent") == []

    def test_tournament_history(self, tmp_path, monkeypatch):
        history_path = tmp_path / "history.jsonl"
        monkeypatch.setattr("dharma_swarm.ginko_evolution.TOURNAMENT_HISTORY_PATH", history_path)
        t = PromptTournament(agents_dir=tmp_path)
        t.save_tournament_result({"tournament_id": "t1", "status": "ok"})
        t.save_tournament_result({"tournament_id": "t2", "status": "ok"})
        history = t.get_tournament_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_mutate_prompt_no_available_providers(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        t = PromptTournament()
        with patch(
            "dharma_swarm.ginko_evolution.complete_via_preferred_runtime_providers",
            new=AsyncMock(side_effect=RuntimeError("No preferred providers available")),
        ):
            result = await t.mutate_prompt("original prompt", {"success_rate": 0.5})
        assert result == "original prompt"  # Safe fallback

    @pytest.mark.asyncio
    async def test_mutate_prompt_uses_runtime_provider_stack(self):
        t = PromptTournament()
        with patch(
            "dharma_swarm.ginko_evolution.complete_via_preferred_runtime_providers",
            new=AsyncMock(
                return_value=(
                    LLMResponse(content="mutated prompt", model="nim-local"),
                    SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
                )
            ),
        ):
            result = await t.mutate_prompt("original prompt", {"success_rate": 0.5})
        assert result == "mutated prompt"

    @pytest.mark.asyncio
    async def test_run_tournament_no_agents(self, tmp_path, monkeypatch):
        history_path = tmp_path / "history.jsonl"
        monkeypatch.setattr("dharma_swarm.ginko_evolution.TOURNAMENT_HISTORY_PATH", history_path)
        t = PromptTournament(agents_dir=tmp_path / "empty")
        result = await t.run_tournament()
        assert result["status"] == "no_agents"
        assert result["rankings"] == []

    @pytest.mark.asyncio
    async def test_run_tournament_with_agents(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)
        history_path = tmp_path / "history.jsonl"
        monkeypatch.setattr("dharma_swarm.ginko_evolution.TOURNAMENT_HISTORY_PATH", history_path)

        self._setup_fleet(tmp_path, ["a", "b", "c", "d", "e"])
        t = PromptTournament(agents_dir=tmp_path)

        # Mock mutation to return a changed prompt
        async def mock_mutate(self_inner, current, scores):
            return current + " [mutated]"

        with patch.object(PromptTournament, "mutate_prompt", mock_mutate):
            result = await t.run_tournament()

        assert result["status"] == "completed"
        assert result["agent_count"] == 5
        assert len(result["winners"]) == 2
        assert len(result["mutated"]) >= 1
        # History should be saved
        assert history_path.exists()

    @pytest.mark.asyncio
    async def test_tournament_few_agents(self, tmp_path, monkeypatch):
        history_path = tmp_path / "history.jsonl"
        monkeypatch.setattr("dharma_swarm.ginko_evolution.TOURNAMENT_HISTORY_PATH", history_path)
        monkeypatch.setattr("dharma_swarm.ginko_evolution.AGENTS_DIR", tmp_path)

        self._setup_fleet(tmp_path, ["a", "b"])
        t = PromptTournament(agents_dir=tmp_path)
        result = await t.run_tournament()
        assert result["status"] == "completed"
        # 2 agents = all winners, no losers
        assert len(result["winners"]) == 2
        assert result["mutated"] == []


# ---------------------------------------------------------------------------
# format_tournament_report
# ---------------------------------------------------------------------------


class TestFormatTournamentReport:
    def _make_result(self):
        return {
            "tournament_id": "test_001",
            "timestamp": "2024-06-15T12:00:00",
            "status": "completed",
            "agent_count": 5,
            "rankings": [
                {"name": "epsilon", "composite_fitness": 0.85, "success_rate": 0.9, "total_calls": 30},
                {"name": "delta", "composite_fitness": 0.75, "success_rate": 0.8, "total_calls": 25},
                {"name": "gamma", "composite_fitness": 0.65, "success_rate": 0.7, "total_calls": 20},
                {"name": "beta", "composite_fitness": 0.50, "success_rate": 0.6, "total_calls": 15},
                {"name": "alpha", "composite_fitness": 0.35, "success_rate": 0.5, "total_calls": 10},
            ],
            "winners": [
                {"name": "epsilon", "fitness": 0.85, "action": "prompt_preserved"},
                {"name": "delta", "fitness": 0.75, "action": "prompt_preserved"},
            ],
            "mutated": [
                {
                    "name": "alpha",
                    "status": "mutated",
                    "old_generation": 0,
                    "new_generation": 1,
                    "fitness_before": 0.35,
                    "prompt_length_before": 200,
                    "prompt_length_after": 250,
                },
            ],
            "unchanged": [
                {"name": "gamma", "fitness": 0.65},
            ],
            "tournament_interval_days": 30,
        }

    def test_contains_header(self):
        report = format_tournament_report(self._make_result())
        assert "GINKO PROMPT EVOLUTION TOURNAMENT" in report

    def test_contains_rankings(self):
        report = format_tournament_report(self._make_result())
        assert "RANKINGS" in report
        assert "epsilon" in report
        assert "0.8500" in report

    def test_contains_winners(self):
        report = format_tournament_report(self._make_result())
        assert "WINNERS" in report
        assert "prompt_preserved" in report

    def test_contains_mutated(self):
        report = format_tournament_report(self._make_result())
        assert "MUTATED" in report
        assert "gen 0 -> 1" in report

    def test_contains_unchanged(self):
        report = format_tournament_report(self._make_result())
        assert "UNCHANGED" in report
        assert "gamma" in report

    def test_empty_result(self):
        report = format_tournament_report({
            "tournament_id": "empty",
            "status": "no_agents",
            "rankings": [],
            "winners": [],
            "mutated": [],
            "unchanged": [],
        })
        assert "no_agents" in report
        assert "(none)" in report

    def test_returns_string(self):
        assert isinstance(format_tournament_report(self._make_result()), str)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_fleet_agents(self):
        assert len(FLEET_AGENTS) >= 6
        assert "kimi" in FLEET_AGENTS

    def test_mutation_model(self):
        assert len(MUTATION_MODEL) > 5
