"""REST API Gateway — Programmatic access to dharma_swarm.

Exposes the ontology, logic layer, lineage, guardrails, and workflow
systems via FastAPI.  This is the OSDK equivalent — typed clients
can talk to dharma_swarm over HTTP instead of importing Python.

Routes:
  POST   /api/tasks              Create a task
  GET    /api/tasks/{id}         Get task by ID
  GET    /api/agents             List active agents
  GET    /api/ontology           Browse typed objects
  GET    /api/ontology/{type}    Describe a specific type
  GET    /api/ontology/objects   List all objects
  GET    /api/lineage/{id}       Trace artifact lineage
  GET    /api/lineage/{id}/impact  Impact analysis
  POST   /api/workflows/{name}  Execute a named workflow
  GET    /api/workflows          List registered workflows
  GET    /api/health             Swarm health + stats
  GET    /api/schema             Full ontology schema for LLM context (OAG)

Usage:
  from dharma_swarm.api import create_app
  app = create_app()
  # uvicorn dharma_swarm.api:app --port 8000

Integration:
  ontology.py     — OntologyRegistry for type/object/link/action CRUD
  lineage.py      — LineageGraph for provenance queries
  workflow.py     — Compile and execute workflows
  guardrails.py   — GuardrailRunner wraps mutating endpoints
  models.py       — Task, AgentConfig for swarm operations
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REQUEST/RESPONSE MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"
    assigned_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateObjectRequest(BaseModel):
    type_name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "api"


class ExecuteActionRequest(BaseModel):
    object_type: str
    action_name: str
    object_id: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    executed_by: str = "api"


class WorkflowExecuteRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel):
    status: str = "ok"
    data: Any = None
    error: str = ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APP FACTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def create_app(
    registry: Any | None = None,
    lineage_graph: Any | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        registry: OntologyRegistry instance.  If None, creates default.
        lineage_graph: LineageGraph instance.  If None, creates default.

    Returns:
        Configured FastAPI app.
    """
    app = FastAPI(
        title="dharma_swarm API",
        description="Palantir-grade typed ontology API for consciousness research",
        version="0.1.0",
    )

    # Lazy-initialize dependencies
    _state: dict[str, Any] = {}

    def _get_registry():
        if "registry" not in _state:
            if registry is not None:
                _state["registry"] = registry
            else:
                from dharma_swarm.ontology_runtime import get_shared_registry

                _state["registry"] = get_shared_registry()
        return _state["registry"]

    def _persist_registry() -> None:
        if registry is None:
            from dharma_swarm.ontology_runtime import persist_shared_registry

            persist_shared_registry(_get_registry())

    def _get_lineage():
        if "lineage" not in _state:
            if lineage_graph is not None:
                _state["lineage"] = lineage_graph
            else:
                from dharma_swarm.lineage import LineageGraph
                _state["lineage"] = LineageGraph()
        return _state["lineage"]

    # ── Health ────────────────────────────────────────────────────────

    @app.get("/api/health")
    async def health() -> ApiResponse:
        reg = _get_registry()
        stats = reg.stats()
        lineage_stats = _get_lineage().stats()
        return ApiResponse(data={
            "ontology": stats,
            "lineage": lineage_stats,
            "status": "healthy",
        })

    # ── Ontology: Types ──────────────────────────────────────────────

    @app.get("/api/ontology")
    async def list_types() -> ApiResponse:
        reg = _get_registry()
        types = [
            {
                "name": t.name,
                "description": t.description,
                "telos_alignment": t.telos_alignment,
                "shakti": t.shakti_energy.value,
                "property_count": len(t.properties),
            }
            for t in reg.get_types()
        ]
        return ApiResponse(data=types)

    @app.get("/api/schema")
    async def full_schema() -> ApiResponse:
        """Full ontology schema for LLM context injection (OAG)."""
        reg = _get_registry()
        return ApiResponse(data={
            "schema": reg.schema_for_llm(),
            "graph": reg.graph_summary(),
            "stats": reg.stats(),
        })

    # ── Ontology: Objects ────────────────────────────────────────────
    # NOTE: These must be registered BEFORE /api/ontology/{type_name}
    # so FastAPI doesn't match "objects" as a type_name parameter.

    @app.get("/api/ontology/objects")
    async def list_objects(type_name: str | None = None) -> ApiResponse:
        reg = _get_registry()
        if type_name:
            objs = reg.get_objects_by_type(type_name)
        else:
            objs = list(reg._objects.values())
        return ApiResponse(data=[
            {
                "id": o.id,
                "type": o.type_name,
                "properties": o.properties,
                "created_by": o.created_by,
                "version": o.version,
            }
            for o in objs
        ])

    @app.post("/api/ontology/objects")
    async def create_object(req: CreateObjectRequest) -> ApiResponse:
        reg = _get_registry()
        obj, errors = reg.create_object(
            type_name=req.type_name,
            properties=req.properties,
            created_by=req.created_by,
        )
        if errors:
            raise HTTPException(400, "; ".join(errors))
        _persist_registry()
        return ApiResponse(data={
            "id": obj.id,
            "type": obj.type_name,
            "properties": obj.properties,
        })

    @app.get("/api/ontology/objects/{obj_id}")
    async def get_object(obj_id: str) -> ApiResponse:
        reg = _get_registry()
        obj = reg.get_object(obj_id)
        if obj is None:
            raise HTTPException(404, f"Object not found: {obj_id}")
        return ApiResponse(data={
            "id": obj.id,
            "type": obj.type_name,
            "properties": obj.properties,
            "context": reg.object_context_for_llm(obj_id),
        })

    # ── Ontology: Actions ────────────────────────────────────────────

    @app.post("/api/ontology/actions")
    async def execute_action(req: ExecuteActionRequest) -> ApiResponse:
        reg = _get_registry()
        execution = reg.execute_action(
            object_type=req.object_type,
            action_name=req.action_name,
            object_id=req.object_id,
            params=req.params,
            executed_by=req.executed_by,
        )
        _persist_registry()
        if execution.result in ("failed", "blocked"):
            raise HTTPException(400, execution.error)
        return ApiResponse(data={
            "result": execution.result,
            "action": execution.action_name,
            "gate_results": execution.gate_results,
        })

    # ── Ontology: Describe Type (after specific routes) ──────────────

    @app.get("/api/ontology/{type_name}")
    async def describe_type(type_name: str) -> ApiResponse:
        reg = _get_registry()
        obj_type = reg.get_type(type_name)
        if obj_type is None:
            raise HTTPException(404, f"Type not found: {type_name}")
        return ApiResponse(data={
            "description": reg.describe_type(type_name),
            "links": [
                {"name": ld.name, "target": ld.target_type, "cardinality": ld.cardinality.value}
                for ld in reg.get_links_for(type_name)
            ],
            "actions": [
                {"name": ad.name, "deterministic": ad.is_deterministic, "gates": ad.telos_gates}
                for ad in reg.get_actions_for(type_name)
            ],
        })

    # ── Tasks ────────────────────────────────────────────────────────

    @app.post("/api/tasks")
    async def create_task(req: CreateTaskRequest) -> ApiResponse:
        from dharma_swarm.models import Task, TaskPriority
        try:
            priority = TaskPriority(req.priority)
        except ValueError:
            priority = TaskPriority.NORMAL

        task = Task(
            title=req.title,
            description=req.description,
            priority=priority,
            assigned_to=req.assigned_to,
            metadata=req.metadata,
        )
        return ApiResponse(data={
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "priority": task.priority.value,
        })

    # ── Lineage ──────────────────────────────────────────────────────

    @app.get("/api/lineage/{artifact_id}")
    async def get_lineage(artifact_id: str) -> ApiResponse:
        lg = _get_lineage()
        chain = lg.provenance(artifact_id)
        return ApiResponse(data={
            "artifact_id": chain.artifact_id,
            "root_sources": chain.root_sources,
            "depth": chain.depth,
            "chain": [
                {
                    "edge_id": e.edge_id,
                    "task_id": e.task_id,
                    "operation": e.operation,
                    "inputs": e.input_artifacts,
                    "outputs": e.output_artifacts,
                    "agent": e.agent,
                    "timestamp": e.timestamp,
                }
                for e in chain.chain
            ],
        })

    @app.get("/api/lineage/{artifact_id}/impact")
    async def get_impact(artifact_id: str) -> ApiResponse:
        lg = _get_lineage()
        impact = lg.impact(artifact_id)
        return ApiResponse(data={
            "root_artifact": impact.root_artifact,
            "affected_artifacts": impact.affected_artifacts,
            "affected_tasks": impact.affected_tasks,
            "depth": impact.depth,
            "total_descendants": impact.total_descendants,
        })

    # ── Workflows ────────────────────────────────────────────────────

    @app.get("/api/workflows")
    async def list_workflows_endpoint() -> ApiResponse:
        from dharma_swarm.workflow import list_workflows
        return ApiResponse(data=list_workflows())

    @app.post("/api/workflows/{name}")
    async def execute_workflow(name: str, req: WorkflowExecuteRequest) -> ApiResponse:
        from dharma_swarm.workflow import compile_workflow
        try:
            compiled = compile_workflow(name)
        except ValueError as exc:
            raise HTTPException(404, str(exc))

        result = await compiled.execute(context=req.context)
        return ApiResponse(data={
            "workflow_id": result.workflow_id,
            "name": result.name,
            "status": result.status.value,
            "version": result.version,
            "deterministic_ratio": result.deterministic_ratio,
            "total_duration_seconds": result.total_duration_seconds,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "deterministic": s.deterministic,
                    "duration": s.duration_seconds,
                }
                for s in result.steps
            ],
        })

    return app


# Module-level app for `uvicorn dharma_swarm.api:app`
app = create_app()
