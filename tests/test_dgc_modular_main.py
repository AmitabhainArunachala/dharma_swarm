from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch


WORKTREE_ROOT = Path(__file__).resolve().parents[1]


def _clear_dgc_modules() -> None:
    for name in list(sys.modules):
        if name == "dharma_swarm.dgc" or name.startswith("dharma_swarm.dgc."):
            sys.modules.pop(name, None)


def test_dgc_package_resolves_within_worktree() -> None:
    _clear_dgc_modules()
    package = importlib.import_module("dharma_swarm.dgc")

    package_file = Path(package.__file__).resolve()
    assert package_file.is_relative_to(WORKTREE_ROOT)


def test_dgc_context_uses_runtime_path_overrides(tmp_path, monkeypatch) -> None:
    _clear_dgc_modules()
    repo_root = tmp_path / "custom-repo"
    repo_root.mkdir()
    (repo_root / ".env").write_text("DGC_ALPHA=repo\n", encoding="utf-8")

    state_root = tmp_path / "runtime-state"
    env_dir = state_root / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "nvidia_remote.env").write_text("DGC_BETA=state\n", encoding="utf-8")

    monkeypatch.delenv("DGC_ALPHA", raising=False)
    monkeypatch.delenv("DGC_BETA", raising=False)

    from dharma_swarm.dgc.context import build_context

    ctx = build_context(
        home=tmp_path,
        env={
            "DHARMA_REPO_ROOT": str(repo_root),
            "DHARMA_HOME": str(state_root),
            "DGC_GAMMA": "explicit",
        },
    )

    assert ctx.home == tmp_path
    assert ctx.repo_root == repo_root
    assert ctx.state_root == state_root
    assert ctx.legacy_core_root == tmp_path / "dgc-core"
    assert ctx.env["DGC_ALPHA"] == "repo"
    assert ctx.env["DGC_BETA"] == "state"
    assert ctx.env["DGC_GAMMA"] == "explicit"
    assert "DGC_ALPHA" not in os.environ
    assert "DGC_BETA" not in os.environ


def test_dispatch_known_runtime_ops_commands_route_through_command_packs() -> None:
    _clear_dgc_modules()
    from dharma_swarm.dgc.main import _dispatch_known_command

    with patch("dharma_swarm.dgc.commands.status.cmd_status") as status_mock:
        assert _dispatch_known_command(["status"]) is True
        status_mock.assert_called_once_with()

    with patch("dharma_swarm.dgc.commands.status.cmd_runtime_status") as runtime_status_mock:
        assert _dispatch_known_command(
            ["runtime-status", "--limit", "7", "--db-path", "/tmp/runtime.db"]
        ) is True
        runtime_status_mock.assert_called_once_with(limit=7, db_path="/tmp/runtime.db")

    with patch("dharma_swarm.dgc.commands.ops.cmd_health") as health_mock:
        assert _dispatch_known_command(["health"]) is True
        health_mock.assert_called_once_with()

    with patch("dharma_swarm.dgc.commands.ops.cmd_maintenance") as maintenance_mock:
        assert _dispatch_known_command(["maintenance", "--dry-run", "--max-mb", "12.5"]) is True
        maintenance_mock.assert_called_once_with(dry_run=True, max_mb=12.5)
