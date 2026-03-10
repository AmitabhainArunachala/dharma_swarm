from __future__ import annotations

from pathlib import Path

from dharma_swarm.doctor import doctor_exit_code, render_doctor_report, run_doctor


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
    assert report["summary"]["total"] >= 6
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
