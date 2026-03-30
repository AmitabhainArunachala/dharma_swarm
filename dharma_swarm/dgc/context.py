"""Runtime context types for the modular DGC command system."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dharma_swarm.runtime_paths import resolve_runtime_paths


@dataclass(frozen=True)
class DgcContext:
    """Explicit runtime context for modular DGC command execution."""

    home: Path
    repo_root: Path
    state_root: Path
    legacy_core_root: Path
    env: dict[str, str]


def _load_env_file(path: Path) -> dict[str, str]:
    """Load KEY=VALUE pairs from an env file without mutating process state."""
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return loaded

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        loaded.setdefault(key, value)
    return loaded


def build_context(
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> DgcContext:
    """Build explicit DGC runtime context without mutating process globals."""
    explicit_env = dict(env or {})
    runtime_paths = resolve_runtime_paths(
        home=home,
        env=explicit_env,
    )

    resolved_env: dict[str, str] = {}
    resolved_env.update(_load_env_file(runtime_paths.repo_env_file))
    resolved_env.update(_load_env_file(runtime_paths.nvidia_remote_env_file))
    resolved_env.update(explicit_env)

    return DgcContext(
        home=runtime_paths.home.resolve(),
        repo_root=runtime_paths.repo_root.resolve(),
        state_root=runtime_paths.state_root.resolve(),
        legacy_core_root=(runtime_paths.home / "dgc-core").resolve(),
        env=resolved_env,
    )
