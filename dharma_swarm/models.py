"""Pydantic data models for DHARMA SWARM.

All shared types, enums, and data structures used across the swarm system.
Every module imports from here — this is the schema contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# === Enums ===

class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    STARTING = "starting"
    STOPPING = "stopping"
    DEAD = "dead"


class AgentRole(str, Enum):
    CODER = "coder"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    TESTER = "tester"
    ORCHESTRATOR = "orchestrator"
    GENERAL = "general"
    # PSMV cognitive roles (from 5-role agent briefings)
    CARTOGRAPHER = "cartographer"
    ARCHEOLOGIST = "archeologist"
    SURGEON = "surgeon"
    ARCHITECT = "architect"
    VALIDATOR = "validator"


class MessagePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class GateTier(str, Enum):
    A = "A"  # Absolute block
    B = "B"  # Strong block
    C = "C"  # Advisory


class GateResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class GateDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


class TopologyType(str, Enum):
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"
    PIPELINE = "pipeline"
    BROADCAST = "broadcast"


class MemoryLayer(str, Enum):
    IMMEDIATE = "immediate"
    SESSION = "session"
    DEVELOPMENT = "development"
    WITNESS = "witness"
    META = "meta"


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    LOCAL = "local"


# === Utility ===

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


# === Core Models ===

class Task(BaseModel):
    """A unit of work in the swarm."""
    id: str = Field(default_factory=_new_id)
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    assigned_to: Optional[str] = None
    created_by: str = "system"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    depends_on: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    result: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Configuration for spawning an agent."""
    id: str = Field(default_factory=_new_id)
    name: str
    role: AgentRole = AgentRole.GENERAL
    provider: ProviderType = ProviderType.ANTHROPIC
    model: str = "claude-sonnet-4-20250514"
    system_prompt: str = ""
    max_turns: int = 50
    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    """Runtime state of an agent."""
    id: str
    name: str
    role: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    turns_used: int = 0
    tasks_completed: int = 0
    error: Optional[str] = None


class Message(BaseModel):
    """A message between agents."""
    id: str = Field(default_factory=_new_id)
    from_agent: str
    to_agent: str
    subject: Optional[str] = None
    body: str
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.UNREAD
    created_at: datetime = Field(default_factory=_utc_now)
    read_at: Optional[datetime] = None
    reply_to: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GateCheckResult(BaseModel):
    """Result of running telos gates on an action."""
    decision: GateDecision
    reason: str
    gate_results: dict[str, tuple[GateResult, str]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utc_now)


class MemoryEntry(BaseModel):
    """An entry in the strange loop memory system."""
    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    layer: MemoryLayer
    content: str
    source: str = "agent"
    tags: list[str] = Field(default_factory=list)
    development_marker: bool = False
    witness_quality: float = 0.5


class SwarmState(BaseModel):
    """Overall swarm status snapshot."""
    agents: list[AgentState] = Field(default_factory=list)
    tasks_pending: int = 0
    tasks_running: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    uptime_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)


class TaskDispatch(BaseModel):
    """A task assignment from orchestrator to agent."""
    task_id: str
    agent_id: str
    topology: TopologyType = TopologyType.FAN_OUT
    timeout_seconds: float = 300.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxResult(BaseModel):
    """Result from running code in a sandbox."""
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False


class LLMRequest(BaseModel):
    """A request to an LLM provider."""
    model: str
    messages: list[dict[str, str]]
    system: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    tools: list[dict[str, Any]] = Field(default_factory=list)


class LLMResponse(BaseModel):
    """Response from an LLM provider."""
    content: str
    model: str
    usage: dict[str, int] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: Optional[str] = None
