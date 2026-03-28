from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.scout_audit import (
    HealthStatus,
    audit_pipeline,
    audit_scout_domain,
    render_pipeline_markdown,
    write_pipeline_audit,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_report(*, timestamp: datetime, error: str | None = None) -> dict[str, object]:
    return {
        "domain": "architecture",
        "model": "xiaomi/mimo-v2-pro",
        "provider": "openrouter",
        "timestamp": timestamp.isoformat(),
        "duration_seconds": 12.5,
        "files_read": ["dharma_swarm/swarm.py"],
        "commands_run": ["python3 -m pytest tests/test_swarm.py -q"],
        "findings": [
            {
                "title": "God object pressure in SwarmManager",
                "severity": "critical",
                "category": "observation",
                "description": "SwarmManager still centralizes too much responsibility.",
                "file_path": "dharma_swarm/swarm.py",
                "line_number": 42,
                "confidence": 0.92,
                "actionable": True,
                "suggested_action": "Extract queue handling into a dedicated collaborator.",
            },
            {
                "title": "Import boundary leak",
                "severity": "medium",
                "category": "improvement",
                "description": "routing imports runtime glue directly.",
                "confidence": 0.7,
                "actionable": False,
            },
        ],
        "meta_observations": "Architecture is improving but still too center-heavy.",
        "raw_response": "structured output",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "error": error,
    }


def test_audit_scout_domain_passes_on_fresh_valid_report(tmp_path: Path) -> None:
    now = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)
    scouts_dir = tmp_path / "scouts"
    report = _make_report(timestamp=now - timedelta(minutes=20))
    _write_json(scouts_dir / "architecture" / "latest.json", report)
    (scouts_dir / "architecture" / "history.jsonl").write_text(
        json.dumps(report) + "\n",
        encoding="utf-8",
    )

    audit = audit_scout_domain(
        "architecture",
        scouts_dir=scouts_dir,
        now=now,
        max_age_seconds=3600,
    )

    assert audit.status is HealthStatus.PASS
    assert audit.findings_count == 2
    assert audit.critical_count == 1
    assert audit.actionable_count == 1
    assert audit.history_entries == 1
    assert audit.issues == []


def test_audit_scout_domain_marks_missing_latest_report_as_fail(tmp_path: Path) -> None:
    audit = audit_scout_domain(
        "routing",
        scouts_dir=tmp_path / "scouts",
        now=datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=3600,
    )

    assert audit.status is HealthStatus.FAIL
    assert [issue.code for issue in audit.issues] == ["missing_latest_report"]


def test_audit_scout_domain_marks_stale_and_error_reports_warn(tmp_path: Path) -> None:
    now = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)
    scouts_dir = tmp_path / "scouts"
    report = _make_report(
        timestamp=now - timedelta(hours=8),
        error="provider fallback exhausted",
    )
    _write_json(scouts_dir / "tests" / "latest.json", report)

    audit = audit_scout_domain(
        "tests",
        scouts_dir=scouts_dir,
        now=now,
        max_age_seconds=3600,
    )

    assert audit.status is HealthStatus.WARN
    assert {issue.code for issue in audit.issues} == {"stale_report", "report_error", "missing_history"}


def test_audit_scout_domain_marks_malformed_json_as_fail(tmp_path: Path) -> None:
    latest = tmp_path / "scouts" / "security" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text("{not valid json", encoding="utf-8")

    audit = audit_scout_domain(
        "security",
        scouts_dir=tmp_path / "scouts",
        now=datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=3600,
    )

    assert audit.status is HealthStatus.FAIL
    assert [issue.code for issue in audit.issues] == ["malformed_latest_report"]


def test_audit_pipeline_summarizes_domains_synthesis_and_queue(tmp_path: Path) -> None:
    now = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)
    state_dir = tmp_path / ".dharma"
    scouts_dir = state_dir / "scouts"

    arch_report = _make_report(timestamp=now - timedelta(minutes=30))
    arch_report["domain"] = "architecture"
    _write_json(scouts_dir / "architecture" / "latest.json", arch_report)
    (scouts_dir / "architecture" / "history.jsonl").write_text(json.dumps(arch_report) + "\n", encoding="utf-8")

    test_report = _make_report(timestamp=now - timedelta(hours=4))
    test_report["domain"] = "tests"
    _write_json(scouts_dir / "tests" / "latest.json", test_report)

    synthesis_file = scouts_dir / "synthesis" / "2026-03-28_0000.md"
    synthesis_file.parent.mkdir(parents=True, exist_ok=True)
    synthesis_file.write_text("# Synthesis\n", encoding="utf-8")

    queue_file = state_dir / "overnight" / "queue.yaml"
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    queue_file.write_text(
        "- id: fix-routing\n"
        "  goal: tighten provider ranking loop\n"
        "- id: write-tests\n"
        "  goal: add routing memory coverage\n",
        encoding="utf-8",
    )

    audit = audit_pipeline(
        state_dir=state_dir,
        expected_domains=("architecture", "tests", "routing"),
        now=now,
        domain_max_age_seconds=3600,
        require_synthesis=True,
        require_queue=True,
    )

    assert audit.status is HealthStatus.FAIL
    assert audit.summary["total_domains"] == 3
    assert audit.summary["failing_domains"] == 1
    assert audit.summary["warning_domains"] == 1
    assert audit.synthesis.status is HealthStatus.PASS
    assert audit.overnight_queue.status is HealthStatus.PASS


def test_write_pipeline_audit_persists_latest_and_history(tmp_path: Path) -> None:
    now = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)
    state_dir = tmp_path / ".dharma"
    scouts_dir = state_dir / "scouts"
    report = _make_report(timestamp=now - timedelta(minutes=5))
    _write_json(scouts_dir / "architecture" / "latest.json", report)
    (scouts_dir / "architecture" / "history.jsonl").write_text(json.dumps(report) + "\n", encoding="utf-8")

    audit = audit_pipeline(
        state_dir=state_dir,
        expected_domains=("architecture",),
        now=now,
    )
    written = write_pipeline_audit(audit, output_dir=scouts_dir / "health")

    assert written["latest_json"].exists()
    assert written["latest_md"].exists()
    assert written["history_jsonl"].exists()
    history_lines = written["history_jsonl"].read_text(encoding="utf-8").splitlines()
    assert len(history_lines) == 1


def test_render_pipeline_markdown_contains_operator_summary(tmp_path: Path) -> None:
    now = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)
    state_dir = tmp_path / ".dharma"
    scouts_dir = state_dir / "scouts"
    report = _make_report(timestamp=now - timedelta(minutes=5))
    _write_json(scouts_dir / "architecture" / "latest.json", report)
    (scouts_dir / "architecture" / "history.jsonl").write_text(json.dumps(report) + "\n", encoding="utf-8")

    audit = audit_pipeline(
        state_dir=state_dir,
        expected_domains=("architecture",),
        now=now,
    )
    markdown = render_pipeline_markdown(audit)

    assert "# Scout Pipeline Health" in markdown
    assert "architecture" in markdown
    assert "overnight queue" in markdown.lower()
