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
    related_traces: list[str] = Field(default_factory=list)


class RuntimeHealthOut(BaseModel):
    status: str = "unknown"
    snapshot_status: str = "missing"
    daemon_pid: int | None = None
    live_daemon_pid: int | None = None
    daemon_pid_mismatch: bool = False
    operator_pid: int | None = None
    last_tick: str | None = None
    agent_count: int | None = None
    task_count: int | None = None
    anomaly_count: int | None = None
    source: str | None = None
    maintenance_summary: str = "runtime snapshot missing"
    runtime_warnings: list[str] = Field(default_factory=list)


class HealthOut(BaseModel):
    overall_status: str = "unknown"
    agent_health: list[AgentHealthOut] = Field(default_factory=list)
    anomalies: list[AnomalyOut] = Field(default_factory=list)
    total_traces: int = 0
    traces_last_hour: int = 0
    failure_rate: float = 0.0
    mean_fitness: float | None = None
    runtime: RuntimeHealthOut | None = None


class HealthResponse(ApiResponse):
    data: HealthOut | None = None


class AnomalyListResponse(ApiResponse):
    data: list[AnomalyOut] = Field(default_factory=list)


# ── Agents ────────────────────────────────────────────────────────

class AgentOut(BaseModel):
    id: str
    name: str
    agent_slug: str = ""
    display_name: str = ""
    role: str
    status: str = "idle"
    current_task: str | None = None
    started_at: str | None = None
    last_heartbeat: str | None = None
    turns_used: int = 0
    tasks_completed: int = 0
    provider: str = ""
    model: str = ""
    model_label: str = ""
    model_key: str = ""
    error: str | None = None


class SpawnAgentRequest(BaseModel):
    name: str
    role: str = "general"
    provider: str | None = None
    model: str | None = None


class AgentConfigOut(BaseModel):
    display_name: str | None = None
    role: str | None = None
    provider: str | None = None
    model: str | None = None
    thread: str | None = None
    tier: str | None = None
    strengths: list[str] = Field(default_factory=list)


class AgentTraceOut(BaseModel):
    id: str
    timestamp: str
    action: str
    state: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentHealthStatsOut(BaseModel):
    total_actions: int = 0
    failures: int = 0
    success_rate: float = 1.0
    last_seen: str | None = None


class AssignedTaskOut(BaseModel):
    id: str
    title: str
    status: str = "pending"
    priority: str = "normal"
    created_at: str = ""
    result: str | None = None


class AgentCostOut(BaseModel):
    daily_spent: float = 0.0
    weekly_spent: float = 0.0
    budget_status: str = "OK"


class CoreFileOut(BaseModel):
    file_path: str
    salience: float = 0.0
    count: int = 0
    last_touch: str | None = None


class AvailableModelOut(BaseModel):
    model_id: str
    label: str
    tier: str | None = None


class AgentProviderStatusOut(BaseModel):
    provider: str
    available: bool = False


class AgentDetailOut(BaseModel):
    agent: AgentOut
    config: AgentConfigOut = Field(default_factory=AgentConfigOut)
    recent_traces: list[AgentTraceOut] = Field(default_factory=list)
    health_stats: AgentHealthStatsOut = Field(default_factory=AgentHealthStatsOut)
    assigned_tasks: list[AssignedTaskOut] = Field(default_factory=list)
    fitness_history: list[dict[str, Any]] = Field(default_factory=list)
    cost: AgentCostOut = Field(default_factory=AgentCostOut)
    core_files: list[CoreFileOut] = Field(default_factory=list)
    available_models: list[AvailableModelOut] = Field(default_factory=list)
    available_roles: list[str] = Field(default_factory=list)
    provider_status: list[AgentProviderStatusOut] = Field(default_factory=list)
    task_history: list[dict[str, Any]] = Field(default_factory=list)


class AgentResponse(ApiResponse):
    data: AgentOut | None = None


