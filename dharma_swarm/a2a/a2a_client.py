"""A2A Client -- delegates tasks to other agents.

Discovers agent capabilities via cards, selects the best agent,
sends tasks, and monitors completion. This is the outbound half
of the A2A protocol.

For local agents: direct dispatch via A2AServer.
For remote agents (AGNI/RUSHABDEV): HTTP (future milestone).

Usage::

    client = A2AClient(registry=card_registry, server=a2a_server)

    # Find who can do code review
    agents = client.discover("code_review")

    # Delegate to best match
    result = client.delegate("code_review", "Please review auth module")

    # Or delegate to a specific agent
    result = client.delegate_to("reviewer-1", "Review this PR")
"""

from __future__ import annotations

import logging
from typing import Any

from dharma_swarm.a2a.agent_card import AgentCard, CardRegistry
from dharma_swarm.a2a.a2a_server import (
    A2AMessage,
    A2AServer,
    A2ATask,
    A2ATaskStatus,
)

logger = logging.getLogger(__name__)


class DelegationResult:
    """Result of a task delegation attempt.

    Attributes:
        success: Whether the task completed successfully.
        task: The A2ATask (with full lifecycle data).
        agent_name: Name of the agent that handled the task.
        result_text: The text result (convenience accessor).
        error: Error message if failed.
    """

    __slots__ = ("success", "task", "agent_name", "result_text", "error")

    def __init__(
        self,
        success: bool,
        task: A2ATask | None = None,
        agent_name: str = "",
        result_text: str = "",
        error: str = "",
    ) -> None:
        self.success = success
        self.task = task
        self.agent_name = agent_name
        self.result_text = result_text
        self.error = error

    def __repr__(self) -> str:
        status = "ok" if self.success else "FAILED"
        return f"DelegationResult({status}, agent={self.agent_name!r})"


class A2AClient:
    """Client for discovering agents and delegating tasks via A2A.

    Requires a CardRegistry for discovery and an A2AServer for dispatch.
    Both are injected -- the client does not own their lifecycle.

    Args:
        registry: Card registry for agent discovery.
        server: A2A server for task dispatch.
        default_from: Default requester agent name.
    """

    def __init__(
        self,
        registry: CardRegistry,
        server: A2AServer,
        default_from: str = "client",
    ) -> None:
        self._registry = registry
        self._server = server
        self._default_from = default_from

    # -- discovery -----------------------------------------------------------

    def discover(self, capability: str) -> list[AgentCard]:
        """Find agents with a matching capability.

        Args:
            capability: Search string matched against capability names/descriptions.

        Returns:
            List of AgentCards that match, sorted by name.
        """
        return self._registry.discover(capability)

    def discover_available(self, capability: str) -> list[AgentCard]:
        """Find available agents (not busy/dead) with a matching capability.

        Args:
            capability: Search string.

        Returns:
            List of available matching AgentCards.
        """
        matches = self._registry.discover(capability)
        return [c for c in matches if c.status in ("idle", "starting")]

    # -- delegation ----------------------------------------------------------

    def delegate(
        self,
        capability: str,
        message: str,
        from_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationResult:
        """Discover the best agent for a capability and delegate a task.

        Agent selection: picks the first available agent with the capability.
        Future: score by fitness, latency, cost, etc.

        Args:
            capability: The capability needed.
            message: Task description / instruction text.
            from_agent: Requester name (defaults to self._default_from).
            metadata: Optional metadata to attach to the task.

        Returns:
            DelegationResult with the outcome.
        """
        agents = self.discover_available(capability)
        if not agents:
            # Fall back to all agents with capability (even busy ones)
            agents = self.discover(capability)

        if not agents:
            logger.warning("No agent found for capability: %s", capability)
            return DelegationResult(
                success=False,
                error=f"No agent found with capability: {capability!r}",
            )

        # Select best candidate (first match for now)
        card = agents[0]
        return self.delegate_to(
            card.name,
            message,
            capability=capability,
            from_agent=from_agent,
            metadata=metadata,
        )

    def delegate_to(
        self,
        agent_name: str,
        message: str,
        capability: str = "",
        from_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationResult:
        """Delegate a task to a specific named agent.

        Args:
            agent_name: Target agent name.
            message: Task description / instruction text.
            capability: Capability being requested (optional).
            from_agent: Requester name.
            metadata: Optional metadata.

        Returns:
            DelegationResult with the outcome.
        """
        card = self._registry.get(agent_name)
        if card is None:
            return DelegationResult(
                success=False,
                error=f"Agent not found in registry: {agent_name!r}",
            )

        task = A2ATask(
            from_agent=from_agent or self._default_from,
            to_agent=agent_name,
            capability=capability,
            messages=[A2AMessage.text(message)],
            metadata=metadata or {},
        )

        logger.info(
            "Delegating to %s: capability=%s, message=%s...",
            agent_name, capability, message[:80],
        )

        # Submit to server (synchronous local dispatch)
        result_task = self._server.submit(task)

        success = result_task.status == A2ATaskStatus.COMPLETED
        return DelegationResult(
            success=success,
            task=result_task,
            agent_name=agent_name,
            result_text=result_task.result,
            error=result_task.error,
        )

    def get_task_status(self, task_id: str) -> A2ATaskStatus | None:
        """Check the status of a previously delegated task.

        Args:
            task_id: The task ID returned from delegation.

        Returns:
            Current task status, or None if not found.
        """
        return self._server.get_status(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a previously delegated task.

        Returns True if cancellation was successful.
        """
        return self._server.cancel(task_id)
