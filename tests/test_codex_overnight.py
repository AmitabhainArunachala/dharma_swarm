from __future__ import annotations

import errno
import importlib
import json
import pwd
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import dharma_swarm.codex_overnight as overnight
from dharma_swarm.codex_overnight import (
    GitSnapshot,
    build_codex_exec_command,
    build_codex_env,
    build_cycle_prompt,
    ensure_autoresearch_files,
    gather_git_snapshot,
    parse_summary_fields,
    prepare_codex_home,
    run_cycle,
)


def test_build_codex_exec_command_includes_model_and_state_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    state_dir = tmp_path / ".dharma"
    output_file = tmp_path / "last_message.txt"
    cmd = build_codex_exec_command(
        repo_root=repo_root,
        state_dir=state_dir,
        output_file=output_file,
        model="gpt-5.4",
    )

    assert cmd[:6] == ["codex", "-a", "never", "-s", "workspace-write", "exec"]
    assert cmd[6:8] == ["-m", "gpt-5.4"]
    assert "--add-dir" in cmd
    assert str(state_dir) in cmd
    assert "-o" in cmd
    assert str(output_file) in cmd
    assert "--full-auto" not in cmd
    assert cmd[-1] == "-"


def test_build_cycle_prompt_mentions_mission_and_dirty_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    state_dir = tmp_path / ".dharma"
    (repo_root / "docs" / "dse").mkdir(parents=True)
    (repo_root / "docs" / "dse" / "README.md").write_text("# DSE\n", encoding="utf-8")
    snapshot = GitSnapshot(
        branch="main",
        head="abc123",
        dirty=True,
        changed_files=[" M dharma_swarm/swarm.py", "?? tests/test_new.py"],
        staged_count=0,
        unstaged_count=1,
        untracked_count=1,
    )

    prompt = build_cycle_prompt(
        mission="Ship the next bounded DSE slice.",
        repo_root=repo_root,
        state_dir=state_dir,
        cycle=3,
        before=snapshot,
        previous_summary="RESULT: previous cycle landed tests",
    )

    assert "Ship the next bounded DSE slice." in prompt
    assert "Respect existing uncommitted user changes." in prompt
    assert "docs/dse/README.md" in prompt
    assert "?? tests/test_new.py" in prompt
    assert "HYPOTHESIS:" in prompt
    assert "SELF_UPDATE:" in prompt
    assert "CRITIC_UPDATE:" in prompt
    assert "locked local scorer at `evaluate.py`" in prompt


def test_build_cycle_prompt_surfaces_focus_metrics_and_isolation_context(tmp_path: Path) -> None:
    repo_root = tmp_path / "worktree"
    source_repo_root = tmp_path / "source"
    state_dir = tmp_path / ".dharma"
    snapshot = _snapshot(dirty=False)

    prompt = build_cycle_prompt(
        mission="Target the weakest runtime metrics.",
        repo_root=repo_root,
        state_dir=state_dir,
        cycle=9,
        before=snapshot,
        previous_summary="RESULT: previous cycle landed.",
        source_repo_root=source_repo_root,
        isolated_worktree=True,
        focus_metrics=("cost_efficiency (0.4125)", "latency_p95 (0.5074)", "tool_reliability (0.8856)"),
        preloaded_overlay=("dharma_swarm/codex_overnight.py", "evaluate.py"),
    )

    assert "Current weakest scored dimensions to target directly" in prompt
    assert "cost_efficiency (0.4125)" in prompt
    assert "latency_p95 (0.5074)" in prompt
    assert "tool_reliability (0.8856)" in prompt
    assert f"isolated git worktree at {repo_root}" in prompt
    assert str(source_repo_root) in prompt
    assert "supervisor overlay files" in prompt
    assert "dharma_swarm/codex_overnight.py" in prompt


def test_gather_git_snapshot_counts_untracked_and_unstaged_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True, capture_output=True, text=True)

    tracked = repo_root / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    tracked.write_text("base\nchange\n", encoding="utf-8")
    (repo_root / "new.txt").write_text("hello\n", encoding="utf-8")

    snapshot = gather_git_snapshot(repo_root)

    assert snapshot.branch != "unknown"
    assert snapshot.dirty is True
    assert snapshot.unstaged_count >= 1
    assert snapshot.untracked_count == 1
    assert any("tracked.txt" in line for line in snapshot.changed_files)


def test_parse_summary_fields_extracts_structured_lines() -> None:
    fields = parse_summary_fields(
        "HYPOTHESIS: adding timeouts to TAP health checks avoids router stalls\n"
        "PREDICTED_OMEGA_DELTA: +0.04\n"
        "PREDICTED_PSI_DELTA: +0.02\n"
        "CONFIDENCE: 0.80\n"
        "RESULT: shipped bounded slice\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest tests/test_codex_overnight.py -q\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: explicit timeouts improve routing resilience\n"
        "CRITIC_UPDATE: none\n"
    )

    assert fields["hypothesis"] == "adding timeouts to TAP health checks avoids router stalls"
    assert fields["predicted_omega_delta"] == "+0.04"
    assert fields["predicted_psi_delta"] == "+0.02"
    assert fields["confidence"] == "0.80"
    assert fields["result"] == "shipped bounded slice"
    assert fields["files"] == "dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py"
    assert fields["tests"] == "pytest tests/test_codex_overnight.py -q"
    assert fields["blockers"] == "none"
    assert fields["self_update"] == "explicit timeouts improve routing resilience"
    assert fields["critic_update"] == "none"


def test_parse_float_field_rejects_non_finite_values() -> None:
    assert overnight._parse_float_field(float("nan")) is None
    assert overnight._parse_float_field(float("inf")) is None
    assert overnight._parse_float_field("-inf") is None
    assert overnight._parse_float_field("nan%") is None


def test_parse_eval_summary_line_ignores_non_finite_metrics() -> None:
    parsed = overnight._parse_eval_summary_line("Ω=nan Ψ=inf HP1=0.9000 HP2=-inf")

    assert parsed["summary_line"] == "Ω=nan Ψ=inf HP1=0.9000 HP2=-inf"
    assert "omega" not in parsed
    assert "psi" not in parsed
    assert parsed["hp_scores"] == [
        {
            "name": "HP1",
            "score": pytest.approx(0.9),
            "weight": 0.0,
            "detail": {},
        }
    ]


