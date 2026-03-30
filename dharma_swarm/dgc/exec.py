"""Execution adapters for the modular DGC command system."""

from __future__ import annotations

import os
import subprocess
from typing import Mapping, Sequence


def run_capture(cmd: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a command and capture text output.

    This is a transitional helper; policy and richer error handling will be
    added as the legacy CLI is decomposed.
    """

    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def run_checked(cmd: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a command and raise a readable error on non-zero exit."""
    result = run_capture(cmd, check=False, **kwargs)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        suffix = f": {stderr}" if stderr else ""
        raise RuntimeError(f"command {' '.join(cmd)} failed with exit code {result.returncode}{suffix}")
    return result


def launch_background(cmd: Sequence[str], **kwargs: object) -> subprocess.Popen[bytes] | subprocess.Popen[str]:
    """Launch a command in a detached background session."""
    return subprocess.Popen(cmd, start_new_session=True, **kwargs)


def exec_replace(
    file: str,
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    """Replace the current process with a command."""
    if env is None:
        os.execvp(file, list(argv))
    os.execvpe(file, list(argv), dict(env))
