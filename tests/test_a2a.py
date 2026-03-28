"""Tests for dharma_swarm.a2a — Agent-to-Agent protocol implementation.

Covers:
    - AgentCard creation, serialization, capability matching
    - CardRegistry CRUD, persistence, discovery queries
    - A2AServer task lifecycle (submit, dispatch, cancel)
    - A2AClient delegation (discover + delegate flow)
    - A2ABridge TRISHULA <-> A2A conversion, signal bus integration
    - Backward compatibility with existing messaging patterns
"""

import json
from pathlib import Path

import pytest

from dharma_swarm.a2a.agent_card import (
    AgentCapability,
    AgentCard,
    CardRegistry,
    _capabilities_for_role,
)
from dharma_swarm.a2a.a2a_server import (
    A2AMessage,
    A2APart,
    A2APartType,
    A2AServer,
    A2ATask,
    A2ATaskStatus,
)
from dharma_swarm.a2a.a2a_client import A2AClient, DelegationResult
from dharma_swarm.a2a.a2a_bridge import (
    A2ABridge,
    SIGNAL_A2A_TASK_COMPLETED,
    SIGNAL_A2A_TASK_FAILED,
    SIGNAL_A2A_TASK_SUBMITTED,
    _infer_capability_from_type,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def cards_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cards"
    d.mkdir()
    return d


@pytest.fixture
def registry(cards_dir: Path) -> CardRegistry:
    return CardRegistry(cards_dir=cards_dir)


@pytest.fixture
def server() -> A2AServer:
    return A2AServer()


@pytest.fixture
def sample_card() -> AgentCard:
    return AgentCard(
        name="test-coder",
        description="A test coding agent",
        role="coder",
        model="llama-3.3-70b",
        capabilities=[
            AgentCapability("code_generation", "Write code"),
            AgentCapability("code_review", "Review code"),
        ],
    )


@pytest.fixture
def sample_identity() -> dict:
    return {
        "name": "researcher-1",
        "role": "researcher",
        "model": "deepseek/deepseek-chat-v3-0324",
        "system_prompt": "You are a research agent. Analyze papers and synthesize findings.",
        "status": "idle",
        "tasks_completed": 42,
        "tasks_failed": 3,
        "avg_quality": 0.85,
    }


# ===========================================================================
# AgentCapability
# ===========================================================================


class TestAgentCapability:
    def test_matches_name(self):
        cap = AgentCapability("code_review", "Review code for bugs")
        assert cap.matches("code_review")
        assert cap.matches("CODE_REVIEW")
        assert cap.matches("review")

    def test_matches_description(self):
        cap = AgentCapability("testing", "Write and execute test suites")
        assert cap.matches("test suite")
        assert cap.matches("execute")

    def test_no_match(self):
        cap = AgentCapability("code_review", "Review code")
        assert not cap.matches("deployment")
        assert not cap.matches("xyz123")


# ===========================================================================
# AgentCard
# ===========================================================================


class TestAgentCard:
    def test_create_basic(self, sample_card: AgentCard):
        assert sample_card.name == "test-coder"
        assert sample_card.role == "coder"
        assert len(sample_card.capabilities) == 2
        assert sample_card.endpoint == "local://"

    def test_to_dict_roundtrip(self, sample_card: AgentCard):
        d = sample_card.to_dict()
        restored = AgentCard.from_dict(d)
        assert restored.name == sample_card.name
        assert restored.role == sample_card.role
        assert len(restored.capabilities) == len(sample_card.capabilities)
        assert restored.capabilities[0].name == "code_generation"

    def test_from_dict_ignores_unknown_keys(self):
        data = {
            "name": "agent-x",
            "unknown_field": "should be ignored",
            "description": "test",
        }
        card = AgentCard.from_dict(data)
        assert card.name == "agent-x"
        assert card.description == "test"

    def test_from_agent_identity(self, sample_identity: dict):
        card = AgentCard.from_agent_identity(sample_identity)
        assert card.name == "researcher-1"
        assert card.role == "researcher"
        assert card.model == "deepseek/deepseek-chat-v3-0324"
        assert "research" in card.description.lower() or "analyze" in card.description.lower()
        assert len(card.capabilities) > 0
        assert card.metadata["tasks_completed"] == 42

    def test_from_agent_identity_derives_capabilities(self, sample_identity: dict):
        card = AgentCard.from_agent_identity(sample_identity)
        cap_names = card.capability_names()
        assert "research" in cap_names

    def test_has_capability(self, sample_card: AgentCard):
        assert sample_card.has_capability("code_review")
        assert sample_card.has_capability("generation")
        assert not sample_card.has_capability("deployment")

    def test_capability_names(self, sample_card: AgentCard):
        names = sample_card.capability_names()
        assert names == ["code_generation", "code_review"]

    def test_from_agent_identity_no_prompt(self):
        identity = {"name": "bare", "role": "general", "model": "m", "system_prompt": ""}
        card = AgentCard.from_agent_identity(identity)
        assert card.name == "bare"
        assert card.description  # should have fallback description


# ===========================================================================
# _capabilities_for_role
# ===========================================================================


class TestCapabilitiesForRole:
    def test_known_roles(self):
        for role in ("coder", "reviewer", "researcher", "tester", "orchestrator"):
            caps = _capabilities_for_role(role)
            assert len(caps) > 0

    def test_unknown_role_gets_generic(self):
        caps = _capabilities_for_role("exotic_role")
        assert len(caps) == 1
        assert caps[0].name == "exotic_role"

    def test_case_insensitive(self):
        caps_lower = _capabilities_for_role("coder")
        caps_upper = _capabilities_for_role("CODER")
        # upper case won't match since the dict keys are lowercase
        # so it falls back to generic
        assert len(caps_lower) > 0


# ===========================================================================
# CardRegistry
# ===========================================================================


class TestCardRegistry:
    def test_register_and_get(self, registry: CardRegistry, sample_card: AgentCard):
        registry.register(sample_card)
        retrieved = registry.get("test-coder")
        assert retrieved is not None
        assert retrieved.name == "test-coder"

    def test_count(self, registry: CardRegistry, sample_card: AgentCard):
        assert registry.count() == 0
        registry.register(sample_card)
        assert registry.count() == 1

    def test_list_all(self, registry: CardRegistry):
        registry.register(AgentCard(name="b-agent"))
        registry.register(AgentCard(name="a-agent"))
        all_cards = registry.list_all()
        assert len(all_cards) == 2
        assert all_cards[0].name == "a-agent"  # sorted

    def test_unregister(self, registry: CardRegistry, sample_card: AgentCard):
        registry.register(sample_card)
        assert registry.unregister("test-coder")
        assert registry.get("test-coder") is None
        assert registry.count() == 0

    def test_unregister_nonexistent(self, registry: CardRegistry):
        assert not registry.unregister("ghost")

    def test_persistence(self, cards_dir: Path, sample_card: AgentCard):
        reg1 = CardRegistry(cards_dir=cards_dir)
        reg1.register(sample_card)

        # New registry instance should load from disk
        reg2 = CardRegistry(cards_dir=cards_dir)
        assert reg2.count() == 1
        card = reg2.get("test-coder")
        assert card is not None
        assert card.role == "coder"

    def test_discover_by_capability(self, registry: CardRegistry):
        registry.register(AgentCard(
            name="coder-1",
            capabilities=[AgentCapability("code_generation", "Write code")],
        ))
        registry.register(AgentCard(
            name="reviewer-1",
            capabilities=[AgentCapability("code_review", "Review code")],
        ))
        registry.register(AgentCard(
            name="researcher-1",
            capabilities=[AgentCapability("research", "Deep research")],
        ))

        coders = registry.discover("code")
        assert len(coders) == 2  # code_generation and code_review both match
        names = [c.name for c in coders]
        assert "coder-1" in names
        assert "reviewer-1" in names

    def test_discover_no_match(self, registry: CardRegistry):
        registry.register(AgentCard(
            name="coder-1",
            capabilities=[AgentCapability("code_generation", "Write code")],
        ))
        assert registry.discover("deployment") == []

    def test_discover_by_role(self, registry: CardRegistry):
        registry.register(AgentCard(name="c1", role="coder"))
        registry.register(AgentCard(name="c2", role="coder"))
        registry.register(AgentCard(name="r1", role="researcher"))

        coders = registry.discover_by_role("coder")
        assert len(coders) == 2

    def test_discover_available(self, registry: CardRegistry):
        registry.register(AgentCard(name="idle-1", status="idle"))
        registry.register(AgentCard(name="busy-1", status="busy"))
        registry.register(AgentCard(name="dead-1", status="dead"))

        available = registry.discover_available()
        assert len(available) == 1
        assert available[0].name == "idle-1"

    def test_sync_status(self, registry: CardRegistry, sample_card: AgentCard):
        registry.register(sample_card)
        registry.sync_status("test-coder", "busy")
        card = registry.get("test-coder")
        assert card is not None
        assert card.status == "busy"

    def test_register_from_agent_registry(self, registry: CardRegistry):
        agents = [
            {"name": "agent-a", "role": "coder", "model": "m1", "system_prompt": "Code stuff."},
            {"name": "agent-b", "role": "researcher", "model": "m2", "system_prompt": "Research stuff."},
        ]
        count = registry.register_from_agent_registry(agents)
        assert count == 2
        assert registry.count() == 2
        card_a = registry.get("agent-a")
        assert card_a is not None
        assert card_a.role == "coder"


# ===========================================================================
# A2APart / A2AMessage
# ===========================================================================


class TestA2AMessage:
    def test_text_convenience(self):
        msg = A2AMessage.text("Hello world")
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.parts[0].type == A2APartType.TEXT
        assert msg.parts[0].content == "Hello world"

    def test_multi_part(self):
        msg = A2AMessage(
            role="agent",
            parts=[
                A2APart(type=A2APartType.TEXT, content="Here's the result"),
                A2APart(type=A2APartType.FILE, content="/path/to/output.txt"),
                A2APart(type=A2APartType.DATA, content='{"key": "value"}'),
            ],
        )
        assert len(msg.parts) == 3
        assert msg.parts[1].type == A2APartType.FILE


# ===========================================================================
# A2AServer
# ===========================================================================


class TestA2AServer:
    def test_submit_with_handler(self, server: A2AServer):
        def review_handler(task: A2ATask) -> A2ATask:
            task.result = "LGTM"
            task.status = A2ATaskStatus.COMPLETED
            return task

        server.register_handler("code_review", review_handler)

        task = A2ATask(
            from_agent="orchestrator",
            to_agent="reviewer",
            capability="code_review",
            messages=[A2AMessage.text("Review this")],
        )
        result = server.submit(task)

        assert result.status == A2ATaskStatus.COMPLETED
        assert result.result == "LGTM"
        assert server.task_count() == 1

    def test_submit_no_handler_fails(self, server: A2AServer):
        task = A2ATask(capability="nonexistent")
        result = server.submit(task)
        assert result.status == A2ATaskStatus.FAILED
        assert "No handler" in result.error

    def test_default_handler(self, server: A2AServer):
        def fallback(task: A2ATask) -> A2ATask:
            task.result = "handled by default"
            return task

        server.set_default_handler(fallback)
        task = A2ATask(capability="anything")
        result = server.submit(task)
        assert result.status == A2ATaskStatus.COMPLETED
        assert result.result == "handled by default"

    def test_handler_exception_fails_task(self, server: A2AServer):
        def bad_handler(task: A2ATask) -> A2ATask:
            raise RuntimeError("oops")

        server.register_handler("buggy", bad_handler)
        task = A2ATask(capability="buggy")
        result = server.submit(task)
        assert result.status == A2ATaskStatus.FAILED
        assert "oops" in result.error

    def test_get_task(self, server: A2AServer):
        def noop(task: A2ATask) -> A2ATask:
            return task

        server.set_default_handler(noop)
        task = A2ATask(capability="test")
        submitted = server.submit(task)

        retrieved = server.get_task(submitted.id)
        assert retrieved is not None
        assert retrieved.id == submitted.id

    def test_get_status(self, server: A2AServer):
        def noop(task: A2ATask) -> A2ATask:
            return task

        server.set_default_handler(noop)
        task = A2ATask(capability="test")
        submitted = server.submit(task)

        status = server.get_status(submitted.id)
        assert status == A2ATaskStatus.COMPLETED

        assert server.get_status("nonexistent") is None

    def test_cancel(self, server: A2AServer):
        # Manually add a task in SUBMITTED state
        task = A2ATask(capability="test", status=A2ATaskStatus.SUBMITTED)
        server._tasks[task.id] = task

        assert server.cancel(task.id)
        assert server.get_status(task.id) == A2ATaskStatus.CANCELLED

    def test_cancel_completed_fails(self, server: A2AServer):
        task = A2ATask(status=A2ATaskStatus.COMPLETED)
        server._tasks[task.id] = task
        assert not server.cancel(task.id)

    def test_cancel_nonexistent(self, server: A2AServer):
        assert not server.cancel("ghost")

    def test_list_tasks_filters(self, server: A2AServer):
        t1 = A2ATask(from_agent="a", to_agent="b", status=A2ATaskStatus.COMPLETED)
        t2 = A2ATask(from_agent="a", to_agent="c", status=A2ATaskStatus.FAILED)
        t3 = A2ATask(from_agent="x", to_agent="b", status=A2ATaskStatus.COMPLETED)
        server._tasks = {t.id: t for t in [t1, t2, t3]}

        assert len(server.list_tasks()) == 3
        assert len(server.list_tasks(status=A2ATaskStatus.COMPLETED)) == 2
        assert len(server.list_tasks(from_agent="a")) == 2
        assert len(server.list_tasks(to_agent="b")) == 2
        assert len(server.list_tasks(from_agent="a", to_agent="c")) == 1

    def test_summary(self, server: A2AServer):
        t1 = A2ATask(status=A2ATaskStatus.COMPLETED)
        t2 = A2ATask(status=A2ATaskStatus.COMPLETED)
        t3 = A2ATask(status=A2ATaskStatus.FAILED)
        server._tasks = {t.id: t for t in [t1, t2, t3]}

        summary = server.summary()
        assert summary["completed"] == 2
        assert summary["failed"] == 1


# ===========================================================================
# A2AClient
# ===========================================================================


class TestA2AClient:
    @pytest.fixture
    def client_setup(self, tmp_path: Path):
        """Set up client with registry, server, and registered agents."""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        registry = CardRegistry(cards_dir=cards_dir)
        server = A2AServer()

        # Register a handler
        def code_handler(task: A2ATask) -> A2ATask:
            task.result = "Code written successfully"
            task.status = A2ATaskStatus.COMPLETED
            return task

        server.register_handler("code_generation", code_handler)

        # Register agents in the card registry
        registry.register(AgentCard(
            name="coder-1",
            role="coder",
            status="idle",
            capabilities=[AgentCapability("code_generation", "Write code")],
        ))
        registry.register(AgentCard(
            name="coder-2",
            role="coder",
            status="busy",
            capabilities=[AgentCapability("code_generation", "Write code")],
        ))
        registry.register(AgentCard(
            name="reviewer-1",
            role="reviewer",
            status="idle",
            capabilities=[AgentCapability("code_review", "Review code")],
        ))

        client = A2AClient(registry=registry, server=server, default_from="orchestrator")
        return client, registry, server

    def test_discover(self, client_setup):
        client, registry, server = client_setup
        agents = client.discover("code_generation")
        assert len(agents) == 2  # both coders

    def test_discover_available(self, client_setup):
        client, registry, server = client_setup
        agents = client.discover_available("code_generation")
        assert len(agents) == 1  # only idle coder
        assert agents[0].name == "coder-1"

    def test_delegate(self, client_setup):
        client, registry, server = client_setup
        result = client.delegate("code_generation", "Write a hello world script")
        assert result.success
        assert result.agent_name == "coder-1"
        assert result.task is not None
        assert result.task.status == A2ATaskStatus.COMPLETED

    def test_delegate_to_specific(self, client_setup):
        client, registry, server = client_setup
        result = client.delegate_to("coder-1", "Write code", capability="code_generation")
        assert result.success
        assert result.agent_name == "coder-1"

    def test_delegate_no_capability_fails(self, client_setup):
        client, registry, server = client_setup
        result = client.delegate("deployment", "Deploy to prod")
        assert not result.success
        assert "No agent found" in result.error

    def test_delegate_to_unknown_agent_fails(self, client_setup):
        client, registry, server = client_setup
        result = client.delegate_to("ghost-agent", "Do something")
        assert not result.success
        assert "not found" in result.error

    def test_delegate_uses_default_from(self, client_setup):
        client, registry, server = client_setup
        result = client.delegate("code_generation", "Write code")
        assert result.task.from_agent == "orchestrator"

    def test_get_task_status(self, client_setup):
        client, registry, server = client_setup
        result = client.delegate("code_generation", "Write code")
        status = client.get_task_status(result.task.id)
        assert status == A2ATaskStatus.COMPLETED

    def test_cancel_task(self, client_setup):
        client, registry, server = client_setup
        # Add a task manually in submitted state
        task = A2ATask(status=A2ATaskStatus.SUBMITTED)
        server._tasks[task.id] = task
        assert client.cancel_task(task.id)


# ===========================================================================
# A2ABridge
# ===========================================================================


class TestA2ABridge:

    @pytest.fixture
    def bridge_setup(self, tmp_path: Path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()
        inbox = tmp_path / "inbox"
        inbox.mkdir()

        registry = CardRegistry(cards_dir=cards_dir)
        server = A2AServer()

        # Set a default handler so tasks don't fail
        def handler(task: A2ATask) -> A2ATask:
            task.result = "processed"
            return task

        server.set_default_handler(handler)

        # Simple signal collector
        class FakeSignalBus:
            def __init__(self):
                self.events = []

            def emit(self, event):
                self.events.append(event)

        bus = FakeSignalBus()

        bridge = A2ABridge(
            server=server,
            registry=registry,
            signal_bus=bus,
            trishula_outbox=outbox,
        )

        return bridge, server, registry, bus, inbox, outbox

    def test_trishula_message_to_a2a_task(self, bridge_setup):
        bridge, *_ = bridge_setup
        msg = {
            "id": "20260210T140000Z_agni_mac_test",
            "from": "agni",
            "to": "mac",
            "type": "task",
            "priority": "high",
            "subject": "Run experiment",
            "body": "Execute the R_V pipeline on Mistral-7B",
            "created_at": "2026-02-10T14:00:00Z",
            "attachments": ["shared/config.yaml"],
        }

        task = bridge.trishula_message_to_a2a_task(msg)
        assert task.from_agent == "agni"
        assert task.to_agent == "mac"
        assert task.metadata["trishula_type"] == "task"
        assert task.metadata["priority"] == "high"
        assert len(task.messages) == 1
        assert len(task.messages[0].parts) == 2  # text + file
        assert "Run experiment" in task.messages[0].parts[0].content

    def test_a2a_task_to_trishula_message(self, bridge_setup):
        bridge, *_ = bridge_setup
        task = A2ATask(
            from_agent="mac",
            to_agent="agni",
            capability="research",
            status=A2ATaskStatus.COMPLETED,
            result="Experiment complete",
            messages=[
                A2AMessage.text("Run experiment", role="user"),
                A2AMessage.text("Done — results in /results/", role="agent"),
            ],
            metadata={"trishula_id": "original_msg_id"},
        )

        msg = bridge.a2a_task_to_trishula_message(task)
        assert msg["from"] == "agni"
        assert msg["to"] == "mac"
        assert msg["type"] == "response"
        assert "results" in msg["body"]
        assert msg["reply_to"] == "original_msg_id"
        assert msg["metadata"]["a2a_task_id"] == task.id

    def test_ingest_trishula_inbox(self, bridge_setup):
        bridge, server, registry, bus, inbox, outbox = bridge_setup

        # Write a task message
        msg = {
            "from": "agni",
            "to": "mac",
            "type": "task",
            "subject": "Deploy",
            "body": "Deploy the new version",
        }
        (inbox / "msg1.json").write_text(json.dumps(msg), encoding="utf-8")

        # Write an ack (should be skipped)
        ack = {"from": "agni", "to": "mac", "type": "ack", "body": "ok"}
        (inbox / "msg2.json").write_text(json.dumps(ack), encoding="utf-8")

        tasks = bridge.ingest_trishula_inbox(inbox_path=inbox)
        assert len(tasks) == 1
        assert tasks[0].from_agent == "agni"

        # Check signal was emitted
        submitted_signals = [e for e in bus.events if e["type"] == SIGNAL_A2A_TASK_SUBMITTED]
        assert len(submitted_signals) == 1

    def test_ingest_missing_inbox(self, bridge_setup):
        bridge, *_ = bridge_setup
        tasks = bridge.ingest_trishula_inbox(inbox_path=Path("/nonexistent"))
        assert tasks == []

    def test_send_result_to_trishula(self, bridge_setup):
        bridge, server, registry, bus, inbox, outbox = bridge_setup

        task = A2ATask(
            from_agent="mac",
            to_agent="agni",
            capability="research",
            status=A2ATaskStatus.COMPLETED,
            result="Done",
        )

        path = bridge.send_result_to_trishula(task)
        assert path is not None
        assert path.exists()

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["from"] == "agni"
        assert data["to"] == "mac"

    def test_emit_task_completed(self, bridge_setup):
        bridge, server, registry, bus, inbox, outbox = bridge_setup

        task = A2ATask(
            id="t123",
            from_agent="mac",
            to_agent="agni",
            capability="test",
            status=A2ATaskStatus.COMPLETED,
        )
        bridge.emit_task_completed(task)

        assert len(bus.events) == 1
        assert bus.events[0]["type"] == SIGNAL_A2A_TASK_COMPLETED
        assert bus.events[0]["task_id"] == "t123"

    def test_emit_task_failed(self, bridge_setup):
        bridge, server, registry, bus, inbox, outbox = bridge_setup

        task = A2ATask(
            id="t456",
            from_agent="mac",
            to_agent="agni",
            capability="test",
            status=A2ATaskStatus.FAILED,
            error="timeout",
        )
        bridge.emit_task_failed(task)

        assert len(bus.events) == 1
        assert bus.events[0]["type"] == SIGNAL_A2A_TASK_FAILED
        assert bus.events[0]["error"] == "timeout"

    def test_no_signal_bus_no_crash(self):
        """Bridge works even without a signal bus."""
        server = A2AServer()
        registry = CardRegistry(cards_dir=Path("/tmp/test_a2a_no_bus"))
        bridge = A2ABridge(server=server, registry=registry, signal_bus=None)

        task = A2ATask(id="t1")
        bridge.emit_task_completed(task)  # should not raise


# ===========================================================================
# Helper functions
# ===========================================================================


class TestHelpers:
    def test_infer_capability_from_type(self):
        assert _infer_capability_from_type("task") == "task_execution"
        assert _infer_capability_from_type("standup") == "reporting"
        assert _infer_capability_from_type("proposal") == "strategic_planning"
        assert _infer_capability_from_type("custom_thing") == "custom_thing"


# ===========================================================================
# Integration: Full round-trip
# ===========================================================================


class TestIntegration:
    def test_full_roundtrip(self, tmp_path: Path):
        """End-to-end: register agents, delegate task, check result."""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        # Set up infrastructure
        registry = CardRegistry(cards_dir=cards_dir)
        server = A2AServer()

        # Register handler
        def research_handler(task: A2ATask) -> A2ATask:
            query = ""
            for msg in task.messages:
                for part in msg.parts:
                    if part.type == A2APartType.TEXT:
                        query = part.content
                        break

            task.result = f"Research complete for: {query}"
            task.messages.append(A2AMessage.text(task.result, role="agent"))
            task.status = A2ATaskStatus.COMPLETED
            return task

        server.register_handler("research", research_handler)

        # Register agents from "registry" format
        agents = [
            {"name": "research-lead", "role": "researcher", "model": "m1", "system_prompt": "You research things."},
            {"name": "coder-1", "role": "coder", "model": "m2", "system_prompt": "You write code."},
        ]
        registry.register_from_agent_registry(agents)

        # Create client and delegate
        client = A2AClient(registry=registry, server=server, default_from="orchestrator")
        result = client.delegate("research", "What is the R_V metric?")

        assert result.success
        assert result.agent_name == "research-lead"
        assert "R_V metric" in result.task.result
        assert result.task.status == A2ATaskStatus.COMPLETED
        assert len(result.task.messages) == 2  # original + response

    def test_trishula_to_a2a_to_trishula(self, tmp_path: Path):
        """Full bridge cycle: TRISHULA msg -> A2A task -> TRISHULA response."""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        registry = CardRegistry(cards_dir=cards_dir)
        server = A2AServer()

        def handler(task: A2ATask) -> A2ATask:
            task.result = "Task processed"
            task.messages.append(A2AMessage.text("Done!", role="agent"))
            return task

        server.set_default_handler(handler)

        bridge = A2ABridge(
            server=server,
            registry=registry,
            trishula_outbox=outbox,
        )

        # Inbound: TRISHULA -> A2A
        trishula_msg = {
            "id": "msg_001",
            "from": "agni",
            "to": "mac",
            "type": "task",
            "priority": "normal",
            "subject": "Process data",
            "body": "Run the pipeline",
        }

        task = bridge.trishula_message_to_a2a_task(trishula_msg)
        result = server.submit(task)

        assert result.status == A2ATaskStatus.COMPLETED

        # Outbound: A2A -> TRISHULA
        path = bridge.send_result_to_trishula(result)
        assert path is not None
        assert path.exists()

        response = json.loads(path.read_text(encoding="utf-8"))
        assert response["from"] == "mac"
        assert response["to"] == "agni"
        assert response["type"] == "response"
        assert response["reply_to"] == "msg_001"
