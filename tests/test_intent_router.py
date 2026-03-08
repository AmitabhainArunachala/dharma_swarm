"""Tests for Intent Router — task decomposition and skill matching."""

from __future__ import annotations

import pytest

from dharma_swarm.intent_router import (
    IntentRouter,
    TaskIntent,
    DecomposedTask,
)


class TestIntentAnalysis:
    """Tests for single-task intent analysis."""

    def test_analyze_fix_bug(self):
        router = IntentRouter()
        intent = router.analyze("fix the broken test in metrics.py")
        assert intent.primary_skill == "surgeon"
        assert intent.confidence > 0
        assert intent.risk_level in ("low", "medium")

    def test_analyze_scan_ecosystem(self):
        router = IntentRouter()
        intent = router.analyze("scan the ecosystem and map all paths")
        assert intent.primary_skill == "cartographer"

    def test_analyze_research(self):
        router = IntentRouter()
        intent = router.analyze("analyze the experimental data for the rv paper")
        assert intent.primary_skill == "researcher"

    def test_analyze_build_feature(self):
        router = IntentRouter()
        intent = router.analyze("implement a new caching feature")
        assert intent.primary_skill == "builder"

    def test_analyze_test_everything(self):
        router = IntentRouter()
        intent = router.analyze("validate all tests pass and check quality")
        assert intent.primary_skill == "validator"

    def test_analyze_unknown_task(self):
        router = IntentRouter()
        intent = router.analyze("quantum entanglement simulation")
        # Should still return something, just low confidence
        assert isinstance(intent, TaskIntent)

    def test_confidence_scales(self):
        router = IntentRouter()
        # Multiple matching keywords → higher confidence
        specific = router.analyze("fix the bug error in the broken test")
        vague = router.analyze("do something nice")
        assert specific.confidence > vague.confidence


class TestComplexityEstimation:
    """Tests for complexity detection."""

    def test_trivial_task(self):
        router = IntentRouter()
        intent = router.analyze("show me the current status")
        assert intent.complexity == "trivial"

    def test_simple_task(self):
        router = IntentRouter()
        intent = router.analyze("fix typo in the readme")
        assert intent.complexity == "simple"

    def test_moderate_task(self):
        router = IntentRouter()
        intent = router.analyze("add a new feature to the CLI")
        assert intent.complexity == "moderate"

    def test_complex_task(self):
        router = IntentRouter()
        intent = router.analyze("refactor the entire pipeline to use parallel execution")
        assert intent.complexity == "complex"

    def test_epic_task(self):
        router = IntentRouter()
        intent = router.analyze("full rewrite of the entire system with migration")
        assert intent.complexity == "epic"


class TestRiskAssessment:
    """Tests for risk level detection."""

    def test_safe_action(self):
        router = IntentRouter()
        intent = router.analyze("read the config file and show status")
        assert intent.risk_level == "low"

    def test_medium_risk(self):
        router = IntentRouter()
        intent = router.analyze("modify the configuration settings")
        assert intent.risk_level == "medium"

    def test_high_risk(self):
        router = IntentRouter()
        intent = router.analyze("deploy the changes to staging")
        assert intent.risk_level == "high"

    def test_critical_risk(self):
        router = IntentRouter()
        intent = router.analyze("delete all credentials and reset everything")
        assert intent.risk_level == "critical"


class TestDecomposition:
    """Tests for compound task decomposition."""

    def test_single_task_no_decomposition(self):
        router = IntentRouter()
        result = router.decompose("fix the bug")
        assert len(result.sub_tasks) == 1
        assert result.has_parallel_work is False

    def test_compound_and_task(self):
        router = IntentRouter()
        result = router.decompose("fix the bug and then run the tests")
        assert len(result.sub_tasks) == 2

    def test_compound_comma_task(self):
        router = IntentRouter()
        result = router.decompose(
            "scan the ecosystem and fix broken tests"
        )
        assert len(result.sub_tasks) == 2

    def test_parallel_detection(self):
        router = IntentRouter()
        result = router.decompose(
            "scan the ecosystem and fix the broken test"
        )
        # scan → cartographer, fix → surgeon = different skills = parallel
        if len(result.sub_tasks) == 2:
            skills = {st.primary_skill for st in result.sub_tasks}
            if len(skills) > 1:
                assert result.has_parallel_work is True

    def test_agent_count_recommendation(self):
        router = IntentRouter()
        result = router.decompose(
            "full rewrite of the entire system with migration"
        )
        assert result.total_agents >= 1


class TestRouting:
    """Tests for the route() convenience method."""

    def test_route_returns_skill_and_intent(self):
        router = IntentRouter()
        skill_name, intent = router.route("fix the broken metrics test")
        assert skill_name == "surgeon"
        assert isinstance(intent, TaskIntent)

    def test_route_unknown_defaults_to_general(self):
        router = IntentRouter()
        skill_name, _ = router.route("do something abstract")
        assert skill_name == "general"

    def test_route_with_registry(self):
        from dharma_swarm.skills import SkillRegistry
        from pathlib import Path
        skills_dir = Path(__file__).parent.parent / "dharma_swarm" / "skills"
        registry = SkillRegistry(skill_dirs=[skills_dir])
        router = IntentRouter(registry=registry)
        skill_name, intent = router.route("explore the ecosystem map")
        # Registry match should boost confidence
        assert intent.confidence > 0
