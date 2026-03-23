"""Tests for jk_subteams.py — JK sub-agent team definitions."""

from __future__ import annotations

from dharma_swarm.jk_subteams import (
    ALL_TEAMS,
    CRITIC_TEAM,
    FIELD_TEAM,
    MARKET_TEAM,
    PUBLISH_TEAM,
    STANDARDS_TEAM,
    TEAM_BY_NAME,
    TRUTH_TEAM,
    TeamSpec,
    team_prompt,
    teams_for_layer,
)


# ---------------------------------------------------------------------------
# TeamSpec
# ---------------------------------------------------------------------------


class TestTeamSpec:
    def test_frozen(self):
        """TeamSpec is frozen dataclass."""
        t = TeamSpec(
            name="test",
            mission="test mission",
            gate="SATYA",
            credibility_layer=0,
            artifacts=("a.md",),
            lead_model_hint="codex",
            system_prompt_seed="test seed",
        )
        assert t.name == "test"
        # Frozen: cannot modify
        try:
            t.name = "changed"  # type: ignore
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_default_stigmergy_channel(self):
        t = TeamSpec(
            name="test",
            mission="m",
            gate="G",
            credibility_layer=0,
            artifacts=(),
            lead_model_hint="x",
            system_prompt_seed="s",
        )
        assert t.stigmergy_channel == "strategy"

    def test_custom_stigmergy_channel(self):
        t = TeamSpec(
            name="test",
            mission="m",
            gate="G",
            credibility_layer=0,
            artifacts=(),
            lead_model_hint="x",
            system_prompt_seed="s",
            stigmergy_channel="governance",
        )
        assert t.stigmergy_channel == "governance"


# ---------------------------------------------------------------------------
# Team registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_teams_count(self):
        assert len(ALL_TEAMS) == 6

    def test_team_names_unique(self):
        names = [t.name for t in ALL_TEAMS]
        assert len(names) == len(set(names))

    def test_team_by_name_complete(self):
        assert len(TEAM_BY_NAME) == 6
        for t in ALL_TEAMS:
            assert t.name in TEAM_BY_NAME
            assert TEAM_BY_NAME[t.name] is t

    def test_known_teams_exist(self):
        assert TRUTH_TEAM.name == "jk-truth"
        assert STANDARDS_TEAM.name == "jk-standards"
        assert MARKET_TEAM.name == "jk-market"
        assert PUBLISH_TEAM.name == "jk-publish"
        assert FIELD_TEAM.name == "jk-field"
        assert CRITIC_TEAM.name == "jk-critic"


# ---------------------------------------------------------------------------
# Team properties
# ---------------------------------------------------------------------------


class TestTeamProperties:
    def test_all_have_gates(self):
        for t in ALL_TEAMS:
            assert t.gate, f"{t.name} missing gate"

    def test_all_have_missions(self):
        for t in ALL_TEAMS:
            assert len(t.mission) > 20, f"{t.name} mission too short"

    def test_all_have_artifacts(self):
        for t in ALL_TEAMS:
            assert len(t.artifacts) >= 1, f"{t.name} missing artifacts"

    def test_all_have_system_prompt(self):
        for t in ALL_TEAMS:
            assert len(t.system_prompt_seed) > 20, f"{t.name} prompt too short"

    def test_gates_are_telos(self):
        valid_gates = {"SATYA", "DHARMA", "SWARAJ", "AHIMSA", "TAPAS", "SHAKTI", "MOKSHA"}
        for t in ALL_TEAMS:
            assert t.gate in valid_gates, f"{t.name} has invalid gate: {t.gate}"

    def test_credibility_layers(self):
        layers = {t.credibility_layer for t in ALL_TEAMS}
        # At least 3 distinct layers
        assert len(layers) >= 3

    def test_truth_team_layer_zero(self):
        assert TRUTH_TEAM.credibility_layer == 0


# ---------------------------------------------------------------------------
# teams_for_layer
# ---------------------------------------------------------------------------


class TestTeamsForLayer:
    def test_layer_0(self):
        result = teams_for_layer(0)
        assert len(result) >= 1
        assert TRUTH_TEAM in result

    def test_layer_nonexistent(self):
        result = teams_for_layer(99)
        assert result == []

    def test_layer_3_has_multiple(self):
        result = teams_for_layer(3)
        # Standards and Critic are both layer 3
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# team_prompt
# ---------------------------------------------------------------------------


class TestTeamPrompt:
    def test_contains_team_name(self):
        prompt = team_prompt(TRUTH_TEAM)
        assert "jk-truth" in prompt

    def test_contains_mission(self):
        prompt = team_prompt(TRUTH_TEAM)
        assert "Reconcile contradictions" in prompt

    def test_contains_gate(self):
        prompt = team_prompt(TRUTH_TEAM)
        assert "SATYA" in prompt

    def test_contains_artifacts(self):
        prompt = team_prompt(TRUTH_TEAM)
        assert "truth_ledger" in prompt

    def test_contains_system_prompt_seed(self):
        prompt = team_prompt(TRUTH_TEAM)
        assert "TRUTH team" in prompt

    def test_with_context(self):
        prompt = team_prompt(TRUTH_TEAM, context="Working on audit")
        assert "Working on audit" in prompt
        assert "Context" in prompt

    def test_without_context(self):
        prompt = team_prompt(TRUTH_TEAM, context="")
        assert "Context" not in prompt
