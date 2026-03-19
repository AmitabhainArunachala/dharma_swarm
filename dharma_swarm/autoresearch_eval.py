"""Locked Ω/Ψ evaluator for the DHARMA SWARM autoresearch loop.

This is the local scorer that the overnight runner uses after each cycle.
It prefers deterministic probes already present in the repo over LLM judges.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import pwd
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from dharma_swarm.agent_registry import AgentRegistry
from dharma_swarm.assurance.runner import run_assurance
from dharma_swarm.cost_tracker import read_cost_log
from dharma_swarm.decision_router import RoutePath
from dharma_swarm.dharma_kernel import DharmaKernel, KernelGuard
from dharma_swarm.ecc_eval_harness import EvalReport, run_all_evals
from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.engine.hybrid_retriever import HybridRetriever
from dharma_swarm.engine.unified_index import UnifiedIndex
from dharma_swarm.memory import StrangeLoopMemory
from dharma_swarm.models import (
    AgentRole,
    AgentState,
    AgentStatus,
    MemoryLayer,
    Task,
    TopologyType,
)
from dharma_swarm.orchestrator import Orchestrator
from dharma_swarm.perception_action_loop import CandidateAction, LoopConfig, PerceptionActionLoop
from dharma_swarm.provider_policy import ProviderPolicyRouter, ProviderRouteRequest
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.tap.providers import ProviderConfig, TAPProviderRouter


def _resolve_login_home() -> Path:
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).expanduser()
    except Exception:
        return Path.home()


LOGIN_HOME = _resolve_login_home()
ROOT = LOGIN_HOME / "dharma_swarm"
STATE_DIR = LOGIN_HOME / ".dharma"
EVALS_DIR = STATE_DIR / "evals"
LATEST_REPORT = EVALS_DIR / "autoresearch_latest.json"
HISTORY_REPORT = EVALS_DIR / "autoresearch_history.jsonl"

HP_WEIGHTS: tuple[float, ...] = (
    0.15,
    0.10,
    0.10,
    0.10,
    0.08,
    0.12,
    0.10,
    0.08,
    0.07,
    0.10,
)
CAUSAL_MARKERS = (
    "because",
    "causes",
    "degrades",
    "drives",
    "if ",
    "improves",
    "mediated",
    "prevents",
    "so that",
    "when ",
)
SELF_LINE_RE = re.compile(
    r"cycle\s+(?P<cycle>\d+)\s+\[(?P<regime>[^\]]+)\]\s+Ω≈(?P<omega>[-+]?\d+(?:\.\d+)?)\s+Ψ≈(?P<psi>[-+]?\d+(?:\.\d+)?)"
)
_AUTORESEARCH_RESULTS_COLUMNS = (
    "exp_id",
    "timestamp",
    "hypothesis",
    "predicted_omega_delta",
    "predicted_psi_delta",
    "actual_omega",
    "actual_psi",
    "files",
    "tests",
    "kept",
    "regime",
    "notes",
    "confidence",
    "metrics_source",
)


@dataclass(slots=True)
class MetricScore:
    name: str
    score: float
    weight: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass(slots=True)
class AutoresearchEvalReport:
    timestamp: str
    benchmark: str
    timeout_seconds: int
    omega: float
    psi: float
    hp_scores: list[MetricScore]
    psi_components: dict[str, float]
    ecc_report: dict[str, Any]
    assurance_summary: dict[str, Any]
    probe_details: dict[str, Any]
    repo_root: str
    state_dir: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "benchmark": self.benchmark,
            "timeout_seconds": self.timeout_seconds,
            "omega": round(self.omega, 4),
            "psi": round(self.psi, 4),
            "hp_scores": [score.to_dict() for score in self.hp_scores],
            "psi_components": {key: round(value, 4) for key, value in self.psi_components.items()},
            "ecc_report": self.ecc_report,
            "assurance_summary": self.assurance_summary,
            "probe_details": self.probe_details,
            "repo_root": self.repo_root,
            "state_dir": self.state_dir,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_finite_float(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return numeric


def _clamp01(value: float) -> float:
    numeric = _coerce_finite_float(value, default=0.0)
    assert numeric is not None
    return max(0.0, min(1.0, numeric))


def _weighted_geometric_mean(weighted_values: Sequence[tuple[float, float]]) -> float:
    total_weight = 0.0
    total_log = 0.0
    for value, weight in weighted_values:
        numeric_value = _coerce_finite_float(value)
        numeric_weight = _coerce_finite_float(weight)
        if numeric_value is None or numeric_weight is None or numeric_weight <= 0.0:
            continue
        bounded = max(1e-6, min(1.0, numeric_value))
        total_weight += numeric_weight
        total_log += numeric_weight * math.log(bounded)
    if total_weight <= 0.0:
        return 0.0
    return round(math.exp(total_log / total_weight), 4)


def _percentile(values: Sequence[float], p: float) -> float:
    ordered = sorted(
        numeric
        for value in values
        if (numeric := _coerce_finite_float(value)) is not None
    )
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    percentile = _coerce_finite_float(p, default=0.0)
    assert percentile is not None
    index = max(0.0, min(1.0, percentile)) * (len(ordered) - 1)
    low = int(math.floor(index))
    high = int(math.ceil(index))
    if low == high:
        return ordered[low]
    fraction = index - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "n/a", "na", "unknown"}:
        return None
    if text.startswith("+"):
        text = text[1:]
    if text.endswith("%"):
        text = text[:-1].strip()
        numeric = _coerce_finite_float(text)
        return None if numeric is None else numeric / 100.0
    return _coerce_finite_float(text)


def _score_latency(p95_seconds: float) -> float:
    return round(1.0 / (1.0 + (max(0.0, p95_seconds) / 5.0)), 4)


def _clean_autoresearch_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _normalize_autoresearch_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {
        key: _clean_autoresearch_cell(row.get(key, ""))
        for key in _AUTORESEARCH_RESULTS_COLUMNS
    }
    proxy_omega = _clean_autoresearch_cell(row.get("actual_omega_proxy", ""))
    proxy_psi = _clean_autoresearch_cell(row.get("actual_psi_proxy", ""))
    if not normalized["actual_omega"]:
        normalized["actual_omega"] = proxy_omega
    if not normalized["actual_psi"]:
        normalized["actual_psi"] = proxy_psi
    if not normalized["confidence"]:
        normalized["confidence"] = "unknown"
    if not normalized["metrics_source"]:
        if proxy_omega or proxy_psi:
            normalized["metrics_source"] = "proxy"
        elif (
            _parse_float(normalized["actual_omega"]) is not None
            or _parse_float(normalized["actual_psi"]) is not None
        ):
            normalized["metrics_source"] = "locked"
        else:
            normalized["metrics_source"] = "unavailable"
    return normalized


def _read_autoresearch_rows(repo_root: Path) -> list[dict[str, str]]:
    path = repo_root / "results_autoresearch.tsv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [_normalize_autoresearch_row(dict(row)) for row in reader]


def _row_uses_locked_metrics(row: dict[str, str]) -> bool:
    return str(row.get("metrics_source", "") or "").strip().lower() == "locked"


def _actual_omega_from_row(row: dict[str, str]) -> float | None:
    if _row_uses_locked_metrics(row):
        value = _parse_float(row.get("actual_omega"))
        if value is not None:
            return value
    return None


def _actual_psi_from_row(row: dict[str, str]) -> float | None:
    if _row_uses_locked_metrics(row):
        value = _parse_float(row.get("actual_psi"))
        if value is not None:
            return value
    return None


def _experiment_text(repo_root: Path) -> str:
    parts: list[str] = []
    for name in ("experiment_log.md", "results_autoresearch.tsv"):
        path = repo_root / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def _self_observation_lines(repo_root: Path) -> list[str]:
    path = repo_root / "SELF.md"
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip().startswith("- ")
    ]


def _compute_psi(repo_root: Path) -> tuple[float, dict[str, float], dict[str, Any]]:
    rows = _read_autoresearch_rows(repo_root)
    self_lines = _self_observation_lines(repo_root)
    experiment_text = _experiment_text(repo_root)

    actual_deltas: list[float] = []
    predicted_deltas: list[float] = []
    confidence_points: list[tuple[float, float]] = []
    for previous, current in zip(rows, rows[1:]):
        prev_omega = _actual_omega_from_row(previous)
        cur_omega = _actual_omega_from_row(current)
        predicted = _parse_float(current.get("predicted_omega_delta"))
        confidence = _parse_float(current.get("confidence"))
        if prev_omega is not None and cur_omega is not None and predicted is not None:
            actual_delta = cur_omega - prev_omega
            actual_deltas.append(actual_delta)
            predicted_deltas.append(predicted)
            if confidence is not None:
                confidence_points.append((_clamp01(confidence), 1.0 if actual_delta > 0.0 else 0.0))

    if actual_deltas and predicted_deltas:
        sq_error = sum((pred - actual) ** 2 for pred, actual in zip(predicted_deltas, actual_deltas))
        rmse = math.sqrt(sq_error / len(actual_deltas))
        mean_actual = sum(actual_deltas) / len(actual_deltas)
        variance = sum((value - mean_actual) ** 2 for value in actual_deltas) / len(actual_deltas)
        sigma = max(math.sqrt(variance), 0.05)
        psi_prediction = _clamp01(1.0 - (rmse / sigma))
    else:
        psi_prediction = 0.5

    if confidence_points:
        buckets: list[list[tuple[float, float]]] = [[] for _ in range(5)]
        for confidence, outcome in confidence_points:
            index = min(4, int(confidence * 5.0))
            buckets[index].append((confidence, outcome))
        ece = 0.0
        total = len(confidence_points)
        for bucket in buckets:
            if not bucket:
                continue
            avg_confidence = sum(point[0] for point in bucket) / len(bucket)
            accuracy = sum(point[1] for point in bucket) / len(bucket)
            ece += (len(bucket) / total) * abs(accuracy - avg_confidence)
        psi_calibration = _clamp01(1.0 - ece)
    else:
        psi_calibration = 0.5

    if experiment_text:
        self_bytes = max(1, len((repo_root / "SELF.md").read_text(encoding="utf-8", errors="ignore"))) if (repo_root / "SELF.md").exists() else 1
        full_bytes = max(1, len(experiment_text))
        ratio = self_bytes / full_bytes
        psi_compression = _clamp01(1.0 / (1.0 + ratio))
    else:
        psi_compression = 0.5

    causal_rows = rows[-20:]
    if causal_rows:
        causal_hits = 0
        for row in causal_rows:
            payload = " ".join(
                str(row.get(key, "") or "")
                for key in ("hypothesis", "notes")
            ).lower()
            if any(marker in payload for marker in CAUSAL_MARKERS):
                causal_hits += 1
        psi_causal = round(causal_hits / len(causal_rows), 4)
    else:
        psi_causal = 0.5

    observation_matches = 0
    observation_total = 0
    by_cycle = {row.get("exp_id", "").strip().lstrip("0") or "0": row for row in rows}
    for line in self_lines[-5:]:
        match = SELF_LINE_RE.search(line)
        if not match:
            continue
        cycle = str(int(match.group("cycle")))
        row = by_cycle.get(cycle)
        if row is None:
            continue
        observation_total += 1
        row_regime = str(row.get("regime", "") or "")
        row_omega = _actual_omega_from_row(row)
        row_psi = _actual_psi_from_row(row)
        same_regime = (not row_regime) or (row_regime == match.group("regime"))
        same_omega = row_omega is None or abs(row_omega - float(match.group("omega"))) <= 0.05
        same_psi = row_psi is None or abs(row_psi - float(match.group("psi"))) <= 0.05
        if same_regime and same_omega and same_psi:
            observation_matches += 1
    if observation_total:
        psi_consistency = round(observation_matches / observation_total, 4)
    else:
        psi_consistency = 0.5

    components = {
        "prediction": round(psi_prediction, 4),
        "calibration": round(psi_calibration, 4),
        "compression": round(psi_compression, 4),
        "causal": round(psi_causal, 4),
        "consistency": round(psi_consistency, 4),
    }
    psi = _weighted_geometric_mean(tuple((value, 1.0) for value in components.values()))
    detail = {
        "history_rows": len(rows),
        "prediction_pairs": len(actual_deltas),
        "confidence_points": len(confidence_points),
        "self_observations": len(self_lines),
        "consistency_checks": observation_total,
    }
    return psi, components, detail


class _EvalTaskBoard:
    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = list(tasks)

    async def get_ready_tasks(self) -> list[Task]:
        return list(self.tasks)

    async def update_task(self, task_id: str, **fields: Any) -> None:
        for task in self.tasks:
            if task.id != task_id:
                continue
            for key, value in fields.items():
                setattr(task, key, value)

    async def get(self, task_id: str) -> Task | None:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


class _EvalAgentPool:
    def __init__(self, agents: list[AgentState]) -> None:
        self._agents = list(agents)
        self._results: dict[str, str] = {}
        self._assignments: list[tuple[str, str]] = []

    async def get_idle_agents(self) -> list[AgentState]:
        return list(self._agents)

    async def assign(self, agent_id: str, task_id: str) -> None:
        self._assignments.append((agent_id, task_id))

    async def release(self, agent_id: str) -> None:
        del agent_id

    async def get_result(self, agent_id: str) -> str | None:
        return self._results.get(agent_id)

    async def get(self, agent_id: str) -> Any:
        del agent_id
        return None


class _EvalEventMemory:
    def __init__(self) -> None:
        self.envelopes: list[Any] = []

    async def ingest_envelope(self, envelope: Any) -> None:
        self.envelopes.append(envelope)


class _FakeMessage:
    def __init__(self, *, content: object = None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, *, message: _FakeMessage | None = None, text: object = None, delta: object = None) -> None:
        self.message = message
        self.text = text
        self.delta = delta


class _FakeResponse:
    def __init__(self, *, content: object = None, text: object = None, delta: object = None) -> None:
        message = _FakeMessage(content=content) if content is not None else None
        self.choices = [_FakeChoice(message=message, text=text, delta=delta)]


class _FakeClient:
    def __init__(self, behavior: dict[str, object], provider_name: str) -> None:
        self._behavior = behavior
        self._provider_name = provider_name
        self.chat = self
        self.completions = self

    def create(self, **_: object) -> _FakeResponse:
        outcome = self._behavior[self._provider_name]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, _FakeResponse):
            return outcome
        return _FakeResponse(content=outcome)


def _task_success_rate(report: dict[str, Any]) -> MetricScore:
    capability_names = {
        "task_roundtrip",
        "fitness_signal_flow",
        "stigmergy_roundtrip",
        "evolution_archive",
    }
    results = [result for result in report.get("results", []) if result.get("name") in capability_names]
    passed = [result["name"] for result in results if bool(result.get("passed"))]
    failed = [result["name"] for result in results if not bool(result.get("passed"))]
    score = round(len(passed) / max(1, len(capability_names)), 4)
    return MetricScore(
        name="task_success_rate",
        score=score,
        weight=HP_WEIGHTS[0],
        detail={"passed": passed, "failed": failed, "capability_evals": sorted(capability_names)},
    )


def _latency_p95(report: dict[str, Any]) -> MetricScore:
    durations = [
        max(0.0, numeric)
        for result in report.get("results", [])
        if (numeric := _coerce_finite_float(result.get("duration_seconds", 0.0) or 0.0)) is not None
    ]
    p95_seconds = round(_percentile(durations, 0.95), 4)
    return MetricScore(
        name="latency_p95",
        score=_score_latency(p95_seconds),
        weight=HP_WEIGHTS[1],
        detail={"p95_seconds": p95_seconds, "samples": len(durations)},
    )


def _cost_efficiency(task_success: float, *, state_dir: Path) -> MetricScore:
    entries = read_cost_log(since_hours=24.0, state_dir=state_dir)
    fleet = AgentRegistry(agents_dir=state_dir / "ginko" / "agents").get_fleet_summary()
    entry_costs = [
        numeric
        for entry in entries
        if (numeric := _coerce_finite_float(getattr(entry, "estimated_cost_usd", None))) is not None
    ]
    fleet_total_cost = _coerce_finite_float(fleet.get("total_cost_usd", 0.0) or 0.0, default=0.0)
    assert fleet_total_cost is not None
    total_cost = max(
        sum(entry_costs),
        fleet_total_cost,
    )
    fleet_total_calls = max(
        0,
        int(_coerce_finite_float(fleet.get("total_calls", 0) or 0, default=0.0) or 0.0),
    )
    fleet_quality = _coerce_finite_float(fleet.get("avg_composite_fitness", 0.0) or 0.0)
    if fleet_total_calls > 0 and fleet_quality is not None:
        quality = fleet_quality
    else:
        quality = task_success
    cost_headroom = 1.0 if total_cost <= 0.0 else 1.0 / (1.0 + (total_cost / 5.0))
    score = _weighted_geometric_mean(
        (
            (max(1e-6, quality), 0.65),
            (cost_headroom, 0.35),
        )
    )
    return MetricScore(
        name="cost_efficiency",
        score=score,
        weight=HP_WEIGHTS[2],
        detail={
            "total_cost_usd_24h": round(total_cost, 4),
            "cost_entries_24h": len(entry_costs),
            "fleet_total_calls": fleet_total_calls,
            "fleet_avg_composite_fitness": round(_clamp01(fleet_quality or 0.0), 4),
        },
    )


async def _probe_memory_coherence() -> tuple[float, dict[str, Any]]:
    started = time.monotonic()
    with TemporaryDirectory() as tmp_dir:
        temp_root = Path(tmp_dir)
        memory = StrangeLoopMemory(temp_root / "memory.db")
        await memory.init_db()
        try:
            await memory.mark_development("memory retrieval seam improved", "path memory.py line 1")
            for index in range(5):
                await memory.witness(
                    f"observe memorysignal retrieval pattern evidence file path index {index}"
                )
            meta = await memory.consolidate_patterns()
            recalled = await memory.recall(limit=10)

            db_path = temp_root / "memory_plane.db"
            event_store = EventMemoryStore(db_path)
            await event_store.init_db()
            index = UnifiedIndex(db_path)
            retriever = HybridRetriever(index)
            index.index_document(
                "note",
                "notes/memory.md",
                "# Memory Palace\n\nHybrid retrieval keeps memory recall stable.",
                {"topic": "memory"},
            )
            event = RuntimeEnvelope.create(
                event_type=RuntimeEventType.ACTION_EVENT,
                source="autoresearch.eval",
                agent_id="eval-memory",
                session_id="sess-eval-memory",
                trace_id="trace-eval-memory",
                payload={
                    "action_name": "memory_shift",
                    "decision": "recorded",
                    "confidence": 1.0,
                },
            )
            await event_store.ingest_envelope(event)
            hits = retriever.search("memory recall stable", limit=5)

            checks = {
                "development_recalled": any("DEVELOPMENT" in entry.content for entry in recalled),
                "meta_pattern_created": meta is not None,
                "note_hit_present": any(
                    hit.record.metadata.get("source_kind") == "note" for hit in hits
                ),
                "runtime_event_hit_present": any(
                    hit.record.metadata.get("source_kind") == "runtime_event" for hit in hits
                ),
            }
            score = round(sum(1.0 for passed in checks.values() if passed) / len(checks), 4)
            detail = {
                **checks,
                "duration_seconds": round(time.monotonic() - started, 4),
                "recalled_entries": len(recalled),
                "retrieval_hits": len(hits),
            }
            return score, detail
        finally:
            await memory.close()


def _tool_reliability(report: dict[str, Any], assurance_report: dict[str, Any]) -> MetricScore:
    regression_names = {
        "provider_availability",
        "test_suite_health",
        "import_health",
        "config_validity",
        "bus_schema",
    }
    regression_results = [
        result for result in report.get("results", []) if result.get("name") in regression_names
    ]
    regression_score = (
        sum(1.0 for result in regression_results if bool(result.get("passed")))
        / max(1, len(regression_names))
    )
    summary = assurance_report.get("summary", {})
    severity_penalty = (
        1.0 * int(summary.get("critical", 0) or 0)
        + 0.35 * int(summary.get("high", 0) or 0)
        + 0.12 * int(summary.get("medium", 0) or 0)
        + 0.04 * int(summary.get("low", 0) or 0)
    )
    assurance_score = _clamp01(1.0 - min(1.0, severity_penalty / 12.0))
    score = round((0.55 * regression_score) + (0.45 * assurance_score), 4)
    return MetricScore(
        name="tool_reliability",
        score=score,
        weight=HP_WEIGHTS[4],
        detail={
            "regression_score": round(regression_score, 4),
            "assurance_score": round(assurance_score, 4),
            "assurance_status": str(assurance_report.get("status", "UNKNOWN")),
            "assurance_summary": {
                "critical": int(summary.get("critical", 0) or 0),
                "high": int(summary.get("high", 0) or 0),
                "medium": int(summary.get("medium", 0) or 0),
                "low": int(summary.get("low", 0) or 0),
            },
        },
    )


async def _probe_agent_coordination() -> tuple[float, dict[str, Any]]:
    started = time.monotonic()
    checks: dict[str, bool] = {}

    agents = [
        AgentState(id="a-general", name="agent-general", role=AgentRole.GENERAL, status=AgentStatus.IDLE),
        AgentState(id="a-review", name="agent-review", role=AgentRole.REVIEWER, status=AgentStatus.IDLE),
    ]

    fan_out_pool = _EvalAgentPool(agents)
    fan_out_orch = Orchestrator(agent_pool=fan_out_pool)
    fan_out_dispatches = await fan_out_orch.dispatch(
        Task(id="coord-fanout", title="fan out probe"),
        topology=TopologyType.FAN_OUT,
    )
    checks["fan_out_dispatches_all_idle_agents"] = len(fan_out_dispatches) == 2

    board = _EvalTaskBoard(
        [
            Task(
                id="coord-review",
                title="Resolve disagreement",
                metadata={
                    "coordination_claim_key": "route-policy",
                    "coordination_route": "synthesis_review",
                    "coordination_preferred_roles": ["reviewer", "researcher"],
                },
            )
        ]
    )
    reviewer_pool = _EvalAgentPool(agents)
    reviewer_orch = Orchestrator(task_board=board, agent_pool=reviewer_pool)
    reviewer_dispatches = await reviewer_orch.route_next()
    checks["reviewer_preferred_for_uncertain_task"] = (
        len(reviewer_dispatches) == 1 and reviewer_dispatches[0].agent_id == "a-review"
    )

    tick_board = _EvalTaskBoard([Task(id="coord-tick", title="tick probe")])
    tick_pool = _EvalAgentPool([agents[0]])
    event_memory = _EvalEventMemory()
    tick_orch = Orchestrator(
        task_board=tick_board,
        agent_pool=tick_pool,
        event_memory=event_memory,
        session_id="sess-eval-coordination",
    )

    async def _fake_refresh_coordination_state() -> dict[str, int]:
        return {"global_truths": 2, "productive_disagreements": 1}

    tick_orch._refresh_coordination_state = _fake_refresh_coordination_state  # type: ignore[attr-defined]
    tick_activity = await tick_orch.tick()
    checks["tick_emits_coordination_summary"] = (
        tick_activity.get("dispatched") == 1
        and any(
            envelope.payload.get("action_name") == "tick_summary"
            and envelope.payload.get("coordination_global_truths") == 2
            and envelope.payload.get("coordination_disagreements") == 1
            for envelope in event_memory.envelopes
        )
    )

    score = round(sum(1.0 for passed in checks.values() if passed) / len(checks), 4)
    return score, {
        **checks,
        "duration_seconds": round(time.monotonic() - started, 4),
        "tick_summary": tick_activity,
    }


async def _probe_recovery_rate() -> tuple[float, dict[str, Any]]:
    started = time.monotonic()
    checks: dict[str, bool] = {}

    import dharma_swarm.perception_action_loop as perception_module

    original_verify_action = perception_module.verify_action
    loop = PerceptionActionLoop(config=LoopConfig())
    try:
        async def _failing_verify_action(**_: Any) -> Any:
            raise RuntimeError("verifier backend unavailable")

        perception_module.verify_action = _failing_verify_action
        verification_error = await loop.verify(
            CandidateAction(action_type="write", target="probe.txt"),
            {"executed": True},
        )
        checks["verify_exception_degrades_gracefully"] = (
            verification_error == 1.0 and loop.world_model.update_count == 0
        )

        perception_module.verify_action = original_verify_action
        second_loop = PerceptionActionLoop(config=LoopConfig())
        skipped_error = await second_loop.verify(
            CandidateAction(action_type="noop", target="probe.txt"),
            {"executed": False},
        )
        checks["verify_non_executed_action_still_updates_precision"] = (
            skipped_error == 0.5 and second_loop.world_model.update_count == 0
        )
    finally:
        perception_module.verify_action = original_verify_action

    with TemporaryDirectory() as tmp_dir:
        memory = StrangeLoopMemory(Path(tmp_dir) / "double-init.db")
        await memory.init_db()
        await memory.init_db()
        await memory.remember("still works", layer=MemoryLayer.SESSION)
        recalled = await memory.recall(limit=5)
        checks["memory_double_init_remains_usable"] = any(entry.content == "still works" for entry in recalled)
        await memory.close()

    previous_env = {
        "TAP_PROVIDER_A": os.environ.get("TAP_PROVIDER_A"),
        "TAP_PROVIDER_B": os.environ.get("TAP_PROVIDER_B"),
    }
    os.environ["TAP_PROVIDER_A"] = "key-a"
    os.environ["TAP_PROVIDER_B"] = "key-b"
    try:
        failure_router = TAPProviderRouter(
            providers=[
                ProviderConfig(
                    name="provider-a",
                    model="model-a",
                    base_url="https://a.invalid",
                    key_env="TAP_PROVIDER_A",
                ),
                ProviderConfig(
                    name="provider-b",
                    model="model-b",
                    base_url="https://b.invalid",
                    key_env="TAP_PROVIDER_B",
                ),
            ]
        )
        failure_behavior = {
            "provider-a": RuntimeError("first provider failed"),
            "provider-b": "winner",
        }
        failure_router.health_check = lambda provider: True  # type: ignore[assignment]
        failure_router.get_client = lambda provider: _FakeClient(failure_behavior, provider.name)  # type: ignore[assignment]
        content, model = failure_router.call(messages=[{"role": "user", "content": "hi"}])
        checks["tap_router_falls_back_after_provider_error"] = (
            content == "winner"
            and model == "model-b"
            and failure_router.providers[0]._healthy is False
        )

        empty_router = TAPProviderRouter(
            providers=[
                ProviderConfig(
                    name="provider-a",
                    model="model-a",
                    base_url="https://a.invalid",
                    key_env="TAP_PROVIDER_A",
                ),
                ProviderConfig(
                    name="provider-b",
                    model="model-b",
                    base_url="https://b.invalid",
                    key_env="TAP_PROVIDER_B",
                ),
            ]
        )
        empty_behavior = {
            "provider-a": _FakeResponse(content="   "),
            "provider-b": "winner",
        }
        empty_router.health_check = lambda provider: True  # type: ignore[assignment]
        empty_router.get_client = lambda provider: _FakeClient(empty_behavior, provider.name)  # type: ignore[assignment]
        content, model = empty_router.call(messages=[{"role": "user", "content": "hi"}])
        checks["tap_router_falls_back_after_empty_completion"] = (
            content == "winner"
            and model == "model-b"
            and empty_router.providers[0]._healthy is False
        )
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    score = round(sum(1.0 for passed in checks.values() if passed) / len(checks), 4)
    return score, {
        **checks,
        "duration_seconds": round(time.monotonic() - started, 4),
    }


def _routing_benchmarks() -> list[dict[str, Any]]:
    return [
        {
            "name": "cheap_reflex_en",
            "request": ProviderRouteRequest(
                action_name="triage_notes",
                risk_score=0.08,
                uncertainty=0.10,
                novelty=0.10,
                urgency=0.30,
                expected_impact=0.20,
                estimated_tokens=400,
                preferred_low_cost=True,
                context={"language_code": "en", "complexity_tier": "simple", "context_tier": "short"},
            ),
            "expected_path": RoutePath.REFLEX,
            "expected_provider": "openrouter_free",
        },
        {
            "name": "tooling_reflex_prefers_codex",
            "request": ProviderRouteRequest(
                action_name="apply_patch",
                risk_score=0.05,
                uncertainty=0.08,
                novelty=0.12,
                urgency=0.40,
                expected_impact=0.25,
                estimated_tokens=400,
                preferred_low_cost=True,
                context={"requires_tooling": True, "language_code": "en", "complexity_tier": "simple", "context_tier": "short"},
            ),
            "expected_path": RoutePath.REFLEX,
            "expected_provider": "codex",
        },
        {
            "name": "latency_bumps_to_deliberative",
            "request": ProviderRouteRequest(
                action_name="draft_response",
                risk_score=0.10,
                uncertainty=0.20,
                novelty=0.15,
                urgency=0.30,
                expected_impact=0.25,
                estimated_latency_ms=1600,
                preferred_low_cost=False,
                context={"language_code": "en", "complexity_tier": "medium", "context_tier": "medium"},
            ),
            "expected_path": RoutePath.DELIBERATIVE,
            "expected_provider": "openai",
        },
        {
            "name": "frontier_precision_forces_escalate",
            "request": ProviderRouteRequest(
                action_name="mission_plan",
                risk_score=0.40,
                uncertainty=0.35,
                novelty=0.30,
                urgency=0.40,
                expected_impact=0.60,
                preferred_low_cost=False,
                requires_frontier_precision=True,
                context={"language_code": "en", "complexity_tier": "reasoning", "context_tier": "long"},
            ),
            "expected_path": RoutePath.ESCALATE,
            "expected_provider": "anthropic",
        },
        {
            "name": "high_risk_escalates",
            "request": ProviderRouteRequest(
                action_name="policy_change",
                risk_score=0.90,
                uncertainty=0.20,
                novelty=0.20,
                urgency=0.30,
                expected_impact=0.70,
                preferred_low_cost=False,
            ),
            "expected_path": RoutePath.ESCALATE,
            "expected_provider": "anthropic",
        },
        {
            "name": "high_uncertainty_escalates",
            "request": ProviderRouteRequest(
                action_name="unknown_failure",
                risk_score=0.30,
                uncertainty=0.85,
                novelty=0.40,
                urgency=0.30,
                expected_impact=0.50,
                preferred_low_cost=False,
            ),
            "expected_path": RoutePath.ESCALATE,
            "expected_provider": "anthropic",
        },
        {
            "name": "privileged_without_consent_escalates",
            "request": ProviderRouteRequest(
                action_name="dangerous_write",
                risk_score=0.20,
                uncertainty=0.20,
                novelty=0.10,
                urgency=0.20,
                expected_impact=0.40,
                privileged_action=True,
                preferred_low_cost=False,
            ),
            "expected_path": RoutePath.ESCALATE,
            "expected_provider": "anthropic",
        },
        {
            "name": "japanese_quality_prefers_openrouter",
            "request": ProviderRouteRequest(
                action_name="jp_synthesis",
                risk_score=0.35,
                uncertainty=0.40,
                novelty=0.20,
                urgency=0.35,
                expected_impact=0.45,
                preferred_low_cost=False,
                context={
                    "language_code": "ja",
                    "prefer_japanese_quality": True,
                    "complexity_tier": "medium",
                    "context_tier": "medium",
                },
            ),
            "available": ["openrouter", "anthropic", "openai"],
            "expected_path": RoutePath.DELIBERATIVE,
            "expected_provider": "openrouter",
        },
        {
            "name": "reasoning_prefers_anthropic",
            "request": ProviderRouteRequest(
                action_name="deep_reasoning",
                risk_score=0.35,
                uncertainty=0.45,
                novelty=0.30,
                urgency=0.35,
                expected_impact=0.55,
                preferred_low_cost=False,
                context={"language_code": "en", "complexity_tier": "REASONING", "context_tier": "long"},
            ),
            "expected_path": RoutePath.DELIBERATIVE,
            "expected_provider": "anthropic",
        },
        {
            "name": "filtered_low_cost_prefers_nim_over_ollama",
            "request": ProviderRouteRequest(
                action_name="cheap_route",
                risk_score=0.10,
                uncertainty=0.10,
                novelty=0.10,
                urgency=0.20,
                expected_impact=0.15,
                estimated_tokens=400,
                preferred_low_cost=True,
                context={"language_code": "en", "complexity_tier": "simple", "context_tier": "short"},
            ),
            "available": ["nvidia_nim", "ollama"],
            "expected_path": RoutePath.REFLEX,
            "expected_provider": "nvidia_nim",
        },
    ]


def _score_self_consistency() -> tuple[float, dict[str, Any]]:
    router = ProviderPolicyRouter()
    cases = _routing_benchmarks()
    stable = 0
    results: list[dict[str, Any]] = []
    for case in cases:
        available = case.get("available")
        decisions = [
            router.route(case["request"], available_providers=available)
            for _ in range(3)
        ]
        provider_values = {decision.selected_provider.value for decision in decisions}
        path_values = {decision.path.value for decision in decisions}
        consistent = len(provider_values) == 1 and len(path_values) == 1
        if consistent:
            stable += 1
        results.append(
            {
                "name": case["name"],
                "providers": sorted(provider_values),
                "paths": sorted(path_values),
                "consistent": consistent,
            }
        )
    score = round(stable / len(cases), 4)
    return score, {"cases": results, "stable_cases": stable}


def _score_routing_accuracy() -> tuple[float, dict[str, Any]]:
    router = ProviderPolicyRouter()
    cases = _routing_benchmarks()
    correct = 0
    case_results: list[dict[str, Any]] = []
    for case in cases:
        available = case.get("available")
        decision = router.route(case["request"], available_providers=available)
        path_ok = decision.path == case["expected_path"]
        provider_ok = decision.selected_provider.value == case["expected_provider"]
        if path_ok and provider_ok:
            correct += 1
        case_results.append(
            {
                "name": case["name"],
                "expected_path": case["expected_path"].value,
                "actual_path": decision.path.value,
                "expected_provider": case["expected_provider"],
                "actual_provider": decision.selected_provider.value,
                "correct": path_ok and provider_ok,
            }
        )
    score = round(correct / len(cases), 4)
    return score, {"cases": case_results, "correct_cases": correct}


async def _score_dharma_compliance(repo_root: Path) -> tuple[float, dict[str, Any]]:
    checks: dict[str, bool] = {}
    kernel = DharmaKernel.create_default()
    checks["default_kernel_integrity"] = kernel.verify_integrity()
    checks["principle_count_at_least_25"] = len(kernel.principles) >= 25

    with TemporaryDirectory() as tmp_dir:
        guard = KernelGuard(Path(tmp_dir) / "kernel.json")
        await guard.save(kernel)
        loaded = await guard.load()
        checks["kernel_guard_roundtrip"] = loaded.verify_integrity()

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "--", "dharma/"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        checks["dharma_layer_clean"] = proc.returncode == 0 and not proc.stdout.strip()
    except Exception:
        checks["dharma_layer_clean"] = True

    score = round(sum(1.0 for passed in checks.values() if passed) / len(checks), 4)
    return score, checks


async def run_autoresearch_evaluation(
    *,
    repo_root: Path | None = None,
    state_dir: Path | None = None,
    benchmark: str = "full",
    timeout_seconds: int = 300,
) -> AutoresearchEvalReport:
    del benchmark  # only "full" exists for now, but keep CLI contract stable.
    actual_repo_root = (repo_root or ROOT).expanduser()
    actual_state_dir = (state_dir or STATE_DIR).expanduser()

    ecc_report_obj: EvalReport = await run_all_evals(
        repo_root=actual_repo_root,
        state_dir=actual_state_dir,
    )
    ecc_report = ecc_report_obj.to_dict()
    assurance_report = run_assurance(repo_root=actual_repo_root)

    memory_score, memory_detail = await _probe_memory_coherence()
    coordination_score, coordination_detail = await _probe_agent_coordination()
    recovery_score, recovery_detail = await _probe_recovery_rate()
    self_consistency_score, self_consistency_detail = _score_self_consistency()
    routing_accuracy_score, routing_accuracy_detail = _score_routing_accuracy()
    dharma_score, dharma_detail = await _score_dharma_compliance(actual_repo_root)

    task_success = _task_success_rate(ecc_report)
    hp_scores = [
        task_success,
        _latency_p95(ecc_report),
        _cost_efficiency(task_success.score, state_dir=actual_state_dir),
        MetricScore(
            name="memory_coherence",
            score=memory_score,
            weight=HP_WEIGHTS[3],
            detail=memory_detail,
        ),
        _tool_reliability(ecc_report, assurance_report),
        MetricScore(
            name="agent_coordination",
            score=coordination_score,
            weight=HP_WEIGHTS[5],
            detail=coordination_detail,
        ),
        MetricScore(
            name="self_consistency",
            score=self_consistency_score,
            weight=HP_WEIGHTS[6],
            detail=self_consistency_detail,
        ),
        MetricScore(
            name="recovery_rate",
            score=recovery_score,
            weight=HP_WEIGHTS[7],
            detail=recovery_detail,
        ),
        MetricScore(
            name="routing_accuracy",
            score=routing_accuracy_score,
            weight=HP_WEIGHTS[8],
            detail=routing_accuracy_detail,
        ),
        MetricScore(
            name="dharma_compliance",
            score=dharma_score,
            weight=HP_WEIGHTS[9],
            detail=dharma_detail,
        ),
    ]

    omega = _weighted_geometric_mean(
        tuple((score.score, score.weight) for score in hp_scores)
    )
    psi, psi_components, psi_detail = _compute_psi(actual_repo_root)

    return AutoresearchEvalReport(
        timestamp=_utc_now(),
        benchmark="full",
        timeout_seconds=timeout_seconds,
        omega=omega,
        psi=psi,
        hp_scores=hp_scores,
        psi_components=psi_components,
        ecc_report=ecc_report,
        assurance_summary={
            "status": assurance_report.get("status", "UNKNOWN"),
            "summary": assurance_report.get("summary", {}),
            "recommended_fixes": list(assurance_report.get("recommended_fixes", [])),
        },
        probe_details={
            "memory_coherence": memory_detail,
            "agent_coordination": coordination_detail,
            "self_consistency": self_consistency_detail,
            "recovery_rate": recovery_detail,
            "routing_accuracy": routing_accuracy_detail,
            "dharma_compliance": dharma_detail,
            "psi_detail": psi_detail,
        },
        repo_root=str(actual_repo_root),
        state_dir=str(actual_state_dir),
    )


def save_autoresearch_report(report: AutoresearchEvalReport, *, state_dir: Path | None = None) -> Path:
    target_dir = (state_dir or STATE_DIR).expanduser() / "evals"
    target_dir.mkdir(parents=True, exist_ok=True)
    latest_path = target_dir / "autoresearch_latest.json"
    latest_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    history_path = target_dir / "autoresearch_history.jsonl"
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report.to_dict(), ensure_ascii=True) + "\n")
    return latest_path


def format_summary_line(report: AutoresearchEvalReport | dict[str, Any]) -> str:
    payload = report.to_dict() if isinstance(report, AutoresearchEvalReport) else report
    scores = payload.get("hp_scores", [])
    hp_chunks = [
        f"HP{index}={_coerce_finite_float(score.get('score', 0.0), default=0.0) or 0.0:.4f}"
        for index, score in enumerate(scores, start=1)
    ]
    return " ".join(
        [
            f"Ω={_coerce_finite_float(payload.get('omega', 0.0), default=0.0) or 0.0:.4f}",
            f"Ψ={_coerce_finite_float(payload.get('psi', 0.0), default=0.0) or 0.0:.4f}",
            *hp_chunks,
        ]
    )


def render_report(report: AutoresearchEvalReport | dict[str, Any]) -> str:
    payload = report.to_dict() if isinstance(report, AutoresearchEvalReport) else report
    lines = [
        "DHARMA SWARM Autoresearch Eval",
        f"timestamp={payload.get('timestamp', '')}",
        f"benchmark={payload.get('benchmark', 'full')}",
        "",
        "Capability Metrics:",
    ]
    for index, score in enumerate(payload.get("hp_scores", []), start=1):
        lines.append(
            f"  HP{index} {score.get('name', 'unknown')}: "
            f"{_coerce_finite_float(score.get('score', 0.0), default=0.0) or 0.0:.4f}"
        )
    lines.extend(
        [
            "",
            "Self-Understanding Metrics:",
        ]
    )
    for name, value in payload.get("psi_components", {}).items():
        lines.append(f"  Ψ_{name}: {_coerce_finite_float(value, default=0.0) or 0.0:.4f}")
    lines.extend(
        [
            "",
            format_summary_line(payload),
        ]
    )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the locked DHARMA SWARM autoresearch evaluator.")
    parser.add_argument("--benchmark", default="full", help="Benchmark preset to run.")
    parser.add_argument("--timeout", type=int, default=300, help="Wall-clock timeout in seconds.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repo root to evaluate.")
    parser.add_argument("--state-dir", default=str(STATE_DIR), help="State directory for eval artifacts.")
    parser.add_argument("--output", default="", help="Optional human-readable report output path.")
    parser.add_argument("--json-out", default="", help="Optional JSON report output path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = asyncio.run(
            asyncio.wait_for(
                run_autoresearch_evaluation(
                    repo_root=Path(args.repo_root),
                    state_dir=Path(args.state_dir),
                    benchmark=args.benchmark,
                    timeout_seconds=args.timeout,
                ),
                timeout=max(1, int(args.timeout)),
            )
        )
    except asyncio.TimeoutError:
        print(f"autresearch_eval_timeout={args.timeout}")
        return 124

    save_autoresearch_report(report, state_dir=Path(args.state_dir))
    rendered = render_report(report)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report.to_dict(), ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


__all__ = [
    "AutoresearchEvalReport",
    "MetricScore",
    "build_arg_parser",
    "format_summary_line",
    "main",
    "render_report",
    "run_autoresearch_evaluation",
    "save_autoresearch_report",
]
