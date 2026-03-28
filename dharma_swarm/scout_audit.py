"""Operator-facing health and audit surface for the scout pipeline.

This module deliberately stays pure and local: it reads scout reports,
cron-adjacent artifacts, synthesis outputs, and overnight queue files
without making any model calls. The goal is to answer a simple question:

Did the overnight intelligence pipeline actually run, and if not, what broke?
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False


DEFAULT_STATE_DIR = Path.home() / ".dharma"
DEFAULT_SCOUTS_DIR = DEFAULT_STATE_DIR / "scouts"
DEFAULT_HEALTH_DIR = DEFAULT_SCOUTS_DIR / "health"
DEFAULT_DOMAIN_MAX_AGE_SECONDS = 26 * 3600
DEFAULT_SYNTHESIS_MAX_AGE_SECONDS = 26 * 3600
DEFAULT_QUEUE_MAX_AGE_SECONDS = 26 * 3600


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_age_seconds(*, timestamp: datetime | None, now: datetime) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, (now - timestamp).total_seconds())


def _count_nonempty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


class HealthStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class AuditIssue(BaseModel):
    code: str
    severity: HealthStatus
    message: str


class ScoutDomainAudit(BaseModel):
    domain: str
    status: HealthStatus = HealthStatus.PASS
    report_path: str = ""
    timestamp: str | None = None
    age_seconds: float | None = None
    model: str = ""
    provider: str = ""
    findings_count: int = 0
    critical_count: int = 0
    actionable_count: int = 0
    history_entries: int = 0
    issues: list[AuditIssue] = Field(default_factory=list)


class ArtifactAudit(BaseModel):
    name: str
    status: HealthStatus = HealthStatus.PASS
    path: str = ""
    timestamp: str | None = None
    age_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    issues: list[AuditIssue] = Field(default_factory=list)


class ScoutPipelineAudit(BaseModel):
    generated_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    status: HealthStatus = HealthStatus.PASS
    state_dir: str
    scouts_dir: str
    domains: list[ScoutDomainAudit] = Field(default_factory=list)
    synthesis: ArtifactAudit = Field(default_factory=lambda: ArtifactAudit(name="synthesis"))
    overnight_queue: ArtifactAudit = Field(default_factory=lambda: ArtifactAudit(name="overnight_queue"))
    summary: dict[str, int] = Field(default_factory=dict)


def _push_issue(issues: list[AuditIssue], code: str, severity: HealthStatus, message: str) -> None:
    issues.append(AuditIssue(code=code, severity=severity, message=message))


def _status_from_issues(issues: list[AuditIssue]) -> HealthStatus:
    if any(issue.severity is HealthStatus.FAIL for issue in issues):
        return HealthStatus.FAIL
    if any(issue.severity is HealthStatus.WARN for issue in issues):
        return HealthStatus.WARN
    return HealthStatus.PASS


def _merge_statuses(*statuses: HealthStatus) -> HealthStatus:
    if any(status is HealthStatus.FAIL for status in statuses):
        return HealthStatus.FAIL
    if any(status is HealthStatus.WARN for status in statuses):
        return HealthStatus.WARN
    return HealthStatus.PASS


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "expected top-level JSON object"
    return data, None


def _latest_artifact_file(directory: Path, *, suffixes: tuple[str, ...]) -> Path | None:
    if not directory.exists():
        return None
    candidates = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in suffixes]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def audit_scout_domain(
    domain: str,
    *,
    scouts_dir: Path = DEFAULT_SCOUTS_DIR,
    now: datetime | None = None,
    max_age_seconds: float = DEFAULT_DOMAIN_MAX_AGE_SECONDS,
) -> ScoutDomainAudit:
    current = now or _utc_now()
    latest_path = scouts_dir / domain / "latest.json"
    history_path = scouts_dir / domain / "history.jsonl"
    issues: list[AuditIssue] = []
    audit = ScoutDomainAudit(domain=domain, report_path=str(latest_path))

    if not latest_path.exists():
        _push_issue(issues, "missing_latest_report", HealthStatus.FAIL, f"{latest_path} does not exist")
        audit.issues = issues
        audit.status = _status_from_issues(issues)
        return audit

    payload, load_error = _load_json(latest_path)
    if payload is None:
        _push_issue(
            issues,
            "malformed_latest_report",
            HealthStatus.FAIL,
            f"Could not parse {latest_path.name}: {load_error}",
        )
        audit.issues = issues
        audit.status = _status_from_issues(issues)
        return audit

    timestamp = _parse_timestamp(payload.get("timestamp"))
    if timestamp is None:
        _push_issue(issues, "invalid_timestamp", HealthStatus.FAIL, "Report timestamp is missing or invalid")
    else:
        audit.timestamp = timestamp.isoformat()
        audit.age_seconds = _safe_age_seconds(timestamp=timestamp, now=current)
        if audit.age_seconds is not None and audit.age_seconds > max_age_seconds:
            _push_issue(
                issues,
                "stale_report",
                HealthStatus.WARN,
                f"Latest report is stale by {int(audit.age_seconds)} seconds",
            )

    findings = payload.get("findings")
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        _push_issue(issues, "invalid_findings", HealthStatus.FAIL, "Report findings must be a list")
        findings = []

    audit.model = str(payload.get("model") or "")
    audit.provider = str(payload.get("provider") or "")
    audit.findings_count = len(findings)
    audit.critical_count = sum(
        1
        for finding in findings
        if isinstance(finding, dict) and str(finding.get("severity") or "").lower() == "critical"
    )
    audit.actionable_count = sum(
        1
        for finding in findings
        if isinstance(finding, dict) and bool(finding.get("actionable"))
    )

    error_text = str(payload.get("error") or "").strip()
    if error_text:
        _push_issue(issues, "report_error", HealthStatus.WARN, error_text)

    audit.history_entries = _count_nonempty_lines(history_path)
    if audit.history_entries == 0:
        _push_issue(issues, "missing_history", HealthStatus.WARN, f"{history_path} is missing or empty")

    audit.issues = issues
    audit.status = _status_from_issues(issues)
    return audit


def audit_synthesis(
    *,
    scouts_dir: Path = DEFAULT_SCOUTS_DIR,
    now: datetime | None = None,
    max_age_seconds: float = DEFAULT_SYNTHESIS_MAX_AGE_SECONDS,
    require: bool = False,
) -> ArtifactAudit:
    current = now or _utc_now()
    synthesis_dir = scouts_dir / "synthesis"
    artifact = ArtifactAudit(name="synthesis", metadata={"file_count": 0})
    latest = _latest_artifact_file(synthesis_dir, suffixes=(".md", ".json", ".yaml", ".yml"))

    if latest is None:
        if require:
            artifact.issues.append(
                AuditIssue(
                    code="missing_synthesis",
                    severity=HealthStatus.FAIL,
                    message=f"No synthesis artifact found in {synthesis_dir}",
                )
            )
            artifact.status = HealthStatus.FAIL
        return artifact

    updated = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    artifact.path = str(latest)
    artifact.timestamp = updated.isoformat()
    artifact.age_seconds = _safe_age_seconds(timestamp=updated, now=current)
    artifact.metadata["file_count"] = len(
        [path for path in synthesis_dir.iterdir() if path.is_file()]
    ) if synthesis_dir.exists() else 0
    if artifact.age_seconds is not None and artifact.age_seconds > max_age_seconds:
        artifact.issues.append(
            AuditIssue(
                code="stale_synthesis",
                severity=HealthStatus.WARN,
                message=f"Synthesis artifact is stale by {int(artifact.age_seconds)} seconds",
            )
        )
    if not latest.read_text(encoding="utf-8").strip():
        artifact.issues.append(
            AuditIssue(
                code="empty_synthesis",
                severity=HealthStatus.WARN,
                message=f"{latest.name} is empty",
            )
        )
    artifact.status = _status_from_issues(artifact.issues)
    return artifact


def _queue_task_count(queue_path: Path) -> tuple[int, list[AuditIssue]]:
    issues: list[AuditIssue] = []
    raw = queue_path.read_text(encoding="utf-8")
    text = raw.strip()
    if not text:
        issues.append(
            AuditIssue(
                code="empty_queue",
                severity=HealthStatus.WARN,
                message=f"{queue_path.name} is empty",
            )
        )
        return 0, issues
    if _YAML_AVAILABLE:
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="malformed_queue",
                    severity=HealthStatus.FAIL,
                    message=f"Failed to parse queue YAML: {exc}",
                )
            )
            return 0, issues
        if parsed is None:
            issues.append(
                AuditIssue(
                    code="empty_queue",
                    severity=HealthStatus.WARN,
                    message=f"{queue_path.name} is empty",
                )
            )
            return 0, issues
        if not isinstance(parsed, list):
            issues.append(
                AuditIssue(
                    code="malformed_queue",
                    severity=HealthStatus.FAIL,
                    message="Overnight queue must be a YAML list",
                )
            )
            return 0, issues
        return len(parsed), issues

    count = sum(1 for line in raw.splitlines() if line.lstrip().startswith("- "))
    if count == 0:
        issues.append(
            AuditIssue(
                code="empty_queue",
                severity=HealthStatus.WARN,
                message="Could not identify any queue entries",
            )
        )
    return count, issues


def audit_overnight_queue(
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    now: datetime | None = None,
    max_age_seconds: float = DEFAULT_QUEUE_MAX_AGE_SECONDS,
    require: bool = False,
) -> ArtifactAudit:
    current = now or _utc_now()
    queue_path = state_dir / "overnight" / "queue.yaml"
    artifact = ArtifactAudit(name="overnight_queue", path=str(queue_path), metadata={"task_count": 0})

    if not queue_path.exists():
        if require:
            artifact.issues.append(
                AuditIssue(
                    code="missing_queue",
                    severity=HealthStatus.FAIL,
                    message=f"{queue_path} does not exist",
                )
            )
            artifact.status = HealthStatus.FAIL
        return artifact

    updated = datetime.fromtimestamp(queue_path.stat().st_mtime, tz=timezone.utc)
    artifact.timestamp = updated.isoformat()
    artifact.age_seconds = _safe_age_seconds(timestamp=updated, now=current)
    if artifact.age_seconds is not None and artifact.age_seconds > max_age_seconds:
        artifact.issues.append(
            AuditIssue(
                code="stale_queue",
                severity=HealthStatus.WARN,
                message=f"Overnight queue is stale by {int(artifact.age_seconds)} seconds",
            )
        )

    task_count, issues = _queue_task_count(queue_path)
    artifact.metadata["task_count"] = task_count
    artifact.issues.extend(issues)
    artifact.status = _status_from_issues(artifact.issues)
    return artifact


def audit_pipeline(
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    expected_domains: tuple[str, ...] = (),
    now: datetime | None = None,
    domain_max_age_seconds: float = DEFAULT_DOMAIN_MAX_AGE_SECONDS,
    synthesis_max_age_seconds: float = DEFAULT_SYNTHESIS_MAX_AGE_SECONDS,
    queue_max_age_seconds: float = DEFAULT_QUEUE_MAX_AGE_SECONDS,
    require_synthesis: bool = False,
    require_queue: bool = False,
) -> ScoutPipelineAudit:
    current = now or _utc_now()
    scouts_dir = state_dir / "scouts"
    discovered = (
        {
            path.name
            for path in scouts_dir.iterdir()
            if path.is_dir() and path.name not in {"synthesis", "health"}
        }
        if scouts_dir.exists()
        else set()
    )
    domains = tuple(sorted(discovered | set(expected_domains)))

    domain_audits = [
        audit_scout_domain(
            domain,
            scouts_dir=scouts_dir,
            now=current,
            max_age_seconds=domain_max_age_seconds,
        )
        for domain in domains
    ]
    synthesis = audit_synthesis(
        scouts_dir=scouts_dir,
        now=current,
        max_age_seconds=synthesis_max_age_seconds,
        require=require_synthesis,
    )
    overnight_queue = audit_overnight_queue(
        state_dir=state_dir,
        now=current,
        max_age_seconds=queue_max_age_seconds,
        require=require_queue,
    )

    passing_domains = sum(1 for audit in domain_audits if audit.status is HealthStatus.PASS)
    warning_domains = sum(1 for audit in domain_audits if audit.status is HealthStatus.WARN)
    failing_domains = sum(1 for audit in domain_audits if audit.status is HealthStatus.FAIL)
    overall = _merge_statuses(
        *(audit.status for audit in domain_audits),
        synthesis.status,
        overnight_queue.status,
    )

    return ScoutPipelineAudit(
        generated_at=current.isoformat(),
        status=overall,
        state_dir=str(state_dir),
        scouts_dir=str(scouts_dir),
        domains=domain_audits,
        synthesis=synthesis,
        overnight_queue=overnight_queue,
        summary={
            "total_domains": len(domain_audits),
            "passing_domains": passing_domains,
            "warning_domains": warning_domains,
            "failing_domains": failing_domains,
        },
    )


def render_pipeline_markdown(audit: ScoutPipelineAudit) -> str:
    lines = [
        "# Scout Pipeline Health",
        "",
        f"- Generated at: `{audit.generated_at}`",
        f"- Overall status: `{audit.status.value}`",
        f"- Domains: `{audit.summary.get('total_domains', 0)}`",
        f"- Passing domains: `{audit.summary.get('passing_domains', 0)}`",
        f"- Warning domains: `{audit.summary.get('warning_domains', 0)}`",
        f"- Failing domains: `{audit.summary.get('failing_domains', 0)}`",
        "",
        "## Domain Health",
        "",
    ]
    for domain in audit.domains:
        lines.append(
            f"- `{domain.domain}`: `{domain.status.value}` | findings={domain.findings_count} "
            f"| critical={domain.critical_count} | actionable={domain.actionable_count}"
        )
        for issue in domain.issues:
            lines.append(f"  - `{issue.code}`: {issue.message}")

    lines.extend(
        [
            "",
            "## Synthesis",
            "",
            f"- status: `{audit.synthesis.status.value}`",
            f"- path: `{audit.synthesis.path or 'missing'}`",
            "",
            "## Overnight Queue",
            "",
            f"- status: `{audit.overnight_queue.status.value}`",
            f"- path: `{audit.overnight_queue.path or 'missing'}`",
            f"- task_count: `{audit.overnight_queue.metadata.get('task_count', 0)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_pipeline_audit(
    audit: ScoutPipelineAudit,
    *,
    output_dir: Path = DEFAULT_HEALTH_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stamp = (
        audit.generated_at
        .replace(":", "")
        .replace("+", "_")
        .replace("-", "")
        .replace("T", "_")
    )
    timestamped_json = output_dir / f"audit_{safe_stamp}.json"
    timestamped_md = output_dir / f"audit_{safe_stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    history_jsonl = output_dir / "history.jsonl"

    json_payload = audit.model_dump_json(indent=2)
    markdown_payload = render_pipeline_markdown(audit)

    timestamped_json.write_text(json_payload + "\n", encoding="utf-8")
    timestamped_md.write_text(markdown_payload, encoding="utf-8")
    latest_json.write_text(json_payload + "\n", encoding="utf-8")
    latest_md.write_text(markdown_payload, encoding="utf-8")
    with history_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(audit.model_dump_json() + "\n")

    return {
        "latest_json": latest_json,
        "latest_md": latest_md,
        "history_jsonl": history_jsonl,
        "timestamped_json": timestamped_json,
        "timestamped_md": timestamped_md,
    }


__all__ = [
    "ArtifactAudit",
    "AuditIssue",
    "DEFAULT_HEALTH_DIR",
    "DEFAULT_SCOUTS_DIR",
    "DEFAULT_STATE_DIR",
    "HealthStatus",
    "ScoutDomainAudit",
    "ScoutPipelineAudit",
    "audit_overnight_queue",
    "audit_pipeline",
    "audit_scout_domain",
    "audit_synthesis",
    "render_pipeline_markdown",
    "write_pipeline_audit",
]
