"""A2A Agent Cards -- capability advertisement for dharma_swarm agents.

Each agent publishes a card describing what it can do.
Other agents (local or remote) discover capabilities via cards.

Implements the Agent Card concept from Google's A2A protocol:
- Structured metadata: name, description, capabilities, endpoint, auth
- Registry for storing and querying cards
- Auto-generation from existing AgentIdentity / AgentConfig
- Persistence to ~/.dharma/a2a/cards/ as JSON files

Agent Cards are the foundation of the A2A protocol. Without cards,
agents cannot discover each other. Every agent MUST have a card.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DHARMA_HOME = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
_DEFAULT_CARDS_DIR = _DHARMA_HOME / "a2a" / "cards"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AgentCapability:
    """A single capability that an agent advertises.

    Attributes:
        name: Short identifier (e.g., "code_review", "research", "deploy").
        description: Human-readable explanation of what this capability does.
        input_modes: Accepted input types (e.g., ["text", "file", "data"]).
        output_modes: Produced output types.
    """

    name: str
    description: str = ""
    input_modes: list[str] = field(default_factory=lambda: ["text"])
    output_modes: list[str] = field(default_factory=lambda: ["text"])

    def matches(self, query: str) -> bool:
        """Check if this capability matches a search query (case-insensitive).

        Matches against name and description via substring containment.
        """
        q = query.lower()
        return q in self.name.lower() or q in self.description.lower()


@dataclass
class AgentCard:
    """A2A Agent Card -- structured metadata describing an agent.

    Follows Google's A2A Agent Card spec (simplified for local-first use).

    Attributes:
        name: Unique agent identifier within the swarm.
        description: What this agent does (1-2 sentences).
        capabilities: List of advertised capabilities.
        endpoint: For remote agents, the HTTP URL. For local, "local://".
        auth_type: Authentication method ("none", "api_key", "bearer").
        role: Agent role from dharma_swarm (e.g., "coder", "researcher").
        model: LLM model identifier.
        provider: LLM provider (e.g., "openrouter", "anthropic").
        status: Current agent status ("idle", "busy", "dead").
        version: Card schema version.
        created_at: ISO-8601 timestamp of card creation.
        updated_at: ISO-8601 timestamp of last update.
        metadata: Arbitrary extra data.
    """

    name: str
    description: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    endpoint: str = "local://"
    auth_type: str = "none"
    role: str = "general"
    model: str = ""
    provider: str = ""
    status: str = "idle"
    version: str = "1.0"
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCard:
        """Deserialize from dict, handling nested capabilities."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {}
        for k, v in data.items():
            if k not in known_fields:
                continue
            if k == "capabilities" and isinstance(v, list):
                caps = []
                for item in v:
                    if isinstance(item, dict):
                        cap_fields = {
                            f.name for f in AgentCapability.__dataclass_fields__.values()
                        }
                        caps.append(
                            AgentCapability(**{ck: cv for ck, cv in item.items() if ck in cap_fields})
                        )
                    elif isinstance(item, AgentCapability):
                        caps.append(item)
                filtered[k] = caps
            else:
                filtered[k] = v
        return cls(**filtered)

    @classmethod
    def from_agent_identity(cls, identity: dict[str, Any]) -> AgentCard:
        """Generate an AgentCard from an existing AgentIdentity dict.

        Maps role -> capabilities heuristically. This is the bridge between
        the existing agent_registry.py and the A2A protocol.
        """
        name = identity.get("name", "unknown")
        role = identity.get("role", "general")
        model = identity.get("model", "")
        prompt = identity.get("system_prompt", "")

        # Derive description from system prompt (first sentence or fallback)
        description = ""
        if prompt:
            # Take first sentence (up to 200 chars)
            for end_char in (".", "\n"):
                idx = prompt.find(end_char)
                if 0 < idx <= 200:
                    description = prompt[:idx + 1].strip()
                    break
            if not description:
                description = prompt[:200].strip()
        if not description:
            description = f"{role} agent in dharma_swarm"

        # Derive capabilities from role
        capabilities = _capabilities_for_role(role)

        return cls(
            name=name,
            description=description,
            capabilities=capabilities,
            role=role,
            model=model,
            status=identity.get("status", "idle"),
            metadata={
                "tasks_completed": identity.get("tasks_completed", 0),
                "tasks_failed": identity.get("tasks_failed", 0),
                "avg_quality": identity.get("avg_quality", 0.0),
            },
        )

    def has_capability(self, query: str) -> bool:
        """Check if this agent has a capability matching the query."""
        return any(cap.matches(query) for cap in self.capabilities)

    def capability_names(self) -> list[str]:
        """Return list of capability name strings."""
        return [cap.name for cap in self.capabilities]