def test_resolve_cycle_summary_prefers_more_structured_stdout_over_partial_output(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "last_message.txt"
    output_file.write_text("RESULT: partial summary only\n", encoding="utf-8")
    stdout_summary = (
        "HYPOTHESIS: prefer the more structured cycle summary source\n"
        "PREDICTED_OMEGA_DELTA: +0.02\n"
        "PREDICTED_PSI_DELTA: +0.01\n"
        "CONFIDENCE: 0.75\n"
        "RESULT: preserved the complete cycle summary\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: summary selection should prefer richer structured output\n"
        "CRITIC_UPDATE: none\n"
    )

    resolved = overnight._resolve_cycle_summary(output_file=output_file, stdout=stdout_summary)

    assert resolved == stdout_summary.strip()


def test_resolve_cycle_summary_prefers_meaningful_stdout_over_default_filled_output(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "last_message.txt"
    output_file.write_text(
        "HYPOTHESIS: unknown\n"
        "PREDICTED_OMEGA_DELTA: unknown\n"
        "PREDICTED_PSI_DELTA: unknown\n"
        "CONFIDENCE: unknown\n"
        "RESULT: (missing)\n"
        "FILES: none\n"
        "TESTS: not run\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: none\n"
        "CRITIC_UPDATE: none\n",
        encoding="utf-8",
    )
    stdout_summary = (
        "HYPOTHESIS: prefer the summary source with real signal over placeholder defaults\n"
        "PREDICTED_OMEGA_DELTA: +0.03\n"
        "PREDICTED_PSI_DELTA: +0.02\n"
        "CONFIDENCE: 0.81\n"
        "RESULT: preserved the substantive cycle report\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: summary scoring should discount default placeholders\n"
        "CRITIC_UPDATE: none\n"
    )

    resolved = overnight._resolve_cycle_summary(output_file=output_file, stdout=stdout_summary)

    assert resolved == stdout_summary.strip()


def test_parse_eval_summary_line_accepts_summary_without_hp_scores() -> None:
    payload = overnight._parse_eval_summary_line(
        "DHARMA SWARM Autoresearch Eval\n"
        "Capability Metrics:\n"
        "\n"
        "Self-Understanding Metrics:\n"
        "\n"
        "Ω=0.8123 Ψ=0.7011\n"
    )

    assert payload["summary_line"] == "Ω=0.8123 Ψ=0.7011"
    assert payload["omega"] == pytest.approx(0.8123)
    assert payload["psi"] == pytest.approx(0.7011)
    assert payload.get("hp_scores") is None


def test_classify_regime_prefers_oscillating_when_recent_deltas_flip_sign_multiple_times() -> None:
    regime = overnight._classify_regime(
        history=[0.80, 0.83, 0.81],
        current=0.84,
    )

    assert regime == "oscillating"


def test_ensure_autoresearch_files_creates_append_only_scaffolding(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    paths = ensure_autoresearch_files(repo_root)

    assert paths["self_model"].exists()
    assert paths["critic"].exists()
    assert paths["experiment_log"].exists()
    assert paths["audit_log"].exists()
    assert paths["hp_interactions"].exists()
    assert paths["results"].exists()
    assert "results_autoresearch.tsv" in str(paths["results"])
    header = paths["results"].read_text(encoding="utf-8")
    assert header.startswith("exp_id\ttimestamp\t")
    assert "actual_omega\tactual_psi\t" in header
    assert header.rstrip("\n").endswith("\tconfidence\tmetrics_source")


def test_ensure_autoresearch_files_restores_header_when_results_file_is_empty(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    results_path = repo_root / "results_autoresearch.tsv"
    results_path.write_text("", encoding="utf-8")

    paths = ensure_autoresearch_files(repo_root)

    assert paths["results"] == results_path
    assert results_path.read_text(encoding="utf-8") == overnight.AUTORESEARCH_RESULTS_HEADER


def test_sync_worktree_overlay_removes_deleted_source_file_from_isolated_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repo_root = tmp_path / "source-repo"
    source_repo_root.mkdir()
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()
    stale_path = worktree_root / "stale.txt"
    stale_path.write_text("stale\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "WORKTREE_OVERLAY_PATHS", ("stale.txt",))

    synced = overnight._sync_worktree_overlay(
        source_repo_root=source_repo_root,
        worktree_root=worktree_root,
    )

    assert synced == ["stale.txt"]
    assert not stale_path.exists()
    manifest = json.loads((worktree_root / ".codex_overnight_overlay.json").read_text(encoding="utf-8"))
    assert manifest["paths"] == ["stale.txt"]


def test_sync_worktree_overlay_removes_deleted_source_directory_from_isolated_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repo_root = tmp_path / "source-repo"
    source_repo_root.mkdir()
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()
    stale_dir = worktree_root / "stale-dir"
    stale_dir.mkdir()
    (stale_dir / "nested.txt").write_text("stale\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "WORKTREE_OVERLAY_PATHS", ("stale-dir",))

    synced = overnight._sync_worktree_overlay(
        source_repo_root=source_repo_root,
        worktree_root=worktree_root,
    )

    assert synced == ["stale-dir"]
    assert not stale_dir.exists()
    manifest = json.loads((worktree_root / ".codex_overnight_overlay.json").read_text(encoding="utf-8"))
    assert manifest["paths"] == ["stale-dir"]


def test_ensure_autoresearch_files_migrates_legacy_locked_rows_to_current_schema(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    results_path = repo_root / "results_autoresearch.tsv"
    results_path.write_text(
        overnight.AUTORESEARCH_RESULTS_HEADER
        + "001\t2026-03-18T00:00:00Z\tCarry locked metrics forward\t+0.02\t+0.01\t0.8100\t0.6200\tnone\tpytest -q\tkeep\tbaseline\tLegacy row without confidence or metrics source\n",
        encoding="utf-8",
    )

    ensure_autoresearch_files(repo_root)

    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == overnight.AUTORESEARCH_RESULTS_HEADER.rstrip("\n")
    assert len(lines[1].split("\t")) == len(overnight.AUTORESEARCH_RESULTS_COLUMNS)
    assert lines[1].endswith("\tunknown\tlocked")


def test_ensure_autoresearch_files_migrates_proxy_header_rows_to_current_schema(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    results_path = repo_root / "results_autoresearch.tsv"
    results_path.write_text(
        "exp_id\ttimestamp\thypothesis\tpredicted_omega_delta\tpredicted_psi_delta\t"
        "actual_omega_proxy\tactual_psi_proxy\tfiles\ttests\tkept\tregime\tnotes\n"
        "001\t2026-03-18T00:00:00Z\tPreserve proxy history\t+0.01\t+0.01\t0.7000\t0.5000\tnone\tpytest -q\tkeep\tbaseline\tProxy-only legacy row\n",
        encoding="utf-8",
    )

    ensure_autoresearch_files(repo_root)

    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == overnight.AUTORESEARCH_RESULTS_HEADER.rstrip("\n")
    migrated = lines[1].split("\t")
    assert migrated[5] == "0.7000"
    assert migrated[6] == "0.5000"
    assert migrated[-2:] == ["unknown", "proxy"]


def test_ensure_autoresearch_files_salvages_headerless_legacy_locked_rows(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    results_path = repo_root / "results_autoresearch.tsv"
    results_path.write_text(
        "001\t2026-03-18T00:00:00Z\tRecover headerless locked row\t+0.02\t+0.01\t"
        "0.8100\t0.6200\tnone\tpytest -q\tkeep\tbaseline\tLegacy row without header\n",
        encoding="utf-8",
    )

    ensure_autoresearch_files(repo_root)

    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == overnight.AUTORESEARCH_RESULTS_HEADER.rstrip("\n")
    assert lines[1].split("\t") == [
        "001",
        "2026-03-18T00:00:00Z",
        "Recover headerless locked row",
        "+0.02",
        "+0.01",
        "0.8100",
        "0.6200",
        "none",
        "pytest -q",
        "keep",
        "baseline",
        "Legacy row without header",
        "unknown",
        "locked",
    ]


def test_ensure_autoresearch_files_salvages_headerless_current_rows(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    results_path = repo_root / "results_autoresearch.tsv"
    results_path.write_text(
        "009\t2026-03-18T09:56:30Z\tPreserve current row\t+0.01\t+0.02\t\t\t"
        "dharma_swarm/codex_overnight.py\tpytest -q tests/test_codex_overnight.py\t"
        "discard\tconverging\tCurrent row without header\t0.82\tproxy\n",
        encoding="utf-8",
    )

    ensure_autoresearch_files(repo_root)

    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == overnight.AUTORESEARCH_RESULTS_HEADER.rstrip("\n")
    assert lines[1].split("\t") == [
        "009",
        "2026-03-18T09:56:30Z",
        "Preserve current row",
        "+0.01",
        "+0.02",
        "",
        "",
        "dharma_swarm/codex_overnight.py",
        "pytest -q tests/test_codex_overnight.py",
        "discard",
        "converging",
        "Current row without header",
        "0.82",
        "proxy",
    ]


def test_ensure_autoresearch_files_normalizes_results_rows_while_lock_is_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    results_path = repo_root / "results_autoresearch.tsv"
    results_path.write_text(
        overnight.AUTORESEARCH_RESULTS_HEADER
        + "001\t2026-03-18T00:00:00Z\tRepair under lock\t+0.01\t+0.01\t0.8000\t0.6000\tnone\tpytest -q\tkeep\tbaseline\tLegacy row without confidence or metrics source\n",
        encoding="utf-8",
    )
    calls: list[int] = []
    state = {"locked": False}
    original_normalize = overnight._normalize_results_tsv

    def recording_flock(_fd: int, op: int) -> None:
        calls.append(op)
        if op == overnight.fcntl.LOCK_EX:
            state["locked"] = True
        elif op == overnight.fcntl.LOCK_UN:
            state["locked"] = False

    def asserting_normalize(text: str) -> str:
        assert state["locked"] is True
        return original_normalize(text)

    monkeypatch.setattr(overnight.fcntl, "flock", recording_flock)
    monkeypatch.setattr(overnight, "_normalize_results_tsv", asserting_normalize)

    ensure_autoresearch_files(repo_root)

    assert calls == [overnight.fcntl.LOCK_EX, overnight.fcntl.LOCK_UN]
    assert state["locked"] is False
    assert results_path.read_text(encoding="utf-8").splitlines()[1].endswith("\tunknown\tlocked")


def test_append_autoresearch_artifacts_locks_experiment_and_results_appends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths = ensure_autoresearch_files(repo_root)
    calls: list[int] = []

    monkeypatch.setattr(overnight.fcntl, "flock", lambda _fd, op: calls.append(op))

    overnight._append_autoresearch_artifacts(
        repo_root=repo_root,
        snapshot={
            "cycle": 7,
            "ts": "2026-03-18T12:00:00Z",
            "summary_fields": {
                "hypothesis": "locked appends prevent interleaved overnight artifacts",
                "predicted_omega_delta": "+0.01",
                "predicted_psi_delta": "+0.01",
                "confidence": "0.70",
                "result": "shipped bounded slice",
                "files": "dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py",
                "tests": "pytest -q tests/test_codex_overnight.py",
                "blockers": "none",
                "self_update": "none",
                "critic_update": "none",
            },
            "metrics_source": "locked",
            "actual_omega": 0.82,
            "actual_psi": 0.61,
            "omega_proxy": 0.5,
            "psi_proxy": 0.5,
            "regime": "baseline",
            "kept": True,
            "evaluator": {"summary_line": "Ω=0.8200 Ψ=0.6100"},
        },
    )

    experiment_log = paths["experiment_log"].read_text(encoding="utf-8")
    results_lines = paths["results"].read_text(encoding="utf-8").splitlines()

    assert "## Cycle 007 — 2026-03-18T12:00:00Z" in experiment_log
    assert results_lines[-1].startswith(
        "007\t2026-03-18T12:00:00Z\tlocked appends prevent interleaved overnight artifacts\t"
    )
    assert calls == [
        overnight.fcntl.LOCK_EX,
        overnight.fcntl.LOCK_UN,
        overnight.fcntl.LOCK_EX,
        overnight.fcntl.LOCK_UN,
        overnight.fcntl.LOCK_EX,
        overnight.fcntl.LOCK_UN,
    ]


def test_append_autoresearch_artifacts_normalizes_multiline_results_row_fields(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths = ensure_autoresearch_files(repo_root)

    overnight._append_autoresearch_artifacts(
        repo_root=repo_root,
        snapshot={
            "cycle": 8,
            "ts": "2026-03-18T12:05:00Z",
            "summary_fields": {
                "hypothesis": "flatten multiline\nhypotheses\tbefore append",
                "predicted_omega_delta": "+0.02",
                "predicted_psi_delta": "+0.01",
                "confidence": "0.71\n",
                "result": "bounded slice\nwith wrapped note",
                "files": "dharma_swarm/codex_overnight.py,\ntests/test_codex_overnight.py",
                "tests": "pytest -q tests/test_codex_overnight.py\r\npython3 -m compileall",
                "blockers": "none",
                "self_update": "none",
                "critic_update": "none",
            },
            "metrics_source": "locked",
            "actual_omega": 0.83,
            "actual_psi": 0.62,
            "omega_proxy": 0.5,
            "psi_proxy": 0.5,
            "regime": "baseline\n",
            "kept": False,
            "evaluator": {"summary_line": "Ω=0.8300 Ψ=0.6200"},
        },
    )

    results_lines = paths["results"].read_text(encoding="utf-8").splitlines()

    assert len(results_lines) == 2
    row = results_lines[-1].split("\t")
    assert len(row) == len(overnight.AUTORESEARCH_RESULTS_COLUMNS)
    assert row == [
        "008",
        "2026-03-18T12:05:00Z",
        "flatten multiline hypotheses before append",
        "+0.02",
        "+0.01",
        "0.8300",
        "0.6200",
        "dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py",
        "pytest -q tests/test_codex_overnight.py  python3 -m compileall",
        "discard",
        "baseline",
        "bounded slice with wrapped note",
        "0.71",
        "locked",
    ]


def test_atomic_write_text_overwrites_existing_file_without_leaving_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.json"

    overnight._atomic_write_text(target, '{"v": 1}\n')
    overnight._atomic_write_text(target, '{"v": 2}\n')

    assert target.read_text(encoding="utf-8") == '{"v": 2}\n'
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_append_text_uses_advisory_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "log.md"
    calls: list[int] = []

    monkeypatch.setattr(overnight.fcntl, "flock", lambda _fd, op: calls.append(op))

    overnight.append_text(target, "hello world")

    assert target.read_text(encoding="utf-8") == "hello world\n"
    assert calls == [overnight.fcntl.LOCK_EX, overnight.fcntl.LOCK_UN]


def test_append_jsonl_uses_advisory_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "cycles.jsonl"
    calls: list[int] = []

    monkeypatch.setattr(overnight.fcntl, "flock", lambda _fd, op: calls.append(op))

    overnight.append_jsonl(target, {"cycle": 1, "ok": True})

    assert target.read_text(encoding="utf-8") == '{"cycle": 1, "ok": true}\n'
    assert calls == [overnight.fcntl.LOCK_EX, overnight.fcntl.LOCK_UN]


def test_read_json_returns_empty_mapping_for_non_object_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('["not", "an", "object"]\n', encoding="utf-8")

    assert overnight._read_json(payload_path) == {}


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

        reloaded = importlib.reload(overnight)
        parser = reloaded.build_arg_parser()
        defaults = parser.parse_args([])
        config_text = reloaded._render_minimal_codex_config(repo_root=tmp_path / "repo")

        assert reloaded.LOGIN_HOME == login_home
        assert reloaded.ROOT == login_home / "dharma_swarm"
        assert reloaded.STATE == login_home / ".dharma"
        assert reloaded.REAL_CODEX_DIR == login_home / ".codex"
        assert defaults.repo_root == str(login_home / "dharma_swarm")
        assert defaults.state_dir == str(login_home / ".dharma")
        assert f'[projects."{login_home}"]' in config_text
        assert f'[projects."{env_home}"]' not in config_text

    importlib.reload(overnight)


def test_prepare_codex_home_creates_lean_home_and_copies_runtime_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")
    (real_codex_dir / "version.json").write_text('{"version":"1"}\n', encoding="utf-8")
    (real_codex_dir / "skills" / ".system").mkdir(parents=True)
    (real_codex_dir / "skills" / ".system" / "SKILL.md").write_text("skill body\n", encoding="utf-8")
    (real_codex_dir / "agents").mkdir()
    (real_codex_dir / "agents" / "reviewer.toml").write_text("model = 'gpt-5.4'\n", encoding="utf-8")
    (real_codex_dir / "rules").mkdir()
    (real_codex_dir / "rules" / "default.rules").write_text("allow all\n", encoding="utf-8")
    (real_codex_dir / "vendor_imports").mkdir()
    (real_codex_dir / "vendor_imports" / "skills-curated-cache.json").write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    home_root = prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    lean_codex_dir = home_root / ".codex"
    assert home_root == state_dir / "codex_lean_home"
    assert (home_root / ".dharma").is_symlink()
    assert (home_root / ".dharma").resolve() == state_dir
    assert (lean_codex_dir / "memories").is_dir()
    assert (lean_codex_dir / "auth.json").read_text(encoding="utf-8") == '{"token":"abc"}\n'
    assert (lean_codex_dir / "version.json").read_text(encoding="utf-8") == '{"version":"1"}\n'
    assert (lean_codex_dir / "skills" / ".system" / "SKILL.md").read_text(encoding="utf-8") == "skill body\n"
    assert (lean_codex_dir / "agents" / "reviewer.toml").read_text(encoding="utf-8") == "model = 'gpt-5.4'\n"
    assert (lean_codex_dir / "rules" / "default.rules").read_text(encoding="utf-8") == "allow all\n"
    assert (lean_codex_dir / "vendor_imports" / "skills-curated-cache.json").read_text(encoding="utf-8") == "[]\n"

    config_text = (lean_codex_dir / "config.toml").read_text(encoding="utf-8")
    assert f'[projects."{overnight.LOGIN_HOME}"]' in config_text
    assert f'[projects."{repo_root}"]' in config_text
    assert 'approval_policy = "never"' in config_text


def test_prepare_codex_home_honors_custom_home_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    custom_home = tmp_path / "isolated-home"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    home_root = prepare_codex_home(
        repo_root=repo_root,
        state_dir=state_dir,
        home_root=custom_home,
    )

    assert home_root == custom_home
    assert not (state_dir / "codex_lean_home").exists()
    assert (custom_home / ".dharma").is_symlink()
    assert (custom_home / ".dharma").resolve() == state_dir
    assert (custom_home / ".codex" / "auth.json").read_text(encoding="utf-8") == '{"token":"abc"}\n'
    assert (custom_home / ".codex" / "config.toml").exists()


def test_prepare_codex_home_refreshes_managed_entries_without_clearing_memories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"first"}\n', encoding="utf-8")
    (real_codex_dir / "skills" / ".system").mkdir(parents=True)
    (real_codex_dir / "skills" / ".system" / "fresh.md").write_text("fresh\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    home_root = prepare_codex_home(repo_root=repo_root, state_dir=state_dir)
    lean_codex_dir = home_root / ".codex"
    (lean_codex_dir / "skills" / ".system" / "stale.md").write_text("stale\n", encoding="utf-8")
    (lean_codex_dir / "memories" / "note.txt").write_text("keep me\n", encoding="utf-8")

    (real_codex_dir / "auth.json").write_text('{"token":"second"}\n', encoding="utf-8")
    prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    assert (lean_codex_dir / "auth.json").read_text(encoding="utf-8") == '{"token":"second"}\n'
    assert (lean_codex_dir / "skills" / ".system" / "fresh.md").read_text(encoding="utf-8") == "fresh\n"
    assert not (lean_codex_dir / "skills" / ".system" / "stale.md").exists()
    assert (lean_codex_dir / "memories" / "note.txt").read_text(encoding="utf-8") == "keep me\n"


def test_prepare_codex_home_replaces_stale_nonempty_state_alias_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    home_root = state_dir / "codex_lean_home"
    stale_alias = home_root / ".dharma"
    (stale_alias / "nested").mkdir(parents=True)
    (stale_alias / "nested" / "orphan.txt").write_text("stale\n", encoding="utf-8")

    prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    assert stale_alias.is_symlink()
    assert stale_alias.resolve() == state_dir.resolve()
    assert not (stale_alias / "nested" / "orphan.txt").exists()


def test_prepare_codex_home_removes_managed_entries_when_source_disappears(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")
    (real_codex_dir / "skills" / ".system").mkdir(parents=True)
    (real_codex_dir / "skills" / ".system" / "SKILL.md").write_text("skill body\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    home_root = prepare_codex_home(repo_root=repo_root, state_dir=state_dir)
    lean_codex_dir = home_root / ".codex"
    assert (lean_codex_dir / "auth.json").exists()
    assert (lean_codex_dir / "skills").is_dir()

    (real_codex_dir / "auth.json").unlink()
    shutil.rmtree(real_codex_dir / "skills")

    prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    assert not (lean_codex_dir / "auth.json").exists()
    assert not (lean_codex_dir / "skills").exists()


def test_prepare_codex_home_replaces_dangling_managed_file_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"fresh"}\n', encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    lean_codex_dir = state_dir / "codex_lean_home" / ".codex"
    lean_codex_dir.mkdir(parents=True)
    stale_link = lean_codex_dir / "auth.json"
    stale_link.symlink_to(tmp_path / "missing-auth.json")

    prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    assert stale_link.is_symlink() is False
    assert stale_link.read_text(encoding="utf-8") == '{"token":"fresh"}\n'


def test_prepare_codex_home_replaces_managed_directory_symlink_without_touching_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "skills" / ".system").mkdir(parents=True)
    (real_codex_dir / "skills" / ".system" / "SKILL.md").write_text("fresh skill\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    lean_codex_dir = state_dir / "codex_lean_home" / ".codex"
    lean_codex_dir.mkdir(parents=True)
    foreign_skills_dir = tmp_path / "foreign-skills"
    foreign_skills_dir.mkdir()
    (foreign_skills_dir / "stale.md").write_text("leave me alone\n", encoding="utf-8")
    skills_link = lean_codex_dir / "skills"
    skills_link.symlink_to(foreign_skills_dir, target_is_directory=True)

    prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    assert skills_link.is_symlink() is False
    assert (skills_link / ".system" / "SKILL.md").read_text(encoding="utf-8") == "fresh skill\n"
    assert (foreign_skills_dir / "stale.md").read_text(encoding="utf-8") == "leave me alone\n"


def test_prepare_codex_home_replaces_config_symlink_without_touching_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    lean_codex_dir = state_dir / "codex_lean_home" / ".codex"
    lean_codex_dir.mkdir(parents=True)
    foreign_config = tmp_path / "foreign-config.toml"
    foreign_config.write_text("keep = true\n", encoding="utf-8")
    config_link = lean_codex_dir / "config.toml"
    config_link.symlink_to(foreign_config)

    prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    assert config_link.is_symlink() is False
    assert 'approval_policy = "never"' in config_link.read_text(encoding="utf-8")
    assert foreign_config.read_text(encoding="utf-8") == "keep = true\n"


def test_prepare_codex_home_replaces_empty_nested_dharma_dir_with_state_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    nested_state_dir = state_dir / "codex_lean_home" / ".dharma"
    nested_state_dir.mkdir(parents=True)

    home_root = prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    state_alias = home_root / ".dharma"
    assert state_alias.is_symlink()
    assert state_alias.resolve() == state_dir


def test_prepare_codex_home_skips_managed_file_that_disappears_mid_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    real_copy2 = shutil.copy2

    def flaky_copy2(src, dst, *args, **kwargs):
        src_path = Path(src)
        if src_path.name == "auth.json":
            src_path.unlink()
            raise FileNotFoundError(src)
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(overnight.shutil, "copy2", flaky_copy2)

    home_root = prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    lean_codex_dir = home_root / ".codex"
    assert (lean_codex_dir / "config.toml").exists()
    assert not (lean_codex_dir / "auth.json").exists()


def test_prepare_codex_home_skips_managed_directory_when_copytree_reports_only_missing_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "skills" / ".system").mkdir(parents=True)
    (real_codex_dir / "skills" / ".system" / "SKILL.md").write_text("skill body\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)

    real_copytree = shutil.copytree

    def flaky_copytree(src, dst, *args, **kwargs):
        src_path = Path(src)
        if src_path.name == "skills":
            raise shutil.Error(
                [
                    (
                        str(src_path / ".system" / "SKILL.md"),
                        str(Path(dst) / ".system" / "SKILL.md"),
                        FileNotFoundError("transient"),
                    )
                ]
            )
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(overnight.shutil, "copytree", flaky_copytree)

    home_root = prepare_codex_home(repo_root=repo_root, state_dir=state_dir)

    lean_codex_dir = home_root / ".codex"
    assert (lean_codex_dir / "config.toml").exists()
    assert not (lean_codex_dir / "skills").exists()


def test_build_codex_env_scrubs_codex_vars_and_points_home_to_lean_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")
    (real_codex_dir / "skills" / ".system").mkdir(parents=True)
    (real_codex_dir / "skills" / ".system" / "SKILL.md").write_text("skill body\n", encoding="utf-8")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)
    monkeypatch.setenv("CODEX_HOME", "/tmp/old-codex-home")
    monkeypatch.setenv("CODEX_API_KEY", "stale-key")
    monkeypatch.setenv("UNCHANGED_ENV", "still-here")

    env = build_codex_env(repo_root=repo_root, state_dir=state_dir)

    assert env["HOME"] == str(state_dir / "codex_lean_home")
    assert env["DHARMA_HOME"] == str(state_dir)
    assert env["PWD"] == str(repo_root)
    assert env["UNCHANGED_ENV"] == "still-here"
    assert "CODEX_HOME" not in env
    assert "CODEX_API_KEY" not in env
    assert (Path(env["HOME"]) / ".codex" / "auth.json").exists()
    assert (Path(env["HOME"]) / ".codex" / "skills" / ".system" / "SKILL.md").read_text(encoding="utf-8") == "skill body\n"


def _snapshot(*, dirty: bool = False) -> GitSnapshot:
    return GitSnapshot(
        branch="main",
        head="abc123",
        dirty=dirty,
        changed_files=[" M dharma_swarm/example.py"] if dirty else [],
        staged_count=0,
        unstaged_count=1 if dirty else 0,
        untracked_count=0,
    )


def test_run_cycle_falls_back_to_stdout_when_codex_output_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: a bounded fallback cycle should still log autoresearch state\n"
        "PREDICTED_OMEGA_DELTA: +0.01\n"
        "PREDICTED_PSI_DELTA: +0.02\n"
        "CONFIDENCE: 0.65\n"
        "RESULT: fallback from stdout\n"
        "FILES: none\n"
        "TESTS: not run\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: even summary fallback cycles should preserve the self-model trail\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None and "Cycle: 1" in input_text
        assert env is not None
        assert env["PWD"] == str(repo_root)
        assert env["HOME"].endswith("codex_lean_home")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8200 Ψ=0.6100 HP1=0.8000",
            "omega": 0.82,
            "psi": 0.61,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["summary_text"] == stdout_summary.strip()
    assert result["omega_proxy"] > 0
    assert result["psi_proxy"] > 0
    assert result["actual_omega"] == pytest.approx(0.82)
    assert result["actual_psi"] == pytest.approx(0.61)
    assert result["metrics_source"] == "locked"
    assert result["regime"] == "baseline"
    assert result["kept"] is True
    assert (run_dir / "latest_last_message.txt").read_text(encoding="utf-8") == stdout_summary
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "RESULT: fallback from stdout FILES: none TESTS: not run BLOCKERS: none" in report_text
    assert (repo_root / "SELF.md").exists()
    assert "preserve the self-model trail" in (repo_root / "SELF.md").read_text(encoding="utf-8")
    results_lines = (repo_root / "results_autoresearch.tsv").read_text(encoding="utf-8").splitlines()
    assert len(results_lines) >= 2
    assert results_lines[-1].endswith("\t0.65\tlocked")


def test_run_cycle_uses_run_scoped_codex_home_to_avoid_shared_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    real_codex_dir = tmp_path / "real_codex"
    real_codex_dir.mkdir()
    (real_codex_dir / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: run-scoped Codex homes avoid shared overnight mutation\n"
        "PREDICTED_OMEGA_DELTA: +0.01\n"
        "PREDICTED_PSI_DELTA: +0.01\n"
        "CONFIDENCE: 0.69\n"
        "RESULT: isolated the cycle Codex home under the run directory\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: concurrent overnight runs should not share mutable Codex lean homes\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None and "Cycle: 1" in input_text
        assert env is not None
        assert env["HOME"] == str(run_dir / "codex_lean_home")
        assert (Path(env["HOME"]) / ".codex" / "auth.json").read_text(encoding="utf-8") == '{"token":"abc"}\n'
        assert (Path(env["HOME"]) / ".codex" / "config.toml").exists()
        assert not (state_dir / "codex_lean_home").exists()
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "REAL_CODEX_DIR", real_codex_dir)
    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8200 Ψ=0.6100",
            "omega": 0.82,
            "psi": 0.61,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert (run_dir / "codex_lean_home" / ".codex" / "auth.json").exists()
    assert not (state_dir / "codex_lean_home").exists()


def test_run_cycle_prefers_stdout_when_output_file_summary_is_incomplete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: richer stdout summaries should override partial last-message files\n"
        "PREDICTED_OMEGA_DELTA: +0.02\n"
        "PREDICTED_PSI_DELTA: +0.01\n"
        "CONFIDENCE: 0.72\n"
        "RESULT: preserved the complete cycle summary despite a partial output file\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: summary source selection should be based on structured completeness\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None and "Cycle: 1" in input_text
        assert env is not None
        output_file = Path(cmd[cmd.index("-o") + 1])
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("RESULT: partial summary only\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8200 Ψ=0.6100",
            "omega": 0.82,
            "psi": 0.61,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["summary_text"] == stdout_summary.strip()
    assert result["summary_fields"]["hypothesis"] == (
        "richer stdout summaries should override partial last-message files"
    )
    assert result["summary_fields"]["result"] == (
        "preserved the complete cycle summary despite a partial output file"
    )
    assert (run_dir / "latest_last_message.txt").read_text(encoding="utf-8") == stdout_summary


def test_run_cycle_prefers_stdout_when_output_file_is_only_default_placeholders(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: richer stdout summaries should beat default placeholder last-message files\n"
        "PREDICTED_OMEGA_DELTA: +0.03\n"
        "PREDICTED_PSI_DELTA: +0.02\n"
        "CONFIDENCE: 0.81\n"
        "RESULT: retained the real cycle report instead of the placeholder template\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: placeholder summaries should not outrank substantive stdout\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None and "Cycle: 1" in input_text
        assert env is not None
        output_file = Path(cmd[cmd.index("-o") + 1])
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            "HYPOTHESIS: unknown\n"
            "PREDICTED_OMEGA_DELTA: unknown\n"
            "PREDICTED_PSI_DELTA: unknown\n"
            "CONFIDENCE: unknown\n"
            "RESULT: (missing)\n"
            "FILES: none\n"
            "TESTS: not run\n"
            "BLOCKERS: none\n"
            "SELF_UPDATE: none\n"
            "CRITIC_UPDATE: none\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8400 Ψ=0.6200",
            "omega": 0.84,
            "psi": 0.62,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["summary_text"] == stdout_summary.strip()
    assert result["summary_fields"]["hypothesis"] == (
        "richer stdout summaries should beat default placeholder last-message files"
    )
    assert result["summary_fields"]["result"] == (
        "retained the real cycle report instead of the placeholder template"
    )
    assert (run_dir / "latest_last_message.txt").read_text(encoding="utf-8") == stdout_summary


def test_run_cycle_uses_timeout_output_as_summary_when_codex_times_out(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout, input_text
        assert env is not None
        assert env["PWD"] == str(repo_root)
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=30,
            output=b"RESULT: partial cycle output\nFILES: none\n",
            stderr=b"BLOCKERS: timed out\n",
        )

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "",
            "omega": None,
            "psi": None,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    latest_message = (run_dir / "latest_last_message.txt").read_text(encoding="utf-8")
    assert result["rc"] == 124
    assert result["timed_out"] is True
    assert result["summary_text"].splitlines() == [
        "HYPOTHESIS: unknown",
        "PREDICTED_OMEGA_DELTA: unknown",
        "PREDICTED_PSI_DELTA: unknown",
        "CONFIDENCE: unknown",
        "RESULT: partial cycle output",
        "FILES: none",
        "TESTS: not run",
        "BLOCKERS: timed out",
        "SELF_UPDATE: none",
        "CRITIC_UPDATE: none",
    ]
    assert latest_message == result["summary_text"] + "\n"


def test_run_cycle_records_structured_failure_when_codex_binary_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout, input_text, env
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", cmd[0])

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(
        overnight,
        "build_codex_env",
        lambda **_: {"HOME": str(state_dir / "codex_lean_home"), "PWD": str(repo_root)},
    )
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "",
            "omega": None,
            "psi": None,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    latest_message = (run_dir / "latest_last_message.txt").read_text(encoding="utf-8")
    assert result["rc"] == 127
    assert result["timed_out"] is False
    assert result["summary_fields"]["hypothesis"] == "unknown"
    assert result["summary_fields"]["predicted_omega_delta"] == "unknown"
    assert result["summary_fields"]["predicted_psi_delta"] == "unknown"
    assert result["summary_fields"]["confidence"] == "unknown"
    assert result["summary_fields"]["files"] == "none"
    assert result["summary_fields"]["tests"] == "not run"
    assert "codex invocation failed" in result["summary_fields"]["result"]
    assert "No such file or directory" in result["summary_fields"]["blockers"]
    assert result["summary_fields"]["self_update"] == "none"
    assert result["summary_fields"]["critic_update"] == "none"
    assert latest_message == result["summary_text"] + "\n"


def test_run_cycle_records_structured_failure_when_codex_home_prep_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_build_codex_env(**_: object) -> dict[str, str]:
        raise PermissionError(errno.EACCES, "Permission denied", state_dir / "codex_lean_home")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "build_codex_env", fake_build_codex_env)
    monkeypatch.setattr(
        overnight,
        "run_cmd",
        lambda *args, **kwargs: pytest.fail("codex should not launch when home prep fails"),
    )
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "",
            "omega": None,
            "psi": None,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    latest_message = (run_dir / "latest_last_message.txt").read_text(encoding="utf-8")
    assert result["rc"] == 126
    assert result["timed_out"] is False
    assert result["summary_fields"]["hypothesis"] == "unknown"
    assert result["summary_fields"]["predicted_omega_delta"] == "unknown"
    assert result["summary_fields"]["predicted_psi_delta"] == "unknown"
    assert result["summary_fields"]["confidence"] == "unknown"
    assert result["summary_fields"]["files"] == "none"
    assert result["summary_fields"]["tests"] == "not run"
    assert "codex home preparation failed" in result["summary_fields"]["result"]
    assert "Permission denied" in result["summary_fields"]["blockers"]
    assert result["summary_fields"]["self_update"] == "none"
    assert result["summary_fields"]["critic_update"] == "none"
    assert latest_message == result["summary_text"] + "\n"


def test_run_cycle_marks_metrics_unavailable_when_evaluator_launch_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: evaluator launch failure should not discard a bounded cycle\n"
        "PREDICTED_OMEGA_DELTA: +0.02\n"
        "PREDICTED_PSI_DELTA: +0.02\n"
        "CONFIDENCE: 0.70\n"
        "RESULT: shipped bounded slice\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: score-sidecar failures should not masquerade as locked metrics\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        if cmd[0] == "codex":
            assert input_text is not None and "Cycle: 1" in input_text
            assert env is not None
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")
        assert cmd[1] == "evaluate.py"
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", cmd[0])

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["evaluator"]["rc"] == 127
    assert result["evaluator"]["timed_out"] is False
    assert "evaluator invocation failed:" in result["evaluator"]["summary_line"]
    assert "No such file or directory" in result["evaluator"]["summary_line"]
    assert result["actual_omega"] is None
    assert result["actual_psi"] is None
    assert result["metrics_source"] == "unavailable"
    assert result["regime"] == "unknown"
    assert result["kept"] is False
    assert Path(result["evaluator"]["log_file"]).read_text(encoding="utf-8").startswith(
        "evaluator invocation failed:"
    )
    results_lines = (repo_root / "results_autoresearch.tsv").read_text(encoding="utf-8").splitlines()
    assert results_lines[-1].endswith("\t0.70\tunavailable")
    assert "\t\t" in results_lines[-1]


def test_run_locked_evaluator_parses_stdout_summary_when_json_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout, input_text, env
        assert cwd == repo_root
        assert cmd[0] == overnight.sys.executable
        assert cmd[1] == "evaluate.py"
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=(
                "DHARMA SWARM Autoresearch Eval\n"
                "Capability Metrics:\n"
                "\n"
                "Self-Understanding Metrics:\n"
                "\n"
                "Ω=0.8450 Ψ=0.6220\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)

    result = overnight._run_locked_evaluator(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["summary_line"] == "Ω=0.8450 Ψ=0.6220"
    assert result["omega"] == pytest.approx(0.8450)
    assert result["psi"] == pytest.approx(0.6220)
    assert result["hp_scores"] == []
    assert Path(result["log_file"]).read_text(encoding="utf-8").rstrip().endswith("Ω=0.8450 Ψ=0.6220")


def test_run_locked_evaluator_preserves_json_metrics_and_backfills_summary_line(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout, input_text, env
        assert cwd == repo_root
        assert cmd[0] == overnight.sys.executable
        assert cmd[1] == "evaluate.py"
        json_out = Path(cmd[cmd.index("--json-out") + 1])
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(
                {
                    "omega": 0.845,
                    "psi": 0.622,
                    "hp_scores": [
                        {
                            "name": "task_success_rate",
                            "score": 0.9,
                            "weight": 0.15,
                            "detail": {"passed": 4},
                        }
                    ],
                    "psi_components": {"prediction": 0.7},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=(
                "DHARMA SWARM Autoresearch Eval\n"
                "Capability Metrics:\n"
                "\n"
                "Self-Understanding Metrics:\n"
                "\n"
                "Ω=0.8450 Ψ=0.6220 HP1=0.9000\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)

    result = overnight._run_locked_evaluator(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["summary_line"] == "Ω=0.8450 Ψ=0.6220 HP1=0.9000"
    assert result["omega"] == pytest.approx(0.8450)
    assert result["psi"] == pytest.approx(0.6220)
    assert result["hp_scores"][0]["name"] == "task_success_rate"
    assert result["psi_components"] == {"prediction": 0.7}
    assert Path(result["json_file"]).exists()


def test_run_locked_evaluator_coerces_numeric_string_metrics_from_json_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout, input_text, env
        assert cwd == repo_root
        json_out = Path(cmd[cmd.index("--json-out") + 1])
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(
                {
                    "omega": "0.845",
                    "psi": "0.622",
                    "hp_scores": [],
                    "psi_components": {"prediction": 0.7},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=(
                "DHARMA SWARM Autoresearch Eval\n"
                "Capability Metrics:\n"
                "\n"
                "Self-Understanding Metrics:\n"
                "\n"
                "Ω=0.8450 Ψ=0.6220\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)

    result = overnight._run_locked_evaluator(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["summary_line"] == "Ω=0.8450 Ψ=0.6220"
    assert result["omega"] == pytest.approx(0.8450)
    assert result["psi"] == pytest.approx(0.6220)
    assert result["psi_components"] == {"prediction": 0.7}


def test_run_locked_evaluator_drops_non_finite_metrics_from_json_and_stdout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout, input_text, env
        assert cwd == repo_root
        json_out = Path(cmd[cmd.index("--json-out") + 1])
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(
                {
                    "omega": "nan",
                    "psi": "inf",
                    "hp_scores": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="Ω=nan Ψ=inf HP1=0.9000\n",
            stderr="",
        )

    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)

    result = overnight._run_locked_evaluator(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["summary_line"] == "Ω=nan Ψ=inf HP1=0.9000"
    assert result["omega"] is None
    assert result["psi"] is None
    assert result["hp_scores"] == [
        {
            "name": "HP1",
            "score": pytest.approx(0.9),
            "weight": 0.0,
            "detail": {},
        }
    ]


def test_run_locked_evaluator_ignores_non_mapping_json_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout, input_text, env
        assert cwd == repo_root
        json_out = Path(cmd[cmd.index("--json-out") + 1])
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text('["unexpected"]\n', encoding="utf-8")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=(
                "DHARMA SWARM Autoresearch Eval\n"
                "Capability Metrics:\n"
                "\n"
                "Self-Understanding Metrics:\n"
                "\n"
                "Ω=0.8450 Ψ=0.6220\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)

    result = overnight._run_locked_evaluator(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["summary_line"] == "Ω=0.8450 Ψ=0.6220"
    assert result["omega"] == pytest.approx(0.8450)
    assert result["psi"] == pytest.approx(0.6220)
    assert result["hp_scores"] == []


def test_run_cycle_ignores_non_mapping_previous_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "latest.json").write_text('["stale"]\n', encoding="utf-8")
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: corrupted previous snapshots should degrade to an empty baseline\n"
        "PREDICTED_OMEGA_DELTA: +0.01\n"
        "PREDICTED_PSI_DELTA: +0.01\n"
        "CONFIDENCE: 0.60\n"
        "RESULT: continued despite stale snapshot corruption\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: non-object state files should collapse to defaults instead of crashing the loop\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None
        assert env is not None
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8200 Ψ=0.6100",
            "omega": 0.82,
            "psi": 0.61,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["actual_omega"] == pytest.approx(0.82)
    assert result["actual_psi"] == pytest.approx(0.61)
    assert result["metrics_source"] == "locked"
    assert result["kept"] is True


def test_run_cycle_uses_stringified_locked_metrics_from_previous_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "latest.json").write_text(
        json.dumps(
            {
                "metrics_source": "locked",
                "actual_omega": "0.80",
                "actual_psi": "0.60",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "cycles.jsonl").write_text(
        json.dumps(
            {
                "metrics_source": "locked",
                "actual_omega": "0.79",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: stringified locked metrics should still drive keep decisions\n"
        "PREDICTED_OMEGA_DELTA: +0.01\n"
        "PREDICTED_PSI_DELTA: -0.01\n"
        "CONFIDENCE: 0.72\n"
        "RESULT: persisted metric drift no longer hides a regressing cycle\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: numeric-string state should still preserve evaluator continuity\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None
        assert env is not None
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8100 Ψ=0.5900",
            "omega": 0.81,
            "psi": 0.59,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["actual_omega"] == pytest.approx(0.81)
    assert result["actual_psi"] == pytest.approx(0.59)
    assert result["metrics_source"] == "locked"
    assert result["regime"] == "converging"
    assert result["kept"] is False


def test_run_cycle_marks_repeated_locked_metric_sign_flips_as_oscillating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "latest.json").write_text(
        json.dumps(
            {
                "metrics_source": "locked",
                "actual_omega": 0.81,
                "actual_psi": 0.60,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "cycles.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"metrics_source": "locked", "actual_omega": 0.80}),
                json.dumps({"metrics_source": "locked", "actual_omega": 0.83}),
                json.dumps({"metrics_source": "locked", "actual_omega": 0.81}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: repeated locked-metric sign flips should be labeled oscillating\n"
        "PREDICTED_OMEGA_DELTA: +0.03\n"
        "PREDICTED_PSI_DELTA: +0.00\n"
        "CONFIDENCE: 0.73\n"
        "RESULT: regime labels now preserve unstable progress patterns\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: trend labels should preserve oscillation, not collapse it into convergence\n"
        "CRITIC_UPDATE: none\n"
    )

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None
        assert env is not None
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8400 Ψ=0.6000",
            "omega": 0.84,
            "psi": 0.60,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    result = run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    assert result["rc"] == 0
    assert result["timed_out"] is False
    assert result["actual_omega"] == pytest.approx(0.84)
    assert result["actual_psi"] == pytest.approx(0.60)
    assert result["metrics_source"] == "locked"
    assert result["regime"] == "oscillating"
    assert result["kept"] is True


def test_run_cycle_uses_atomic_writes_for_checkpoint_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    run_dir = state_dir / "logs" / "codex_overnight" / "run"
    snapshots = [_snapshot(dirty=True), _snapshot(dirty=True)]
    stdout_summary = (
        "HYPOTHESIS: atomic checkpoint writes prevent truncated overnight state\n"
        "PREDICTED_OMEGA_DELTA: +0.01\n"
        "PREDICTED_PSI_DELTA: +0.01\n"
        "CONFIDENCE: 0.70\n"
        "RESULT: wrote checkpoint state atomically\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest -q tests/test_codex_overnight.py\n"
        "BLOCKERS: none\n"
        "SELF_UPDATE: checkpoint files should be replace-based, not rewritten in place\n"
        "CRITIC_UPDATE: none\n"
    )
    original_atomic_write = overnight._atomic_write_text
    written_paths: list[Path] = []

    def recording_atomic_write(
        path: Path,
        text: str,
        *,
        encoding: str = "utf-8",
        errors: str | None = None,
    ) -> None:
        written_paths.append(path)
        original_atomic_write(path, text, encoding=encoding, errors=errors)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None
        assert env is not None
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

    monkeypatch.setattr(overnight, "_atomic_write_text", recording_atomic_write)
    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        overnight,
        "_run_locked_evaluator",
        lambda **_: {
            "rc": 0,
            "timed_out": False,
            "summary_line": "Ω=0.8200 Ψ=0.6100",
            "omega": 0.82,
            "psi": 0.61,
            "hp_scores": [],
            "psi_components": {},
            "json_file": "",
            "report_file": "",
            "log_file": "",
        },
    )

    run_cycle(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=1,
        mission="Keep shipping.",
        model="",
        timeout=30,
    )

    written = set(written_paths)
    assert run_dir / "latest_last_message.txt" in written
    assert run_dir / "latest.json" in written
    assert overnight.heartbeat_file_for(state_dir) in written


def test_main_writes_manifest_and_handoff_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=True)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return initial_snapshot

    def fake_run_cycle(**_: object) -> dict[str, object]:
        summary_text = (
            "RESULT: shipped bounded slice\n"
            "FILES: dharma_swarm/codex_overnight.py\n"
            "TESTS: pytest tests/test_codex_overnight.py -q\n"
            "BLOCKERS: none"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-13T00:00:00Z",
            "started_at": "2026-03-13T00:00:00Z",
            "duration_sec": 12.5,
            "rc": 0,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(_snapshot(dirty=False)),
        }

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
            "--mission-brief",
            "Ship the overnight build packet.",
            "--label",
            "allnight-yolo",
        ]
    )

    assert rc == 0
    run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"] == "allnight-yolo"
    assert manifest["cycles_completed"] == 1
    assert manifest["latest_summary_fields"]["result"] == "shipped bounded slice"
    assert (run_dir / "mission_brief.md").read_text(encoding="utf-8") == "Ship the overnight build packet.\n"

    handoff_text = (run_dir / "morning_handoff.md").read_text(encoding="utf-8")
    assert "shipped bounded slice" in handoff_text
    assert "allnight-yolo" in handoff_text
    shared_handoff = state_dir / "shared" / "codex_overnight_handoff.md"
    assert shared_handoff.exists()
    assert "pytest tests/test_codex_overnight.py -q" in shared_handoff.read_text(encoding="utf-8")


def test_main_repairs_missing_run_manifest_before_update(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=True)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return initial_snapshot

    def fake_run_cycle(**kwargs: object) -> dict[str, object]:
        run_dir = kwargs["run_dir"]
        assert isinstance(run_dir, Path)
        (run_dir / "run_manifest.json").unlink()
        summary_text = (
            "RESULT: repaired missing manifest metadata\n"
            "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
            "TESTS: pytest tests/test_codex_overnight.py -q\n"
            "BLOCKERS: none"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-18T00:00:00Z",
            "started_at": "2026-03-18T00:00:00Z",
            "duration_sec": 1.0,
            "rc": 0,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(initial_snapshot),
        }

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
            "--mission-brief",
            "Repair the run manifest if it disappears.",
            "--label",
            "manifest-heal",
        ]
    )

    assert rc == 0
    run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"] == "manifest-heal"
    assert manifest["mission_excerpt"] == "Repair the run manifest if it disappears."
    assert manifest["settings"]["label"] == "manifest-heal"
    assert manifest["initial_git_snapshot"] == asdict(initial_snapshot)
    assert manifest["cycles_completed"] == 1


def test_main_repairs_malformed_run_manifest_before_update(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=True)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return initial_snapshot

    def fake_run_cycle(**kwargs: object) -> dict[str, object]:
        run_dir = kwargs["run_dir"]
        assert isinstance(run_dir, Path)
        (run_dir / "run_manifest.json").write_text('["junk"]\n', encoding="utf-8")
        summary_text = (
            "RESULT: repaired malformed manifest metadata\n"
            "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
            "TESTS: pytest tests/test_codex_overnight.py -q\n"
            "BLOCKERS: none"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-18T00:00:00Z",
            "started_at": "2026-03-18T00:00:00Z",
            "duration_sec": 1.0,
            "rc": 0,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(initial_snapshot),
        }

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
            "--mission-brief",
            "Repair the run manifest if it becomes malformed.",
            "--label",
            "manifest-heal",
        ]
    )

    assert rc == 0
    run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"] == "manifest-heal"
    assert manifest["mission_excerpt"] == "Repair the run manifest if it becomes malformed."
    assert manifest["settings"]["label"] == "manifest-heal"
    assert manifest["initial_git_snapshot"] == asdict(initial_snapshot)
    assert manifest["cycles_completed"] == 1


def test_main_routes_run_manifest_and_handoff_files_through_atomic_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=True)
    original_atomic_write = overnight._atomic_write_text
    written_paths: list[Path] = []

    def recording_atomic_write(
        path: Path,
        text: str,
        *,
        encoding: str = "utf-8",
        errors: str | None = None,
    ) -> None:
        written_paths.append(path)
        original_atomic_write(path, text, encoding=encoding, errors=errors)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return initial_snapshot

    def fake_run_cycle(**_: object) -> dict[str, object]:
        summary_text = (
            "RESULT: shipped bounded slice\n"
            "FILES: dharma_swarm/codex_overnight.py\n"
            "TESTS: pytest tests/test_codex_overnight.py -q\n"
            "BLOCKERS: none"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-13T00:00:00Z",
            "started_at": "2026-03-13T00:00:00Z",
            "duration_sec": 12.5,
            "rc": 0,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(_snapshot(dirty=False)),
        }

    monkeypatch.setattr(overnight, "_atomic_write_text", recording_atomic_write)
    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
            "--mission-brief",
            "Ship the overnight build packet.",
            "--label",
            "allnight-yolo",
        ]
    )

    assert rc == 0
    run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())
    written = set(written_paths)
    assert state_dir / "codex_overnight_run_dir.txt" in written
    assert run_dir / "mission_brief.md" in written
    assert run_dir / "run_manifest.json" in written
    assert run_dir / "morning_handoff.md" in written
    assert state_dir / "shared" / "codex_overnight_handoff.md" in written


def test_main_returns_cycle_rc_for_failed_once_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=True)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return initial_snapshot

    def fake_run_cycle(**_: object) -> dict[str, object]:
        summary_text = (
            "RESULT: cycle failed before codex could launch\n"
            "FILES: none\n"
            "TESTS: not run\n"
            "BLOCKERS: codex missing\n"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-18T00:00:00Z",
            "started_at": "2026-03-18T00:00:00Z",
            "duration_sec": 1.0,
            "rc": 127,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(initial_snapshot),
        }

    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
        ]
    )

    assert rc == 127
    run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())
    handoff_text = (run_dir / "morning_handoff.md").read_text(encoding="utf-8")
    assert "cycle failed before codex could launch" in handoff_text


def test_main_can_route_cycles_through_isolated_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_repo_root = tmp_path / "source-repo"
    source_repo_root.mkdir()
    worktree_repo_root = tmp_path / "worktree-repo"
    worktree_repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=False)
    run_cycle_calls: list[dict[str, object]] = []

    def fake_prepare_isolated_worktree(
        *,
        source_repo_root: Path,
        state_dir: Path,
        run_dir: Path,
        label: str,
        worktree_root: Path | None = None,
    ) -> tuple[Path, list[str]]:
        assert source_repo_root == tmp_path / "source-repo"
        assert state_dir == tmp_path / ".dharma"
        assert isinstance(run_dir, Path)
        assert label == "isolated-run"
        assert worktree_root == tmp_path / "custom-worktrees"
        return worktree_repo_root, ["dharma_swarm/codex_overnight.py", "evaluate.py"]

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == worktree_repo_root
        return initial_snapshot

    def fake_run_cycle(**kwargs: object) -> dict[str, object]:
        run_cycle_calls.append(kwargs)
        summary_text = (
            "RESULT: isolated worktree cycle completed\n"
            "FILES: dharma_swarm/providers.py\n"
            "TESTS: pytest -q tests/test_providers.py\n"
            "BLOCKERS: none"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-18T00:00:00Z",
            "started_at": "2026-03-18T00:00:00Z",
            "duration_sec": 1.0,
            "rc": 0,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(initial_snapshot),
            "actual_omega": 0.84,
            "actual_psi": 0.74,
            "metrics_source": "locked",
            "regime": "baseline",
            "kept": True,
        }

    monkeypatch.setattr(overnight, "prepare_isolated_worktree", fake_prepare_isolated_worktree)
    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc = overnight.main(
        [
            "--once",
            "--repo-root",
            str(source_repo_root),
            "--state-dir",
            str(state_dir),
            "--label",
            "isolated-run",
            "--isolate-worktree",
            "--worktree-root",
            str(tmp_path / "custom-worktrees"),
        ]
    )

    assert rc == 0
    assert len(run_cycle_calls) == 1
    assert run_cycle_calls[0]["repo_root"] == worktree_repo_root
    assert run_cycle_calls[0]["source_repo_root"] == source_repo_root
    assert run_cycle_calls[0]["isolated_worktree"] is True
    assert run_cycle_calls[0]["preloaded_overlay"] == ["dharma_swarm/codex_overnight.py", "evaluate.py"]

    run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["repo_root"] == str(worktree_repo_root)
    assert manifest["source_repo_root"] == str(source_repo_root)
    assert manifest["isolated_worktree"] is True
    assert manifest["worktree_overlay"] == ["dharma_swarm/codex_overnight.py", "evaluate.py"]

    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert f"- repo_root: {worktree_repo_root}" in report_text
    assert f"- source_repo_root: {source_repo_root}" in report_text
    assert "- isolated_worktree: true" in report_text


def test_main_allocates_distinct_run_dirs_for_same_second_launches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_dir = tmp_path / ".dharma"
    initial_snapshot = _snapshot(dirty=True)

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 3, 18, 0, 0, 0, tzinfo=tz or timezone.utc)

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return initial_snapshot

    def fake_run_cycle(**_: object) -> dict[str, object]:
        summary_text = (
            "RESULT: shipped bounded slice\n"
            "FILES: dharma_swarm/codex_overnight.py\n"
            "TESTS: pytest tests/test_codex_overnight.py -q\n"
            "BLOCKERS: none"
        )
        return {
            "cycle": 1,
            "ts": "2026-03-18T00:00:00Z",
            "started_at": "2026-03-18T00:00:00Z",
            "duration_sec": 1.0,
            "rc": 0,
            "timed_out": False,
            "prompt_file": str(state_dir / "prompt.md"),
            "output_file": str(state_dir / "output.md"),
            "stdout_file": str(state_dir / "stdout.log"),
            "summary_text": summary_text,
            "summary_fields": parse_summary_fields(summary_text),
            "before": asdict(initial_snapshot),
            "after": asdict(initial_snapshot),
        }

    monkeypatch.setattr(overnight, "datetime", FixedDateTime)
    monkeypatch.setattr(overnight, "gather_git_snapshot", fake_gather_git_snapshot)
    monkeypatch.setattr(overnight, "run_cycle", fake_run_cycle)

    rc1 = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
        ]
    )
    first_run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())

    rc2 = overnight.main(
        [
            "--once",
            "--repo-root",
            str(repo_root),
            "--state-dir",
            str(state_dir),
        ]
    )
    second_run_dir = Path((state_dir / "codex_overnight_run_dir.txt").read_text(encoding="utf-8").strip())

    assert rc1 == 0
    assert rc2 == 0
    assert first_run_dir.name == "20260318T000000Z"
    assert second_run_dir.name == "20260318T000000Z-01"
    assert first_run_dir != second_run_dir
    assert (first_run_dir / "run_manifest.json").exists()
    assert (second_run_dir / "run_manifest.json").exists()
