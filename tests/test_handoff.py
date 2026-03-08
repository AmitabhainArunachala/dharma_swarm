"""Tests for dharma_swarm.handoff -- A2A-inspired structured handoff protocol."""

import pytest

from dharma_swarm.handoff import (
    Artifact,
    ArtifactType,
    Handoff,
    HandoffPriority,
    HandoffProtocol,
)


@pytest.fixture
def protocol(tmp_path):
    """HandoffProtocol backed by a temp JSONL file."""
    return HandoffProtocol(store_path=tmp_path / "handoffs.jsonl")


def _artifact(
    atype: ArtifactType = ArtifactType.CODE_DIFF,
    content: str = "diff --git a/foo.py",
    summary: str = "Changed foo.py",
) -> Artifact:
    return Artifact(artifact_type=atype, content=content, summary=summary)


# ---------------------------------------------------------------------------
# 1. Create handoff with single artifact
# ---------------------------------------------------------------------------


async def test_create_single_artifact(protocol):
    h = await protocol.create_handoff(
        from_agent="surgeon",
        to_agent="validator",
        task_context="Fix import cycle in models.py",
        artifacts=[_artifact()],
    )
    assert len(h.id) == 12
    assert h.from_agent == "surgeon"
    assert h.to_agent == "validator"
    assert h.status == "pending"
    assert len(h.artifacts) == 1
    assert h.artifacts[0].artifact_type == ArtifactType.CODE_DIFF


# ---------------------------------------------------------------------------
# 2. Create handoff with multiple artifacts
# ---------------------------------------------------------------------------


async def test_create_multiple_artifacts(protocol):
    arts = [
        _artifact(ArtifactType.CODE_DIFF, "diff content", "fixed bug"),
        _artifact(ArtifactType.TEST_RESULTS, "3 passed", "tests ok"),
        _artifact(ArtifactType.ANALYSIS, "root cause: ...", "analysis"),
    ]
    h = await protocol.create_handoff(
        from_agent="surgeon",
        to_agent="validator",
        task_context="Multi-artifact handoff",
        artifacts=arts,
    )
    assert len(h.artifacts) == 3
    types = {a.artifact_type for a in h.artifacts}
    assert types == {ArtifactType.CODE_DIFF, ArtifactType.TEST_RESULTS, ArtifactType.ANALYSIS}


# ---------------------------------------------------------------------------
# 3. Get pending handoffs for specific agent
# ---------------------------------------------------------------------------


async def test_get_pending_for_agent(protocol):
    await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="task A", artifacts=[_artifact()],
    )
    await protocol.create_handoff(
        from_agent="surgeon", to_agent="architect",
        task_context="task B", artifacts=[_artifact()],
    )
    pending = await protocol.get_pending("validator")
    assert len(pending) == 1
    assert pending[0].task_context == "task A"


# ---------------------------------------------------------------------------
# 4. Acknowledge handoff changes status
# ---------------------------------------------------------------------------


async def test_acknowledge_handoff(protocol):
    h = await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="ack test", artifacts=[_artifact()],
    )
    await protocol.acknowledge(h.id)
    assert protocol._pending[h.id].status == "acknowledged"
    # No longer appears in pending list.
    pending = await protocol.get_pending("validator")
    assert len(pending) == 0


# ---------------------------------------------------------------------------
# 5. Reject handoff with reason
# ---------------------------------------------------------------------------


async def test_reject_handoff_with_reason(protocol):
    h = await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="reject test", artifacts=[_artifact()],
    )
    await protocol.reject(h.id, reason="Out of scope")
    assert protocol._pending[h.id].status == "rejected"
    assert protocol._pending[h.id].reject_reason == "Out of scope"


# ---------------------------------------------------------------------------
# 6. Get artifacts filtered by type
# ---------------------------------------------------------------------------


async def test_get_artifacts_filtered(protocol):
    arts = [
        _artifact(ArtifactType.CODE_DIFF, "diff1", "d1"),
        _artifact(ArtifactType.TEST_RESULTS, "results", "t1"),
        _artifact(ArtifactType.CODE_DIFF, "diff2", "d2"),
    ]
    h = await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="filter test", artifacts=arts,
    )
    diffs = await protocol.get_artifacts(h.id, ArtifactType.CODE_DIFF)
    assert len(diffs) == 2
    tests = await protocol.get_artifacts(h.id, ArtifactType.TEST_RESULTS)
    assert len(tests) == 1
    all_arts = await protocol.get_artifacts(h.id)
    assert len(all_arts) == 3


# ---------------------------------------------------------------------------
# 7. Build context from handoffs (priority ordering)
# ---------------------------------------------------------------------------


async def test_build_context_priority_ordering(protocol):
    await protocol.create_handoff(
        from_agent="a", to_agent="receiver",
        task_context="low priority info",
        artifacts=[_artifact(ArtifactType.CONTEXT, "ctx", "info")],
        priority=HandoffPriority.INFORMATIONAL,
    )
    await protocol.create_handoff(
        from_agent="b", to_agent="receiver",
        task_context="blocking work",
        artifacts=[_artifact(ArtifactType.PLAN, "plan", "urgent plan")],
        priority=HandoffPriority.BLOCKING,
    )
    ctx = await protocol.build_context_from_handoffs("receiver")
    assert ctx  # non-empty
    # BLOCKING should appear before INFORMATIONAL.
    blocking_pos = ctx.find("BLOCKING")
    info_pos = ctx.find("INFORMATIONAL")
    assert blocking_pos < info_pos


