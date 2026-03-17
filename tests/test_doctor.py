from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import subprocess

from dharma_swarm.doctor import (
    _check_daemon_integrity,
    _check_doctor_schedule,
    _check_message_bus_integrity,
    create_doctor_job,
    doctor_exit_code,
    load_latest_doctor_report,
    render_doctor_report,
    run_doctor,
    write_doctor_artifacts,
)


def _create_message_bus_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE messages (id TEXT)")
        conn.execute("CREATE TABLE heartbeats (agent_id TEXT, last_seen TEXT)")
        conn.execute("CREATE TABLE subscriptions (agent_id TEXT, topic TEXT)")
        conn.execute("CREATE TABLE artifacts (id TEXT)")
        conn.execute("CREATE TABLE events (event_id TEXT, consumed_at TEXT)")
        conn.execute("INSERT INTO messages (id) VALUES ('m-1')")
        conn.commit()


def test_doctor_exit_code_matrix() -> None:
    clean = {"summary": {"warn": 0, "fail": 0}}
    warn_only = {"summary": {"warn": 2, "fail": 0}}
    fail_any = {"summary": {"warn": 1, "fail": 1}}

    assert doctor_exit_code(clean, strict=False) == 0
    assert doctor_exit_code(clean, strict=True) == 0
    assert doctor_exit_code(warn_only, strict=False) == 0
    assert doctor_exit_code(warn_only, strict=True) == 1
    assert doctor_exit_code(fail_any, strict=False) == 2
    assert doctor_exit_code(fail_any, strict=True) == 2


def test_run_doctor_quick_report_shape(monkeypatch, tmp_path: Path) -> None:
    launcher = tmp_path / "dgc"
    launcher.write_text("#!/bin/sh\n_bootstrap_env()\n", encoding="utf-8")
    launcher.chmod(0o755)

    monkeypatch.setenv("DGC_ROUTER_REDIS_URL", "redis://127.0.0.1:1")
    monkeypatch.setenv("DGC_FASTTEXT_MODEL_PATH", str(tmp_path / "lid.176.bin"))
    monkeypatch.setenv("DGC_ROUTER_CANARY_PERCENT", "5")
    monkeypatch.setenv("DGC_ROUTER_LEARNING_ENABLED", "1")
    monkeypatch.setattr("dharma_swarm.doctor.shutil.which", lambda _: str(launcher))

    report = run_doctor(timeout_seconds=0.1, quick=True)
    assert isinstance(report, dict)
    assert "status" in report
    assert "summary" in report
    assert "checks" in report
    assert "assurance" in report
    assert "artifacts" in report
    assert report["summary"]["total"] >= 8
    statuses = {entry.get("status") for entry in report["checks"]}
    assert statuses.issubset({"PASS", "WARN", "FAIL"})


