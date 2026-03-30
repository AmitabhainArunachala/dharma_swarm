from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    home: Path
    repo_root: Path
    state_root: Path
    repo_env_file: Path
    state_env_file: Path
    daemon_env_file: Path
    nvidia_remote_env_file: Path
    runtime_env_helper: Path

    @property
    def bootstrap_env_files(self) -> tuple[Path, Path]:
        return (self.repo_env_file, self.nvidia_remote_env_file)

    @property
    def runtime_env_files(self) -> tuple[Path, Path, Path]:
        return (self.home / ".env", self.state_env_file, self.daemon_env_file)


def _resolve_home(*, home: str | Path | None, env: Mapping[str, str]) -> Path:
    if home is not None:
        return Path(home).expanduser()

    raw_home = str(env.get("HOME", "")).strip()
    if raw_home:
        return Path(raw_home).expanduser()
    return Path.home()


def _resolve_root(
    *,
    env: Mapping[str, str],
    env_var: str,
    default: Path,
) -> Path:
    raw_value = str(env.get(env_var, "")).strip()
    if raw_value:
        return Path(raw_value).expanduser()
    return default


def resolve_runtime_paths(
    *,
    home: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> RuntimePaths:
    env_map = os.environ if env is None else env
    resolved_home = _resolve_home(home=home, env=env_map)
    repo_root = _resolve_root(
        env=env_map,
        env_var="DHARMA_REPO_ROOT",
        default=resolved_home / "dharma_swarm",
    )
    state_root = _resolve_root(
        env=env_map,
        env_var="DHARMA_HOME",
        default=resolved_home / ".dharma",
    )

    return RuntimePaths(
        home=resolved_home,
        repo_root=repo_root,
        state_root=state_root,
        repo_env_file=repo_root / ".env",
        state_env_file=state_root / ".env",
        daemon_env_file=state_root / "daemon.env",
        nvidia_remote_env_file=state_root / "env" / "nvidia_remote.env",
        runtime_env_helper=repo_root / "scripts" / "load_runtime_env.sh",
    )
