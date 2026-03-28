from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.dharma_corpus import Claim, ClaimCategory, ClaimStatus
from dharma_swarm.dharma_kernel import DharmaKernel
from dharma_swarm.models import AgentRole
from dharma_swarm.orientation_packet import DirectiveSummary
from dharma_swarm.runtime_bridge import RuntimeAdapter, RuntimeBridge, RuntimeDescriptor
from dharma_swarm.semantic_governance import ActionEnvelope


class DummyAdapter(RuntimeAdapter):
    def __init__(self) -> None:
        self.descriptor = RuntimeDescriptor(
            runtime_id="dummy",
            name="Dummy Runtime",
            runtime_type="test",
            capabilities=["orientation", "governed_actions"],
        )

    def normalize_action(self, payload: object) -> ActionEnvelope:
        data = dict(payload)
        return ActionEnvelope(
            actor_id=data["actor_id"],
            actor_type=data["actor_type"],
            runtime_type=self.descriptor.runtime_type,
            action_type=data["action_type"],
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
        )


def _claim(claim_id: str, statement: str, enforcement: str = "warn") -> Claim:
    return Claim(
        id=claim_id,
        statement=statement,
        category=ClaimCategory.ARCHITECTURAL,
        confidence=0.9,
        enforcement=enforcement,
        status=ClaimStatus.ACCEPTED,
    )


def test_runtime_bridge_registers_and_lists_descriptors():
    bridge = RuntimeBridge()
    descriptor = bridge.register(DummyAdapter())
    assert descriptor.runtime_id == "dummy"
    assert [item.runtime_id for item in bridge.list_descriptors()] == ["dummy"]


def test_runtime_bridge_issues_orientation_packet():
    bridge = RuntimeBridge()
    bridge.register(DummyAdapter())
    packet = bridge.issue_orientation(
        "dummy",
        role=AgentRole.WORKER.value,
        kernel=DharmaKernel.create_default(),
        claims=[_claim("DC-2026-0001", "keep routing explicit")],
        contradictions=[
            Contradiction(
                contradiction_id="ctr-1",
                claim_ids=["DC-2026-0001", "DC-2026-0002"],
                reason="declared",
            )
        ],
        directives=[DirectiveSummary(directive_id="d1", title="Cybernetics", summary="close the loop")],
        role_context="Act conservatively.",
    )
    assert packet.role == AgentRole.WORKER.value
    assert packet.active_claims
    assert any(item.startswith("runtime:dummy") for item in packet.provenance)


def test_runtime_bridge_governs_action_through_registered_adapter():
    bridge = RuntimeBridge()
    bridge.register(DummyAdapter())
    envelope, verdict = bridge.govern_action(
        "dummy",
        {
            "actor_id": "agent-1",
            "actor_type": "worker",
            "action_type": "shell_command",
            "content": "delete the production database now",
        },
        claims=[_claim("DC-2026-0001", "delete production database", enforcement="block")],
    )
    assert envelope.runtime_type == "test"
    assert verdict.enforcement_level == "block"
    assert verdict.allowed is False
