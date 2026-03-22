"""Telemetry-driven optimization and donor absorption index.

This module absorbs the strongest reusable ideas from external agent stacks
without letting them become DHARMA's runtime skeleton:

- TensorZero/LiteLLM: control-plane style provider ranking
- Phoenix: evaluation and tracing-aware optimization
- A2A: explicit interoperability targets
- browser-use / Skyvern: action-surface donor targets
- mem0: memory-plane donor targets

The result is sovereign: recommendations are computed from DHARMA-owned tables
and donor repos are tracked as implementation targets rather than direct
dependencies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from typing import Any

from dharma_swarm.telemetry_plane import TelemetryPlaneStore


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


@dataclass(frozen=True)
class ProviderOptimizationRecommendation:
    provider: str
    optimization_score: float
    recommended_role: str
    dominant_path: str
    route_count: int
    avg_confidence: float
    avg_eval_score: float
    human_required_rate: float
    intervention_rate: float
    policy_block_rate: float
    total_cost_usd: float
    total_revenue_usd: float
    net_usd: float
    reasons: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DonorAbsorptionTarget:
    donor_id: str
    repo: str
    url: str
    capability_area: str
    dharma_surface: str
    priority: int
    implementation_phase: str
    steal_exactly: tuple[str, ...] = ()
    ignore_or_reimplement: tuple[str, ...] = ()
    why: str = ""


DONOR_ABSORPTION_TARGETS: tuple[DonorAbsorptionTarget, ...] = (
    DonorAbsorptionTarget(
        donor_id="tensorzero",
        repo="tensorzero/tensorzero",
        url="https://github.com/tensorzero/tensorzero",
        capability_area="llm_gateway_observability_optimization",
        dharma_surface="provider_policy.py, telemetry_plane.py, evaluation_registry.py",
        priority=1,
        implementation_phase="phase_1_control_plane",
        steal_exactly=(
            "gateway-grade model routing discipline",
            "online evaluation and optimization loops",
            "experiment-friendly observability semantics",
        ),
        ignore_or_reimplement=(
            "vendor-specific runtime assumptions",
            "any non-sovereign request object model",
        ),
        why="DHARMA needs a closed loop from route decision to measurable optimization."
    ),
    DonorAbsorptionTarget(
        donor_id="autogen",
        repo="microsoft/autogen",
        url="https://github.com/microsoft/autogen",
        capability_area="multi_agent_orchestration_patterns",
        dharma_surface="agent orchestration, team collaboration, future multi-agent protocols",
        priority=2,
        implementation_phase="phase_3_orchestration",
        steal_exactly=(
            "team-based agent collaboration patterns",
            "multi-agent task decomposition",
            "shared memory coordination",
        ),
        ignore_or_reimplement=(
            "framework-specific agent implementations",
            "non-sovereign team management assumptions",
        ),
        why="DHARMA needs to absorb multi-agent orchestration patterns while maintaining sovereign control."
    ),
    DonorAbsorptionTarget(
        donor_id="litellm",
        repo="BerriAI/litellm",
        url="https://github.com/BerriAI/litellm",
        capability_area="provider_gateway_cost_tracking",
        dharma_surface="base_provider.py, model_manager.py, provider_policy.py",
        priority=1,
        implementation_phase="phase_1_control_plane",
        steal_exactly=(
            "provider normalization patterns",
            "cost tracking and gateway fallback logic",
            "load-balancing and multi-provider failover ideas",
        ),
        ignore_or_reimplement=(
            "proxy-first operational assumptions",
            "direct dependency on external gateway formats",
        ),
        why="DHARMA already routes providers, but its routing brain needs stronger cost-aware discipline.",
    ),
    DonorAbsorptionTarget(
        donor_id="a2a",
        repo="a2aproject/A2A",
        url="https://github.com/a2aproject/A2A",
        capability_area="agent_interoperability_protocol",
        dharma_surface="handoff.py, contracts/runtime.py, future interop adapters",
        priority=1,
        implementation_phase="phase_1_interop",
        steal_exactly=(
            "capability discovery patterns",
            "task handoff protocol semantics",
            "opaque-agent interoperability boundaries",
        ),
        ignore_or_reimplement=(
            "non-DHARMA lifecycle semantics",
        ),
        why="Sovereign systems still need an external protocol boundary.",
    ),
    DonorAbsorptionTarget(
        donor_id="phoenix",
        repo="Arize-ai/phoenix",
        url="https://github.com/Arize-ai/phoenix",
        capability_area="tracing_eval_observability",
        dharma_surface="telemetry_plane.py, telemetry_views.py, dashboard telemetry",
        priority=1,
        implementation_phase="phase_1_observability",
        steal_exactly=(
            "trace-first evaluation workflows",
            "subject-centric experiment views",
            "debuggable failure analysis surfaces",
        ),
        ignore_or_reimplement=(
            "hosted-first assumptions",
        ),
        why="Telemetry should explain behavior, not just count rows.",
    ),
    DonorAbsorptionTarget(
        donor_id="browser_use",
        repo="browser-use/browser-use",
        url="https://github.com/browser-use/browser-use",
        capability_area="browser_action_runtime",
        dharma_surface="gateway/, sandbox/, future browser adapters",
        priority=2,
        implementation_phase="phase_2_action_surface",
        steal_exactly=(
            "web action abstractions",
            "agent-accessible browser state patterns",
        ),
        ignore_or_reimplement=(
            "framework-specific orchestration wrappers",
        ),
        why="DHARMA eventually needs a first-class browser action layer.",
    ),
    DonorAbsorptionTarget(
        donor_id="skyvern",
        repo="Skyvern-AI/skyvern",
        url="https://github.com/Skyvern-AI/skyvern",
        capability_area="structured_web_workflows",
        dharma_surface="workflow execution, checkpointing, gateway surfaces",
        priority=2,
        implementation_phase="phase_2_action_surface",
        steal_exactly=(
            "reliable browser workflow patterns",
            "checkpoint-heavy web task decomposition",
        ),
        ignore_or_reimplement=(
            "hosted automation assumptions",
        ),
        why="Browser action is more useful when it is checkpointed and reproducible.",
    ),
    DonorAbsorptionTarget(
        donor_id="mem0",
        repo="mem0ai/mem0",
        url="https://github.com/mem0ai/mem0",
        capability_area="memory_productization",
        dharma_surface="engine/event_memory.py, engine/unified_index.py, contracts/intelligence.py",
        priority=2,
        implementation_phase="phase_2_memory",
        steal_exactly=(
            "memory retrieval ergonomics",
            "cross-session memory shaping ideas",
        ),
        ignore_or_reimplement=(
            "non-sovereign memory storage formats",
        ),
        why="DHARMA already has memory primitives, but they need cleaner operational policy.",
    ),
    DonorAbsorptionTarget(
        donor_id="autogen",
        repo="microsoft/autogen",
        url="https://github.com/microsoft/autogen",
        capability_area="multi_agent_orchestration_patterns",
        dharma_surface="swarm_router.py, operator_bridge.py, handoff.py",
        priority=3,
        implementation_phase="phase_3_orchestration",
        steal_exactly=(
            "role-based coordination patterns",
            "conversation-to-workflow decomposition ideas",
        ),
        ignore_or_reimplement=(
            "framework-owned message schema",
        ),
        why="Useful donor for multi-agent patterns, not a sovereign foundation.",
    ),
    DonorAbsorptionTarget(
        donor_id="agent_framework",
        repo="microsoft/agent-framework",
        url="https://github.com/microsoft/agent-framework",
        capability_area="durable_workflow_deployment",
        dharma_surface="runtime_state.py, operator_bridge.py, contracts/runtime.py",
        priority=3,
        implementation_phase="phase_3_orchestration",
        steal_exactly=(
            "durable workflow semantics",
            "deployment-grade lifecycle ideas",
        ),
        ignore_or_reimplement=(
            "framework-specific deployment substrate",
        ),
        why="DHARMA needs durability patterns, but should keep its own runtime envelope.",
    ),
    DonorAbsorptionTarget(
        donor_id="pydantic_ai",
        repo="pydantic/pydantic-ai",
        url="https://github.com/pydantic/pydantic-ai",
        capability_area="typed_agent_contracts",
        dharma_surface="contracts/, api models, tool schemas",
        priority=3,
        implementation_phase="phase_3_contract_hardening",
        steal_exactly=(
            "typed tool and output discipline",
            "schema-first agent boundary ideas",
        ),
        ignore_or_reimplement=(
            "framework-owned agent runtime",
        ),
        why="DHARMA's sovereign contracts need stronger typed ergonomics over time.",
    ),
)


class TelemetryOptimizer:
    """Compute sovereign optimization recommendations from DHARMA-owned state."""

    def __init__(self, telemetry: TelemetryPlaneStore | None = None) -> None:
        self.telemetry = telemetry or TelemetryPlaneStore()

    async def provider_recommendations(
        self,
        *,
        limit: int = 8,
    ) -> list[ProviderOptimizationRecommendation]:
        await self.telemetry.init_db()
        return await asyncio.to_thread(self.provider_recommendations_sync, limit=limit)

    def provider_recommendations_sync(
        self,
        *,
        limit: int = 8,
    ) -> list[ProviderOptimizationRecommendation]:
        rows = self._load_rows()
        return self._build_provider_recommendations(rows, limit=limit)

    def _build_provider_recommendations(
        self,
        rows: dict[str, list[sqlite3.Row]],
        *,
        limit: int,
    ) -> list[ProviderOptimizationRecommendation]:
        provider_stats = self._aggregate_provider_stats(rows)
        if not provider_stats:
            return []

        max_cost = max((item["total_cost_usd"] for item in provider_stats.values()), default=0.0)
        max_volume = max((item["route_count"] for item in provider_stats.values()), default=1)
        recommendations: list[ProviderOptimizationRecommendation] = []

        for provider, stats in provider_stats.items():
            route_count = int(stats["route_count"] or 0)
            avg_confidence = (stats["confidence_total"] / route_count) if route_count else 0.0
            avg_eval_score = (
                stats["eval_total"] / stats["eval_count"]
                if stats["eval_count"]
                else avg_confidence
            )
            human_required_rate = (
                stats["human_required_count"] / route_count if route_count else 0.0
            )
            intervention_rate = (
                stats["intervention_count"] / route_count if route_count else 0.0
            )
            policy_block_rate = (
                stats["policy_block_count"] / stats["policy_count"]
                if stats["policy_count"]
                else 0.0
            )
            total_cost_usd = float(stats["total_cost_usd"])
            total_revenue_usd = float(stats["total_revenue_usd"])
            net_usd = total_revenue_usd - total_cost_usd
            cost_penalty = (total_cost_usd / max_cost) if max_cost > 0 else 0.0
            maturity_bonus = min(route_count / max(max_volume, 1), 1.0)
            optimization_score = round(
                (
                    0.30 * avg_eval_score
                    + 0.20 * avg_confidence
                    + 0.15 * (1.0 - human_required_rate)
                    + 0.10 * (1.0 - intervention_rate)
                    + 0.10 * (1.0 - policy_block_rate)
                    + 0.10 * (1.0 - min(cost_penalty, 1.0))
                    + 0.05 * maturity_bonus
                ),
                6,
            )
            dominant_path = self._dominant_key(stats["path_counts"], fallback="unknown")
            recommended_role = self._recommended_role(
                score=optimization_score,
                dominant_path=dominant_path,
                human_required_rate=human_required_rate,
                total_cost_usd=total_cost_usd,
            )
            reasons = self._reasons_for_provider(
                avg_confidence=avg_confidence,
                avg_eval_score=avg_eval_score,
                human_required_rate=human_required_rate,
                intervention_rate=intervention_rate,
                policy_block_rate=policy_block_rate,
                total_cost_usd=total_cost_usd,
                max_cost=max_cost,
                maturity_bonus=maturity_bonus,
            )
            actions = self._actions_for_provider(
                avg_eval_score=avg_eval_score,
                human_required_rate=human_required_rate,
                intervention_rate=intervention_rate,
                policy_block_rate=policy_block_rate,
                total_cost_usd=total_cost_usd,
                max_cost=max_cost,
            )
            recommendations.append(
                ProviderOptimizationRecommendation(
                    provider=provider,
                    optimization_score=optimization_score,
                    recommended_role=recommended_role,
                    dominant_path=dominant_path,
                    route_count=route_count,
                    avg_confidence=round(avg_confidence, 6),
                    avg_eval_score=round(avg_eval_score, 6),
                    human_required_rate=round(human_required_rate, 6),
                    intervention_rate=round(intervention_rate, 6),
                    policy_block_rate=round(policy_block_rate, 6),
                    total_cost_usd=round(total_cost_usd, 6),
                    total_revenue_usd=round(total_revenue_usd, 6),
                    net_usd=round(net_usd, 6),
                    reasons=tuple(reasons),
                    recommended_actions=tuple(actions),
                )
            )

        recommendations.sort(
            key=lambda item: (
                -item.optimization_score,
                item.human_required_rate,
                item.total_cost_usd,
                item.provider,
            )
        )
        return recommendations[: max(limit, 1)]

    def donor_targets(
        self,
        *,
        limit: int | None = None,
        priority: int | None = None,
    ) -> list[DonorAbsorptionTarget]:
        items = list(DONOR_ABSORPTION_TARGETS)
        if priority is not None:
            items = [item for item in items if item.priority == priority]
        items.sort(key=lambda item: (item.priority, item.implementation_phase, item.donor_id))
        if limit is not None:
            items = items[: max(limit, 0)]
        return items

    def _load_rows(self) -> dict[str, list[sqlite3.Row]]:
        db_path = Path(self.telemetry.db_path)
        if not db_path.exists():
            return {
                "routing": [],
                "policy": [],
                "intervention": [],
                "economic": [],
                "evaluation": [],
            }
        with sqlite3.connect(str(db_path)) as db:
            db.row_factory = sqlite3.Row
            table_names = {
                str(row["name"])
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            routing_rows: list[sqlite3.Row] = []
            policy_rows: list[sqlite3.Row] = []
            intervention_rows: list[sqlite3.Row] = []
            economic_rows: list[sqlite3.Row] = []
            evaluation_rows: list[sqlite3.Row] = []
            if "routing_decisions" in table_names:
                routing_rows = db.execute(
                    "SELECT decision_id, session_id, task_id, run_id, action_name, route_path,"
                    " selected_provider, selected_model_hint, confidence, requires_human,"
                    " reasons_json, metadata_json, created_at"
                    " FROM routing_decisions"
                ).fetchall()
            if "policy_decisions" in table_names:
                policy_rows = db.execute(
                    "SELECT decision_id, session_id, task_id, run_id, policy_name, decision,"
                    " confidence, metadata_json, created_at FROM policy_decisions"
                ).fetchall()
            if "intervention_outcomes" in table_names:
                intervention_rows = db.execute(
                    "SELECT intervention_id, session_id, task_id, run_id, intervention_type,"
                    " outcome_status, impact_score, metadata_json, created_at"
                    " FROM intervention_outcomes"
                ).fetchall()
            if "economic_events" in table_names:
                economic_rows = db.execute(
                    "SELECT event_id, session_id, task_id, run_id, event_kind, amount, currency,"
                    " counterparty, metadata_json, created_at FROM economic_events"
                ).fetchall()
            if "intelligence_evaluation_records" in table_names:
                evaluation_rows = db.execute(
                    "SELECT evaluation_id, subject_kind, subject_id, metric, score,"
                    " session_id, task_id, run_id, metadata_json, recorded_at"
                    " FROM intelligence_evaluation_records"
                ).fetchall()
        return {
            "routing": list(routing_rows),
            "policy": list(policy_rows),
            "intervention": list(intervention_rows),
            "economic": list(economic_rows),
            "evaluation": list(evaluation_rows),
        }

    def _aggregate_provider_stats(
        self,
        rows: dict[str, list[sqlite3.Row]],
    ) -> dict[str, dict[str, Any]]:
        provider_stats: dict[str, dict[str, Any]] = {}
        task_provider_map: dict[str, set[str]] = {}
        run_provider_map: dict[str, set[str]] = {}

        for row in rows["routing"]:
            provider = str(row["selected_provider"] or "").strip()
            if not provider:
                continue
            stats = provider_stats.setdefault(
                provider,
                {
                    "route_count": 0,
                    "confidence_total": 0.0,
                    "human_required_count": 0,
                    "intervention_count": 0,
                    "policy_count": 0,
                    "policy_block_count": 0,
                    "eval_total": 0.0,
                    "eval_count": 0,
                    "total_cost_usd": 0.0,
                    "total_revenue_usd": 0.0,
                    "path_counts": {},
                },
            )
            stats["route_count"] += 1
            stats["confidence_total"] += float(row["confidence"] or 0.0)
            stats["human_required_count"] += 1 if int(row["requires_human"] or 0) else 0
            route_path = str(row["route_path"] or "unknown")
            stats["path_counts"][route_path] = int(stats["path_counts"].get(route_path, 0)) + 1
            task_id = str(row["task_id"] or "").strip()
            run_id = str(row["run_id"] or "").strip()
            if task_id:
                task_provider_map.setdefault(task_id, set()).add(provider)
            if run_id:
                run_provider_map.setdefault(run_id, set()).add(provider)

        for row in rows["policy"]:
            provider = self._resolve_provider(
                run_id=str(row["run_id"] or ""),
                task_id=str(row["task_id"] or ""),
                metadata=_json_load(row["metadata_json"], {}),
                run_provider_map=run_provider_map,
                task_provider_map=task_provider_map,
            )
            if not provider or provider not in provider_stats:
                continue
            stats = provider_stats[provider]
            stats["policy_count"] += 1
            decision = str(row["decision"] or "").strip().lower()
            if decision and decision not in {"approved", "allow", "allowed", "pass", "passed"}:
                stats["policy_block_count"] += 1

        for row in rows["intervention"]:
            provider = self._resolve_provider(
                run_id=str(row["run_id"] or ""),
                task_id=str(row["task_id"] or ""),
                metadata=_json_load(row["metadata_json"], {}),
                run_provider_map=run_provider_map,
                task_provider_map=task_provider_map,
            )
            if not provider or provider not in provider_stats:
                continue
            provider_stats[provider]["intervention_count"] += 1

        for row in rows["economic"]:
            metadata = _json_load(row["metadata_json"], {})
            provider = self._provider_from_metadata(metadata) or str(row["counterparty"] or "").strip()
            if not provider:
                provider = self._resolve_provider(
                    run_id=str(row["run_id"] or ""),
                    task_id=str(row["task_id"] or ""),
                    metadata=metadata,
                    run_provider_map=run_provider_map,
                    task_provider_map=task_provider_map,
                )
            if not provider or provider not in provider_stats:
                continue
            if str(row["currency"] or "USD").upper() != "USD":
                continue
            amount = float(row["amount"] or 0.0)
            if str(row["event_kind"] or "").strip().lower() == "revenue":
                provider_stats[provider]["total_revenue_usd"] += amount
            else:
                provider_stats[provider]["total_cost_usd"] += amount

        for row in rows["evaluation"]:
            metadata = _json_load(row["metadata_json"], {})
            provider = self._provider_from_evaluation(
                subject_kind=str(row["subject_kind"] or ""),
                subject_id=str(row["subject_id"] or ""),
                run_id=str(row["run_id"] or ""),
                task_id=str(row["task_id"] or ""),
                metadata=metadata,
                run_provider_map=run_provider_map,
                task_provider_map=task_provider_map,
            )
            if not provider or provider not in provider_stats:
                continue
            provider_stats[provider]["eval_total"] += float(row["score"] or 0.0)
            provider_stats[provider]["eval_count"] += 1

        return provider_stats

    @staticmethod
    def _provider_from_metadata(metadata: dict[str, Any]) -> str:
        for key in ("provider", "selected_provider", "recommended_provider", "counterparty"):
            value = str(metadata.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _provider_from_evaluation(
        self,
        *,
        subject_kind: str,
        subject_id: str,
        run_id: str,
        task_id: str,
        metadata: dict[str, Any],
        run_provider_map: dict[str, set[str]],
        task_provider_map: dict[str, set[str]],
    ) -> str:
        if subject_kind.lower() in {"provider", "routing_provider", "provider_route"}:
            return subject_id.strip()
        provider = self._provider_from_metadata(metadata)
        if provider:
            return provider
        return self._resolve_provider(
            run_id=run_id,
            task_id=task_id,
            metadata=metadata,
            run_provider_map=run_provider_map,
            task_provider_map=task_provider_map,
        )

    def _resolve_provider(
        self,
        *,
        run_id: str,
        task_id: str,
        metadata: dict[str, Any],
        run_provider_map: dict[str, set[str]],
        task_provider_map: dict[str, set[str]],
    ) -> str:
        provider = self._provider_from_metadata(metadata)
        if provider:
            return provider
        run_id = run_id.strip()
        task_id = task_id.strip()
        if run_id:
            candidates = run_provider_map.get(run_id, set())
            if len(candidates) == 1:
                return next(iter(candidates))
        if task_id:
            candidates = task_provider_map.get(task_id, set())
            if len(candidates) == 1:
                return next(iter(candidates))
        return ""

    @staticmethod
    def _dominant_key(counts: dict[str, int], *, fallback: str) -> str:
        if not counts:
            return fallback
        return max(counts.items(), key=lambda item: (item[1], item[0]))[0]

    @staticmethod
    def _recommended_role(
        *,
        score: float,
        dominant_path: str,
        human_required_rate: float,
        total_cost_usd: float,
    ) -> str:
        if score >= 0.78 and human_required_rate <= 0.2:
            return "promote_to_default_lane"
        if dominant_path == "escalate" or human_required_rate >= 0.5:
            return "reserve_for_frontier_or_human_guarded_work"
        if total_cost_usd > 0.0 and score < 0.62:
            return "deprioritize_for_bounded_tasks"
        return "keep_as_balanced_fallback"

    @staticmethod
    def _reasons_for_provider(
        *,
        avg_confidence: float,
        avg_eval_score: float,
        human_required_rate: float,
        intervention_rate: float,
        policy_block_rate: float,
        total_cost_usd: float,
        max_cost: float,
        maturity_bonus: float,
    ) -> list[str]:
        reasons: list[str] = []
        if avg_eval_score >= 0.85:
            reasons.append("high_eval_signal")
        if avg_confidence >= 0.8:
            reasons.append("high_router_confidence")
        if human_required_rate <= 0.2:
            reasons.append("low_human_requirement")
        if intervention_rate <= 0.15:
            reasons.append("low_operator_intervention")
        if policy_block_rate <= 0.1:
            reasons.append("policy_aligned")
        if max_cost <= 0 or total_cost_usd <= (0.25 * max_cost):
            reasons.append("cost_efficient")
        if maturity_bonus >= 0.7:
            reasons.append("operationally_mature")
        if not reasons:
            reasons.append("baseline_signal")
        return reasons

    @staticmethod
    def _actions_for_provider(
        *,
        avg_eval_score: float,
        human_required_rate: float,
        intervention_rate: float,
        policy_block_rate: float,
        total_cost_usd: float,
        max_cost: float,
    ) -> list[str]:
        actions: list[str] = []
        if avg_eval_score < 0.7:
            actions.append("run_provider_eval_benchmark")
        if human_required_rate > 0.4 or intervention_rate > 0.35:
            actions.append("add_checkpoint_or_human_gate_before_default_use")
        if policy_block_rate > 0.25:
            actions.append("tighten_route_policy_or_reduce_privileged_scope")
        if max_cost > 0 and total_cost_usd > (0.6 * max_cost):
            actions.append("shift_bounded_tasks_to_lower_cost_lane")
        if not actions:
            actions.append("promote_for_more_live_traffic")
        return actions
