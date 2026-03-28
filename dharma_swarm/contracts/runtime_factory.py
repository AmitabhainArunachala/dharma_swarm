"""Factory helpers for sovereign runtime layer adoption."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dharma_swarm.checkpoint import CheckpointStore as LoopCheckpointStore
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.runtime_state import RuntimeStateStore
from dharma_swarm.session_ledger import SessionLedger

from .runtime import (
    AgentRuntime,
    CheckpointStore as RuntimeCheckpointStore,
    GatewayAdapter,
    InteropAdapter,
    SandboxProvider,
)
from .runtime_adapters import (
    A2A_TASK_PACKET_FORMAT,
    FilesystemCheckpointStoreAdapter,
    LocalSandboxProviderAdapter,
    MessageBusGatewayAdapter,
    OPERATOR_BRIDGE_QUEUE_FORMAT,
    RUNTIME_SNAPSHOT_FORMAT,
    RuntimeStateAgentRuntimeAdapter,
    SovereignRuntimeInteropAdapter,
)

SUPPORTED_RUNTIME_SNAPSHOT_FORMATS = (
    RUNTIME_SNAPSHOT_FORMAT,
    OPERATOR_BRIDGE_QUEUE_FORMAT,
    A2A_TASK_PACKET_FORMAT,
)


def validate_runtime_snapshot_format(format_name: str) -> str:
    """Reject unsupported snapshot formats at the sovereign layer boundary."""
    if format_name not in SUPPORTED_RUNTIME_SNAPSHOT_FORMATS:
        supported = ", ".join(SUPPORTED_RUNTIME_SNAPSHOT_FORMATS)
        raise ValueError(
            f"Unsupported runtime snapshot format {format_name!r}; "
            f"supported formats: {supported}"
        )
    return format_name


@dataclass(frozen=True, slots=True)
class SovereignRuntimeLayer:
    """Single construction surface for runtime-side sovereign contracts."""

    state_dir: Path
    message_bus: MessageBus
    runtime_state: RuntimeStateStore
    checkpoint_backend: LoopCheckpointStore
    ledger: SessionLedger
    operator_bridge: OperatorBridge
    agent_runtime: AgentRuntime
    gateway: GatewayAdapter
    checkpoints: RuntimeCheckpointStore
    sandbox: SandboxProvider
    interop: InteropAdapter
    snapshot_formats: tuple[str, ...] = SUPPORTED_RUNTIME_SNAPSHOT_FORMATS

    async def export_snapshot(
        self,
        *,
        format_name: str = RUNTIME_SNAPSHOT_FORMAT,
    ) -> dict[str, object]:
        validated = validate_runtime_snapshot_format(format_name)
        return await self.interop.export_snapshot(format_name=validated)

    async def import_snapshot(
        self,
        payload: dict[str, object],
        *,
        source: str,
    ) -> dict[str, object]:
        validate_runtime_snapshot_format(str(payload.get("format") or source))
        return await self.interop.import_snapshot(payload, source=source)


async def build_sovereign_runtime_layer(
    *,
    state_dir: Path,
    session_id: str | None = None,
    bridge_agent_id: str = "operator_bridge",
    default_workdir: Path | None = None,
) -> SovereignRuntimeLayer:
    """Construct the concrete sovereign runtime layer for a state directory."""
    resolved_state_dir = Path(state_dir)
    resolved_state_dir.mkdir(parents=True, exist_ok=True)

    db_dir = resolved_state_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    message_bus_path = db_dir / "messages.db"
    runtime_db_path = resolved_state_dir / "state" / "runtime.db"
    checkpoint_dir = resolved_state_dir / "state" / "checkpoints"
    ledger_dir = resolved_state_dir / "ledgers"

    message_bus = MessageBus(message_bus_path)
    runtime_state = RuntimeStateStore(runtime_db_path)
    checkpoint_backend = LoopCheckpointStore(base_dir=checkpoint_dir)
    ledger = SessionLedger(
        base_dir=ledger_dir,
        session_id=session_id,
        runtime_db_path=runtime_db_path,
    )

    await message_bus.init_db()
    await runtime_state.init_db()

    operator_bridge = OperatorBridge(
        message_bus=message_bus,
        ledger=ledger,
        runtime_state=runtime_state,
        bridge_agent_id=bridge_agent_id,
    )
    await operator_bridge.init_db()

    agent_runtime = RuntimeStateAgentRuntimeAdapter(runtime_state)
    gateway = MessageBusGatewayAdapter(message_bus)
    checkpoints = FilesystemCheckpointStoreAdapter(checkpoint_backend)
    sandbox = LocalSandboxProviderAdapter(
        default_workdir=default_workdir or resolved_state_dir,
    )
    interop = SovereignRuntimeInteropAdapter(
        runtime_state=runtime_state,
        message_bus=message_bus,
        checkpoint_store=checkpoint_backend,
        operator_bridge=operator_bridge,
    )

    return SovereignRuntimeLayer(
        state_dir=resolved_state_dir,
        message_bus=message_bus,
        runtime_state=runtime_state,
        checkpoint_backend=checkpoint_backend,
        ledger=ledger,
        operator_bridge=operator_bridge,
        agent_runtime=agent_runtime,
        gateway=gateway,
        checkpoints=checkpoints,
        sandbox=sandbox,
        interop=interop,
    )


__all__ = [
    "SUPPORTED_RUNTIME_SNAPSHOT_FORMATS",
    "SovereignRuntimeLayer",
    "build_sovereign_runtime_layer",
    "validate_runtime_snapshot_format",
]
