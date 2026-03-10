from __future__ import annotations

import subprocess
from pathlib import Path

from dharma_swarm.codex_overnight import (
    GitSnapshot,
    build_codex_exec_command,
    build_cycle_prompt,
    gather_git_snapshot,
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
