"""Sheaf-theoretic coordination layer for swarm discoveries.

This is a bounded Phase 4 implementation over existing swarm artifacts:
agents, message channels, and discovery records. Compatible local sections
glue into global truths; incompatible sections are recorded as productive
H^1 obstructions with Anekanta annotations.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from statistics import mean
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.anekanta_gate import AnekantaResult, evaluate_anekanta
from dharma_swarm.models import AgentState, Message, _new_id


def _agent_id(agent: AgentState | str) -> str:
    return agent if isinstance(agent, str) else agent.id


def _channel_model(channel: InformationChannel | Mapping[str, Any]) -> InformationChannel:
    if isinstance(channel, InformationChannel):
        return channel
    return InformationChannel.model_validate(channel)


def _canonicalize(text: str) -> str:
    return " ".join(text.lower().split())


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class InformationChannel(BaseModel):
    """A communication morphism in the noosphere site."""

    source_agent: str
    target_agent: str
    topics: list[str] = Field(default_factory=list)
    message_ids: list[str] = Field(default_factory=list)
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Discovery(BaseModel):
    """A local section published by one agent."""

    id: str = Field(default_factory=_new_id)
    agent_id: str
    claim_key: str = ""
    content: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    perspective: str = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def canonical_claim_key(self) -> str:
        return self.claim_key or _canonicalize(self.content)

    @property
    def normalized_content(self) -> str:
        return _canonicalize(self.content)


class OverlapAgreement(BaseModel):
    """Compatible local sections on an overlap."""

    agents: tuple[str, str]
    claim_key: str
    discovery_ids: list[str] = Field(default_factory=list)


class OverlapConflict(BaseModel):
    """Incompatible local sections on an overlap."""

    agents: tuple[str, str]
    claim_key: str
    left: Discovery
    right: Discovery
    anekanta: AnekantaResult


class CohomologyClass(BaseModel):
    """A first-order obstruction to gluing local sections."""

    claim_key: str
    agent_ids: list[str] = Field(default_factory=list)
    conflicting_contents: dict[str, str] = Field(default_factory=dict)
    local_sections: dict[str, Discovery] = Field(default_factory=dict)
    anekanta: AnekantaResult
    reason: str = ""


class DescentData(BaseModel):
    """Agreement and conflict data on overlaps."""

    agreements: list[OverlapAgreement] = Field(default_factory=list)
    conflicts: list[OverlapConflict] = Field(default_factory=list)
    published_agents: list[str] = Field(default_factory=list)


class CoordinationResult(BaseModel):
    """Result of one coordination pass."""

    global_truths: list[Discovery] = Field(default_factory=list)
    productive_disagreements: list[CohomologyClass] = Field(default_factory=list)
    descent_data: DescentData = Field(default_factory=DescentData)
    cohomological_dimension: int = 0
    is_globally_coherent: bool = True


class NoosphereSite:
    """Site of agents and information-sharing channels."""

    def __init__(
        self,
        agents: Sequence[AgentState | str],
        channels: (
            Mapping[tuple[str, str], InformationChannel | Mapping[str, Any]]
            | Sequence[InformationChannel | Mapping[str, Any]]
            | None
        ) = None,
    ) -> None:
        self.agents: dict[str, AgentState | str] = {
            _agent_id(agent): agent for agent in agents
        }
        if channels is None:
            self.channels: dict[tuple[str, str], InformationChannel] = {}
        elif isinstance(channels, Mapping):
            self.channels = {
                key: _channel_model(channel)
                for key, channel in channels.items()
            }
        else:
            self.channels = {
                (model.source_agent, model.target_agent): model
                for model in (_channel_model(channel) for channel in channels)
            }

    @classmethod
    def from_messages(
        cls,
        agents: Sequence[AgentState | str],
        messages: Sequence[Message],
    ) -> "NoosphereSite":
        channels: dict[tuple[str, str], InformationChannel] = {}
        for message in messages:
            key = (message.from_agent, message.to_agent)
            topic = str(message.metadata.get("topic", "") or message.subject or "").strip()
            existing = channels.get(key)
            if existing is None:
                existing = InformationChannel(
                    source_agent=message.from_agent,
                    target_agent=message.to_agent,
                    weight=0.0,
                )
                channels[key] = existing
            existing.message_ids.append(message.id)
            existing.weight += 1.0
            if topic:
                existing.topics = _dedupe([*existing.topics, topic])
        return cls(agents, channels)

    @property
    def agent_ids(self) -> list[str]:
        return list(self.agents)

    def neighbors(self, agent: AgentState | str) -> set[str]:
        agent_id = _agent_id(agent)
        linked: set[str] = set()
        for source, target in self.channels:
            if source == agent_id:
                linked.add(target)
            if target == agent_id:
                linked.add(source)
        return linked

    def has_overlap(self, left: AgentState | str, right: AgentState | str) -> bool:
        left_id = _agent_id(left)
        right_id = _agent_id(right)
        return (
            (left_id, right_id) in self.channels
            or (right_id, left_id) in self.channels
        )

    def overlap_pairs(self) -> list[tuple[str, str]]:
        return [
            (left, right)
            for left, right in combinations(self.agent_ids, 2)
            if self.has_overlap(left, right)
        ]

    def is_connected_subset(self, agent_ids: Sequence[str]) -> bool:
        wanted = {_agent_id(agent_id) for agent_id in agent_ids}
        if not wanted:
            return False
        start = next(iter(wanted))
        seen = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for neighbor in self.neighbors(current):
                if neighbor in wanted and neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        return seen == wanted

    def covering_sieve(self, agent: AgentState | str) -> list[set[str]]:
        agent_id = _agent_id(agent)
        cover = self.neighbors(agent_id) | {agent_id}
        return [cover] if cover else [{agent_id}]


class DiscoverySheaf:
    """Sheaf of local discoveries indexed by agent."""

    def __init__(
        self,
        initial_sections: Mapping[str, Sequence[Discovery]] | None = None,
    ) -> None:
        self._sections: dict[str, list[Discovery]] = {
            agent_id: [discovery.model_copy(deep=True) for discovery in discoveries]
            for agent_id, discoveries in (initial_sections or {}).items()
        }

    def publish(
        self,
        agent: AgentState | str,
        discoveries: Sequence[Discovery],
    ) -> None:
        agent_id = _agent_id(agent)
        bucket = self._sections.setdefault(agent_id, [])
        bucket.extend(discovery.model_copy(deep=True) for discovery in discoveries)

    def local_sections(self, agent: AgentState | str) -> list[Discovery]:
        return [
            discovery.model_copy(deep=True)
            for discovery in self._sections.get(_agent_id(agent), [])
        ]

    def by_claim(self, agent: AgentState | str) -> dict[str, Discovery]:
        grouped: dict[str, Discovery] = {}
        for discovery in self._sections.get(_agent_id(agent), []):
            key = discovery.canonical_claim_key
            incumbent = grouped.get(key)
            if incumbent is None or discovery.confidence >= incumbent.confidence:
                grouped[key] = discovery
        return grouped

    @staticmethod
    def compatible(left: Discovery, right: Discovery) -> bool:
        return (
            left.canonical_claim_key == right.canonical_claim_key
            and left.normalized_content == right.normalized_content
        )

    def restriction(
        self,
        discovery: Discovery,
        from_agent: AgentState | str,
        to_agent: AgentState | str,
    ) -> Discovery:
        return discovery.model_copy(
            update={
                "agent_id": _agent_id(to_agent),
                "perspective": f"restricted:{_agent_id(from_agent)}->{_agent_id(to_agent)}",
                "metadata": {
                    **discovery.metadata,
                    "restricted_from": _agent_id(from_agent),
                    "restricted_to": _agent_id(to_agent),
                },
            }
        )

    def glue(self, local_data: Mapping[str, Discovery]) -> Discovery | None:
        if not local_data:
            return None
        discoveries = list(local_data.values())
        first = discoveries[0]
        if any(not self.compatible(first, other) for other in discoveries[1:]):
            return None
        return Discovery(
            agent_id="GLOBAL",
            claim_key=first.canonical_claim_key,
            content=max(discoveries, key=lambda discovery: len(discovery.content)).content,
            evidence=_dedupe(
                [
                    evidence
                    for discovery in discoveries
                    for evidence in discovery.evidence
                ]
            ),
            confidence=float(mean(discovery.confidence for discovery in discoveries)),
            perspective="global",
            metadata={
                "glued_from": list(local_data),
                "perspectives": _dedupe(
                    [discovery.perspective for discovery in discoveries]
                ),
            },
        )


class CechCohomology:
    """First-order Cech-style cohomology over a discovery sheaf."""

    def _group_sections(
        self,
        sheaf: DiscoverySheaf,
    ) -> dict[str, dict[str, Discovery]]:
        grouped: dict[str, dict[str, Discovery]] = defaultdict(dict)
        for agent_id in list(sheaf._sections):
            for claim_key, discovery in sheaf.by_claim(agent_id).items():
                grouped[claim_key][agent_id] = discovery
        return grouped

    def compute_h0(self, sheaf: DiscoverySheaf, site: NoosphereSite) -> list[Discovery]:
        globals_: list[Discovery] = []
        for local_data in self._group_sections(sheaf).values():
            participants = list(local_data)
            if len(participants) == 1 and len(site.agent_ids) > 1:
                continue
            if len(participants) > 1 and not site.is_connected_subset(participants):
                continue
            glued = sheaf.glue(local_data)
            if glued is not None:
                globals_.append(glued)
        return globals_

    def compute_h1(self, sheaf: DiscoverySheaf, site: NoosphereSite) -> list[CohomologyClass]:
        obstructions: list[CohomologyClass] = []
        for claim_key, local_data in self._group_sections(sheaf).items():
            participants = list(local_data)
            if len(participants) < 2 or not site.is_connected_subset(participants):
                continue
            normalized = {discovery.normalized_content for discovery in local_data.values()}
            if len(normalized) <= 1:
                continue
            combined = " ".join(discovery.content for discovery in local_data.values())
            anekanta = evaluate_anekanta(combined)
            obstructions.append(
                CohomologyClass(
                    claim_key=claim_key,
                    agent_ids=sorted(participants),
                    conflicting_contents={
                        agent_id: discovery.content
                        for agent_id, discovery in local_data.items()
                    },
                    local_sections={
                        agent_id: discovery.model_copy(deep=True)
                        for agent_id, discovery in local_data.items()
                    },
                    anekanta=anekanta,
                    reason="Local sections disagree on overlaps and cannot be glued",
                )
            )
        return obstructions

    def cohomological_dimension(self, site: NoosphereSite) -> int:
        return 1 if site.overlap_pairs() else 0


class CoordinationProtocol:
    """Grothendieck-style descent protocol over local discoveries."""

    def __init__(
        self,
        site: NoosphereSite,
        sheaf: DiscoverySheaf | None = None,
        cohomology: CechCohomology | None = None,
    ) -> None:
        self.site = site
        self.sheaf = sheaf or DiscoverySheaf()
        self.cohomology = cohomology or CechCohomology()

    def publish(
        self,
        agent: AgentState | str,
        discoveries: Sequence[Discovery],
    ) -> None:
        self.sheaf.publish(agent, discoveries)

    def verify_overlaps(self) -> DescentData:
        agreements: list[OverlapAgreement] = []
        conflicts: list[OverlapConflict] = []
        for left_id, right_id in self.site.overlap_pairs():
            left_sections = self.sheaf.by_claim(left_id)
            right_sections = self.sheaf.by_claim(right_id)
            for claim_key in sorted(set(left_sections) & set(right_sections)):
                left = left_sections[claim_key]
                right = right_sections[claim_key]
                if self.sheaf.compatible(left, right):
                    agreements.append(
                        OverlapAgreement(
                            agents=(left_id, right_id),
                            claim_key=claim_key,
                            discovery_ids=[left.id, right.id],
                        )
                    )
                else:
                    conflicts.append(
                        OverlapConflict(
                            agents=(left_id, right_id),
                            claim_key=claim_key,
                            left=left,
                            right=right,
                            anekanta=evaluate_anekanta(left.content, right.content),
                        )
                    )
        return DescentData(
            agreements=agreements,
            conflicts=conflicts,
            published_agents=sorted(self.sheaf._sections),
        )

    def coordinate(self, descent_data: DescentData | None = None) -> CoordinationResult:
        descent = descent_data or self.verify_overlaps()
        h0 = self.cohomology.compute_h0(self.sheaf, self.site)
        h1 = self.cohomology.compute_h1(self.sheaf, self.site)
        return CoordinationResult(
            global_truths=h0,
            productive_disagreements=h1,
            descent_data=descent,
            cohomological_dimension=self.cohomology.cohomological_dimension(self.site),
            is_globally_coherent=not h1,
        )


__all__ = [
    "CechCohomology",
    "CohomologyClass",
    "CoordinationProtocol",
    "CoordinationResult",
    "DescentData",
    "Discovery",
    "DiscoverySheaf",
    "InformationChannel",
    "NoosphereSite",
    "OverlapAgreement",
    "OverlapConflict",
]
