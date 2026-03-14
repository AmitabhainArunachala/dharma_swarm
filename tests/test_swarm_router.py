"""Tests for dharma_swarm.swarm_router."""

from __future__ import annotations

import pytest

from dharma_swarm.decision_router import CollaborationMode
from dharma_swarm.models import ProviderType
from dharma_swarm.provider_policy import ProviderRouteRequest
from dharma_swarm.swarm_router import (
    BlackboardContract,
    RoleRoutePlan,
    SwarmExecutionContract,
    SwarmExecutionPlan,
    SwarmRole,
    SwarmRouter,
    _tupleify,
)


# ---------------------------------------------------------------------------
# _tupleify helper
# ---------------------------------------------------------------------------

class TestTupleify:
    def test_none_returns_empty(self) -> None:
        assert _tupleify(None) == ()

    def test_string_returns_single_item_tuple(self) -> None:
        assert _tupleify("hello") == ("hello",)

    def test_empty_string_returns_empty(self) -> None:
        assert _tupleify("") == ()

    def test_list_of_strings(self) -> None:
        result = _tupleify(["a", "b", "c"])
        assert result == ("a", "b", "c")

    def test_filters_empty_strings(self) -> None:
        result = _tupleify(["a", "", "  ", "b"])
        assert result == ("a", "b")

    def test_integer_input(self) -> None:
        result = _tupleify(42)
        assert result == ("42",)


# ---------------------------------------------------------------------------
# SwarmRouter — basic construction
# ---------------------------------------------------------------------------

class TestSwarmRouterConstruction:
    def test_default_construction(self) -> None:
        router = SwarmRouter()
        assert router.provider_policy is not None
        assert router.decision_router is not None

    def test_plan_returns_execution_plan(self) -> None:
        router = SwarmRouter()
        req = ProviderRouteRequest(
            action_name="write unit tests",
            risk_score=0.1,
            uncertainty=0.1,
            novelty=0.1,
            urgency=0.5,
            expected_impact=0.4,
        )
        plan = router.plan(req)
        assert isinstance(plan, SwarmExecutionPlan)


# ---------------------------------------------------------------------------
# allocate_roles
# ---------------------------------------------------------------------------

class TestAllocateRoles:
    def _req(self, action: str, **kwargs) -> ProviderRouteRequest:
        defaults = dict(risk_score=0.1, uncertainty=0.1, novelty=0.1, urgency=0.4, expected_impact=0.3)
        defaults.update(kwargs)
        return ProviderRouteRequest(action_name=action, **defaults)

    def test_code_action_assigns_coder(self) -> None:
        router = SwarmRouter()
        roles = router.allocate_roles(self._req("fix bug in providers"))
        assert SwarmRole.CODER in roles

    def test_research_action_assigns_researcher(self) -> None:
        router = SwarmRouter()
        # High uncertainty triggers multi-agent, broad domain adds RESEARCHER
        roles = router.allocate_roles(
            self._req("research and analyze routing patterns", uncertainty=0.6, novelty=0.5)
        )
        assert SwarmRole.RESEARCHER in roles

    def test_roles_tuple_has_no_duplicates(self) -> None:
        router = SwarmRouter()
        roles = router.allocate_roles(self._req("implement and test code feature", uncertainty=0.5))
        assert len(roles) == len(set(roles))

    def test_high_risk_adds_critic(self) -> None:
        router = SwarmRouter()
        roles = router.allocate_roles(
            self._req("deploy to production", risk_score=0.8, uncertainty=0.7)
        )
        assert SwarmRole.CRITIC in roles

    def test_simple_low_risk_single_role(self) -> None:
        router = SwarmRouter()
        roles = router.allocate_roles(self._req("list status"))
        # Low risk, no code/research hints → single PLANNER (or CRITIC for review)
        assert len(roles) >= 1


# ---------------------------------------------------------------------------
# build_blackboard
# ---------------------------------------------------------------------------

