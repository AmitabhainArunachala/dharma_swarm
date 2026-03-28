from dharma_swarm.context import build_orientation_packet
from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.dharma_corpus import Claim, ClaimCategory, ClaimStatus
from dharma_swarm.dharma_kernel import DharmaKernel
from dharma_swarm.models import AgentRole
from dharma_swarm.orientation_packet import DirectiveSummary, OrientationPacketBuilder


def _claim(claim_id: str, category: ClaimCategory, confidence: float) -> Claim:
    return Claim(
        id=claim_id,
        statement=f"statement {claim_id}",
        category=category,
        confidence=confidence,
        enforcement="warn",
        status=ClaimStatus.ACCEPTED,
    )


def test_build_packet_is_role_aware():
    kernel = DharmaKernel.create_default()
    claims = [
        _claim("DC-2026-0001", ClaimCategory.THEORETICAL, 0.9),
        _claim("DC-2026-0002", ClaimCategory.EMPIRICAL, 0.8),
        _claim("DC-2026-0003", ClaimCategory.OPERATIONAL, 0.95),
        _claim("DC-2026-0004", ClaimCategory.SAFETY, 0.85),
    ]

    builder = OrientationPacketBuilder()
    researcher_packet = builder.build(role=AgentRole.RESEARCHER.value, kernel=kernel, claims=claims)
    worker_packet = builder.build(role=AgentRole.WORKER.value, kernel=kernel, claims=claims)

    assert researcher_packet.active_claims[0].category == ClaimCategory.THEORETICAL
    assert worker_packet.active_claims[0].category in {ClaimCategory.OPERATIONAL, ClaimCategory.SAFETY, ClaimCategory.ARCHITECTURAL}


def test_packet_keeps_only_contradictions_for_selected_claims():
    kernel = DharmaKernel.create_default()
    claims = [
        _claim("DC-2026-0001", ClaimCategory.ARCHITECTURAL, 0.9),
    ]
    contradictions = [
        Contradiction(
            contradiction_id="ctr-1",
            claim_ids=["DC-2026-0001", "DC-2026-0009"],
            reason="declared",
        ),
        Contradiction(
            contradiction_id="ctr-2",
            claim_ids=["DC-2026-0008", "DC-2026-0009"],
            reason="declared",
        ),
    ]
    packet = OrientationPacketBuilder().build(
        role=AgentRole.WORKER.value,
        kernel=kernel,
        claims=claims,
        contradictions=contradictions,
        directives=[DirectiveSummary(directive_id="d1", title="Cybernetics", summary="close the loop")],
    )
    assert [item.contradiction_id for item in packet.active_contradictions] == ["ctr-1"]


def test_render_text_includes_core_sections():
    kernel = DharmaKernel.create_default()
    packet = OrientationPacketBuilder().build(
        role=AgentRole.GENERAL.value,
        kernel=kernel,
        claims=[_claim("DC-2026-0001", ClaimCategory.ARCHITECTURAL, 0.9)],
        role_context="Focus on bounded governance deltas.",
        task="implement kernel",
    )
    text = OrientationPacketBuilder().render_text(packet)
    assert "Kernel axioms:" in text
    assert "Active claims:" in text
    assert "Role context:" in text


def test_context_build_orientation_packet_exposes_typed_helper():
    packet = build_orientation_packet(
        role=AgentRole.WORKER.value,
        claims=[_claim("DC-2026-0001", ClaimCategory.ARCHITECTURAL, 0.9)],
        role_context="Prefer bounded changes.",
    )
    assert packet.role == AgentRole.WORKER.value
    assert packet.active_claims[0].id == "DC-2026-0001"