def _capabilities_for_role(role: str) -> list[AgentCapability]:
    """Map an agent role to a default set of capabilities.

    This is a heuristic -- agents can override with explicit capabilities.
    """
    role_lower = role.lower()

    # Role -> capability mapping
    _ROLE_MAP: dict[str, list[AgentCapability]] = {
        "coder": [
            AgentCapability("code_generation", "Write, modify, and refactor code"),
            AgentCapability("code_review", "Review code for bugs and improvements"),
            AgentCapability("testing", "Write and run tests"),
        ],
        "reviewer": [
            AgentCapability("code_review", "Thorough code review with feedback"),
            AgentCapability("security_review", "Check for security vulnerabilities"),
        ],
        "researcher": [
            AgentCapability("research", "Deep research and analysis"),
            AgentCapability("literature_review", "Review academic papers and docs"),
            AgentCapability("synthesis", "Synthesize information from multiple sources"),
        ],
        "tester": [
            AgentCapability("testing", "Write and execute test suites"),
            AgentCapability("verification", "Verify claims and results"),
        ],
        "orchestrator": [
            AgentCapability("task_routing", "Route tasks to appropriate agents"),
            AgentCapability("coordination", "Coordinate multi-agent workflows"),
            AgentCapability("monitoring", "Monitor agent health and progress"),
        ],
        "architect": [
            AgentCapability("architecture", "Design system architecture"),
            AgentCapability("code_review", "Review architectural decisions"),
        ],
        "operator": [
            AgentCapability("deployment", "Deploy and manage services"),
            AgentCapability("monitoring", "System monitoring and alerting"),
            AgentCapability("infrastructure", "Manage infrastructure"),
        ],
        "witness": [
            AgentCapability("observation", "Observe and record system state"),
            AgentCapability("reflection", "Reflect on system behavior patterns"),
        ],
        "strategist": [
            AgentCapability("strategic_planning", "High-level strategic analysis"),
            AgentCapability("prioritization", "Prioritize tasks and goals"),
        ],
    }

    capabilities = _ROLE_MAP.get(role_lower, [])
    if not capabilities:
        # Fallback: generic capability named after role
        capabilities = [
            AgentCapability(
                role_lower,
                f"General {role_lower} capabilities",
            )
        ]
    return capabilities


# ---------------------------------------------------------------------------
# Card Registry
# ---------------------------------------------------------------------------


