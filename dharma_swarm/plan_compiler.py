"""Compile proposal intents into explicit execution plans."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _as_str_list(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def _tier_rank(tier: str) -> int:
    order = {"observe": 0, "calibrate": 1, "mutate": 2}
    return order.get(str(tier).strip().lower(), 0)


def _max_tier(left: str, right: str) -> str:
    return left if _tier_rank(left) >= _tier_rank(right) else right


@dataclass(frozen=True)
class PlanContracts:
    test_contract: list[str] = field(default_factory=list)
    rollback_contract: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompiledProposalPlan:
    proposal_id: str
    description: str
    target_files: list[str]
    fix_type: str
    risk_score: float
    risk_level: str
    substrate_plan: dict[str, Any] = field(default_factory=dict)
    contracts: PlanContracts = field(default_factory=PlanContracts)


@dataclass(frozen=True)
class CompiledCyclePlan:
    proposal_batch_id: str
    target_area: str
    proposals: list[CompiledProposalPlan]
    aggregate_risk: float
    highest_risk_level: str
    substrate_plan: dict[str, Any] = field(default_factory=dict)


class PlanCompiler:
    """Compiles proposal objects into executable contracts."""

    _RISK_MAP = {
        "low": 0.20,
        "medium": 0.52,
        "high": 0.80,
        "critical": 0.95,
    }

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root).expanduser().resolve() if project_root else None

    def compile_cycle(
        self,
        *,
        proposal_batch_id: str,
        target_area: str,
        proposals: list[Any],
        env_substrate_plan_json: str | None = None,
    ) -> CompiledCyclePlan:
        compiled: list[CompiledProposalPlan] = []
        for proposal in proposals:
            compiled.append(self._compile_proposal(proposal))

        merged_substrate = self._merge_substrate_plans(
            [item.substrate_plan for item in compiled],
            fallback_json=env_substrate_plan_json,
            proposal_batch_id=proposal_batch_id,
        )
        aggregate_risk = (
            sum(item.risk_score for item in compiled) / len(compiled)
            if compiled
            else 0.0
        )
        if merged_substrate.get("jobs"):
            aggregate_risk = max(
                aggregate_risk,
                0.86 if merged_substrate.get("tier") == "mutate" else 0.65,
            )

        highest = "low"
        for item in compiled:
            highest = self._risk_label_for(
                max(self._RISK_MAP.get(highest, 0.2), item.risk_score)
            )
        if merged_substrate.get("jobs"):
            highest = self._risk_label_for(
                max(self._RISK_MAP.get(highest, 0.2), aggregate_risk)
            )

        return CompiledCyclePlan(
            proposal_batch_id=proposal_batch_id,
            target_area=target_area or "default",
            proposals=compiled,
            aggregate_risk=_clamp01(aggregate_risk),
            highest_risk_level=highest,
            substrate_plan=merged_substrate,
        )

    def _compile_proposal(self, proposal: Any) -> CompiledProposalPlan:
        proposal_id = str(getattr(proposal, "id", "proposal")).strip() or "proposal"
        description = str(getattr(proposal, "description", "")).strip()
        target_files = _as_str_list(getattr(proposal, "target_files", []) or [])
        fix_type = str(getattr(proposal, "fix_type", "")).strip()

        risk_label = str(getattr(proposal, "risk_level", "low")).strip().lower() or "low"
        risk_score = float(self._RISK_MAP.get(risk_label, 0.35))
        if any("/security/" in path or path.endswith("security.py") for path in target_files):
            risk_score = max(risk_score, 0.70)
        if any("runtime" in path or "orchestrator" in path for path in target_files):
            risk_score = max(risk_score, 0.62)

        substrate_plan = self._extract_substrate_plan(proposal)
        if substrate_plan.get("jobs"):
            tier = str(substrate_plan.get("tier", "observe")).strip().lower()
            if tier == "mutate":
                risk_score = max(risk_score, 0.90)
            elif tier == "calibrate":
                risk_score = max(risk_score, 0.68)
            else:
                risk_score = max(risk_score, 0.55)

        contracts = self._contracts_for_plan(
            target_files=target_files,
            has_substrate=bool(substrate_plan.get("jobs")),
        )
        return CompiledProposalPlan(
            proposal_id=proposal_id,
            description=description,
            target_files=target_files,
            fix_type=fix_type,
            risk_score=_clamp01(risk_score),
            risk_level=self._risk_label_for(risk_score),
            substrate_plan=substrate_plan,
            contracts=contracts,
        )

    def _extract_substrate_plan(self, proposal: Any) -> dict[str, Any]:
        metadata = getattr(proposal, "metadata", None)
        payloads: list[Any] = []
        if isinstance(metadata, dict):
            payloads.append(metadata.get("substrate_plan"))
            payloads.append(metadata.get("substrate"))
        payloads.append(getattr(proposal, "substrate_plan", None))
        payloads.append(getattr(proposal, "substrate", None))

        for payload in payloads:
            parsed = self._parse_substrate_payload(payload)
            if parsed:
                return parsed
        return {}

    def _parse_substrate_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return {}
        if not isinstance(payload, dict):
            return {}

        tier = str(payload.get("tier", "observe")).strip().lower() or "observe"
        if tier not in {"observe", "calibrate", "mutate"}:
            tier = "observe"

        jobs = payload.get("jobs", [])
        if not isinstance(jobs, list):
            jobs = []
        cleaned_jobs = [job for job in jobs if isinstance(job, dict)]

        unsafe_full_access = bool(payload.get("unsafe_full_access", False))
        if not cleaned_jobs:
            return {}

        return {
            "tier": tier,
            "unsafe_full_access": unsafe_full_access,
            "jobs": cleaned_jobs,
        }

    def _merge_substrate_plans(
        self,
        plans: list[dict[str, Any]],
        *,
        fallback_json: str | None,
        proposal_batch_id: str,
    ) -> dict[str, Any]:
        tier = "observe"
        unsafe = False
        jobs: list[dict[str, Any]] = []

        for plan in plans:
            if not isinstance(plan, dict):
                continue
            if not plan.get("jobs"):
                continue
            tier = _max_tier(tier, str(plan.get("tier", "observe")).strip().lower())
            unsafe = unsafe or bool(plan.get("unsafe_full_access", False))
            for job in plan.get("jobs", []):
                if isinstance(job, dict):
                    jobs.append(job)

        if not jobs and fallback_json:
            parsed = self._parse_substrate_payload(fallback_json)
            if parsed:
                tier = parsed.get("tier", "observe")
                unsafe = bool(parsed.get("unsafe_full_access", False))
                jobs = [
                    job for job in parsed.get("jobs", []) if isinstance(job, dict)
                ]

        if not jobs:
            return {}
        return {
            "proposal_id": proposal_batch_id,
            "tier": tier,
            "unsafe_full_access": unsafe,
            "jobs": jobs,
        }

    def _contracts_for_plan(
        self,
        *,
        target_files: list[str],
        has_substrate: bool,
    ) -> PlanContracts:
        tests = [
            "run targeted tests for touched files",
            "run evaluator gate protocol before promotion",
        ]
        rollback = [
            "preserve or regenerate restore point for touched files",
            "revert candidate when fitness or safety regresses",
        ]
        if target_files:
            tests.append(f"validate diffs for {len(target_files)} target files")
        if has_substrate:
            tests.append("require KernelGate pass for substrate mutation")
            rollback.append("restore substrate backup artifacts before retry")
        return PlanContracts(test_contract=tests, rollback_contract=rollback)

    def _risk_label_for(self, risk_score: float) -> str:
        score = _clamp01(risk_score)
        if score >= 0.85:
            return "critical"
        if score >= 0.65:
            return "high"
        if score >= 0.40:
            return "medium"
        return "low"
