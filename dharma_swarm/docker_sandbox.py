"""Docker-based sandbox for dharma_swarm agents.

Spawns Docker containers on demand. Each container persists for the agent's
task lifetime and is destroyed on cleanup. Uses the Docker CLI directly
(no SDK dependency) via asyncio subprocesses.

Architecture inspired by Alibaba's ROCK sandbox (arXiv:2512.24873) but
governed by thinkodynamic telos gates. Containers are capability amplifiers
with provenance tracking, not prisons.

Three-layer isolation stack (this module = Layer 3):
    Layer 3: DockerSandbox (strongest — this module)
    Layer 2: LocalSandbox with resource limits (sandbox.py)
    Layer 1: LocalSandbox with regex checks (sandbox.py, always available)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from dharma_swarm.models import SandboxResult
from dharma_swarm.sandbox import Sandbox, SandboxError

logger = logging.getLogger(__name__)


class NetworkMode(str, Enum):
    """Container network access levels."""
    NONE = "none"        # No network — pure computation
    BRIDGE = "bridge"    # Default — full outbound access
    HOST = "host"        # Full access — resource acquisition tasks


@dataclass
class ContainerConfig:
    """Configuration for a Docker sandbox container."""
    image: str = "python:3.11-slim"
    memory_limit: str = "2g"
    cpu_limit: float = 2.0
    network_mode: NetworkMode = NetworkMode.BRIDGE
    timeout: float = 60.0
    workdir: str = "/workspace"
    volumes: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    gpu: bool = False  # --gpus all for mining/training containers


@dataclass
class ContainerEvent:
    """Provenance record for container activity. Feeds stigmergy."""
    timestamp: float
    container_id: str
    event_type: str  # "created" | "executed" | "destroyed" | "anomaly"
    command: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    network_mode: str = ""
    resource_usage: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)


class DockerSandbox(Sandbox):
    """Docker container sandbox with on-demand spawning.

    Container lifecycle:
        1. Created lazily on first execute() call
        2. Persists across multiple execute() calls for the task
        3. Destroyed on cleanup() or garbage collection

    Provenance:
        Every execution is logged as a ContainerEvent for stigmergy
        integration. The system TRACKS resource usage, not prevents it.
    """

    def __init__(
        self,
        config: Optional[ContainerConfig] = None,
        event_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._config = config or ContainerConfig()
        self._container_id: Optional[str] = None
        self._container_name: str = f"dharma-sandbox-{uuid.uuid4().hex[:12]}"
        self._events: list[ContainerEvent] = []
        self._event_callback = event_callback
        self._started = False

    @property
    def container_id(self) -> Optional[str]:
        return self._container_id

    @property
    def container_name(self) -> str:
        return self._container_name

    @property
    def events(self) -> list[ContainerEvent]:
        return list(self._events)

    @property
    def is_running(self) -> bool:
        return self._started and self._container_id is not None

    # -- Docker CLI helpers ------------------------------------------------

    @staticmethod
    async def docker_available() -> bool:
        """Check if Docker daemon is reachable."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            return False

    async def _docker_exec(
        self, *args: str, timeout: float = 30.0
    ) -> tuple[int, str, str]:
        """Run a docker CLI command and return (exit_code, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            "docker", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", "Docker command timed out"

        return (
            proc.returncode or 0,
            raw_out.decode(errors="replace").strip(),
            raw_err.decode(errors="replace").strip(),
        )

    # -- Container lifecycle -----------------------------------------------

    async def _ensure_container(self) -> None:
        """Create container if not already running (lazy initialization)."""
        if self._started:
            return

        cmd = [
            "run", "-d",
            "--name", self._container_name,
            "--memory", self._config.memory_limit,
            f"--cpus={self._config.cpu_limit}",
            f"--network={self._config.network_mode.value}",
            "--workdir", self._config.workdir,
            "--rm",  # auto-remove when stopped
        ]

        # GPU access for mining/training containers
        if self._config.gpu:
            cmd.extend(["--gpus", "all"])

        # Volume mounts (read-only by default for safety + provenance)
        for host_path, container_path in self._config.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}:ro"])

        # Environment variables
        for key, value in self._config.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Keep container alive with tail -f /dev/null
        cmd.extend([self._config.image, "tail", "-f", "/dev/null"])

        exit_code, stdout, stderr = await self._docker_exec(*cmd, timeout=30.0)

        if exit_code != 0:
            raise SandboxError(
                f"Failed to create container {self._container_name}: {stderr}"
            )

        self._container_id = stdout[:12]  # Short container ID
        self._started = True

        event = ContainerEvent(
            timestamp=time.time(),
            container_id=self._container_id,
            event_type="created",
            network_mode=self._config.network_mode.value,
            metadata={
                "image": self._config.image,
                "memory_limit": self._config.memory_limit,
                "cpu_limit": str(self._config.cpu_limit),
                "gpu": str(self._config.gpu),
            },
        )
        self._record_event(event)
        logger.info(
            "Container %s created (image=%s, net=%s, gpu=%s)",
            self._container_id,
            self._config.image,
            self._config.network_mode.value,
            self._config.gpu,
        )

    # -- Sandbox interface -------------------------------------------------

    async def execute(
        self, command: str, timeout: float = 30.0
    ) -> SandboxResult:
        """Execute a command inside the container."""
        await self._ensure_container()

        start = time.monotonic()
        exit_code, stdout, stderr = await self._docker_exec(
            "exec", self._container_name,
            "bash", "-c", command,
            timeout=timeout,
        )
        duration = time.monotonic() - start
        timed_out = exit_code == -1 and "timed out" in stderr

        event = ContainerEvent(
            timestamp=time.time(),
            container_id=self._container_id or "",
            event_type="executed",
            command=command[:500],  # Truncate for logging
            exit_code=exit_code,
            duration_seconds=round(duration, 4),
        )
        self._record_event(event)

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=round(duration, 4),
            timed_out=timed_out,
        )

    async def execute_python(
        self, code: str, timeout: float = 30.0
    ) -> SandboxResult:
        """Execute Python code inside the container."""
        # Write code to a temp file inside container, then run it
        escaped = code.replace("'", "'\\''")
        write_cmd = f"echo '{escaped}' > /tmp/_dharma_run.py"
        await self.execute(write_cmd, timeout=5.0)
        return await self.execute("python3 /tmp/_dharma_run.py", timeout=timeout)

    async def cleanup(self) -> None:
        """Stop and remove the container."""
        if not self._started:
            return

        if self._container_id:
            # Collect resource usage stats before destruction
            stats = await self._get_container_stats()

            exit_code, _, stderr = await self._docker_exec(
                "stop", self._container_name, timeout=10.0
            )
            # --rm flag handles removal, but force-remove if stuck
            if exit_code != 0:
                await self._docker_exec(
                    "rm", "-f", self._container_name, timeout=5.0
                )

            event = ContainerEvent(
                timestamp=time.time(),
                container_id=self._container_id,
                event_type="destroyed",
                resource_usage=stats,
            )
            self._record_event(event)
            logger.info(
                "Container %s destroyed (stats: %s)",
                self._container_id,
                json.dumps(stats),
            )

        self._container_id = None
        self._started = False

    # -- Resource tracking -------------------------------------------------

    async def _get_container_stats(self) -> dict[str, float]:
        """Get container resource usage stats for provenance."""
        if not self._container_id:
            return {}
        try:
            exit_code, stdout, _ = await self._docker_exec(
                "stats", "--no-stream", "--format",
                '{"cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","net":"{{.NetIO}}","block":"{{.BlockIO}}"}',
                self._container_name,
                timeout=5.0,
            )
            if exit_code == 0 and stdout:
                return json.loads(stdout)
        except (json.JSONDecodeError, Exception):
            pass
        return {}

    async def get_network_connections(self) -> list[dict[str, str]]:
        """List active network connections inside the container.

        This is TRACKING, not blocking. Every connection is recorded
        for stigmergy integration and telos gate evaluation.
        """
        if not self.is_running:
            return []
        result = await self.execute(
            "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null || true",
            timeout=5.0,
        )
        # Parse /proc/net/tcp format — just return raw for now
        connections = []
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 4:
                connections.append({
                    "local": parts[1],
                    "remote": parts[2],
                    "state": parts[3],
                })
        return connections

    # -- Event system ------------------------------------------------------

    def _record_event(self, event: ContainerEvent) -> None:
        """Record event for provenance. Optionally notify callback."""
        self._events.append(event)
        if self._event_callback:
            try:
                self._event_callback(event)
            except Exception:
                logger.warning("Event callback failed", exc_info=True)

    def __del__(self) -> None:
        """Warn if container wasn't cleaned up properly."""
        if self._started:
            logger.warning(
                "DockerSandbox %s was garbage collected without cleanup(). "
                "Container may still be running.",
                self._container_name,
            )


