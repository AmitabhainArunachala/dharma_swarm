"""Tests for artifact attachment support in dharma_swarm.message_bus."""

import pytest

from dharma_swarm.handoff import ArtifactType
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import Message, MessagePriority


@pytest.fixture
async def bus(tmp_path):
    """Create a fresh MessageBus with an initialized database."""
    b = MessageBus(tmp_path / "messages.db")
    await b.init_db()
    return b


# Helper to quickly send a message and return (bus, msg).
async def _send_msg(bus: MessageBus, **overrides) -> Message:
    defaults = {"from_agent": "alice", "to_agent": "bob", "body": "hello"}
    defaults.update(overrides)
    msg = Message(**defaults)
    await bus.send(msg)
    return msg


# ------------------------------------------------------------------
# 1. Attach artifact to existing message
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attach_artifact_to_existing_message(bus):
    msg = await _send_msg(bus)
    art_id = await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.CODE_DIFF.value,
        content="--- a/foo.py\n+++ b/foo.py\n@@ ...",
        summary="Fixed null check in foo.py",
        files_touched=["foo.py"],
        metadata={"lines_changed": 3},
    )
    assert isinstance(art_id, str)
    assert len(art_id) > 0


# ------------------------------------------------------------------
# 2. Get artifacts returns correct data
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_artifacts_returns_correct_data(bus):
    msg = await _send_msg(bus)
    await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.ANALYSIS.value,
        content="The system is stable.",
        summary="Stability report",
        files_touched=["report.md"],
        metadata={"confidence": 0.95},
    )
    arts = await bus.get_artifacts(msg.id)
    assert len(arts) == 1
    art = arts[0]
    assert art["artifact_type"] == "analysis"
    assert art["content"] == "The system is stable."
    assert art["summary"] == "Stability report"
    assert art["files_touched"] == ["report.md"]
    assert art["metadata"] == {"confidence": 0.95}
    assert "created_at" in art
    assert art["message_id"] == msg.id


# ------------------------------------------------------------------
# 3. Get artifacts filtered by type
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_artifacts_filtered_by_type(bus):
    msg = await _send_msg(bus)
    await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.CODE_DIFF.value,
        content="diff content",
    )
    await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.TEST_RESULTS.value,
        content="all 42 tests passed",
    )
    await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.CODE_DIFF.value,
        content="another diff",
    )

    diffs = await bus.get_artifacts(msg.id, artifact_type=ArtifactType.CODE_DIFF.value)
    assert len(diffs) == 2
    assert all(a["artifact_type"] == "code_diff" for a in diffs)

    tests = await bus.get_artifacts(msg.id, artifact_type=ArtifactType.TEST_RESULTS.value)
    assert len(tests) == 1
    assert tests[0]["content"] == "all 42 tests passed"


# ------------------------------------------------------------------
# 4. send_with_artifacts creates message and artifacts atomically
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_with_artifacts_atomic(bus):
    msg = Message(
        from_agent="builder", to_agent="reviewer", body="Review this patch",
        subject="Patch v3",
    )
    artifacts = [
        {
            "artifact_type": ArtifactType.CODE_DIFF.value,
            "content": "--- a/main.py\n+++ b/main.py",
            "summary": "Main patch",
            "files_touched": ["main.py"],
        },
        {
            "artifact_type": ArtifactType.TEST_RESULTS.value,
            "content": "12 passed, 0 failed",
        },
    ]
    msg_id = await bus.send_with_artifacts(msg, artifacts)
    assert msg_id == msg.id

    # Verify the message was persisted.
    received = await bus.receive("reviewer")
    assert len(received) == 1
    assert received[0].subject == "Patch v3"

    # Verify all artifacts were persisted.
    arts = await bus.get_artifacts(msg.id)
    assert len(arts) == 2
    types = {a["artifact_type"] for a in arts}
    assert types == {"code_diff", "test_results"}


# ------------------------------------------------------------------
# 5. build_context_from_artifacts formats correctly
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_context_from_artifacts_format(bus):
    msg = Message(
        from_agent="scout", to_agent="lead", body="findings",
        subject="Recon Report", priority=MessagePriority.HIGH,
    )
    await bus.send_with_artifacts(msg, [
        {
            "artifact_type": ArtifactType.ANALYSIS.value,
            "content": "Deep analysis content here",
            "summary": "Found 3 issues",
        },
    ])
    ctx = await bus.build_context_from_artifacts("lead")
    assert ctx.startswith("# Artifact Context")
    assert "[HIGH]" in ctx
    assert "From scout" in ctx
    assert "Recon Report" in ctx
    assert "analysis" in ctx
    assert "Found 3 issues" in ctx