class CardRegistry:
    """Registry for storing, retrieving, and discovering Agent Cards.

    Cards are stored in-memory and persisted to JSON files on disk.
    Supports capability-based discovery queries.

    Attributes:
        cards_dir: Path to directory where cards are persisted.
    """

    def __init__(self, cards_dir: Path | None = None) -> None:
        self.cards_dir = cards_dir or _DEFAULT_CARDS_DIR
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self._cards: dict[str, AgentCard] = {}
        self._load_from_disk()

    # -- persistence ---------------------------------------------------------

    def _card_path(self, name: str) -> Path:
        """Path to a card's JSON file on disk."""
        # Sanitize name for filesystem safety
        safe_name = name.replace("/", "_").replace("\\", "_")
        return self.cards_dir / f"{safe_name}.json"

    def _load_from_disk(self) -> None:
        """Load all cards from the cards directory."""
        if not self.cards_dir.exists():
            return
        for path in sorted(self.cards_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                card = AgentCard.from_dict(data)
                self._cards[card.name] = card
            except Exception as exc:
                logger.warning("Failed to load card %s: %s", path, exc)

    def _persist_card(self, card: AgentCard) -> None:
        """Write a single card to disk."""
        path = self._card_path(card.name)
        try:
            path.write_text(
                json.dumps(card.to_dict(), indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to persist card %s: %s", card.name, exc)

    # -- registration --------------------------------------------------------

    def register(self, card: AgentCard) -> None:
        """Register or update an agent card.

        Persists to disk immediately.
        """
        card.updated_at = _utc_now_iso()
        self._cards[card.name] = card
        self._persist_card(card)
        logger.info("Registered A2A card: %s (%s)", card.name, card.role)

    def unregister(self, name: str) -> bool:
        """Remove an agent card. Returns True if card existed."""
        if name not in self._cards:
            return False
        del self._cards[name]
        path = self._card_path(name)
        if path.exists():
            path.unlink()
        logger.info("Unregistered A2A card: %s", name)
        return True

    # -- retrieval -----------------------------------------------------------

    def get(self, name: str) -> AgentCard | None:
        """Get a card by agent name."""
        return self._cards.get(name)

    def list_all(self) -> list[AgentCard]:
        """Return all registered cards, sorted by name."""
        return sorted(self._cards.values(), key=lambda c: c.name)

    def count(self) -> int:
        """Number of registered cards."""
        return len(self._cards)

    # -- discovery -----------------------------------------------------------

    def discover(self, capability: str) -> list[AgentCard]:
        """Find agents that have a matching capability.

        Args:
            capability: Search query matched against capability names
                and descriptions (case-insensitive substring).

        Returns:
            List of matching AgentCards, sorted by name.
        """
        matches = [
            card
            for card in self._cards.values()
            if card.has_capability(capability)
        ]
        return sorted(matches, key=lambda c: c.name)

    def discover_by_role(self, role: str) -> list[AgentCard]:
        """Find agents with a specific role.

        Args:
            role: Role string to match (case-insensitive).

        Returns:
            List of matching AgentCards.
        """
        role_lower = role.lower()
        return sorted(
            [c for c in self._cards.values() if c.role.lower() == role_lower],
            key=lambda c: c.name,
        )

    def discover_available(self) -> list[AgentCard]:
        """Find agents that are currently available (not busy/dead)."""
        return sorted(
            [c for c in self._cards.values() if c.status in ("idle", "starting")],
            key=lambda c: c.name,
        )

    # -- bulk operations -----------------------------------------------------

    def register_from_agent_registry(
        self,
        agents: list[dict[str, Any]],
    ) -> int:
        """Generate and register cards from a list of AgentIdentity dicts.

        This bridges the existing agent_registry.py to A2A.

        Args:
            agents: List of identity dicts (from AgentRegistry.list_agents()).

        Returns:
            Number of cards registered.
        """
        count = 0
        for identity in agents:
            try:
                card = AgentCard.from_agent_identity(identity)
                self.register(card)
                count += 1
            except Exception as exc:
                name = identity.get("name", "<unknown>")
                logger.warning("Failed to create card for %s: %s", name, exc)
        logger.info("Registered %d A2A cards from agent registry.", count)
        return count

    def sync_status(self, name: str, status: str) -> None:
        """Update the status of a registered card (e.g., idle -> busy).

        No-op if the card doesn't exist.
        """
        card = self._cards.get(name)
        if card is not None:
            card.status = status
            card.updated_at = _utc_now_iso()
            self._persist_card(card)