def create_monitored_sandbox(
    config: Optional[ContainerConfig] = None,
) -> DockerSandbox:
    """Create a DockerSandbox with SandboxMonitor attached.

    The monitor records all container events (network, compute, filesystem)
    and routes high-severity events through telos gate evaluation.
    """
    from dharma_swarm.sandbox_monitor import SandboxMonitor

    sandbox_config = config or ContainerConfig()
    container_name = f"dharma-sandbox-{uuid.uuid4().hex[:12]}"

    monitor = SandboxMonitor(container_id=container_name)

    def _bridge_event(event: ContainerEvent) -> None:
        """Route DockerSandbox events to SandboxMonitor."""
        if event.event_type == "executed":
            monitor.record_process_creation(
                process_name="bash",
                command_line=event.command,
                pid=0,
            )
        elif event.event_type == "created":
            net_mode = event.network_mode or "bridge"
            if net_mode == "host":
                monitor.record_network_connection("0.0.0.0", 0)
        elif event.event_type == "destroyed":
            cpu = event.resource_usage.get("cpu", 0.0)
            if isinstance(cpu, (int, float)):
                monitor.record_compute_usage(cpu_percent=float(cpu))

    sandbox = DockerSandbox(config=sandbox_config, event_callback=_bridge_event)
    # Attach monitor for external access
    sandbox._monitor = monitor  # type: ignore[attr-defined]
    return sandbox
