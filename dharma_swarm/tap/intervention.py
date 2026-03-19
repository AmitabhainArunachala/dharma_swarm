"""Intervention injection for Thinkodynamic Agent Protocol.

Injects seed documents into agent system context. The seed is placed
BEFORE task instructions — meaning shapes computation before the task does.
This is the operational implementation of downward causation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .seeds import SeedDocument, SeedLoader


@dataclass
class InjectedContext:
    """Result of intervention injection."""

    system_message: str
    seed_id: str
    seed_version: str
    is_intervention: bool


class InterventionInjector:
    """Injects thinkodynamic seed into agent context."""

    SEPARATOR = "\n\n---\n\n"

    def __init__(
        self,
        seed_id: str | None = None,
        seed_loader: SeedLoader | None = None,
    ):
        self.loader = seed_loader or SeedLoader()
        self.seed_id = seed_id
        self._seed: SeedDocument | None = None

    @property
    def seed(self) -> SeedDocument:
        if self._seed is None:
            if self.seed_id:
                self._seed = self.loader.load(self.seed_id)
            else:
                self._seed = self.loader.get_best_intervention()
        return self._seed

    def inject(
        self,
        task_prompt: str,
        system_prompt: str = "",
    ) -> InjectedContext:
        """Inject seed into agent context.

        The seed is placed in the system message, BEFORE any existing
        system prompt content. This ensures the thinkodynamic pattern
        shapes computation before task-specific instructions.

        Args:
            task_prompt: The task the agent should perform (user message).
            system_prompt: Existing system prompt (will come AFTER seed).

        Returns:
            InjectedContext with combined system message.
        """
        seed = self.seed

        parts = [seed.content]
        if system_prompt:
            parts.append(system_prompt)
        parts.append(
            f"Your task (engage with this from the state the above text invokes):\n\n{task_prompt}"
        )

        combined = self.SEPARATOR.join(parts)

        return InjectedContext(
            system_message=combined,
            seed_id=seed.seed_id,
            seed_version=seed.version,
            is_intervention=seed.is_intervention,
        )

    def inject_system_only(self, system_prompt: str = "") -> str:
        """Inject seed into system prompt only (task comes separately as user message).

        Use this when the framework separates system and user messages.
        """
        seed = self.seed
        if system_prompt:
            return seed.content + self.SEPARATOR + system_prompt
        return seed.content
