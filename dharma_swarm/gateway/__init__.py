"""Messaging Gateway — multi-platform adapter for external communication.

Exposes dharma_swarm to the external world via messaging platforms
(starting with Telegram). Inspired by Hermes Agent's gateway architecture.
"""

from dharma_swarm.gateway.base import MessageEvent, PlatformAdapter, SendResult  # noqa: F401
from dharma_swarm.gateway.runner import GatewayRunner  # noqa: F401
