"""Multi-agent group chat for collaborative reasoning.

N agents discuss a topic in structured rounds. Each agent sees the full
conversation history and contributes from its specialized perspective.
Optionally, a moderator agent summarizes and directs the conversation.

Inspired by:
  - AutoGen: multi-agent group chat with role-based turns
  - dharma_swarm consolidation.py: Alpha/Beta debate (extended to N agents)

Grounded in:
  - Anekanta (many-sidedness): multiple perspectives yield fuller truth
  - Beer VSM: S4 environmental scanning from multiple viewpoints
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single message in the group chat transcript."""

    speaker: str
    content: str
    round_num: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class GroupChatConfig:
    """Tunable knobs for a group chat session."""

    max_rounds: int = 5
    max_tokens_per_turn: int = 2000
    moderator_name: str | None = None


# Type alias: the provider function takes (system_prompt, user_prompt) -> str.
# Keeping this decoupled from dharma_swarm.providers so the module works
# stand-alone and is trivially testable with a mock.
ProviderFn = Callable[[str, str], Awaitable[str]]


# ---------------------------------------------------------------------------
# GroupChat
# ---------------------------------------------------------------------------


class GroupChat:
    """Orchestrate a multi-round group discussion among N agents.

    Args:
        participants: Ordered list of agent names/roles that will take turns.
        config: Tuning parameters (rounds, token limits, moderator).
        provider_fn: Async callable ``(system_prompt, user_prompt) -> str``
            that produces an LLM completion.  Keeps this module decoupled
            from any specific provider.
    """

    def __init__(
        self,
        participants: list[str],
        config: GroupChatConfig,
        provider_fn: ProviderFn,
    ) -> None:
        if not participants:
            raise ValueError("participants must be non-empty")
        self._participants = list(participants)
        self._config = config
        self._provider_fn = provider_fn
        self.history: list[ChatMessage] = []

    # -- public API ---------------------------------------------------------

    async def run(self, topic: str) -> list[ChatMessage]:
        """Run the full multi-round discussion and return the transcript.

        Each round iterates through all participants in order.  If a
        moderator is configured, it speaks last in every round with a
        synthesis of that round's contributions.
        """
        self.history.clear()
        logger.info(
            "GroupChat starting: %d participants, %d rounds, topic=%r",
            len(self._participants),
            self._config.max_rounds,
            topic[:80],
        )

        for round_num in range(1, self._config.max_rounds + 1):
            # Regular participants
            for participant in self._participants:
                if participant == self._config.moderator_name:
                    continue  # moderator speaks last
                context = self._build_context(participant, topic, round_num)
                response = await self._get_response(participant, context)
                msg = ChatMessage(
                    speaker=participant,
                    content=response,
                    round_num=round_num,
                )
                self.history.append(msg)

            # Moderator synthesis (if configured and present)
            if (
                self._config.moderator_name
                and self._config.moderator_name in self._participants
            ):
                context = self._build_moderator_context(topic, round_num)
                response = await self._get_response(
                    self._config.moderator_name, context
                )
                msg = ChatMessage(
                    speaker=self._config.moderator_name,
                    content=response,
                    round_num=round_num,
                )
                self.history.append(msg)

        logger.info(
            "GroupChat finished: %d messages across %d rounds",
            len(self.history),
            self._config.max_rounds,
        )
        return list(self.history)

    def summarize(self) -> str:
        """Return a plain-text summary of the discussion."""
        if not self.history:
            return "No discussion has taken place."

        lines: list[str] = []
        current_round = 0
        for msg in self.history:
            if msg.round_num != current_round:
                current_round = msg.round_num
                lines.append(f"\n--- Round {current_round} ---")
            lines.append(f"[{msg.speaker}]: {msg.content}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full chat session to a JSON-safe dict."""
        return {
            "participants": list(self._participants),
            "config": {
                "max_rounds": self._config.max_rounds,
                "max_tokens_per_turn": self._config.max_tokens_per_turn,
                "moderator_name": self._config.moderator_name,
            },
            "messages": [
                {
                    "speaker": m.speaker,
                    "content": m.content,
                    "round_num": m.round_num,
                    "timestamp": m.timestamp,
                }
                for m in self.history
            ],
            "total_messages": len(self.history),
        }

    # -- internals ----------------------------------------------------------

    async def _get_response(self, participant: str, context: str) -> str:
        """Get one agent's contribution via the injected provider function."""
        system_prompt = (
            f"You are '{participant}' in a multi-agent group discussion. "
            f"Contribute your unique perspective. Be concise — "
            f"stay under {self._config.max_tokens_per_turn} tokens."
        )
        try:
            return await self._provider_fn(system_prompt, context)
        except Exception:
            logger.exception("Provider call failed for participant %s", participant)
            return f"[{participant} was unable to respond due to a provider error.]"

    def _build_context(self, participant: str, topic: str, round_num: int) -> str:
        """Build the user prompt with topic + full history for a participant."""
        parts: list[str] = [f"Topic: {topic}\n"]
        if self.history:
            parts.append("Conversation so far:")
            for msg in self.history:
                parts.append(f"  [{msg.speaker}] (round {msg.round_num}): {msg.content}")
            parts.append("")
        parts.append(
            f"Round {round_num}: It is your turn, {participant}. "
            "Respond with your perspective, building on what others have said."
        )
        return "\n".join(parts)

    def _build_moderator_context(self, topic: str, round_num: int) -> str:
        """Build the moderator's prompt for synthesizing the current round."""
        round_msgs = [m for m in self.history if m.round_num == round_num]
        parts: list[str] = [
            f"Topic: {topic}\n",
            f"Round {round_num} contributions:",
        ]
        for msg in round_msgs:
            parts.append(f"  [{msg.speaker}]: {msg.content}")
        parts.append(
            "\nAs moderator, synthesize these perspectives. "
            "Identify agreements, disagreements, and what needs deeper exploration."
        )
        return "\n".join(parts)
