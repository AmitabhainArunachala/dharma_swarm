from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _clear_modules(*module_names: str) -> None:
    for module_name in module_names:
        sys.modules.pop(module_name, None)


def test_resolve_runtime_paths_defaults(tmp_path) -> None:
    module = importlib.import_module("dharma_swarm.runtime_paths")

    home = tmp_path / "home"
    paths = module.resolve_runtime_paths(home=home, env={})

    assert paths.home == home
    assert paths.repo_root == home / "dharma_swarm"
    assert paths.state_root == home / ".dharma"
    assert paths.repo_env_file == home / "dharma_swarm" / ".env"
    assert paths.state_env_file == home / ".dharma" / ".env"
    assert paths.daemon_env_file == home / ".dharma" / "daemon.env"
    assert paths.nvidia_remote_env_file == home / ".dharma" / "env" / "nvidia_remote.env"
    assert paths.runtime_env_helper == home / "dharma_swarm" / "scripts" / "load_runtime_env.sh"


def test_resolve_runtime_paths_honors_env_overrides(tmp_path) -> None:
    module = importlib.import_module("dharma_swarm.runtime_paths")

    home = tmp_path / "home"
    repo_root = tmp_path / "runtime-convergence-hardening"
    state_root = tmp_path / "runtime-state"
    paths = module.resolve_runtime_paths(
        home=home,
        env={
            "DHARMA_REPO_ROOT": str(repo_root),
            "DHARMA_HOME": str(state_root),
        },
    )

    assert paths.home == home
    assert paths.repo_root == repo_root
    assert paths.state_root == state_root
    assert paths.repo_env_file == repo_root / ".env"
    assert paths.state_env_file == state_root / ".env"
    assert paths.daemon_env_file == state_root / "daemon.env"
    assert paths.nvidia_remote_env_file == state_root / "env" / "nvidia_remote.env"
    assert paths.runtime_env_helper == repo_root / "scripts" / "load_runtime_env.sh"


def test_dgc_cli_bootstrap_env_uses_canonical_runtime_paths(
    monkeypatch,
    tmp_path,
) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "custom-repo"
    state_root = tmp_path / "runtime-state"

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DHARMA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DHARMA_HOME", str(state_root))

    _clear_modules("dharma_swarm.runtime_paths", "dharma_swarm.dgc_cli")
    module = importlib.import_module("dharma_swarm.dgc_cli")

    seen: list[Path] = []
    monkeypatch.setattr(module, "_load_env_file", lambda path: seen.append(path))

    module._bootstrap_env()

    assert module.HOME == home
    assert module.DHARMA_SWARM == repo_root
    assert module.DHARMA_STATE == state_root
    assert seen == [
        repo_root / ".env",
        state_root / "env" / "nvidia_remote.env",
    ]


def test_chat_tools_use_canonical_runtime_paths(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "custom-repo"
    state_root = tmp_path / "runtime-state"

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DHARMA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DHARMA_HOME", str(state_root))

    _clear_modules("dharma_swarm.runtime_paths", "api.chat_tools")
    module = importlib.import_module("api.chat_tools")

    assert module.PROJECT_ROOT == repo_root
    assert module.ALLOWED_ROOTS == [repo_root, state_root]
    assert module._resolve_path("notes/todo.md") == repo_root / "notes" / "todo.md"