class TestBuildBlackboard:
    def test_blackboard_task_brief_from_action(self) -> None:
        router = SwarmRouter()
        req = ProviderRouteRequest(
            action_name="refactor providers module",
            risk_score=0.1, uncertainty=0.1, novelty=0.1,
            urgency=0.5, expected_impact=0.5,
        )
        bb = router.build_blackboard(req, roles=(SwarmRole.CODER,))
        assert "refactor providers module" in bb.task_brief

    def test_blackboard_has_handoff_order(self) -> None:
        router = SwarmRouter()
        req = ProviderRouteRequest(
            action_name="code review and fix",
            risk_score=0.1, uncertainty=0.1, novelty=0.1,
            urgency=0.5, expected_impact=0.5,
        )
        roles = (SwarmRole.PLANNER, SwarmRole.CODER, SwarmRole.CRITIC)
        bb = router.build_blackboard(req, roles=roles)
        assert "planner" in bb.handoff_order
        assert "coder" in bb.handoff_order
        assert "critic" in bb.handoff_order

    def test_blackboard_uses_context_constraints(self) -> None:
        router = SwarmRouter()
        req = ProviderRouteRequest(
            action_name="update config",
            risk_score=0.1, uncertainty=0.1, novelty=0.1,
            urgency=0.5, expected_impact=0.5,
            context={"constraints": ["no breaking changes", "preserve API"]},
        )
        bb = router.build_blackboard(req, roles=(SwarmRole.PLANNER,))
        assert "no breaking changes" in bb.constraints

    def test_blackboard_default_constraints_when_none(self) -> None:
        router = SwarmRouter()
        req = ProviderRouteRequest(
            action_name="test action",
            risk_score=0.0, uncertainty=0.0, novelty=0.0,
            urgency=0.3, expected_impact=0.3,
        )
        bb = router.build_blackboard(req, roles=(SwarmRole.PLANNER,))
        # Should fall back to default constraint tuple
        assert len(bb.constraints) >= 1


# ---------------------------------------------------------------------------
# build_execution_contract
# ---------------------------------------------------------------------------

class TestBuildExecutionContract:
    def test_contract_has_required_fields(self) -> None:
        router = SwarmRouter()
        contract = router.build_execution_contract()
        assert isinstance(contract, SwarmExecutionContract)
        assert "collaboration_mode" in contract.required_context_keys
        assert "assigned_role" in contract.required_context_keys

    def test_contract_scheduling_mode(self) -> None:
        contract = SwarmRouter().build_execution_contract()
        assert "blackboard" in contract.scheduling_mode


# ---------------------------------------------------------------------------
# plan — integration
# ---------------------------------------------------------------------------

class TestSwarmRouterPlan:
    def _req(self, action: str, **kwargs) -> ProviderRouteRequest:
        defaults = dict(risk_score=0.2, uncertainty=0.2, novelty=0.1, urgency=0.4, expected_impact=0.4)
        defaults.update(kwargs)
        return ProviderRouteRequest(action_name=action, **defaults)

    def test_plan_roles_match_allocated_roles(self) -> None:
        router = SwarmRouter()
        req = self._req("implement coder feature")
        plan = router.plan(req)
        plan_role_names = {rp.role for rp in plan.role_routes}
        assert plan_role_names == set(plan.roles)

    def test_plan_role_routes_all_have_provider(self) -> None:
        router = SwarmRouter()
        req = self._req("debug test failure")
        plan = router.plan(req)
        for rp in plan.role_routes:
            assert rp.route is not None

    def test_plan_api_notes_populated(self) -> None:
        router = SwarmRouter()
        plan = router.plan(self._req("do something"))
        assert len(plan.api_notes) > 0

    def test_coder_role_request_has_complexity_tier(self) -> None:
        router = SwarmRouter()
        req = self._req("fix and implement code module")
        plan = router.plan(req)
        coder_routes = [rp for rp in plan.role_routes if rp.role == SwarmRole.CODER]
        for rp in coder_routes:
            assert rp.request.context.get("complexity_tier") == "COMPLEX"

    def test_researcher_role_requires_frontier(self) -> None:
        router = SwarmRouter()
        req = self._req("research and analyze system behavior", uncertainty=0.6, novelty=0.6)
        plan = router.plan(req)
        researcher_routes = [rp for rp in plan.role_routes if rp.role == SwarmRole.RESEARCHER]
        for rp in researcher_routes:
            assert rp.request.requires_frontier_precision is True

    def test_dependency_roles_for_coder_includes_planner(self) -> None:
        router = SwarmRouter()
        req = self._req("plan and implement feature", uncertainty=0.5, expected_impact=0.7)
        plan = router.plan(req)
        coder_routes = [rp for rp in plan.role_routes if rp.role == SwarmRole.CODER]
        for rp in coder_routes:
            if SwarmRole.PLANNER in plan.roles:
                assert SwarmRole.PLANNER in rp.dependency_roles

    def test_planner_has_no_dependencies(self) -> None:
        router = SwarmRouter()
        req = self._req("plan multi-step operation", uncertainty=0.5)
        plan = router.plan(req)
        planner_routes = [rp for rp in plan.role_routes if rp.role == SwarmRole.PLANNER]
        for rp in planner_routes:
            assert rp.dependency_roles == ()

    def test_role_request_action_name_includes_role(self) -> None:
        router = SwarmRouter()
        req = self._req("debug code issue")
        plan = router.plan(req)
        for rp in plan.role_routes:
            assert rp.role.value in rp.request.action_name
