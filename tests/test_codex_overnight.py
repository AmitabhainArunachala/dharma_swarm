from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import dharma_swarm.codex_overnight as overnight
from dharma_swarm.codex_overnight import (
    GitSnapshot,
    build_codex_exec_command,
    build_cycle_prompt,
    gather_git_snapshot,
    parse_summary_fields,
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

    assert cmd[:4] == ["codex", "exec", "-m", "gpt-5.4"]
    assert "--add-dir" in cmd
    assert str(state_dir) in cmd
    assert "-o" in cmd
    assert str(output_file) in cmd
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
        "RESULT: shipped bounded slice\n"
        "FILES: dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py\n"
        "TESTS: pytest tests/test_codex_overnight.py -q\n"
        "BLOCKERS: none\n"
    )

    assert fields["result"] == "shipped bounded slice"
    assert fields["files"] == "dharma_swarm/codex_overnight.py, tests/test_codex_overnight.py"
    assert fields["tests"] == "pytest tests/test_codex_overnight.py -q"
    assert fields["blockers"] == "none"


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
    stdout_summary = "RESULT: fallback from stdout\nFILES: none\nTESTS: not run\nBLOCKERS: none\n"

    def fake_gather_git_snapshot(path: Path) -> GitSnapshot:
        assert path == repo_root
        return snapshots.pop(0)

    def fake_run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        timeout: int = 30,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        assert cwd == repo_root
        assert input_text is not None and "Cycle: 1" in input_text
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout_summary, stderr="")

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
    assert result["summary_text"] == stdout_summary.strip()
    assert (run_dir / "latest_last_message.txt").read_text(encoding="utf-8") == stdout_summary
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "RESULT: fallback from stdout FILES: none TESTS: not run BLOCKERS: none" in report_text


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
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout, input_text
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=30,
            output=b"RESULT: partial cycle output\nFILES: none\n",
            stderr=b"BLOCKERS: timed out\n",
        )

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

    latest_message = (run_dir / "latest_last_message.txt").read_text(encoding="utf-8")
    assert result["rc"] == 124
    assert result["timed_out"] is True
    assert "RESULT: partial cycle output" in result["summary_text"]
    assert "BLOCKERS: timed out" in result["summary_text"]
    assert latest_message == result["summary_text"] + "\n"


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
