from __future__ import annotations

import importlib
import json
import math
import pwd
from pathlib import Path
from types import SimpleNamespace

import pytest

import dharma_swarm.autoresearch_eval as autoresearch_eval
from dharma_swarm.autoresearch_eval import (
    AutoresearchEvalReport,
    MetricScore,
    format_summary_line,
    run_autoresearch_evaluation,
    save_autoresearch_report,
    _score_dharma_compliance,
)
from dharma_swarm.ecc_eval_harness import EvalReport


def test_format_summary_line_includes_omega_psi_and_all_hps() -> None:
    summary = format_summary_line(
        {
            "omega": 0.8123,
            "psi": 0.7011,
            "hp_scores": [{"score": 0.5}] * 10,
        }
    )

    assert summary.startswith("Ω=0.8123 Ψ=0.7011")
    assert "HP1=0.5000" in summary
    assert "HP10=0.5000" in summary


def test_format_summary_line_sanitizes_non_finite_values() -> None:
    summary = format_summary_line(
        {
            "omega": float("nan"),
            "psi": float("inf"),
            "hp_scores": [{"score": float("-inf")}],
        }
    )

    assert summary == "Ω=0.0000 Ψ=0.0000 HP1=0.0000"


def test_parse_float_rejects_non_finite_values() -> None:
    assert autoresearch_eval._parse_float("nan") is None
    assert autoresearch_eval._parse_float(float("nan")) is None
    assert autoresearch_eval._parse_float("inf") is None
    assert autoresearch_eval._parse_float("-inf") is None
    assert autoresearch_eval._parse_float("nan%") is None
    assert autoresearch_eval._parse_float("inf%") is None


def test_module_defaults_anchor_to_login_home_when_home_env_is_remapped(
    tmp_path: Path,
) -> None:
    login_home = tmp_path / "login-home"
    env_home = tmp_path / "remapped-home"
    login_home.mkdir()
    env_home.mkdir()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("HOME", str(env_home))
        monkeypatch.setattr(
            pwd,
            "getpwuid",
            lambda _uid: SimpleNamespace(pw_dir=str(login_home)),
        )

        reloaded = importlib.reload(autoresearch_eval)
        parser = reloaded.build_arg_parser()
        defaults = parser.parse_args([])

        assert reloaded.LOGIN_HOME == login_home
        assert reloaded.ROOT == login_home / "dharma_swarm"
        assert reloaded.STATE_DIR == login_home / ".dharma"
        assert reloaded.EVALS_DIR == login_home / ".dharma" / "evals"
        assert defaults.repo_root == str(login_home / "dharma_swarm")
        assert defaults.state_dir == str(login_home / ".dharma")

    importlib.reload(autoresearch_eval)


def test_latency_p95_ignores_non_finite_duration_samples() -> None:
    metric = autoresearch_eval._latency_p95(
        {
            "results": [
                {"duration_seconds": 0.2},
                {"duration_seconds": float("nan")},
                {"duration_seconds": "inf"},
            ]
        }
    )

    assert metric.detail["samples"] == 1
    assert metric.detail["p95_seconds"] == pytest.approx(0.2)
    assert metric.score == pytest.approx(autoresearch_eval._score_latency(0.2))


def test_cost_efficiency_ignores_non_finite_cost_and_fitness_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_eval.read_cost_log",
        lambda since_hours=24.0, state_dir=None: [
            SimpleNamespace(estimated_cost_usd=float("nan")),
            SimpleNamespace(estimated_cost_usd=2.5),
        ],
    )

    class _FakeRegistry:
        def __init__(self, agents_dir: Path | None = None) -> None:
            del agents_dir

        def get_fleet_summary(self) -> dict[str, object]:
            return {
                "total_calls": 3,
                "total_cost_usd": float("inf"),
                "avg_composite_fitness": float("nan"),
            }

    monkeypatch.setattr("dharma_swarm.autoresearch_eval.AgentRegistry", _FakeRegistry)

    metric = autoresearch_eval._cost_efficiency(0.8, state_dir=tmp_path)

    assert math.isfinite(metric.score)
    assert metric.detail["total_cost_usd_24h"] == pytest.approx(2.5)
    assert metric.detail["cost_entries_24h"] == 1
    assert metric.detail["fleet_total_calls"] == 3
    assert metric.detail["fleet_avg_composite_fitness"] == pytest.approx(0.0)


