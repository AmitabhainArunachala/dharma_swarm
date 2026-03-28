"""A2A (Agent-to-Agent) protocol implementation for dharma_swarm.

Implements a subset of Google's Agent-to-Agent protocol for standardized
agent discovery and task delegation. Replaces file-based TRISHULA messaging
with structured agent cards, capability discovery, and task lifecycle.

Core components:
    - AgentCard / CardRegistry: capability advertisement and discovery
    - A2AServer: receives task delegations, dispatches to orchestrator
    - A2AClient: discovers agents, delegates tasks, monitors completion
    - A2ABridge: backward-compatible bridge to TRISHULA and signal_bus

Current scope: local-only (in-process function calls between agents).
HTTP transport for inter-VPS communication is a future milestone.
"""

from dharma_swarm.a2a.agent_card import (
    AgentCard,
    AgentCapability,
    CardRegistry,
)
from dharma_swarm.a2a.a2a_server import A2AServer
from dharma_swarm.a2a.a2a_client import A2AClient
from dharma_swarm.a2a.a2a_bridge import A2ABridge

__all__ = [
    "AgentCard",
    "AgentCapability",
    "CardRegistry",
    "A2AServer",
    "A2AClient",
    "A2ABridge",
]
