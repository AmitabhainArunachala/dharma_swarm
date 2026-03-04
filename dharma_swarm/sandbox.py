"""Async execution sandbox for running code and shell commands safely.

Provides a lightweight isolation layer using asyncio subprocesses with
timeout enforcement and basic destructive-command rejection. Real
production usage should delegate safety checks to telos gates.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from dharma_swarm.models import SandboxResult

# Patterns that are always rejected before execution.
# Intentionally conservative -- telos gates handle nuanced policy.
_FORBIDDEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=/dev/zero\b"),
    re.compile(r"\bdd\s+of=/dev/[a-z]"),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;"),  # fork bomb
    re.compile(r"\b>\s*/dev/sd[a-z]"),
    re.compile(r"\bchmod\s+-R\s+777\s+/\s*$"),
]


class SandboxError(Exception):
    """Raised when a sandbox operation is rejected or fails fatally."""


class Sandbox(ABC):
    """Abstract base for execution sandboxes."""

    @abstractmethod
    async def execute(
        self, command: str, timeout: float = 30.0
    ) -> SandboxResult:
        """Run a shell command and return captured output."""

    @abstractmethod
    async def execute_python(
        self, code: str, timeout: float = 30.0
    ) -> SandboxResult:
        """Run a Python code snippet and return captured output."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources held by this sandbox."""


class LocalSandbox(Sandbox):
    """Sandbox backed by local asyncio subprocesses.

    Args:
        workdir: Working directory for commands. A temporary directory
            is created when *None*.
    """

    def __init__(self, workdir: Optional[Path] = None) -> None:
        if workdir is not None:
            self._workdir = workdir
            self._owns_workdir = False
        else:
            self._tmpdir = tempfile.TemporaryDirectory(prefix="dharma_sandbox_")
            self._workdir = Path(self._tmpdir.name)
            self._owns_workdir = True

    @property
    def workdir(self) -> Path:
        return self._workdir

    # -- safety ---------------------------------------------------------

    @staticmethod
    def _check_safety(command: str) -> None:
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(command):
                raise SandboxError(
                    f"Command rejected by safety filter: {pattern.pattern}"
                )

    # -- execution ------------------------------------------------------

    async def execute(
        self, command: str, timeout: float = 30.0
    ) -> SandboxResult:
        self._check_safety(command)
        start = time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._workdir,
        )
        timed_out = False
        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raw_out = b""
            raw_err = b"Execution timed out"
            timed_out = True

        duration = time.monotonic() - start
        return SandboxResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=raw_out.decode(errors="replace"),
            stderr=raw_err.decode(errors="replace"),
            duration_seconds=round(duration, 4),
            timed_out=timed_out,
        )

    async def execute_python(
        self, code: str, timeout: float = 30.0
    ) -> SandboxResult:
        script = self._workdir / "_dharma_run.py"
        script.write_text(code, encoding="utf-8")
        try:
            return await self.execute(f"python3 {script}", timeout=timeout)
        finally:
            script.unlink(missing_ok=True)

    async def cleanup(self) -> None:
        if self._owns_workdir and hasattr(self, "_tmpdir"):
            self._tmpdir.cleanup()


class SandboxManager:
    """Creates, tracks, and tears down sandboxes."""

    def __init__(self) -> None:
        self._active: dict[int, Sandbox] = {}

    def create(
        self,
        sandbox_type: str = "local",
        workdir: Optional[Path] = None,
    ) -> Sandbox:
        """Create a new sandbox and register it.

        Args:
            sandbox_type: Only ``"local"`` is supported today.
            workdir: Optional working directory override.

        Returns:
            A ready-to-use :class:`Sandbox` instance.
        """
        if sandbox_type != "local":
            raise SandboxError(f"Unknown sandbox type: {sandbox_type!r}")
        sb = LocalSandbox(workdir=workdir)
        self._active[id(sb)] = sb
        return sb

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def shutdown_all(self) -> None:
        """Cleanup every tracked sandbox."""
        for sb in list(self._active.values()):
            await sb.cleanup()
        self._active.clear()