def test_save_autoresearch_report_persists_latest_and_history(tmp_path: Path) -> None:
    report = AutoresearchEvalReport(
        timestamp="2026-03-18T00:00:00Z",
        benchmark="full",
        timeout_seconds=300,
        omega=0.8,
        psi=0.7,
        hp_scores=[MetricScore(name=f"hp{i}", score=0.5, weight=0.1) for i in range(10)],
        psi_components={"prediction": 0.7},
        ecc_report={"passed": 9},
        assurance_summary={"status": "PASS", "summary": {}},
        probe_details={"memory": {"ok": True}},
        repo_root=str(tmp_path / "repo"),
        state_dir=str(tmp_path),
    )

    latest = save_autoresearch_report(report, state_dir=tmp_path)

    assert latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["omega"] == pytest.approx(0.8)
    history = tmp_path / "evals" / "autoresearch_history.jsonl"
    assert history.exists()
    assert len(history.read_text(encoding="utf-8").splitlines()) == 1


def test_compute_psi_ignores_non_finite_history_rows(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "SELF.md").write_text(
        "# SELF.md\n\n"
        "## Observations\n"
        "- 2026-03-18T00:00:00Z cycle 001 [baseline] Ω≈0.7500 Ψ≈0.6000: Because memory retrieval improved.\n",
        encoding="utf-8",
    )
    (repo_root / "experiment_log.md").write_text("# experiment log\n", encoding="utf-8")
    (repo_root / "results_autoresearch.tsv").write_text(
        "exp_id\ttimestamp\thypothesis\tpredicted_omega_delta\tpredicted_psi_delta\t"
        "actual_omega\tactual_psi\tfiles\ttests\tkept\tregime\tnotes\tconfidence\tmetrics_source\n"
        "001\t2026-03-18T00:00:00Z\tBecause memory retrieval improved\t+0.05\t+0.02\t0.7500\t0.6000\tnone\tpytest -q\tkeep\tbaseline\tBecause memory retrieval improved.\t0.70\tlocked\n"
        "002\t2026-03-18T00:10:00Z\tWhen metadata is malformed\tinf\t+0.01\tnan\tinf\tnone\tpytest -q\tkeep\tbaseline\tWhen metadata is malformed, the scorer should ignore it.\tnan\tlocked\n",
        encoding="utf-8",
    )

    psi, components, detail = autoresearch_eval._compute_psi(repo_root)

    assert math.isfinite(psi)
    assert components["prediction"] == pytest.approx(0.5)
    assert components["calibration"] == pytest.approx(0.5)
    assert detail["prediction_pairs"] == 0
    assert detail["confidence_points"] == 0


