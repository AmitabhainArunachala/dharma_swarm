"""Tests for jk_credibility_seed.py — Ruthless Critique operational intelligence."""

from __future__ import annotations

from dharma_swarm.jk_credibility_seed import (
    ANTI_PATTERNS,
    COMPETITORS,
    CREDIBILITY_GAPS,
    Competitor,
    CredibilityGap,
    PRIORITY_QUEUE,
    PriorityAction,
)


# ---------------------------------------------------------------------------
# CredibilityGap
# ---------------------------------------------------------------------------


class TestCredibilityGap:
    def test_frozen(self):
        g = CredibilityGap(
            id="TEST-001",
            severity="critical",
            description="test",
            evidence="test",
            resolution="test",
            phase=0,
            owner_team="jk-truth",
        )
        try:
            g.id = "changed"  # type: ignore
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_construction(self):
        g = CredibilityGap(
            id="TEST-001",
            severity="high",
            description="desc",
            evidence="ev",
            resolution="res",
            phase=2,
            owner_team="jk-critic",
        )
        assert g.severity == "high"
        assert g.phase == 2
        assert g.owner_team == "jk-critic"


class TestCredibilityGaps:
    def test_count(self):
        assert len(CREDIBILITY_GAPS) == 14

    def test_ids_unique(self):
        ids = [g.id for g in CREDIBILITY_GAPS]
        assert len(ids) == len(set(ids))

    def test_ids_sequential(self):
        for i, gap in enumerate(CREDIBILITY_GAPS):
            assert gap.id == f"GAP-{i+1:03d}"

    def test_severity_valid(self):
        valid = {"critical", "high", "medium", "low"}
        for g in CREDIBILITY_GAPS:
            assert g.severity in valid, f"{g.id} has invalid severity: {g.severity}"

    def test_first_three_critical(self):
        """First 3 gaps should be critical."""
        for g in CREDIBILITY_GAPS[:3]:
            assert g.severity == "critical", f"{g.id} should be critical"

    def test_all_have_owner_team(self):
        for g in CREDIBILITY_GAPS:
            assert g.owner_team.startswith("jk-"), f"{g.id} bad owner: {g.owner_team}"

    def test_phase_values(self):
        for g in CREDIBILITY_GAPS:
            assert 0 <= g.phase <= 5, f"{g.id} phase {g.phase} out of range"

    def test_descriptions_nonempty(self):
        for g in CREDIBILITY_GAPS:
            assert len(g.description) > 10, f"{g.id} description too short"


# ---------------------------------------------------------------------------
# Competitor
# ---------------------------------------------------------------------------


class TestCompetitor:
    def test_frozen(self):
        c = Competitor(
            name="Test",
            what_they_do="test",
            funding="$0",
            our_advantage="a",
            our_disadvantage="d",
            threat_level="background",
        )
        try:
            c.name = "changed"  # type: ignore
            assert False
        except AttributeError:
            pass


class TestCompetitors:
    def test_count(self):
        assert len(COMPETITORS) >= 7

    def test_names_unique(self):
        names = [c.name for c in COMPETITORS]
        assert len(names) == len(set(names))

    def test_threat_levels_valid(self):
        valid = {"direct", "adjacent", "background"}
        for c in COMPETITORS:
            assert c.threat_level in valid, f"{c.name} invalid: {c.threat_level}"

    def test_known_competitors(self):
        names = {c.name for c in COMPETITORS}
        assert "Sylvera" in names
        assert "BeZero Carbon" in names
        assert "Gold Standard SDG Impact Tool" in names


# ---------------------------------------------------------------------------
# Anti-Patterns
# ---------------------------------------------------------------------------


class TestAntiPatterns:
    def test_count(self):
        assert len(ANTI_PATTERNS) >= 10

    def test_all_nonempty(self):
        for ap in ANTI_PATTERNS:
            assert len(ap) > 10

    def test_contain_negation(self):
        for ap in ANTI_PATTERNS:
            assert "NOT" in ap or "not" in ap, f"Anti-pattern doesn't say NOT: {ap[:30]}"


# ---------------------------------------------------------------------------
# PriorityAction
# ---------------------------------------------------------------------------


class TestPriorityAction:
    def test_frozen(self):
        a = PriorityAction(
            rank=1, action="test", gate="SATYA", phase=0, team="jk-truth",
        )
        try:
            a.rank = 2  # type: ignore
            assert False
        except AttributeError:
            pass

    def test_optional_fields(self):
        a = PriorityAction(
            rank=1, action="test", gate="SATYA", phase=0, team="jk-truth",
        )
        assert a.deadline is None
        assert a.blocked_by is None


class TestPriorityQueue:
    def test_count(self):
        assert len(PRIORITY_QUEUE) >= 16

    def test_ranks_sequential(self):
        for i, action in enumerate(PRIORITY_QUEUE):
            assert action.rank == i + 1

    def test_ranks_unique(self):
        ranks = [a.rank for a in PRIORITY_QUEUE]
        assert len(ranks) == len(set(ranks))

    def test_all_have_gates(self):
        valid_gates = {"SATYA", "DHARMA", "SWARAJ", "AHIMSA", "TAPAS", "SHAKTI", "MOKSHA"}
        for a in PRIORITY_QUEUE:
            assert a.gate in valid_gates, f"Rank {a.rank} invalid gate: {a.gate}"

    def test_phase_0_first(self):
        """Phase 0 actions should come before phase 3+ actions."""
        phase_0 = [a for a in PRIORITY_QUEUE if a.phase == 0]
        phase_3_plus = [a for a in PRIORITY_QUEUE if a.phase >= 3]
        if phase_0 and phase_3_plus:
            assert max(a.rank for a in phase_0) < min(a.rank for a in phase_3_plus)
