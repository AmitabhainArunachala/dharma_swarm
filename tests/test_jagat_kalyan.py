"""Tests for jagat_kalyan.py — the organism's outward-facing intelligence."""

from __future__ import annotations

import json

import pytest

from dharma_swarm.jagat_kalyan import (
    CAPABILITIES,
    JagatKalyanEngine,
    PERPETUAL_QUESTION,
    ServiceProposal,
    WORLD_DOMAINS,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_capabilities_is_nonempty_string(self):
        assert isinstance(CAPABILITIES, str)
        assert len(CAPABILITIES) > 100

    def test_world_domains_has_entries(self):
        assert len(WORLD_DOMAINS) >= 5
        for d in WORLD_DOMAINS:
            assert "domain" in d
            assert "why" in d
            assert "what_we_can_do" in d

    def test_perpetual_question_is_nonempty(self):
        assert isinstance(PERPETUAL_QUESTION, str)
        assert "RIGHT NOW" in PERPETUAL_QUESTION

    def test_world_domains_have_unique_names(self):
        names = [d["domain"] for d in WORLD_DOMAINS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# ServiceProposal
# ---------------------------------------------------------------------------


class TestServiceProposal:
    def test_creation(self):
        p = ServiceProposal(
            domain="ai_safety",
            action="Publish gate framework",
            who_benefits="AI researchers",
            what_exists="11 telos gates",
            what_remains="Docs and packaging",
            time_estimate="3 days",
            cost="$0",
            moksha_check="Liberation — open-sourcing reduces binding",
        )
        assert p.domain == "ai_safety"
        assert p.timestamp > 0

    def test_default_timestamp(self):
        p = ServiceProposal(
            domain="d", action="a", who_benefits="w",
            what_exists="e", what_remains="r",
            time_estimate="t", cost="c", moksha_check="m",
        )
        assert p.timestamp > 1_000_000_000  # sanity check — post-epoch


# ---------------------------------------------------------------------------
# JagatKalyanEngine
# ---------------------------------------------------------------------------


def _sample_proposal(**kw) -> ServiceProposal:
    defaults = dict(
        domain="ai_safety",
        action="publish gate framework",
        who_benefits="AI researchers",
        what_exists="11 telos gates",
        what_remains="docs",
        time_estimate="3 days",
        cost="$0",
        moksha_check="liberation",
    )
    defaults.update(kw)
    return ServiceProposal(**defaults)


class TestJagatKalyanEngine:
    def test_init_creates_dir(self, tmp_path):
        state = tmp_path / "jk_state"
        jk = JagatKalyanEngine(state_dir=state)
        assert state.exists()

    def test_capabilities_property(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        assert jk.capabilities == CAPABILITIES

    def test_world_domains_property(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        assert jk.world_domains == WORLD_DOMAINS

    def test_perpetual_question_property(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        assert jk.perpetual_question == PERPETUAL_QUESTION

    def test_add_proposal(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        p = _sample_proposal()
        jk.add_proposal(p)
        assert len(jk.recent_proposals()) == 1

    def test_recent_proposals_limit(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        for i in range(15):
            jk.add_proposal(_sample_proposal(action=f"action-{i}"))
        recent = jk.recent_proposals(n=5)
        assert len(recent) == 5
        assert recent[-1].action == "action-14"

    def test_recent_proposals_empty(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        assert jk.recent_proposals() == []

    def test_persistence_roundtrip(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        jk.add_proposal(_sample_proposal(domain="mental_health", action="translate"))
        jk.add_proposal(_sample_proposal(domain="ai_access", action="document"))

        # Reload from same dir
        jk2 = JagatKalyanEngine(state_dir=tmp_path)
        proposals = jk2.recent_proposals()
        assert len(proposals) == 2
        assert proposals[0].domain == "mental_health"
        assert proposals[1].domain == "ai_access"

    def test_persistence_file_format(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        jk.add_proposal(_sample_proposal())

        path = tmp_path / "jagat_kalyan_proposals.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["domain"] == "ai_safety"
        assert "timestamp" in data

    def test_load_empty_dir(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        assert jk.recent_proposals() == []

    def test_load_corrupted_jsonl(self, tmp_path):
        path = tmp_path / "jagat_kalyan_proposals.jsonl"
        path.write_text("not valid json\n{also broken\n", encoding="utf-8")
        jk = JagatKalyanEngine(state_dir=tmp_path)
        assert jk.recent_proposals() == []


# ---------------------------------------------------------------------------
# Council prompt generation
# ---------------------------------------------------------------------------


class TestBuildCouncilPrompt:
    def test_prompt_contains_key_sections(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        prompt = jk.build_council_prompt()
        assert "CAPABILITIES" in prompt
        assert "WORLD DOMAINS" in prompt
        assert "YOUR TASK" in prompt
        assert "THIS WEEK" in prompt

    def test_prompt_with_external_context(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        prompt = jk.build_council_prompt("Earthquake in Bali region")
        assert "Earthquake in Bali region" in prompt
        assert "EXTERNAL SIGNAL" in prompt

    def test_prompt_without_external_context(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        prompt = jk.build_council_prompt()
        assert "EXTERNAL SIGNAL" not in prompt


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_empty(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        s = jk.status()
        assert s["total_proposals"] == 0
        assert s["domains_covered"] == []
        assert s["latest"] is None

    def test_status_with_proposals(self, tmp_path):
        jk = JagatKalyanEngine(state_dir=tmp_path)
        jk.add_proposal(_sample_proposal(domain="ai_safety", action="first"))
        jk.add_proposal(_sample_proposal(domain="education", action="second"))

        s = jk.status()
        assert s["total_proposals"] == 2
        assert set(s["domains_covered"]) == {"ai_safety", "education"}
        assert s["latest"] == "second"