def test_compute_psi_accepts_legacy_locked_rows_missing_metrics_source(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "SELF.md").write_text(
        "# SELF.md\n\n"
        "## Observations\n"
        "- 2026-03-18T00:10:00Z cycle 002 [converging] Ω≈0.8000 Ψ≈0.6500: Because upgrades stayed measurable.\n",
        encoding="utf-8",
    )
    (repo_root / "experiment_log.md").write_text("# experiment log\n", encoding="utf-8")
    (repo_root / "results_autoresearch.tsv").write_text(
        "exp_id\ttimestamp\thypothesis\tpredicted_omega_delta\tpredicted_psi_delta\t"
        "actual_omega\tactual_psi\tfiles\ttests\tkept\tregime\tnotes\tconfidence\tmetrics_source\n"
        "001\t2026-03-18T00:00:00Z\tLegacy locked baseline\t+0.05\t+0.02\t0.7500\t0.6000\tnone\tpytest -q\tkeep\tbaseline\tLegacy row before metrics_source existed\n"
        "002\t2026-03-18T00:10:00Z\tLegacy locked follow-up\t+0.05\t+0.03\t0.8000\t0.6500\tnone\tpytest -q\tkeep\tconverging\tLegacy row before confidence existed\n",
        encoding="utf-8",
    )

    rows = autoresearch_eval._read_autoresearch_rows(repo_root)
    psi, components, detail = autoresearch_eval._compute_psi(repo_root)

    assert rows[0]["metrics_source"] == "locked"
    assert rows[0]["confidence"] == "unknown"
    assert rows[1]["metrics_source"] == "locked"
    assert rows[1]["confidence"] == "unknown"
    assert math.isfinite(psi)
    assert components["prediction"] > 0.5
    assert detail["prediction_pairs"] == 1
    assert detail["confidence_points"] == 0


