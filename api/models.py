"""Pydantic API models for dashboard serialization."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Generic Response ──────────────────────────────────────────────

class ApiResponse(BaseModel):
    status: str = "ok"
    data: Any = None
    error: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=None))


# ── Health ────────────────────────────────────────────────────────

class AgentHealthOut(BaseModel):
    agent_name: str
    total_actions: int = 0
    failures: int = 0
    success_rate: float = 1.0
    last_seen: str | None = None
    status: str = "unknown"


class AnomalyOut(BaseModel):
    id: str
    detected_at: str
    anomaly_type: str
    severity: str
    description: str
    related_traces: list[str] = []


class HealthOut(BaseModel):
    overall_status: str = "unknown"
    agent_health: list[AgentHealthOut] = []
    anomalies: list[AnomalyOut] = []
    total_traces: int = 0
    traces_last_hour: int = 0
    failure_rate: float = 0.0
    mean_fitness: float | None = None


# ── Agents ────────────────────────────────────────────────────────

class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    status: str = "idle"
    current_task: str | None = None
    started_at: str | None = None
    last_heartbeat: str | None = None
    turns_used: int = 0
    tasks_completed: int = 0
    provider: str = ""
    model: str = ""
    error: str | None = None


class SpawnAgentRequest(BaseModel):
    name: str
    role: str = "general"
    provider: str | None = None
    model: str | None = None


# ── Tasks ─────────────────────────────────────────────────────────

class TaskOut(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str = "pending"
    priority: str = "normal"
    assigned_to: str | None = None
    created_by: str = "system"
    created_at: str = ""
    updated_at: str = ""
    result: str | None = None


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"
    assigned_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Evolution ─────────────────────────────────────────────────────

class FitnessOut(BaseModel):
    correctness: float = 0.0
    dharmic_alignment: float = 0.0
    performance: float = 0.0
    utilization: float = 0.0
    economic_value: float = 0.0
    elegance: float = 0.0
    efficiency: float = 0.0
    safety: float = 0.0
    weighted: float = 0.0


class ArchiveEntryOut(BaseModel):
    id: str
    timestamp: str
    parent_id: str | None = None
    component: str = ""
    change_type: str = ""
    description: str = ""
    fitness: FitnessOut
    status: str = "proposed"
    gates_passed: list[str] = []
    gates_failed: list[str] = []
    agent_id: str = ""
    model: str = ""


# ── Traces ────────────────────────────────────────────────────────

class TraceOut(BaseModel):
    id: str
    timestamp: str
    agent: str
    action: str
    state: str = "active"
    parent_id: str | None = None
    metadata: dict[str, Any] = {}


# ── Ontology ──────────────────────────────────────────────────────

class OntologyTypeOut(BaseModel):
    name: str
    description: str = ""
    telos_alignment: float = 0.0
    shakti: str = ""
    property_count: int = 0
    link_count: int = 0
    action_count: int = 0
    icon: str = ""


class PropertyOut(BaseModel):
    name: str
    property_type: str
    required: bool = False
    description: str = ""
    searchable: bool = False


class LinkDefOut(BaseModel):
    name: str
    source_type: str
    target_type: str
    cardinality: str = "N:1"
    description: str = ""


class ActionDefOut(BaseModel):
    name: str
    description: str = ""
    requires_approval: bool = False
    telos_gates: list[str] = []
    is_deterministic: bool = True


class OntologyDetailOut(BaseModel):
    name: str
    description: str = ""
    properties: list[PropertyOut] = []
    links: list[LinkDefOut] = []
    actions: list[ActionDefOut] = []
    security_level: str = "internal"
    telos_alignment: float = 0.0
    shakti: str = ""


# ── Lineage ───────────────────────────────────────────────────────

class LineageEdgeOut(BaseModel):
    edge_id: str
    task_id: str
    input_artifacts: list[str] = []
    output_artifacts: list[str] = []
    agent: str = ""
    operation: str = ""
    timestamp: str = ""


class ProvenanceOut(BaseModel):
    artifact_id: str
    chain: list[LineageEdgeOut] = []
    root_sources: list[str] = []
    depth: int = 0


class ImpactOut(BaseModel):
    root_artifact: str
    affected_artifacts: list[str] = []
    affected_tasks: list[str] = []
    depth: int = 0
    total_descendants: int = 0


# ── Stigmergy ────────────────────────────────────────────────────

class StigmergyMarkOut(BaseModel):
    id: str
    timestamp: str
    agent: str
    file_path: str
    action: str
    observation: str = ""
    salience: float = 0.5
    connections: list[str] = []


class HeatmapCell(BaseModel):
    file_path: str
    hour: int
    count: int
    avg_salience: float = 0.5


# ── Commands ──────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class EvolveRequest(BaseModel):
    component: str = "default"
    generations: int = 5


# ── Swarm Overview ────────────────────────────────────────────────

class SwarmOverview(BaseModel):
    agent_count: int = 0
    task_count: int = 0
    tasks_pending: int = 0
    tasks_running: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    mean_fitness: float = 0.0
    uptime_seconds: float = 0.0
    health_status: str = "unknown"
    stigmergy_density: int = 0
    evolution_entries: int = 0


# ── Truth Modules ────────────────────────────────────────────────

class ModuleProcessOut(BaseModel):
    pid: int
    live: bool = False
    source: str = ""
    command: str | None = None
    observed_paths: list[str] = Field(default_factory=list)


class ModuleProjectOut(BaseModel):
    label: str
    path: str
    exists: bool = False
    kind: str = "project"
    modified_at: str | None = None


class ModuleWireOut(BaseModel):
    direction: str
    target: str
    detail: str = ""


class ModuleHistoryOut(BaseModel):
    timestamp: str | None = None
    title: str
    detail: str = ""
    source: str = ""
    status: str = "info"


class ModuleSalientOut(BaseModel):
    kind: str = "file"
    title: str
    detail: str = ""
    path: str | None = None
    timestamp: str | None = None
    reason: str = ""
    score: float = 0.0


class ModuleTruthOut(BaseModel):
    id: str
    name: str
    status: str = "unknown"
    live: bool = False
    summary: str = ""
    status_reason: str = ""
    last_activity: str | None = None
    metrics: dict[str, str] = Field(default_factory=dict)
    processes: list[ModuleProcessOut] = Field(default_factory=list)
    projects: list[ModuleProjectOut] = Field(default_factory=list)
    wiring: list[ModuleWireOut] = Field(default_factory=list)
    history: list[ModuleHistoryOut] = Field(default_factory=list)
    salient: list[ModuleSalientOut] = Field(default_factory=list)
