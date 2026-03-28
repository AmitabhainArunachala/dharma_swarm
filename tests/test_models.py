"""Tests for dharma_swarm.models — Pydantic data models."""

from datetime import datetime, timezone

from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentState,
    AgentStatus,
    GateCheckResult,
    GateDecision,
    GateResult,
    LLMRequest,
    LLMResponse,
    MemoryEntry,
    MemoryLayer,
    Message,
    MessagePriority,
    SandboxResult,
    SwarmState,
    Task,
    TaskDispatch,
    TaskPriority,
    TaskStatus,
    TopologyType,
    _new_id,
    _utc_now,
)


def test_new_id_unique():
    ids = {_new_id() for _ in range(100)}
    assert len(ids) == 100


def test_utc_now():
    now = _utc_now()
    assert now.tzinfo == timezone.utc


def test_task_defaults():
    t = Task(title="Do something")
    assert t.status == TaskStatus.PENDING
    assert t.priority == TaskPriority.NORMAL
    assert t.assigned_to is None
    assert len(t.id) == 16
    assert t.depends_on == []


def test_task_json_roundtrip():
    t = Task(title="Test", description="A test task")
    data = t.model_dump_json()
    t2 = Task.model_validate_json(data)
    assert t2.title == "Test"
    assert t2.id == t.id


def test_agent_config_defaults():
    c = AgentConfig(name="worker")
    assert c.role == AgentRole.GENERAL
    assert c.max_turns == 50
    assert len(c.id) == 16


def test_agent_state():
    s = AgentState(id="abc123", name="test", role=AgentRole.CODER)
    assert s.status == AgentStatus.IDLE
    assert s.tasks_completed == 0


def test_message_defaults():
    m = Message(from_agent="a", to_agent="b", body="hello")
    assert m.priority == MessagePriority.NORMAL
    assert m.status.value == "unread"


def test_gate_check_result():
    r = GateCheckResult(
        decision=GateDecision.ALLOW,
        reason="All passed",
        gate_results={"AHIMSA": (GateResult.PASS, "")},
    )
    assert r.decision == GateDecision.ALLOW


def test_memory_entry():
    e = MemoryEntry(layer=MemoryLayer.WITNESS, content="noticed a shift")
    assert e.witness_quality == 0.5
    assert not e.development_marker


def test_swarm_state():
    s = SwarmState()
    assert s.tasks_pending == 0
    assert s.agents == []


def test_task_dispatch():
    td = TaskDispatch(task_id="t1", agent_id="a1")
    assert td.topology == TopologyType.FAN_OUT
    assert td.timeout_seconds == 300.0


def test_sandbox_result():
    sr = SandboxResult(exit_code=0, stdout="ok")
    assert not sr.timed_out


def test_llm_request():
    r = LLMRequest(model="test", messages=[{"role": "user", "content": "hi"}])
    assert r.max_tokens == 4096


def test_llm_response():
    r = LLMResponse(content="hello", model="test")
    assert r.tool_calls == []


def test_all_enums():
    assert len(TaskStatus) == 6
    assert len(AgentRole) == 19  # 6 base + 6 PSMV cognitive + 6 constitutional + WORKER
    assert len(MemoryLayer) == 5
    assert len(TopologyType) == 4


def test_provider_type_has_claude_code():
    from dharma_swarm.models import ProviderType
    assert ProviderType.CLAUDE_CODE == "claude_code"
    assert ProviderType.GROQ == "groq"
    assert ProviderType.SILICONFLOW == "siliconflow"
    assert ProviderType.TOGETHER == "together"
    assert ProviderType.FIREWORKS == "fireworks"
    assert ProviderType.SAMBANOVA == "sambanova"
    assert ProviderType.MISTRAL == "mistral"
    assert ProviderType.CHUTES == "chutes"
    assert len(ProviderType) >= 18
