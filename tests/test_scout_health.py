from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.scout_health import main


def _write_report(path: Path, *, domain: str, timestamp: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "domain": domain,
        "model": "xiaomi/mimo-v2-pro",
        "provider": "openrouter",
        "timestamp": timestamp.isoformat(),
        "findings": [],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    history = path.parent / "history.jsonl"
    history.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_main_emits_json_and_returns_zero_for_healthy_pipeline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = datetime(2026, 3, 28, 2, 0, tzinfo=timezone.utc)
    state_dir = tmp_path / ".dharma"
    _write_report(
        state_dir / "scouts" / "architecture" / "latest.json",
        domain="architecture",
        timestamp=now - timedelta(minutes=10),
    )

    rc = main(
        [
            "--state-dir",
            str(state_dir),
            "--expected-domain",
            "architecture",
            "--json",
        ],
        now=now,
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["status"] == "pass"
    assert payload["summary"]["passing_domains"] == 1


def test_main_returns_nonzero_and_writes_artifacts_when_requested(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = datetime(2026, 3, 28, 2, 0, tzinfo=timezone.utc)
    state_dir = tmp_path / ".dharma"

    rc = main(
        [
            "--state-dir",
            str(state_dir),
            "--expected-domain",
            "routing",
            "--write",
        ],
        now=now,
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "routing" in captured.out
    assert (state_dir / "scouts" / "health" / "latest.json").exists()
    assert (state_dir / "scouts" / "health" / "latest.md").exists()
