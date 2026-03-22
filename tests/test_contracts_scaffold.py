from __future__ import annotations

from dharma_swarm.contracts import (
    AgentRuntime,
    CheckpointStatus,
    EvaluationSink,
    GatewayAdapter,
    LearningEngine,
    MemoryPlane,
    MemoryTruthState,
    RunStatus,
    SandboxProvider,
    SkillPromotionState,
    SkillStore,
)


def test_contract_enums_expose_canonical_status_values() -> None:
    assert RunStatus.IN_PROGRESS.value == "in_progress"
    assert CheckpointStatus.APPROVED.value == "approved"
    assert MemoryTruthState.PROMOTED.value == "promoted"
    assert SkillPromotionState.SHARED.value == "shared"


def test_contract_protocols_are_importable() -> None:
    for protocol in (
        AgentRuntime,
        GatewayAdapter,
        MemoryPlane,
        LearningEngine,
        SkillStore,
        EvaluationSink,
        SandboxProvider,
    ):
        assert getattr(protocol, "__name__", "")