def test_env_autoload_passes_for_delegate_launcher(monkeypatch, tmp_path: Path) -> None:
    launcher = tmp_path / "dgc"
    launcher.write_text(
        "#!/usr/bin/env python3\n"
        "from dharma_swarm.dgc_cli import main\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    monkeypatch.setattr("dharma_swarm.doctor.shutil.which", lambda _: str(launcher))
    report = run_doctor(timeout_seconds=0.1, quick=True)
    env_check = next(c for c in report["checks"] if c["name"] == "env_autoload")
    assert env_check["status"] == "PASS"


def test_render_doctor_report_contains_header() -> None:
    report = {
        "status": "WARN",
        "summary": {"pass": 3, "warn": 1, "fail": 0},
        "checks": [
            {"name": "env_autoload", "status": "PASS", "summary": "ok", "detail": ""},
            {"name": "redis", "status": "WARN", "summary": "down", "detail": "timeout"},
        ],
        "recommended_fixes": ["Start Redis"],
    }
    text = render_doctor_report(report)
    assert "=== DGC DOCTOR ===" in text
    assert "[PASS] env_autoload: ok" in text
    assert "[WARN] redis: down" in text
    assert "Recommended fixes:" in text


def test_write_and_load_doctor_artifacts(tmp_path: Path) -> None:
    report = {
        "status": "WARN",
        "summary": {"pass": 1, "warn": 1, "fail": 0},
        "checks": [],
        "recommended_fixes": [],
        "assurance": {},
        "artifacts": {},
    }

    artifacts = write_doctor_artifacts(report, output_dir=tmp_path)

    assert Path(artifacts["json"]).exists()
    assert Path(artifacts["markdown"]).exists()
    assert Path(artifacts["history_json"]).exists()
    assert Path(artifacts["history_markdown"]).exists()

    loaded = load_latest_doctor_report(output_dir=tmp_path)
    assert loaded is not None
    assert loaded["status"] == "WARN"


def test_daemon_integrity_warns_on_stale_pid_file(monkeypatch, tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    state_dir.mkdir(parents=True)
    (state_dir / "daemon.pid").write_text("4242", encoding="utf-8")

    monkeypatch.setattr("dharma_swarm.doctor.HOME", tmp_path)
    monkeypatch.setattr("dharma_swarm.doctor._pid_alive", lambda pid: False)
    monkeypatch.setattr(
        "dharma_swarm.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )

    checks = []
    _check_daemon_integrity(checks, timeout_seconds=0.1)

    assert checks[0].name == "daemon_integrity"
    assert checks[0].status == "WARN"
    assert "stale pid files" in checks[0].detail


def test_daemon_integrity_fails_on_multiple_processes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("dharma_swarm.doctor.HOME", tmp_path)
    monkeypatch.setattr("dharma_swarm.doctor._pid_alive", lambda pid: pid in {111, 222})
    ps_output = "\n".join(
        [
            "111 python3 -m dharma_swarm.orchestrate_live",
            "222 /bin/bash /Users/dhyana/dharma_swarm/run_daemon.sh",
        ]
    )
    monkeypatch.setattr(
        "dharma_swarm.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, ps_output, ""),
    )

    checks = []
    _check_daemon_integrity(checks, timeout_seconds=0.1)

    assert checks[0].name == "daemon_integrity"
    assert checks[0].status == "FAIL"
    assert "multiple daemon-like processes" in checks[0].summary


def test_message_bus_integrity_warns_on_shadow_path_and_idle_runtime(monkeypatch, tmp_path: Path) -> None:
    canonical = tmp_path / ".dharma" / "db" / "messages.db"
    shadow = tmp_path / ".dharma" / "message_bus.db"
    _create_message_bus_db(canonical)
    _create_message_bus_db(shadow)

    monkeypatch.setattr("dharma_swarm.doctor.HOME", tmp_path)
    monkeypatch.setattr(
        "dharma_swarm.doctor._list_daemon_like_processes",
        lambda timeout_seconds: [(111, "python3 -m dharma_swarm.orchestrate_live")],
    )

    checks = []
    _check_message_bus_integrity(checks, timeout_seconds=0.1)

    assert checks[0].name == "message_bus_integrity"
    assert checks[0].status == "WARN"
    assert "message_bus.db" in checks[0].detail
    assert "heartbeats=0" in checks[0].detail


def test_doctor_schedule_passes_when_job_is_armed(monkeypatch, tmp_path: Path) -> None:
    cron_dir = tmp_path / ".dharma" / "cron"
    cron_dir.mkdir(parents=True)
    next_run = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    jobs_path = cron_dir / "jobs.json"
    jobs_path.write_text(
        (
            '{"jobs": [{"id": "doc1", "name": "doctor_assurance", "enabled": true, '
            '"handler": "doctor_assurance", "next_run_at": "'
            + next_run
            + '", "last_run_at": null}]}'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("dharma_swarm.doctor.HOME", tmp_path)

    checks = []
    _check_doctor_schedule(checks)

    assert checks[0].name == "doctor_schedule"
    assert checks[0].status == "PASS"
    assert "armed" in checks[0].summary


def test_create_doctor_job_marks_job_urgent(monkeypatch) -> None:
    captured = {}

    def _fake_create_job(prompt, schedule, name=None, repeat=None, deliver="local", urgent=False, **extras):
        captured.update(
            {
                "prompt": prompt,
                "schedule": schedule,
                "name": name,
                "deliver": deliver,
                "urgent": urgent,
                "extras": extras,
            }
        )
        return {"id": "job1", "name": name, "urgent": urgent, **extras}

    monkeypatch.setattr("dharma_swarm.cron_scheduler.create_job", _fake_create_job)

    job = create_doctor_job(schedule="every 2h", quick=True)

    assert captured["urgent"] is True
    assert captured["name"] == "doctor_assurance"
    assert job["urgent"] is True