class AgentListResponse(ApiResponse):
    data: list[AgentOut] = Field(default_factory=list)


class AgentDetailResponse(ApiResponse):
    data: AgentDetailOut | None = None


class AgentStopOut(BaseModel):
    stopped: str


class AgentStopResponse(ApiResponse):
    data: AgentStopOut | None = None


class AgentsSyncOut(BaseModel):
    count: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)


class AgentsSyncResponse(ApiResponse):
    data: AgentsSyncOut | None = None


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
    properties: list[PropertyOut] = Field(default_factory=list)
    links: list[LinkDefOut] = Field(default_factory=list)
    actions: list[ActionDefOut] = Field(default_factory=list)
    security_level: str = "internal"
    telos_alignment: float = 0.0
    shakti: str = ""


class OntologyGraphNodeDataOut(BaseModel):
    label: str
    description: str = ""
    propertyCount: int = 0
    actionCount: int = 0
    linkCount: int = 0
    runtimeCount: int = 0
    shakti: str = ""
    telos: float = 0.0
    icon: str = ""
    zone: str = ""


class OntologyGraphNodeOut(BaseModel):
    id: str
    type: str
    data: OntologyGraphNodeDataOut
    position: dict[str, int]


class OntologyGraphEdgeDataOut(BaseModel):
    cardinality: str = ""


class OntologyGraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    label: str
    data: OntologyGraphEdgeDataOut


class OntologyGraphOut(BaseModel):
    nodes: list[OntologyGraphNodeOut] = Field(default_factory=list)
    edges: list[OntologyGraphEdgeOut] = Field(default_factory=list)


class OntologyStatsOut(BaseModel):
    registered_types: int = 0
    registered_links: int = 0
    registered_actions: int = 0
    total_objects: int = 0
    total_links: int = 0
    action_log_entries: int = 0
    objects_by_type: dict[str, int] = Field(default_factory=dict)
    type_names: list[str] = Field(default_factory=list)


class OntologyObjectOut(BaseModel):
    id: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_by: str = ""
    created_at: str
    updated_at: str
    version: int = 1
    name: str | None = None
    display_name: str | None = None
    agent_slug: str | None = None
    runtime_agent_id: str | None = None
    kaizenops_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    status: str | None = None
    telos_alignment: float | None = None
    witness_quality: float | None = None
    shakti_energy: float | None = None
    tasks_completed: int | None = None
    avg_quality: float | None = None
    last_active: str | None = None
    context: str | None = None


class OntologyTypeListResponse(ApiResponse):
    data: list[OntologyTypeOut] = Field(default_factory=list)


class OntologyDetailResponse(ApiResponse):
    data: OntologyDetailOut | None = None


class OntologyGraphResponse(ApiResponse):
    data: OntologyGraphOut | None = None


class OntologyStatsResponse(ApiResponse):
    data: OntologyStatsOut | None = None


class OntologyObjectListResponse(ApiResponse):
    data: list[OntologyObjectOut] = Field(default_factory=list)


class OntologyObjectResponse(ApiResponse):
    data: OntologyObjectOut | None = None


# ── Lineage ───────────────────────────────────────────────────────

class LineageEdgeOut(BaseModel):
    edge_id: str
    task_id: str
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    agent: str = ""
    operation: str = ""
    timestamp: str = ""


class ProvenanceOut(BaseModel):
    artifact_id: str
    chain: list[LineageEdgeOut] = Field(default_factory=list)
    root_sources: list[str] = Field(default_factory=list)
    depth: int = 0


class ImpactOut(BaseModel):
    root_artifact: str
    affected_artifacts: list[str] = Field(default_factory=list)
    affected_tasks: list[str] = Field(default_factory=list)
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
    connections: list[str] = Field(default_factory=list)
    semantic_type: str = ""
    pillar_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    impact_score: float = 0.0


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


class SwarmOverviewResponse(ApiResponse):
    data: SwarmOverview | None = None


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
