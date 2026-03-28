"""Behavioral output evaluation and lightweight quality analytics."""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.auto_grade.engine import AutoGradeEngine
from dharma_swarm.auto_grade.models import RewardSignal
from dharma_swarm.auto_research.models import ResearchReport, SourceDocument
from dharma_swarm.epistemic_telemetry import analyze_output
from dharma_swarm.metrics import MetricsAnalyzer
from dharma_swarm.models import ProviderType, Task

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
        "your",
    }
)
_FAILURE_MARKERS = (
    "error:",
    "failed",
    "i can't",
    "i cannot",
    "not sure",
    "timeout",
    "unable to",
)
_HEDGE_MARKERS = (
    "i think",
    "i guess",
    "maybe",
    "might",
    "not sure",
    "probably",
)
_ACTION_MARKERS = (
    "next",
    "run",
    "update",
    "verify",
    "write",
    "check",
)
_CODE_MARKERS = (
    "```",
    ".py",
    "def ",
    "class ",
    "pytest",
    "apply_patch",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_provider(provider: ProviderType | str) -> str:
    if isinstance(provider, ProviderType):
        return provider.value
    return str(provider).strip().lower() or "unknown"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_./-]+", text.lower())


def _keyword_set(text: str) -> set[str]:
    return {
        token
        for token in _tokenize(text)
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _looks_like_failure(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _FAILURE_MARKERS)


def _infer_task_type(task: Task) -> str:
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    explicit = metadata.get("task_type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    lowered = "\n".join(part for part in (task.title, task.description) if part).lower()
    if any(marker in lowered for marker in ("bug", "code", "edit", "file", "module", "test")):
        return "code"
    if any(marker in lowered for marker in ("paper", "research", "analyze", "investigate", "compare")):
        return "research"
    if any(marker in lowered for marker in ("deploy", "health", "monitor", "restart", "status")):
        return "ops"
    return "general"


def _line_repetition_penalty(text: str) -> float:
    lines = [line.strip().lower() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return 0.0
    unique_ratio = len(set(lines)) / len(lines)
    return _clamp01(1.0 - unique_ratio)


def _has_structured_output(text: str) -> bool:
    if "```" in text:
        return True
    if re.search(r"(^|\n)(- |\* |\d+\.)", text):
        return True
    if re.search(r"(?:^|\s)[\w./-]+\.(?:py|md|json|yaml|toml)\b", text):
        return True
    return False


@dataclass(slots=True)
class OutputEvaluation:
    """Normalized quality evaluation for one task result."""

    task_id: str
    task_title: str
    task_type: str
    agent_name: str
    provider: str
    model: str
    relevance: float
    correctness: float
    completeness: float
    conciseness: float
    actionability: float
    grounding_score: float
    issue_count: int
    issue_kinds: list[str]
    failure_class: str
    token_count: int
    latency_ms: int
    estimated_cost_usd: float
    success: bool
    judge_provider: str
    judge_strategy: str = "heuristic"
    timestamp: str = field(default_factory=lambda: _utc_now().isoformat())

    @property
    def quality_score(self) -> float:
        return _clamp01(
            (self.relevance * 0.24)
            + (self.correctness * 0.26)
            + (self.completeness * 0.20)
            + (self.conciseness * 0.12)
            + (self.actionability * 0.18)
        )

    @property
    def efficiency(self) -> float:
        return self.quality_score / max(self.estimated_cost_usd, 0.001)

    def to_record(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "task_type": self.task_type,
            "agent_name": self.agent_name,
            "provider": self.provider,
            "model": self.model,
            "relevance": self.relevance,
            "correctness": self.correctness,
            "completeness": self.completeness,
            "conciseness": self.conciseness,
            "actionability": self.actionability,
            "grounding_score": self.grounding_score,
            "issue_count": self.issue_count,
            "issue_kinds": list(self.issue_kinds),
            "failure_class": self.failure_class,
            "token_count": self.token_count,
            "latency_ms": self.latency_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "success": self.success,
            "judge_provider": self.judge_provider,
            "judge_strategy": self.judge_strategy,
            "timestamp": self.timestamp,
            "quality_score": self.quality_score,
            "efficiency": self.efficiency,
        }

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> "OutputEvaluation":
        return cls(
            task_id=str(data.get("task_id", "")),
            task_title=str(data.get("task_title", "")),
            task_type=str(data.get("task_type", "general") or "general"),
            agent_name=str(data.get("agent_name", "")),
            provider=str(data.get("provider", "unknown") or "unknown"),
            model=str(data.get("model", "unknown") or "unknown"),
            relevance=_clamp01(float(data.get("relevance", 0.0))),
            correctness=_clamp01(float(data.get("correctness", 0.0))),
            completeness=_clamp01(float(data.get("completeness", 0.0))),
            conciseness=_clamp01(float(data.get("conciseness", 0.0))),
            actionability=_clamp01(float(data.get("actionability", 0.0))),
            grounding_score=_clamp01(float(data.get("grounding_score", 1.0))),
            issue_count=max(0, int(data.get("issue_count", 0) or 0)),
            issue_kinds=[
                str(item)
                for item in list(data.get("issue_kinds", []) or [])
                if str(item).strip()
            ],
            failure_class=str(data.get("failure_class", "") or ""),
            token_count=max(0, int(data.get("token_count", 0) or 0)),
            latency_ms=max(0, int(data.get("latency_ms", 0) or 0)),
            estimated_cost_usd=max(0.0, float(data.get("estimated_cost_usd", 0.0) or 0.0)),
            success=bool(data.get("success", False)),
            judge_provider=str(data.get("judge_provider", "unknown") or "unknown"),
            judge_strategy=str(data.get("judge_strategy", "heuristic") or "heuristic"),
            timestamp=str(data.get("timestamp", _utc_now().isoformat())),
        )


@dataclass(slots=True)
class AgentScore:
    """Aggregate leaderboard row for one agent."""

    agent_name: str
    runs: int
    mean_quality: float
    mean_efficiency: float
    mean_latency_ms: float


@dataclass(slots=True)
class ModelScore:
    """Aggregate quality summary for one model."""

    model: str
    runs: int
    mean_quality: float
    mean_efficiency: float
    mean_latency_ms: float


class OutputEvaluator:
    """Persist and summarize output-quality evaluations."""

    def __init__(
        self,
        evaluations_path: Path | None = None,
        *,
        judge_provider: ProviderType | str = ProviderType.OLLAMA,
    ) -> None:
        self.evaluations_path = evaluations_path or (Path.home() / ".dharma" / "evaluations.jsonl")
        self.judge_provider = _normalize_provider(judge_provider)
        self._metrics = MetricsAnalyzer()

    async def evaluate(
        self,
        task: Task,
        output: str,
        *,
        agent_name: str,
        provider: ProviderType | str,
        model: str,
        latency_ms: float = 0.0,
        estimated_cost_usd: float = 0.0,
        success: bool | None = None,
        token_count: int | None = None,
        judge_provider: ProviderType | str | None = None,
    ) -> OutputEvaluation:
        """Score an output, append it to the JSONL log, and return the record."""

        task_type = _infer_task_type(task)
        normalized_output = output or ""
        workspace_roots = []
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        raw_roots = metadata.get("workspace_roots") or metadata.get("grounding_roots") or []
        if isinstance(raw_roots, list):
            workspace_roots = [value for value in raw_roots if str(value).strip()]
        diagnostics = analyze_output(normalized_output, workspace_roots=workspace_roots)
        inferred_success = not _looks_like_failure(normalized_output)
        resolved_success = inferred_success if success is None else bool(success and inferred_success)
        if diagnostics.has_blocking_issue:
            resolved_success = False
        signature = self._metrics.analyze(normalized_output)
        task_keywords = _keyword_set(f"{task.title}\n{task.description}")
        output_keywords = _keyword_set(normalized_output)
        overlap = len(task_keywords & output_keywords) / max(1, len(task_keywords))
        structured = 1.0 if _has_structured_output(normalized_output) else 0.0
        word_count = len(normalized_output.split())
        hedged = any(marker in normalized_output.lower() for marker in _HEDGE_MARKERS)
        actionable_hits = sum(
            1
            for marker in _ACTION_MARKERS
            if marker in normalized_output.lower()
        )
        actionable_hits += 1 if structured else 0
        actionable_hits += 1 if re.search(r"(?:^|\s)(?:pytest|python|git|curl|make)\b", normalized_output) else 0

        relevance = _clamp01(0.10 + (0.70 * overlap) + (0.10 * structured) + (0.10 if resolved_success else 0.0))
        if task_type == "code" and any(marker in normalized_output for marker in _CODE_MARKERS):
            relevance = _clamp01(relevance + 0.10)

        correctness = 0.18 if not resolved_success else 0.52
        correctness += 0.12 * structured
        correctness += 0.10 * max(0.0, 1.0 - signature.identity_stability)
        correctness += 0.08 * max(0.0, 1.0 - signature.self_reference_density)
        if signature.recognition_type.value == "MIMICRY":
            correctness -= 0.12
        if hedged:
            correctness -= 0.16
        correctness -= max(0.0, 1.0 - diagnostics.grounding_score) * 0.45
        if task_type == "code" and any(marker in normalized_output for marker in _CODE_MARKERS):
            correctness += 0.10
        correctness = _clamp01(correctness)

        completeness = 0.08 if not normalized_output.strip() else (0.30 if resolved_success else 0.14)
        if word_count >= 30:
            completeness += 0.16
        if word_count >= 120:
            completeness += 0.12
        if structured:
            completeness += 0.12
        if any(marker in normalized_output.lower() for marker in ("todo", "follow up", "later", "not sure")):
            completeness -= 0.18
        completeness = _clamp01(completeness)

        conciseness = 0.0
        if word_count:
            if word_count < 8:
                conciseness = 0.24
            elif word_count <= 220:
                conciseness = 0.86
            elif word_count <= 500:
                conciseness = 0.68
            else:
                conciseness = 0.44
            conciseness -= 0.22 * _line_repetition_penalty(normalized_output)
            if signature.recognition_type.value == "MIMICRY":
                conciseness -= 0.12
        conciseness = _clamp01(conciseness)

        actionability = (0.08 if normalized_output.strip() else 0.0) + (0.12 * actionable_hits)
        if task_type == "code" and structured:
            actionability += 0.10
        if hedged:
            actionability -= 0.10
        if diagnostics.issue_count:
            actionability -= min(0.18, diagnostics.issue_count * 0.04)
        actionability = _clamp01(actionability)

        evaluation = OutputEvaluation(
            task_id=task.id,
            task_title=task.title,
            task_type=task_type,
            agent_name=agent_name,
            provider=_normalize_provider(provider),
            model=str(model or "unknown"),
            relevance=relevance,
            correctness=correctness,
            completeness=completeness,
            conciseness=conciseness,
            actionability=actionability,
            grounding_score=diagnostics.grounding_score,
            issue_count=diagnostics.issue_count,
            issue_kinds=[issue.kind.value for issue in diagnostics.issues],
            failure_class=diagnostics.failure_class,
            token_count=max(1, int(token_count or 0)) if normalized_output.strip() else max(0, int(token_count or 0)),
            latency_ms=max(0, int(latency_ms)),
            estimated_cost_usd=max(0.0, float(estimated_cost_usd)),
            success=resolved_success,
            judge_provider=_normalize_provider(judge_provider or self.judge_provider),
        )
        if evaluation.token_count == 0 and normalized_output.strip():
            evaluation.token_count = max(1, len(normalized_output.split()))

        await self._append(evaluation)
        return evaluation

    async def read_all(self) -> list[OutputEvaluation]:
        """Load every persisted evaluation record."""

        if not self.evaluations_path.exists():
            return []

        def _load_sync() -> list[OutputEvaluation]:
            rows: list[OutputEvaluation] = []
            with open(self.evaluations_path, encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(OutputEvaluation.from_record(json.loads(line)))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
            return rows

        return await asyncio.to_thread(_load_sync)

    async def leaderboard(self) -> list[AgentScore]:
        """Aggregate evaluations by agent."""

        grouped: dict[str, list[OutputEvaluation]] = defaultdict(list)
        for evaluation in await self.read_all():
            grouped[evaluation.agent_name].append(evaluation)

        results = [
            AgentScore(
                agent_name=agent_name,
                runs=len(entries),
                mean_quality=sum(entry.quality_score for entry in entries) / len(entries),
                mean_efficiency=sum(entry.efficiency for entry in entries) / len(entries),
                mean_latency_ms=sum(entry.latency_ms for entry in entries) / len(entries),
            )
            for agent_name, entries in grouped.items()
        ]
        return sorted(results, key=lambda item: (-item.mean_quality, item.agent_name))

    async def compare_models(self, *, task_type: str | None = None) -> list[ModelScore]:
        """Aggregate evaluations by model, optionally filtered by task type."""

        grouped: dict[str, list[OutputEvaluation]] = defaultdict(list)
        for evaluation in await self.read_all():
            if task_type and evaluation.task_type != task_type:
                continue
            grouped[evaluation.model].append(evaluation)

        results = [
            ModelScore(
                model=model,
                runs=len(entries),
                mean_quality=sum(entry.quality_score for entry in entries) / len(entries),
                mean_efficiency=sum(entry.efficiency for entry in entries) / len(entries),
                mean_latency_ms=sum(entry.latency_ms for entry in entries) / len(entries),
            )
            for model, entries in grouped.items()
        ]
        return sorted(results, key=lambda item: (-item.mean_quality, item.model))

    async def model_comparison(self, *, task_type: str | None = None) -> dict[str, float]:
        """Return mean quality by model for quick lookups and automation."""

        summary = await self.compare_models(task_type=task_type)
        return {row.model: row.mean_quality for row in summary}

    async def _append(self, evaluation: OutputEvaluation) -> None:
        def _write_sync() -> None:
            self.evaluations_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.evaluations_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(evaluation.to_record(), sort_keys=True) + "\n")

        await asyncio.to_thread(_write_sync)


class ResearchEvaluator:
    """Thin integration wrapper that routes research reports through AutoGrade."""

    def __init__(self, grader: AutoGradeEngine | None = None) -> None:
        self.grader = grader or AutoGradeEngine()

    def evaluate(
        self,
        report: ResearchReport,
        sources: list[SourceDocument],
        **kwargs: Any,
    ) -> RewardSignal:
        return self.grader.grade(report, sources, **kwargs)
