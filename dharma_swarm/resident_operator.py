"""Thin ResidentOperator compatibility layer over sovereign runtime contracts."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.conversation_store import ConversationStore
from dharma_swarm.contracts import SovereignRuntimeLayer, build_sovereign_runtime_layer
from dharma_swarm.graduation_engine import GraduationEngine

OPERATOR_PORT = 8420


class ResidentOperator:
    """Bootstrap the canonical runtime contracts for resident-operator callers.

    The historical ResidentOperator owned many more behaviors. The current
    overnight adoption path only needs a stable lifecycle surface that
    initializes the sovereign runtime layer plus the lightweight persistence
    stores that existing callers expect to inject or close.
    """

    def __init__(
        self,
        *,
        state_dir: Path | str | None = None,
        session_id: str = "resident_operator",
        bridge_agent_id: str = "operator_bridge",
    ) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else Path.home() / ".dharma"
        self.session_id = session_id
        self.bridge_agent_id = bridge_agent_id
        self._conversations = ConversationStore(
            db_path=self.state_dir / "state" / "resident_operator_conversations.db"
        )
        self._graduation = GraduationEngine(
            db_path=self.state_dir / "state" / "resident_operator_graduation.db"
        )
        self._runtime_layer: SovereignRuntimeLayer | None = None
        self._running = False

    async def start(self) -> None:
        """Initialize persistence shims and the sovereign runtime layer."""
        if self._running:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        await self._conversations.init_db()
        await self._graduation.init_db()
        self._runtime_layer = await build_sovereign_runtime_layer(
            state_dir=self.state_dir,
            session_id=self.session_id,
            bridge_agent_id=self.bridge_agent_id,
        )
        self._running = True

    async def stop(self) -> None:
        """Close lightweight stores and mark the resident operator stopped."""
        if not self._running:
            return
        await self._conversations.close()
        await self._graduation.close()
        self._running = False

    def runtime_contracts(self) -> SovereignRuntimeLayer:
        """Expose the adopted sovereign runtime layer."""
        if self._runtime_layer is None:
            raise RuntimeError("ResidentOperator has not been started")
        return self._runtime_layer


__all__ = ["OPERATOR_PORT", "ResidentOperator"]
