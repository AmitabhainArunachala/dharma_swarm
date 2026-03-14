"""Epistemic telemetry, grounding checks, and provider probe journaling."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


_CLAIM_VERB_RE = re.compile(
    r"\b(?:created?|updated?|modified?|wrote|write|added?|generated?|saved?|patched?|edited?)\b",
    re.IGNORECASE,
)
_PATH_TOKEN_RE = re.compile(
    r"(~?/[\w./-]+\.[A-Za-z0-9]+|(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+|[\w.-]+\.(?:py|md|json|yaml|yml|toml|txt|csv|ts|tsx|js|jsx|sh|sql|ini|cfg|lock))"
)
_TIMEOUT_RE = re.compile(r"\b(?:timed out|timeout|exceeded limit)\b", re.IGNORECASE)
_PROVIDER_ERROR_RE = re.compile(
    r"^(?:error|http error|nvidia nim error|ollama error|openrouter error|provider returned)",
    re.IGNORECASE,
)
_SHELL_LINE_RE = re.compile(r"^\s*(?:[$#>]|(?:bash|sh|zsh)\s+-c\b)")


class EpistemicIssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EpistemicIssueKind(str, Enum):
    EMPTY_RESPONSE = "empty_response"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    MISSING_FILE_CLAIM = "missing_file_claim"
    SHELL_THEATER = "shell_theater"
    PRIMARY_COUNCIL_MISSING = "primary_council_missing"
    COUNCIL_TIMEOUT = "council_timeout"
    TASK_FAILURE = "task_failure"
    PROVIDER_PROBE_FAILURE = "provider_probe_failure"


class OutputIssue(BaseModel):
    kind: EpistemicIssueKind
    severity: EpistemicIssueSeverity
    summary: str
    evidence: str = ""
    related_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutputDiagnostics(BaseModel):
    issues: list[OutputIssue] = Field(default_factory=list)
    grounding_score: float = 1.0
    failure_class: str = ""
    summary: str = ""
    referenced_paths: list[str] = Field(default_factory=list)
    missing_paths: list[str] = Field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def has_blocking_issue(self) -> bool:
        return any(
            issue.severity in {EpistemicIssueSeverity.ERROR, EpistemicIssueSeverity.CRITICAL}
            for issue in self.issues
        )


class EpistemicIncident(BaseModel):
    incident_id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=_utc_now_iso)
    component: str
    kind: EpistemicIssueKind
    severity: EpistemicIssueSeverity
    summary: str
    evidence: str = ""
    related_path: str = ""
    agent_name: str = ""
    provider: str = ""
    model: str = ""
    task_id: str = ""
    task_title: str = ""
    cycle_id: str = ""
    success: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderProbeRecord(BaseModel):
    probe_id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=_utc_now_iso)
    source: str = "provider_smoke"
    provider: str
    status: str
    model: str = ""
    configured_model: str = ""
    strongest_verified: str = ""
    deployment_mode: str = ""
    base_url: str = ""
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def _coerce_workspace_roots(
    workspace_roots: Sequence[str | Path] | None,
) -> list[Path]:
    if not workspace_roots:
        return []
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in workspace_roots:
        text = str(raw).strip()
        if not text:
            continue
        root = Path(text).expanduser()
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        roots.append(root)
    return roots


def _extract_path_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        token = match.group(0).strip("`'\".,:;()[]{}")
        if not token or token.startswith(("http://", "https://")):
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _resolve_claimed_path(token: str, workspace_roots: Sequence[Path]) -> Path | None:
    candidate = Path(token).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for root in workspace_roots:
        resolved = (root / candidate).resolve(strict=False)
        if resolved.exists():
            return resolved
    return None


def analyze_output(
    output: str,
    *,
    workspace_roots: Sequence[str | Path] | None = None,
) -> OutputDiagnostics:
    """Heuristically score whether an output is grounded in real artifacts."""

    normalized = (output or "").strip()
    roots = _coerce_workspace_roots(workspace_roots)
    issues: list[OutputIssue] = []
    referenced_paths: list[str] = []
    missing_paths: list[str] = []

    if not normalized:
        issues.append(
            OutputIssue(
                kind=EpistemicIssueKind.EMPTY_RESPONSE,
                severity=EpistemicIssueSeverity.CRITICAL,
                summary="Provider returned an empty response.",
            )
        )
    else:
        first_line = normalized.splitlines()[0].strip()
        if _PROVIDER_ERROR_RE.match(first_line):
            issues.append(
                OutputIssue(
                    kind=EpistemicIssueKind.PROVIDER_ERROR,
                    severity=EpistemicIssueSeverity.CRITICAL,
                    summary="Provider returned an explicit error payload.",
                    evidence=first_line[:240],
                )
            )
        elif _TIMEOUT_RE.search(normalized):
            issues.append(
                OutputIssue(
                    kind=EpistemicIssueKind.TIMEOUT,
                    severity=EpistemicIssueSeverity.CRITICAL,
                    summary="Execution timed out or exceeded its runtime budget.",
                    evidence=first_line[:240],
                )
            )

    if roots:
        for line in normalized.splitlines():
            if not _CLAIM_VERB_RE.search(line):
                continue
            for token in _extract_path_tokens(line):
                resolved = _resolve_claimed_path(token, roots)
                if resolved is not None:
                    referenced_paths.append(str(resolved))
                    continue
                missing_paths.append(token)
                issues.append(
                    OutputIssue(
                        kind=EpistemicIssueKind.MISSING_FILE_CLAIM,
                        severity=EpistemicIssueSeverity.ERROR,
                        summary=f"Output claimed work on `{token}`, but the path does not exist.",
                        evidence=line[:240],
                        related_path=token,
                    )
                )

    shell_lines = [
        line.strip()
        for line in normalized.splitlines()
        if _SHELL_LINE_RE.match(line.strip())
    ]
    if len(shell_lines) >= 3:
        issues.append(
            OutputIssue(
                kind=EpistemicIssueKind.SHELL_THEATER,
                severity=EpistemicIssueSeverity.WARNING,
                summary="Output contains multiple shell-style trace lines and may be narrative theater.",
                evidence="\n".join(shell_lines[:3])[:240],
            )
        )

    unique_issues: list[OutputIssue] = []
    seen_issue_keys: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.kind.value, issue.summary, issue.related_path)
        if key in seen_issue_keys:
            continue
        seen_issue_keys.add(key)
        unique_issues.append(issue)

    penalties = {
        EpistemicIssueSeverity.INFO: 0.05,
        EpistemicIssueSeverity.WARNING: 0.12,
        EpistemicIssueSeverity.ERROR: 0.35,
        EpistemicIssueSeverity.CRITICAL: 0.55,
    }
    grounding_score = _clamp01(
        1.0 - sum(penalties[issue.severity] for issue in unique_issues)
    )
    failure_class = next(
        (
            issue.kind.value
            for issue in unique_issues
            if issue.severity in {EpistemicIssueSeverity.ERROR, EpistemicIssueSeverity.CRITICAL}
        ),
        "",
    )
    summary = (
        "; ".join(issue.summary for issue in unique_issues[:3])
        if unique_issues
        else "No epistemic grounding issues detected."
    )
    return OutputDiagnostics(
        issues=unique_issues,
        grounding_score=grounding_score,
        failure_class=failure_class,
        summary=summary,
        referenced_paths=referenced_paths,
        missing_paths=missing_paths,
    )


class EpistemicTelemetryStore:
    """Append-only JSONL store for epistemic incidents and provider probes."""

    def __init__(self, *, state_dir: str | Path | None = None) -> None:
        base = Path(state_dir).expanduser() if state_dir is not None else (Path.home() / ".dharma")
        self.base_dir = base / "logs" / "epistemic"
        self.incidents_path = self.base_dir / "incidents.jsonl"
        self.provider_probes_path = self.base_dir / "provider_probes.jsonl"

    def _append_jsonl(self, path: Path, row: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")

    def append_incident(self, incident: EpistemicIncident) -> str:
        self._append_jsonl(self.incidents_path, incident.model_dump(mode="json"))
        return incident.incident_id

    def record_output_diagnostics(
        self,
        diagnostics: OutputDiagnostics,
        *,
        component: str,
        output_text: str,
        agent_name: str = "",
        provider: str = "",
        model: str = "",
        task_id: str = "",
        task_title: str = "",
        cycle_id: str = "",
        success: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        incident_ids: list[str] = []
        for issue in diagnostics.issues:
            incident_ids.append(
                self.append_incident(
                    EpistemicIncident(
                        component=component,
                        kind=issue.kind,
                        severity=issue.severity,
                        summary=issue.summary,
                        evidence=issue.evidence or output_text[:240],
                        related_path=issue.related_path,
                        agent_name=agent_name,
                        provider=provider,
                        model=model,
                        task_id=task_id,
                        task_title=task_title,
                        cycle_id=cycle_id,
                        success=success,
                        metadata={
                            "grounding_score": diagnostics.grounding_score,
                            **(metadata or {}),
                            **issue.metadata,
                        },
                    )
                )
            )
        return incident_ids

    def record_provider_probe_snapshot(
        self,
        payload: dict[str, Any],
        *,
        source: str = "provider_smoke",
    ) -> list[str]:
        probe_ids: list[str] = []
        for provider, block in payload.items():
            if not isinstance(block, dict):
                continue
            record = ProviderProbeRecord(
                source=source,
                provider=str(provider),
                status=str(block.get("status", "")),
                model=str(block.get("model", "")),
                configured_model=str(block.get("configured_model", "")),
                strongest_verified=str(block.get("strongest_verified", "")),
                deployment_mode=str(block.get("deployment_mode", "")),
                base_url=str(block.get("configured_base_url", "")),
                error=str(block.get("error", "")),
                metadata=dict(block),
            )
            self._append_jsonl(self.provider_probes_path, record.model_dump(mode="json"))
            probe_ids.append(record.probe_id)
        return probe_ids

    def read_provider_probes(
        self,
        *,
        provider: str | None = None,
        limit: int | None = None,
    ) -> list[ProviderProbeRecord]:
        if not self.provider_probes_path.exists():
            return []
        rows: list[ProviderProbeRecord] = []
        with self.provider_probes_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    record = ProviderProbeRecord.model_validate_json(stripped)
                except Exception:
                    continue
                if provider and record.provider != provider:
                    continue
                rows.append(record)
        rows.sort(key=lambda item: item.timestamp, reverse=True)
        return rows[:limit] if limit is not None and limit > 0 else rows


__all__ = [
    "EpistemicIncident",
    "EpistemicIssueKind",
    "EpistemicIssueSeverity",
    "EpistemicTelemetryStore",
    "OutputDiagnostics",
    "OutputIssue",
    "ProviderProbeRecord",
    "analyze_output",
]
