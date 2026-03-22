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
    """Creates, tracks, and tears down sandboxes.

    Three-layer isolation stack (auto-selects strongest available):
        Layer 3: DockerSandbox (container isolation, network policies)
        Layer 2: LocalSandbox (subprocess with regex safety checks)
        Layer 1: LocalSandbox (same — always available as fallback)

    Set ``prefer_docker=True`` (default) to auto-select Docker when
    the daemon is reachable. Falls back to LocalSandbox transparently.
    """

    def __init__(self, prefer_docker: bool = True) -> None:
        self._active: dict[int, Sandbox] = {}
        self._prefer_docker = prefer_docker
        self._docker_available: Optional[bool] = None  # Cached after first check

    async def _check_docker(self) -> bool:
        """Check Docker availability (cached)."""
        if self._docker_available is None:
            try:
                from dharma_swarm.docker_sandbox import DockerSandbox
                self._docker_available = await DockerSandbox.docker_available()
            except ImportError:
                self._docker_available = False
        return self._docker_available

    def create(
        self,
        sandbox_type: str = "local",
        workdir: Optional[Path] = None,
    ) -> Sandbox:
        """Create a sandbox (synchronous — always returns LocalSandbox).

        For Docker sandboxes, use :meth:`create_async` instead.

        Args:
            sandbox_type: ``"local"`` or ``"docker"`` (docker raises if unavailable).
            workdir: Optional working directory override.

        Returns:
            A ready-to-use :class:`Sandbox` instance.
        """
        if sandbox_type == "docker":
            raise SandboxError(
                "Docker sandbox requires async creation. Use create_async()."
            )
        if sandbox_type != "local":
            raise SandboxError(f"Unknown sandbox type: {sandbox_type!r}")
        sb = LocalSandbox(workdir=workdir)
        self._active[id(sb)] = sb
        return sb

    async def create_async(
        self,
        sandbox_type: str = "auto",
        workdir: Optional[Path] = None,
        docker_config: Optional[object] = None,
    ) -> Sandbox:
        """Create a sandbox, auto-selecting Docker when available.

        Args:
            sandbox_type: ``"auto"`` (default), ``"docker"``, or ``"local"``.
            workdir: Working directory for local sandboxes.
            docker_config: Optional :class:`ContainerConfig` for Docker sandboxes.

        Returns:
            A :class:`DockerSandbox` if Docker is available and preferred,
            otherwise a :class:`LocalSandbox`.
        """
        use_docker = False

        if sandbox_type == "docker":
            use_docker = True
        elif sandbox_type == "auto" and self._prefer_docker:
            use_docker = await self._check_docker()

        if use_docker:
            try:
                from dharma_swarm.docker_sandbox import DockerSandbox, ContainerConfig
                config = docker_config if isinstance(docker_config, ContainerConfig) else ContainerConfig()
                sb: Sandbox = DockerSandbox(config=config)
                self._active[id(sb)] = sb
                return sb
            except ImportError:
                pass  # Fall through to local
            except SandboxError:
                pass  # Docker unavailable, fall through

        sb = LocalSandbox(workdir=workdir)
        self._active[id(sb)] = sb
        return sb

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def docker_preferred(self) -> bool:
        return self._prefer_docker

    async def shutdown_all(self) -> None:
        """Cleanup every tracked sandbox."""
        for sb in list(self._active.values()):
            await sb.cleanup()
        self._active.clear()
