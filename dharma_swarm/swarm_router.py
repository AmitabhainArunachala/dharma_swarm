"""Deterministic swarm-routing plan on top of provider policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable

from dharma_swarm.decision_router import (
    CollaborationDecision,
    CollaborationMode,
    DecisionInput,
    DecisionRouter,
)
from dharma_swarm.models import ProviderType
from dharma_swarm.provider_policy import (
    ProviderPolicyRouter,
    ProviderRouteDecision,
    ProviderRouteRequest,
)


class SwarmRole(str, Enum):
    PLANNER = "planner"
    CODER = "coder"
    CRITIC = "critic"
    RESEARCHER = "researcher"


def _tupleify(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        value = values.strip()
        return (value,) if value else ()
    if isinstance(values, Iterable):
        items: list[str] = []
        for value in values:
            text = str(value).strip()
            if text:
                items.append(text)
        return tuple(items)
    return (str(values).strip(),)


@dataclass(frozen=True)
class BlackboardContract:
    contract_id: str
    task_brief: str
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    shared_facts: tuple[str, ...]
    open_questions: tuple[str, ...]
    handoff_order: tuple[str, ...]


@dataclass(frozen=True)
class RoleRoutePlan:
    role: SwarmRole
    dependency_roles: tuple[SwarmRole, ...]
    request: ProviderRouteRequest
    route: ProviderRouteDecision


@dataclass(frozen=True)
class SwarmExecutionContract:
    contract_id: str
    required_context_keys: tuple[str, ...]
    blackboard_fields: tuple[str, ...]
    expected_worker_result_fields: tuple[str, ...]
    scheduling_mode: str


@dataclass(frozen=True)
class SwarmExecutionPlan:
    collaboration: CollaborationDecision
    roles: tuple[SwarmRole, ...]
    blackboard: BlackboardContract
    role_routes: tuple[RoleRoutePlan, ...]
    execution_contract: SwarmExecutionContract
    api_notes: tuple[str, ...]


class SwarmRouter:
    """MasRouter-style collaboration and role planner.

    This stays deterministic and provider-policy-backed:
    1. decide whether to fan out
    2. allocate roles
    3. reuse provider policy per role
    """

    def __init__(
        self,
        *,
        provider_policy: ProviderPolicyRouter | None = None,
        decision_router: DecisionRouter | None = None,
    ) -> None:
        self.provider_policy = provider_policy or ProviderPolicyRouter()
        self.decision_router = decision_router or self.provider_policy.decision_router

    def plan(
        self,
        request: ProviderRouteRequest,
        *,
        available_providers: list[ProviderType] | None = None,
    ) -> SwarmExecutionPlan:
        collaboration = self.decision_router.route_collaboration(
            DecisionInput(
                action_name=request.action_name,
                risk_score=request.risk_score,
                uncertainty=request.uncertainty,
                novelty=request.novelty,
                urgency=request.urgency,
                expected_impact=request.expected_impact,
                estimated_latency_ms=request.estimated_latency_ms,
                estimated_tokens=request.estimated_tokens,
                privileged_action=request.privileged_action,
                requires_human_consent=request.requires_human_consent,
                context=request.context,
            )
        )
        roles = self.allocate_roles(request, collaboration=collaboration)
        blackboard = self.build_blackboard(request, roles=roles)
        role_routes = tuple(
            self._plan_role(
                request,
                role=role,
                dependency_roles=self._dependency_roles(role, roles=roles),
                collaboration=collaboration,
                roles=roles,
                blackboard=blackboard,
                available_providers=available_providers,
            )
            for role in roles
        )
        execution_contract = self.build_execution_contract()
        return SwarmExecutionPlan(
            collaboration=collaboration,
            roles=roles,
            blackboard=blackboard,
            role_routes=role_routes,
            execution_contract=execution_contract,
            api_notes=(
                "Seed the blackboard before dispatching role workers.",
                "Dispatch a role only after its dependency_roles have completed and written to the blackboard.",
                "Workers should return role, summary, artifacts, and handoff_notes for downstream aggregation.",
            ),
        )

    def allocate_roles(
        self,
        request: ProviderRouteRequest,
        *,
        collaboration: CollaborationDecision | None = None,
    ) -> tuple[SwarmRole, ...]:
        collaboration = collaboration or self.decision_router.route_collaboration(
            DecisionInput(
                action_name=request.action_name,
                risk_score=request.risk_score,
                uncertainty=request.uncertainty,
                novelty=request.novelty,
                urgency=request.urgency,
                expected_impact=request.expected_impact,
                estimated_latency_ms=request.estimated_latency_ms,
                estimated_tokens=request.estimated_tokens,
                privileged_action=request.privileged_action,
                requires_human_consent=request.requires_human_consent,
                context=request.context,
            )
        )
        ctx = request.context or {}
        action = request.action_name.lower()

        has_code = bool(ctx.get("has_code")) or any(
            token in action
            for token in ("code", "patch", "fix", "debug", "refactor", "implement", "test")
        )
        broad_domain = bool(ctx.get("broad_domain")) or any(
            token in action
            for token in ("research", "compare", "investigate", "survey", "analyze")
        )
        requires_verification = (
            bool(ctx.get("requires_verification"))
            or request.privileged_action
            or request.requires_human_consent
            or request.risk_score >= 0.35
            or request.uncertainty >= 0.35
            or "review" in action
            or "audit" in action
        )
        needs_planner = (
            bool(ctx.get("has_multi_step"))
            or int(ctx.get("reasoning_markers", 0) or 0) >= 2
            or float(ctx.get("complexity_score", 0.0) or 0.0) >= 0.55
        )

        if collaboration.mode == CollaborationMode.SINGLE_AGENT:
            if has_code:
                return (SwarmRole.CODER,)
            if broad_domain:
                return (SwarmRole.RESEARCHER,)
            if requires_verification:
                return (SwarmRole.CRITIC,)
            return (SwarmRole.PLANNER,)

        roles: list[SwarmRole] = [SwarmRole.PLANNER]
        if broad_domain:
            roles.append(SwarmRole.RESEARCHER)
        if has_code:
            roles.append(SwarmRole.CODER)
        if requires_verification or not has_code or needs_planner:
            roles.append(SwarmRole.CRITIC)

        deduped: list[SwarmRole] = []
        seen: set[SwarmRole] = set()
        for role in roles:
            if role in seen:
                continue
            seen.add(role)
            deduped.append(role)
        return tuple(deduped)

    def build_blackboard(
        self,
        request: ProviderRouteRequest,
        *,
        roles: tuple[SwarmRole, ...],
    ) -> BlackboardContract:
        ctx = request.context or {}
        task_brief = str(ctx.get("task_brief") or request.action_name)
        constraints = _tupleify(ctx.get("constraints")) or (
            "Preserve existing provider-policy safety semantics.",
        )
        acceptance = _tupleify(ctx.get("acceptance_criteria")) or (
            "Return a role-local result plus blackboard handoff notes.",
        )
        shared_facts = _tupleify(ctx.get("shared_facts"))
        open_questions = _tupleify(ctx.get("open_questions"))
        return BlackboardContract(
            contract_id="swarm_blackboard_v1",
            task_brief=task_brief,
            constraints=constraints,
            acceptance_criteria=acceptance,
            shared_facts=shared_facts,
            open_questions=open_questions,
            handoff_order=tuple(role.value for role in roles),
        )

    def build_execution_contract(self) -> SwarmExecutionContract:
        return SwarmExecutionContract(
            contract_id="swarm_execution_plan_v1",
            required_context_keys=(
                "collaboration_mode",
                "assigned_role",
                "required_roles",
                "blackboard_contract",
            ),
            blackboard_fields=(
                "contract_id",
                "task_brief",
                "constraints",
                "acceptance_criteria",
                "shared_facts",
                "open_questions",
                "handoff_order",
            ),
            expected_worker_result_fields=(
                "role",
                "summary",
                "artifacts",
                "handoff_notes",
            ),
            scheduling_mode="dependency_ordered_blackboard_handoff",
        )

    def _dependency_roles(
        self,
        role: SwarmRole,
        *,
        roles: tuple[SwarmRole, ...],
    ) -> tuple[SwarmRole, ...]:
        if len(roles) <= 1 or role == SwarmRole.PLANNER:
            return ()
        if role in {SwarmRole.RESEARCHER, SwarmRole.CODER}:
            return (SwarmRole.PLANNER,) if SwarmRole.PLANNER in roles else ()

        dependencies: list[SwarmRole] = []
        for candidate in (
            SwarmRole.PLANNER,
            SwarmRole.RESEARCHER,
            SwarmRole.CODER,
        ):
            if candidate in roles and candidate != role:
                dependencies.append(candidate)
        return tuple(dependencies)

    def _plan_role(
        self,
        request: ProviderRouteRequest,
        *,
        role: SwarmRole,
        dependency_roles: tuple[SwarmRole, ...],
        collaboration: CollaborationDecision,
        roles: tuple[SwarmRole, ...],
        blackboard: BlackboardContract,
        available_providers: list[ProviderType] | None,
    ) -> RoleRoutePlan:
        role_request = self._build_role_request(
            request,
            role=role,
            collaboration=collaboration,
            roles=roles,
            blackboard=blackboard,
        )
        route = self.provider_policy.route(
            role_request,
            available_providers=available_providers,
        )
        return RoleRoutePlan(
            role=role,
            dependency_roles=dependency_roles,
            request=role_request,
            route=route,
        )

    def _build_role_request(
        self,
        request: ProviderRouteRequest,
        *,
        role: SwarmRole,
        collaboration: CollaborationDecision,
        roles: tuple[SwarmRole, ...],
        blackboard: BlackboardContract,
    ) -> ProviderRouteRequest:
        ctx = dict(request.context)
        ctx.update(
            {
                "assigned_role": role.value,
                "collaboration_mode": collaboration.mode.value,
                "required_roles": [item.value for item in roles],
                "blackboard_contract": {
                    "contract_id": blackboard.contract_id,
                    "task_brief": blackboard.task_brief,
                    "constraints": list(blackboard.constraints),
                    "acceptance_criteria": list(blackboard.acceptance_criteria),
                    "shared_facts": list(blackboard.shared_facts),
                    "open_questions": list(blackboard.open_questions),
                    "handoff_order": list(blackboard.handoff_order),
                },
            }
        )

        preferred_low_cost = request.preferred_low_cost
        requires_frontier = request.requires_frontier_precision
        if role in {SwarmRole.RESEARCHER, SwarmRole.CRITIC}:
            preferred_low_cost = False
        if (
            role == SwarmRole.PLANNER
            and collaboration.mode == CollaborationMode.MULTI_AGENT
        ):
            preferred_low_cost = False
        if role == SwarmRole.CODER:
            ctx["complexity_tier"] = "COMPLEX"
            ctx["requires_tooling"] = True
        if role == SwarmRole.RESEARCHER:
            ctx["complexity_tier"] = "REASONING"
            ctx["broad_domain"] = True
            requires_frontier = True
        if role == SwarmRole.CRITIC:
            ctx["complexity_tier"] = "REASONING"
            ctx["requires_verification"] = True
            requires_frontier = True
        if role == SwarmRole.PLANNER and collaboration.mode == CollaborationMode.MULTI_AGENT:
            ctx["complexity_tier"] = "REASONING"

        return replace(
            request,
            action_name=f"{request.action_name}:{role.value}",
            preferred_low_cost=preferred_low_cost,
            requires_frontier_precision=requires_frontier,
            context=ctx,
        )
