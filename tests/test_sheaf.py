from __future__ import annotations

from datetime import datetime, timezone

from dharma_swarm.models import AgentRole, AgentState, Message
from dharma_swarm.sheaf import (
    CechCohomology,
    CoordinationProtocol,
    Discovery,
    DiscoverySheaf,
    NoosphereSite,
)


def _agent(agent_id: str) -> AgentState:
    return AgentState(id=agent_id, name=agent_id, role=AgentRole.GENERAL)


def _message(source: str, target: str, *, topic: str = "", index: int = 0) -> Message:
    return Message(
        id=f"msg-{source}-{target}-{index}",
        from_agent=source,
        to_agent=target,
        subject="coordination",
        body="shared context",
        created_at=datetime(2026, 3, 10, 0, 0, index, tzinfo=timezone.utc),
        metadata={"topic": topic} if topic else {},
    )


def _discovery(agent_id: str, claim_key: str, content: str, confidence: float = 0.8) -> Discovery:
    return Discovery(
        agent_id=agent_id,
        claim_key=claim_key,
        content=content,
        confidence=confidence,
        evidence=[f"evidence:{agent_id}:{claim_key}"],
        perspective=agent_id,
    )


def test_noosphere_site_from_messages_builds_channels_and_covering_sieve() -> None:
    agents = [_agent("a"), _agent("b"), _agent("c")]
    site = NoosphereSite.from_messages(
        agents,
        [
            _message("a", "b", topic="routing", index=1),
            _message("c", "b", topic="routing", index=2),
        ],
    )

    cover = site.covering_sieve("b")

    assert site.has_overlap("a", "b") is True
    assert site.has_overlap("b", "c") is True
    assert cover == [{"a", "b", "c"}]
    assert site.channels[("a", "b")].topics == ["routing"]
    assert site.channels[("a", "b")].message_ids == ["msg-a-b-1"]
    assert site.channels[("a", "b")].weight == 1.0


def test_noosphere_site_normalizes_dict_channels() -> None:
    site = NoosphereSite(
        [_agent("a"), _agent("b"), _agent("c")],
        channels=[
            {"source_agent": "a", "target_agent": "b", "topics": ["routing"]},
            {"source_agent": "b", "target_agent": "c", "topics": ["review"]},
        ],
    )

    assert site.has_overlap("a", "b") is True
    assert site.has_overlap("b", "c") is True
    assert site.channels[("a", "b")].topics == ["routing"]
    assert site.channels[("b", "c")].topics == ["review"]


def test_noosphere_site_accumulates_message_weights_without_double_counting() -> None:
    agents = [_agent("a"), _agent("b")]
    site = NoosphereSite.from_messages(
        agents,
        [
            _message("a", "b", topic="routing", index=1),
            _message("a", "b", topic="routing", index=2),
        ],
    )

    channel = site.channels[("a", "b")]

    assert channel.message_ids == ["msg-a-b-1", "msg-a-b-2"]
    assert channel.topics == ["routing"]
    assert channel.weight == 2.0


def test_sheaf_glues_compatible_local_sections_uniquely() -> None:
    sheaf = DiscoverySheaf()
    data = {
        "a": _discovery("a", "route", "Mechanism, witness, ecosystem all agree."),
        "b": _discovery("b", "route", "Mechanism, witness, ecosystem all agree."),
        "c": _discovery("c", "route", "Mechanism, witness, ecosystem all agree."),
    }

    glued = sheaf.glue(data)

    assert glued is not None
    assert glued.agent_id == "GLOBAL"
    assert glued.claim_key == "route"
    assert set(glued.metadata["glued_from"]) == {"a", "b", "c"}
    assert len(glued.evidence) == 3


def test_cech_h0_finds_global_truth_when_triangle_agrees() -> None:
    agents = [_agent("a"), _agent("b"), _agent("c")]
    site = NoosphereSite(
        agents,
        channels=[
            {"source_agent": "a", "target_agent": "b"},
            {"source_agent": "b", "target_agent": "c"},
            {"source_agent": "c", "target_agent": "a"},
        ],
    )
    protocol = CoordinationProtocol(site)
    for agent_id in ["a", "b", "c"]:
        protocol.publish(
            agent_id,
            [_discovery(agent_id, "route", "Mechanism, witness, ecosystem all agree.")],
        )

    result = protocol.coordinate()

    assert len(result.global_truths) == 1
    assert result.productive_disagreements == []
    assert result.is_globally_coherent is True


def test_cech_h1_records_productive_disagreement_as_anekanta() -> None:
    agents = [_agent("a"), _agent("b"), _agent("c")]
    site = NoosphereSite(
        agents,
        channels=[
            {"source_agent": "a", "target_agent": "b"},
            {"source_agent": "b", "target_agent": "c"},
            {"source_agent": "c", "target_agent": "a"},
        ],
    )
    protocol = CoordinationProtocol(site)
    protocol.publish(
        "a",
        [_discovery("a", "route", "Mechanism and architecture dominate this route.")],
    )
    protocol.publish(
        "b",
        [_discovery("b", "route", "Witness awareness and introspection dominate this route.")],
    )
    protocol.publish(
        "c",
        [_discovery("c", "route", "Ecosystem emergence and feedback dominate this route.")],
    )

    descent = protocol.verify_overlaps()
    result = protocol.coordinate(descent)

    assert result.global_truths == []
    assert result.is_globally_coherent is False
    assert len(result.productive_disagreements) == 1
    obstruction = result.productive_disagreements[0]
    assert obstruction.claim_key == "route"
    assert sorted(obstruction.agent_ids) == ["a", "b", "c"]
    assert obstruction.anekanta.frame_count >= 1
    assert len(descent.conflicts) >= 1


def test_coordination_protocol_reports_agreements_and_conflicts() -> None:
    agents = [_agent("a"), _agent("b"), _agent("c")]
    site = NoosphereSite(
        agents,
        channels=[
            {"source_agent": "a", "target_agent": "b"},
            {"source_agent": "b", "target_agent": "c"},
        ],
    )
    protocol = CoordinationProtocol(site)
    protocol.publish("a", [_discovery("a", "x", "shared claim")])
    protocol.publish("b", [_discovery("b", "x", "shared claim")])
    protocol.publish("b", [_discovery("b", "y", "local b view")])
    protocol.publish("c", [_discovery("c", "y", "different c view")])

    descent = protocol.verify_overlaps()

    assert len(descent.agreements) == 1
    assert len(descent.conflicts) == 1
    assert descent.agreements[0].claim_key == "x"
    assert descent.conflicts[0].claim_key == "y"


def test_cohomological_dimension_scales_with_connectivity() -> None:
    solo_site = NoosphereSite([_agent("solo")], channels=[])
    trio_site = NoosphereSite(
        [_agent("a"), _agent("b"), _agent("c")],
        channels=[
            {"source_agent": "a", "target_agent": "b"},
            {"source_agent": "b", "target_agent": "c"},
        ],
    )
    cohomology = CechCohomology()

    assert cohomology.cohomological_dimension(solo_site) == 0
    assert cohomology.cohomological_dimension(trio_site) == 1