# ------------------------------------------------------------------
# 6. build_context respects budget
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_context_respects_budget(bus):
    msg = Message(
        from_agent="a", to_agent="b", body="x", subject="Big Report",
        priority=MessagePriority.URGENT,
    )
    # Create a large artifact that would exceed the budget.
    big_content = "x" * 10_000
    await bus.send_with_artifacts(msg, [
        {
            "artifact_type": ArtifactType.CONTEXT.value,
            "content": big_content,
            "summary": "A" * 500,
        },
    ])
    ctx = await bus.build_context_from_artifacts("b", budget=200)
    assert len(ctx) <= 250  # allow minor overhead from truncation marker
    assert "truncated" in ctx.lower()


# ------------------------------------------------------------------
# 7. Artifacts persist across connections
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_artifacts_persist_across_connections(tmp_path):
    db_path = tmp_path / "persist.db"

    # First connection: create message + artifact.
    bus1 = MessageBus(db_path)
    await bus1.init_db()
    msg = Message(from_agent="w", to_agent="r", body="data")
    await bus1.send(msg)
    art_id = await bus1.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.METRIC.value,
        content='{"rv": 0.73}',
        summary="R_V measurement",
    )

    # Second connection: read back.
    bus2 = MessageBus(db_path)
    await bus2.init_db()
    arts = await bus2.get_artifacts(msg.id)
    assert len(arts) == 1
    assert arts[0]["id"] == art_id
    assert arts[0]["content"] == '{"rv": 0.73}'


# ------------------------------------------------------------------
# 8. Empty artifacts list returns empty
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_artifacts_empty_returns_empty(bus):
    msg = await _send_msg(bus)
    arts = await bus.get_artifacts(msg.id)
    assert arts == []


# ------------------------------------------------------------------
# 9. Multiple artifacts on one message
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_artifacts_on_one_message(bus):
    msg = await _send_msg(bus)
    types_sent = [
        ArtifactType.CODE_DIFF,
        ArtifactType.ANALYSIS,
        ArtifactType.TEST_RESULTS,
        ArtifactType.PLAN,
        ArtifactType.FILE_LIST,
    ]
    for at in types_sent:
        await bus.attach_artifact(
            message_id=msg.id,
            artifact_type=at.value,
            content=f"content for {at.value}",
        )
    arts = await bus.get_artifacts(msg.id)
    assert len(arts) == 5
    returned_types = {a["artifact_type"] for a in arts}
    assert returned_types == {t.value for t in types_sent}


# ------------------------------------------------------------------
# 10. Artifact types match ArtifactType enum values
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_artifact_types_match_enum(bus):
    msg = await _send_msg(bus)
    for at in ArtifactType:
        art_id = await bus.attach_artifact(
            message_id=msg.id,
            artifact_type=at.value,
            content=f"test {at.value}",
        )
        assert isinstance(art_id, str)

    arts = await bus.get_artifacts(msg.id)
    stored_types = {a["artifact_type"] for a in arts}
    enum_values = {at.value for at in ArtifactType}
    assert stored_types == enum_values


# ------------------------------------------------------------------
# 11. Files_touched is properly serialized/deserialized (JSON list)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_files_touched_json_roundtrip(bus):
    msg = await _send_msg(bus)
    files = [
        "dharma_swarm/message_bus.py",
        "tests/test_message_bus_artifacts.py",
        "dharma_swarm/handoff.py",
    ]
    await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.FILE_LIST.value,
        content="touched files",
        files_touched=files,
    )
    arts = await bus.get_artifacts(msg.id)
    assert arts[0]["files_touched"] == files
    assert isinstance(arts[0]["files_touched"], list)

    # Default should be an empty list.
    await bus.attach_artifact(
        message_id=msg.id,
        artifact_type=ArtifactType.CONTEXT.value,
        content="no files",
    )
    arts_all = await bus.get_artifacts(msg.id)
    ctx_art = [a for a in arts_all if a["artifact_type"] == "context"][0]
    assert ctx_art["files_touched"] == []


# ------------------------------------------------------------------
# 12. Unknown message_id raises ValueError
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attach_to_unknown_message_raises(bus):
    with pytest.raises(ValueError, match="not found"):
        await bus.attach_artifact(
            message_id="totally_nonexistent_id",
            artifact_type=ArtifactType.ERROR_REPORT.value,
            content="orphan artifact",
        )