@pytest.mark.asyncio
async def test_run_autoresearch_evaluation_aggregates_real_metrics_from_mocked_probes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "SELF.md").write_text(
        "# SELF.md — DHARMA SWARM Self-Model\n\n"
        "## Observations\n"
        "- 2026-03-18T00:00:00Z cycle 001 [baseline] Ω≈0.7500 Ψ≈0.6000: Because routing stabilized, memory recall became easier to explain.\n"
        "- 2026-03-18T00:10:00Z cycle 002 [converging] Ω≈0.8000 Ψ≈0.6500: When coordination metadata is explicit, reviewer routing becomes more reliable.\n",
        encoding="utf-8",
    )
    (repo_root / "experiment_log.md").write_text("# experiment log\n", encoding="utf-8")
    (repo_root / "results_autoresearch.tsv").write_text(
        "exp_id\ttimestamp\thypothesis\tpredicted_omega_delta\tpredicted_psi_delta\t"
        "actual_omega\tactual_psi\tfiles\ttests\tkept\tregime\tnotes\tconfidence\tmetrics_source\n"
        "001\t2026-03-18T00:00:00Z\tBecause memory retrieval improved\t+0.05\t+0.02\t0.7500\t0.6000\tnone\tpytest -q\tkeep\tbaseline\tBecause memory retrieval improved.\t0.70\tlocked\n"
        "002\t2026-03-18T00:10:00Z\tWhen routing metadata is explicit\t+0.05\t+0.03\t0.8000\t0.6500\tnone\tpytest -q\tkeep\tconverging\tWhen routing metadata is explicit, reviewer routing improves.\t0.80\tlocked\n",
        encoding="utf-8",
    )

    fake_report = EvalReport(
        timestamp="2026-03-18T00:20:00Z",
        total=9,
        passed=8,
        failed=1,
        pass_at_1=8 / 9,
        results=[
            {"name": "task_roundtrip", "passed": True, "duration_seconds": 0.3, "metrics": {}, "error": ""},
            {"name": "fitness_signal_flow", "passed": True, "duration_seconds": 0.4, "metrics": {}, "error": ""},
            {"name": "stigmergy_roundtrip", "passed": True, "duration_seconds": 0.5, "metrics": {}, "error": ""},
            {"name": "evolution_archive", "passed": True, "duration_seconds": 0.1, "metrics": {}, "error": ""},
            {"name": "provider_availability", "passed": True, "duration_seconds": 0.1, "metrics": {}, "error": ""},
            {"name": "test_suite_health", "passed": True, "duration_seconds": 1.0, "metrics": {}, "error": ""},
            {"name": "import_health", "passed": True, "duration_seconds": 0.2, "metrics": {}, "error": ""},
            {"name": "config_validity", "passed": True, "duration_seconds": 0.1, "metrics": {}, "error": ""},
            {"name": "bus_schema", "passed": False, "duration_seconds": 0.2, "metrics": {}, "error": "missing table"},
        ],
        duration_seconds=2.9,
    )

    observed: dict[str, object] = {}

    async def fake_run_all_evals(*, repo_root: Path | None = None, state_dir: Path | None = None) -> EvalReport:
        observed["repo_root"] = repo_root
        observed["state_dir"] = state_dir
        return fake_report

    class _FakeRegistry:
        def __init__(self, agents_dir: Path | None = None) -> None:
            observed["agents_dir"] = agents_dir

        def get_fleet_summary(self) -> dict[str, float | int]:
            return {
                "total_calls": 0,
                "total_cost_usd": 0.0,
                "avg_composite_fitness": 0.0,
            }

    async def fake_memory() -> tuple[float, dict[str, object]]:
        return 0.9, {"memory_probe": "ok"}

    async def fake_coordination() -> tuple[float, dict[str, object]]:
        return 0.8, {"coordination_probe": "ok"}

    async def fake_recovery() -> tuple[float, dict[str, object]]:
        return 0.7, {"recovery_probe": "ok"}

    async def fake_dharma(_: Path) -> tuple[float, dict[str, object]]:
        return 1.0, {"dharma_probe": "ok"}

    monkeypatch.setattr("dharma_swarm.autoresearch_eval.run_all_evals", fake_run_all_evals)
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_eval.run_assurance",
        lambda repo_root: {
            "status": "PASS",
            "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "recommended_fixes": [],
        },
    )
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_eval.read_cost_log",
        lambda since_hours=24.0, state_dir=None: [],
    )
    monkeypatch.setattr("dharma_swarm.autoresearch_eval.AgentRegistry", _FakeRegistry)
    monkeypatch.setattr("dharma_swarm.autoresearch_eval._probe_memory_coherence", fake_memory)
    monkeypatch.setattr("dharma_swarm.autoresearch_eval._probe_agent_coordination", fake_coordination)
    monkeypatch.setattr("dharma_swarm.autoresearch_eval._probe_recovery_rate", fake_recovery)
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_eval._score_self_consistency",
        lambda: (0.85, {"self_consistency": "ok"}),
    )
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_eval._score_routing_accuracy",
        lambda: (0.9, {"routing_accuracy": "ok"}),
    )
    monkeypatch.setattr("dharma_swarm.autoresearch_eval._score_dharma_compliance", fake_dharma)

    report = await run_autoresearch_evaluation(
        repo_root=repo_root,
        state_dir=tmp_path / ".dharma",
        timeout_seconds=300,
    )

    assert report.omega > 0.0
    assert report.psi > 0.0
    assert len(report.hp_scores) == 10
    assert report.hp_scores[3].score == pytest.approx(0.9)
    assert report.hp_scores[5].score == pytest.approx(0.8)
    assert report.hp_scores[7].score == pytest.approx(0.7)
    assert report.psi_components["prediction"] >= 0.0
    assert report.assurance_summary["status"] == "PASS"
    assert observed["repo_root"] == repo_root
    assert observed["state_dir"] == tmp_path / ".dharma"
    assert observed["agents_dir"] == tmp_path / ".dharma" / "ginko" / "agents"


@pytest.mark.asyncio
async def test_score_dharma_compliance_checks_dharma_layer_path_not_kernel_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        del cwd, capture_output, text, timeout, check
        calls.append(cmd)

        class _Proc:
            returncode = 0
            stdout = ""

        return _Proc()

    monkeypatch.setattr("dharma_swarm.autoresearch_eval.subprocess.run", fake_run)

    score, detail = await _score_dharma_compliance(tmp_path)

    assert score == pytest.approx(1.0)
    assert detail["dharma_layer_clean"] is True
    assert calls == [["git", "status", "--porcelain=v1", "--", "dharma/"]]