# ---------------------------------------------------------------------------
# 8. Build context respects budget
# ---------------------------------------------------------------------------


async def test_build_context_respects_budget(protocol):
    # Create a handoff with a large artifact.
    big_content = "x" * 3000
    await protocol.create_handoff(
        from_agent="a", to_agent="receiver",
        task_context="big task",
        artifacts=[_artifact(ArtifactType.ANALYSIS, big_content, "big")],
    )
    await protocol.create_handoff(
        from_agent="b", to_agent="receiver",
        task_context="second task",
        artifacts=[_artifact(ArtifactType.PLAN, "small", "small plan")],
    )
    ctx = await protocol.build_context_from_handoffs("receiver", budget=200)
    assert len(ctx) <= 250  # budget + small overhead from truncation marker


# ---------------------------------------------------------------------------
# 9. Broadcast handoff appears for all agents
# ---------------------------------------------------------------------------


async def test_broadcast_handoff(protocol):
    await protocol.create_handoff(
        from_agent="orchestrator", to_agent="*",
        task_context="broadcast announcement",
        artifacts=[_artifact(ArtifactType.CONTEXT, "everyone", "all")],
    )
    for name in ["surgeon", "validator", "architect"]:
        pending = await protocol.get_pending(name)
        assert len(pending) == 1
        assert pending[0].to_agent == "*"
    # Sender does not see their own broadcast.
    own = await protocol.get_pending("orchestrator")
    assert len(own) == 0


# ---------------------------------------------------------------------------
# 10. Handoff chain tracks lineage
# ---------------------------------------------------------------------------


async def test_handoff_chain(protocol):
    await protocol.create_handoff(
        from_agent="cartographer", to_agent="surgeon",
        task_context="mapped ecosystem",
        artifacts=[_artifact(ArtifactType.FILE_LIST, "files", "file list")],
    )
    await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="applied fix",
        artifacts=[_artifact(ArtifactType.CODE_DIFF, "diff", "the fix")],
    )
    chain = await protocol.handoff_chain("validator")
    assert len(chain) >= 2
    # Most recent first: surgeon->validator, then cartographer->surgeon.
    assert chain[0].from_agent == "surgeon"
    assert chain[1].from_agent == "cartographer"


# ---------------------------------------------------------------------------
# 11. Summary format is correct
# ---------------------------------------------------------------------------


async def test_summary_format(protocol):
    h = await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="Fix bug in handoff module for better reliability",
        artifacts=[
            _artifact(ArtifactType.CODE_DIFF),
            _artifact(ArtifactType.TEST_RESULTS, "pass", "ok"),
        ],
    )
    s = h.summary()
    assert "surgeon->validator" in s
    assert "code_diff" in s
    assert "test_results" in s
    assert "Fix bug" in s


# ---------------------------------------------------------------------------
# 12. JSONL persistence (write and reload)
# ---------------------------------------------------------------------------


async def test_persistence_roundtrip(tmp_path):
    store = tmp_path / "handoffs.jsonl"
    p1 = HandoffProtocol(store_path=store)
    h = await p1.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="persist test",
        artifacts=[_artifact()],
    )
    # Verify file was written.
    assert store.exists()
    lines = store.read_text().strip().split("\n")
    assert len(lines) >= 1

    # Load into a fresh protocol instance.
    p2 = HandoffProtocol(store_path=store)
    count = await p2.load_from_store()
    assert count >= 1
    # The loaded handoff should be in pending.
    pending = await p2.get_pending("validator")
    assert len(pending) == 1
    assert pending[0].task_context == "persist test"


# ---------------------------------------------------------------------------
# 13. Empty pending returns empty list
# ---------------------------------------------------------------------------


async def test_empty_pending(protocol):
    pending = await protocol.get_pending("nobody")
    assert pending == []


# ---------------------------------------------------------------------------
# 14. Requires_ack flag behavior
# ---------------------------------------------------------------------------


async def test_requires_ack_flag(protocol):
    h_ack = await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="needs ack",
        artifacts=[_artifact()],
        requires_ack=True,
    )
    h_no_ack = await protocol.create_handoff(
        from_agent="surgeon", to_agent="validator",
        task_context="no ack needed",
        artifacts=[_artifact()],
        requires_ack=False,
    )
    assert h_ack.requires_ack is True
    assert h_no_ack.requires_ack is False

    # Both appear in pending.
    pending = await protocol.get_pending("validator")
    assert len(pending) == 2

    # Acknowledge the one that requires it.
    await protocol.acknowledge(h_ack.id)
    pending_after = await protocol.get_pending("validator")
    assert len(pending_after) == 1
    assert pending_after[0].id == h_no_ack.id

    # Attempting to acknowledge a non-existent ID raises KeyError.
    with pytest.raises(KeyError):
        await protocol.acknowledge("nonexistent_id_xyz")
