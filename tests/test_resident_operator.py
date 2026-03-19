"""Tests for ResidentOperator — the core persistent operator agent."""

import asyncio

import pytest

from dharma_swarm.models import ProviderType
from dharma_swarm.resident_operator import (
    OperatorEvent,
    ResidentOperator,
    build_operator_prompt,
    OPERATOR_PORT,
)
from dharma_swarm.graduation_engine import AutonomyLevel
from dharma_swarm.tui.engine.events import SessionEnd, SessionStart, TextComplete


# -- OperatorEvent tests --

def test_operator_event_to_dict():
    event = OperatorEvent(
        event_type="text_delta",
        content="hello",
        session_id="s1",
        msg_id="m1",
        seq=1,
    )
    d = event.to_dict()
    assert d["type"] == "text_delta"
    assert d["content"] == "hello"
    assert d["session_id"] == "s1"
    assert d["msg_id"] == "m1"
    assert d["seq"] == 1


def test_operator_event_to_json():
    event = OperatorEvent(event_type="done", content="")
    j = event.to_json()
    assert '"type": "done"' in j


# -- build_operator_prompt tests --

def test_build_operator_prompt_basic():
    prompt = build_operator_prompt()
    assert "Resident Operator" in prompt
    assert "CONDUCTOR" in prompt
    assert "Jagat Kalyan" in prompt


def test_build_operator_prompt_with_context():
    prompt = build_operator_prompt(
        swarm_state="Agents: 5",
        stigmergy_context="- [scout] high activity",
    )
    assert "Agents: 5" in prompt
    assert "high activity" in prompt


# -- ResidentOperator lifecycle tests --

@pytest.mark.asyncio
async def test_operator_init_defaults():
    op = ResidentOperator()
    assert op.name == "operator"
    assert op.model == "anthropic/claude-sonnet-4"
    assert not op._running


@pytest.mark.asyncio
async def test_operator_start_and_stop(tmp_path):
    op = ResidentOperator(state_dir=tmp_path / ".dharma")
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)

    await op.start()
    assert op._running
    assert op._start_time > 0

    await op.stop()
    assert not op._running


@pytest.mark.asyncio
async def test_operator_start_initializes_bridge_in_state_dir(tmp_path):
    state_dir = tmp_path / ".dharma"
    op = ResidentOperator(state_dir=state_dir)
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)

    await op.start()

    assert op._bridge is not None
    assert op._bridge._initialized is True
    assert op._bridge._ledger.base_dir == state_dir / "ledgers"
    assert op._bridge._runtime_state is not None
    assert op._bridge._runtime_state.db_path == state_dir / "state" / "runtime.db"

    await op.stop()


@pytest.mark.asyncio
async def test_operator_status_dict(tmp_path):
    op = ResidentOperator(state_dir=tmp_path / ".dharma")
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)

    await op.start()
    status = op.status_dict()
    assert status["name"] == "operator"
    assert status["running"] is True
    assert status["interaction_count"] == 0
    assert "graduation" in status
    await op.stop()


@pytest.mark.asyncio
async def test_operator_client_registration(tmp_path):
    op = ResidentOperator(state_dir=tmp_path / ".dharma")
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)

    await op.start()

    q = op.register_client("test_client")
    assert "test_client" in op._connected_clients
    assert q is not None

    op.unregister_client("test_client")
    assert "test_client" not in op._connected_clients

    await op.stop()


@pytest.mark.asyncio
async def test_operator_broadcast(tmp_path):
    op = ResidentOperator(state_dir=tmp_path / ".dharma")
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)

    await op.start()

    q = op.register_client("c1")
    event = OperatorEvent(event_type="notification", content="test")
    await op._broadcast(event)

    received = q.get_nowait()
    assert received.event_type == "notification"
    assert received.content == "test"

    op.unregister_client("c1")
    await op.stop()


def test_operator_port():
    assert OPERATOR_PORT == 8420


# -- Operator proactive scan (smoke test, no real subsystems) --

@pytest.mark.asyncio
async def test_proactive_scan_returns_list(tmp_path):
    op = ResidentOperator(state_dir=tmp_path / ".dharma")
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)
    # No swarm or bridge — scan should return empty gracefully
    events = await op._proactive_scan()
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_codex_operator_resumes_provider_session_and_persists_new_thread_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    op = ResidentOperator(
        state_dir=tmp_path / ".dharma",
        provider_type=ProviderType.CODEX,
        base_system_prompt="You are Codex.",
    )
    op._conversations = _make_mock_store(tmp_path)
    op._graduation = _make_mock_graduation(tmp_path)
    await op.start()
    await op._conversations.create_session(
        "sess-1",
        metadata={"provider_session_id": "thread-123", "provider": "codex"},
    )

    captured: dict[str, str | None] = {}

    class FakeCodexAdapter:
        def __init__(self, workdir=None):
            del workdir

        async def stream(self, request, session_id):
            captured["resume_session_id"] = request.resume_session_id
            yield SessionStart(
                provider_id="codex",
                session_id=session_id,
                model=request.model or "gpt-5.4",
                provider_session_id="thread-456",
            )
            yield TextComplete(
                provider_id="codex",
                session_id=session_id,
                content="resumed output",
                role="assistant",
            )
            yield SessionEnd(
                provider_id="codex",
                session_id=session_id,
                success=True,
            )

        async def close(self):
            return None

    import dharma_swarm.tui.engine.adapters.codex as codex_module

    monkeypatch.setattr(codex_module, "CodexAdapter", FakeCodexAdapter)

    events = [e async for e in op.handle_message("sess-1", "continue", "ui")]
    session = await op._conversations.get_session("sess-1")

    assert captured["resume_session_id"] == "thread-123"
    assert session is not None
    assert session["metadata"]["provider_session_id"] == "thread-456"
    assert any(e.event_type == "done" for e in events)

    await op.stop()


# -- Helpers --

def _make_mock_store(tmp_path):
    from dharma_swarm.conversation_store import ConversationStore
    return ConversationStore(db_path=tmp_path / "test_conv.db")


def _make_mock_graduation(tmp_path):
    from dharma_swarm.graduation_engine import GraduationEngine
    return GraduationEngine(db_path=tmp_path / "test_grad.db")
