"""Agent management endpoints + WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.models import AgentOut, ApiResponse, SpawnAgentRequest
from api.routers._agent_aliases import alias_candidates, matches_agent_alias
from api.routers.chat import (
    ChatMessage,
    _agentic_stream,
    _get_chat_settings,
    _sse_data,
)
from api.ws import manager
from dharma_swarm.ontology_agents import (
    agent_display_name,
    agent_slug,
    canonical_model_key,
    model_label,
    upsert_agent_identity,
    mark_agent_retiring,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agents"])


def _get_swarm():
    from api.main import get_swarm
    return get_swarm()


def _get_trace_store():
    from api.main import get_trace_store

    return get_trace_store()


def _get_agent_registry():
    from dharma_swarm.agent_registry import get_registry

    return get_registry()


def _get_ontology_registry():
    from dharma_swarm.ontology_runtime import get_shared_registry

    return get_shared_registry()


def _identity_to_out(identity_obj) -> dict:
    props = identity_obj.properties
    provider = str(props.get("provider") or "")
    model = str(props.get("model") or "")
    name = str(props.get("name") or props.get("display_name") or identity_obj.id)
    display = str(props.get("display_name") or agent_display_name(name))
    slug = str(props.get("agent_slug") or agent_slug(name))
    return AgentOut(
        id=str(props.get("agent_id") or identity_obj.id),
        name=name,
        agent_slug=slug,
        display_name=display,
        role=str(props.get("role") or "general"),
        status=str(props.get("status") or "unknown"),
        current_task=str(props.get("current_task") or "") or None,
        started_at=str(props.get("started_at") or "") or None,
        last_heartbeat=str(props.get("last_heartbeat") or props.get("last_active") or "") or None,
        turns_used=int(props.get("turns_used", 0) or 0),
        tasks_completed=int(props.get("tasks_completed", 0) or 0),
        provider=provider,
        model=model,
        model_label=model_label(model),
        model_key=str(props.get("model_key") or canonical_model_key(provider, model)),
        error=str(props.get("error") or "") or None,
    ).model_dump()


def _resolve_live_agent(agents, agent_id: str):
    for agent in agents:
        if matches_agent_alias(getattr(agent, "id", None), agent_id):
            return agent
        if matches_agent_alias(getattr(agent, "name", None), agent_id):
            return agent
    return None


def _resolve_identity(agent_id: str):
    registry = _get_ontology_registry()
    for candidate in alias_candidates(agent_id):
        for identity in registry.get_objects_by_type("AgentIdentity"):
            props = identity.properties
            values = (
                identity.id,
                str(props.get("agent_id") or ""),
                str(props.get("name") or ""),
                str(props.get("agent_slug") or ""),
                str(props.get("display_name") or ""),
            )
            if any(matches_agent_alias(value, candidate) for value in values if value):
                return identity
    return None


def _lookup_values(*values: str | None) -> set[str]:
    resolved: set[str] = set()
    for value in values:
        if not value:
            continue
        resolved.update(alias_candidates(value))
    return resolved


async def _load_recent_traces(lookup_values: set[str]) -> list:
    store = _get_trace_store()
    get_recent = getattr(store, "get_recent", None)
    if not callable(get_recent):
        return []
    traces = await get_recent(limit=200)
    filtered = []
    for trace in traces:
        trace_agent = getattr(trace, "agent", None)
        if any(matches_agent_alias(trace_agent, lookup) for lookup in lookup_values):
            filtered.append(trace)
    filtered.sort(key=lambda item: getattr(item, "timestamp", ""), reverse=True)
    return filtered


async def _load_assigned_tasks(swarm, lookup_values: set[str]) -> list:
    list_tasks = getattr(swarm, "list_tasks", None)
    if not callable(list_tasks):
        return []
    tasks = await list_tasks()
    filtered = []
    for task in tasks:
        assigned_to = getattr(task, "assigned_to", None)
        if any(matches_agent_alias(assigned_to, lookup) for lookup in lookup_values):
            filtered.append(task)
    return filtered


def _health_from_traces(traces: list, fallback_last_seen: str | None = None) -> dict:
    total_actions = len(traces)
    failures = 0
    for trace in traces:
        state = str(getattr(trace, "state", "") or "").lower()
        meta = getattr(trace, "metadata", {}) or {}
        if state in {"error", "failed", "failure", "dead"} or meta.get("success") is False:
            failures += 1
    success_rate = 1.0 if total_actions == 0 else max(0.0, 1.0 - (failures / total_actions))
    last_seen = str(getattr(traces[0], "timestamp", "")) if traces else fallback_last_seen
    return {
        "total_actions": total_actions,
        "failures": failures,
        "success_rate": round(success_rate, 4),
        "last_seen": last_seen or None,
    }


def _serialize_trace(trace) -> dict:
    return {
        "id": getattr(trace, "id", ""),
        "timestamp": str(getattr(trace, "timestamp", "")),
        "action": getattr(trace, "action", ""),
        "state": getattr(trace, "state", ""),
        "metadata": getattr(trace, "metadata", {}) or {},
    }


def _serialize_task(task) -> dict:
    return {
        "id": getattr(task, "id", ""),
        "title": getattr(task, "title", ""),
        "status": getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")),
        "priority": getattr(getattr(task, "priority", ""), "value", getattr(task, "priority", "")),
        "created_at": str(getattr(task, "created_at", "")),
        "result": getattr(task, "result", None),
    }


def _common_roles(current_role: str | None) -> list[str]:
    roles = [
        "general",
        "researcher",
        "surgeon",
        "architect",
        "cartographer",
        "validator",
        "archeologist",
        "coder",
        "reviewer",
        "tester",
        "orchestrator",
        "conductor",
    ]
    if current_role and current_role not in roles:
        roles.insert(0, current_role)
    return roles


async def _resolve_agent_payload(agent_id: str) -> dict | None:
    swarm = _get_swarm()
    try:
        live_agents = await swarm.list_agents()
    except Exception:
        logger.debug("Failed to list live agents for resolve payload", exc_info=True)
        live_agents = []

    live_agent = _resolve_live_agent(live_agents, agent_id)
    if live_agent is not None:
        upsert_agent_identity(live_agent)
        agent_out = _agent_to_out(live_agent)
        selected_name = live_agent.name
        selected_id = live_agent.id
    else:
        identity = _resolve_identity(agent_id)
        if identity is None:
            return None
        agent_out = _identity_to_out(identity)
        selected_name = agent_out["name"]
        selected_id = agent_out["id"]

    lookup_values = _lookup_values(agent_id, selected_name, selected_id)
    traces = await _load_recent_traces(lookup_values)
    assigned_tasks = await _load_assigned_tasks(swarm, lookup_values)

    registry = _get_agent_registry()
    registry_identity = registry.load_agent(selected_name) or {}
    fitness_history = registry.get_fitness_history(selected_name)
    budget = registry.check_budget(selected_name)

    current_model = agent_out.get("model") or str(registry_identity.get("model") or "")
    current_role = agent_out.get("role") or str(registry_identity.get("role") or "general")
    current_provider = agent_out.get("provider") or str(registry_identity.get("provider") or "")

    return {
        "agent": agent_out,
        "config": {
            "display_name": agent_out.get("display_name"),
            "role": current_role,
            "provider": current_provider,
            "model": current_model,
            "thread": registry_identity.get("thread"),
            "tier": registry_identity.get("tier"),
            "strengths": registry_identity.get("strengths", []),
        },
        "recent_traces": [_serialize_trace(trace) for trace in traces[:20]],
        "health_stats": _health_from_traces(
            traces,
            fallback_last_seen=agent_out.get("last_heartbeat"),
        ),
        "assigned_tasks": [_serialize_task(task) for task in assigned_tasks[:20]],
        "fitness_history": fitness_history,
        "cost": {
            "daily_spent": float(budget.get("daily_spent", 0.0) or 0.0),
            "weekly_spent": float(budget.get("weekly_spent", 0.0) or 0.0),
            "budget_status": str(budget.get("status", "OK") or "OK"),
        },
        "core_files": [],
        "available_models": (
            [{"model_id": current_model, "label": current_model, "tier": None}]
            if current_model
            else []
        ),
        "available_roles": _common_roles(current_role),
        "provider_status": (
            [{"provider": current_provider, "available": bool(current_provider)}]
            if current_provider
            else []
        ),
        "task_history": list(reversed(registry_identity.get("task_history", [])))[0:50],
    }


def _agent_to_out(agent) -> dict:
    provider = getattr(agent, "provider", "") or ""
    model = getattr(agent, "model", "") or ""
    return AgentOut(
        id=agent.id,
        name=agent.name,
        agent_slug=agent_slug(agent.name),
        display_name=agent_display_name(agent.name),
        role=agent.role.value if hasattr(agent.role, 'value') else str(agent.role),
        status=agent.status.value if hasattr(agent.status, 'value') else str(agent.status),
        current_task=agent.current_task,
        started_at=str(agent.started_at) if agent.started_at else None,
        last_heartbeat=str(agent.last_heartbeat) if agent.last_heartbeat else None,
        turns_used=agent.turns_used,
        tasks_completed=agent.tasks_completed,
        provider=provider,
        model=model,
        model_label=model_label(model),
        model_key=canonical_model_key(provider, model),
        error=agent.error,
    ).model_dump()


@router.get("/agents")
async def list_agents() -> ApiResponse:
    swarm = _get_swarm()
    try:
        agents = await swarm.list_agents()
        for agent in agents:
            upsert_agent_identity(agent)
        return ApiResponse(data=[_agent_to_out(a) for a in agents])
    except Exception as e:
        return ApiResponse(data=[], error=str(e))


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> ApiResponse:
    try:
        payload = await _resolve_agent_payload(agent_id)
        if payload is not None:
            return ApiResponse(data=payload["agent"])
        return ApiResponse(status="error", error=f"Agent not found: {agent_id}")
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.get("/agents/{agent_id}/detail")
async def get_agent_detail(agent_id: str) -> ApiResponse:
    try:
        payload = await _resolve_agent_payload(agent_id)
        if payload is None:
            return ApiResponse(status="error", error=f"Agent not found: {agent_id}")
        return ApiResponse(data=payload)
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.post("/agents/spawn")
async def spawn_agent(req: SpawnAgentRequest) -> ApiResponse:
    swarm = _get_swarm()
    try:
        from dharma_swarm.models import AgentRole, ProviderType
        try:
            role = AgentRole(req.role)
        except ValueError:
            role = AgentRole.GENERAL

        try:
            provider_type = ProviderType(req.provider) if req.provider else ProviderType.CLAUDE_CODE
        except ValueError:
            provider_type = ProviderType.CLAUDE_CODE

        model = req.model or "claude-code"

        agent = await swarm.spawn_agent(
            name=req.name,
            role=role,
            model=model,
            provider_type=provider_type,
        )
        upsert_agent_identity(agent)
        out = _agent_to_out(agent)
        await manager.broadcast("agents", {"event": "agent_spawned", "agent": out})
        return ApiResponse(data=out)
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str) -> ApiResponse:
    swarm = _get_swarm()
    try:
        await swarm.stop_agent(agent_id)
        mark_agent_retiring(agent_id, name=agent_id)
        await manager.broadcast("agents", {"event": "agent_stopped", "agent_id": agent_id})
        return ApiResponse(data={"stopped": agent_id})
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.post("/agents/sync")
async def sync_agents(
    include_kaizenops: bool = Query(
        False,
        description="Attempt live KaizenOps registration while syncing agent contracts.",
    ),
) -> ApiResponse:
    swarm = _get_swarm()
    try:
        results = await swarm.sync_agents(include_kaizenops=include_kaizenops)
        return ApiResponse(data={"count": len(results), "results": results})
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


# ── Provider → chat-profile mapping ───────────────────────────────────

_PROVIDER_PROFILE_MAP: dict[str, str] = {
    "claude_code": "claude_opus",
    "claude": "claude_opus",
    "openai": "codex_operator",
    "codex": "codex_operator",
    "groq": "qwen35_surgeon",
    "qwen": "qwen35_surgeon",
    "glm": "glm5_researcher",
    "kimi": "kimi_k25_scout",
}


def _profile_id_for_provider(provider: str) -> str:
    """Map an agent's provider string to a chat profile ID."""
    provider_lower = provider.lower()
    for key, profile_id in _PROVIDER_PROFILE_MAP.items():
        if key in provider_lower:
            return profile_id
    return "claude_opus"


def _build_agent_system_prompt(payload: dict[str, Any]) -> str:
    """Build a contextual system prompt from the resolved agent payload."""
    agent = payload["agent"]
    config = payload["config"]

    display_name = agent.get("display_name") or agent.get("name") or "Agent"
    role = config.get("role") or agent.get("role") or "general"
    status = agent.get("status") or "unknown"
    current_task = agent.get("current_task") or "none"
    provider = config.get("provider") or agent.get("provider") or "unknown"
    model = config.get("model") or agent.get("model") or "unknown"
    strengths = config.get("strengths") or []

    parts = [
        f"You are {display_name}, a {role} agent running on {provider}/{model}.",
        f"Status: {status}. Current task: {current_task}.",
    ]

    if strengths:
        parts.append(f"Strengths: {', '.join(strengths)}.")

    # Last 5 assigned tasks
    tasks = payload.get("assigned_tasks", [])[:5]
    if tasks:
        task_lines = [f"  - {t.get('title', '?')} [{t.get('status', '?')}]" for t in tasks]
        parts.append("Recent assigned tasks:\n" + "\n".join(task_lines))

    # Last 5 traces
    traces = payload.get("recent_traces", [])[:5]
    if traces:
        trace_lines = [f"  - {t.get('action', '?')} [{t.get('state', '?')}]" for t in traces]
        parts.append("Recent traces:\n" + "\n".join(trace_lines))

    parts.append(
        "Your active context: answer questions about your role, current work, "
        "and the swarm system. Use tools when available to gather live data."
    )

    return "\n\n".join(parts)


# ── Agent chat request model ──────────────────────────────────────────

class AgentChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: str | None = None


# ── Agent config update request model ─────────────────────────────────

class AgentConfigRequest(BaseModel):
    role: str | None = None
    model: str | None = None
    display_name: str | None = None
    strengths: list[str] | None = None


@router.post("/agents/{agent_id}/chat")
async def agent_chat(agent_id: str, req: AgentChatRequest):
    """Per-agent SSE chat endpoint.

    Resolves the agent's identity, builds an agent-specific system prompt,
    maps the agent's provider to a chat profile, and streams an agentic
    response in the same SSE format as ``/api/chat``.
    """
    payload = await _resolve_agent_payload(agent_id)
    if payload is None:
        return StreamingResponse(
            iter([_sse_data({"error": f"Agent not found: {agent_id}"}),
                  "data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    agent = payload["agent"]
    config = payload["config"]
    provider_str = config.get("provider") or agent.get("provider") or ""

    # Resolve chat profile from agent's provider
    profile_id = _profile_id_for_provider(provider_str)
    settings = _get_chat_settings(profile_id)

    if not settings.available:
        return StreamingResponse(
            iter([_sse_data({"error": f"Chat profile '{profile_id}' is not available. "
                            f"Configure the required API key or CLI."}),
                  "data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    # Build agent-contextual system prompt
    system_prompt = _build_agent_system_prompt(payload)
    if req.context:
        system_prompt += f"\n\nAdditional context: {req.context}"

    # Build messages for API
    api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in req.messages:
        api_messages.append({"role": m.role, "content": m.content})

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    session_id = f"agent-{agent_id}-{timestamp}"

    async def stream():
        yield _sse_data({"session_id": session_id})
        async for chunk in _agentic_stream(
            api_messages,
            settings,
            session_id=session_id,
            profile_id=profile_id,
        ):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agents/{agent_id}/config")
async def update_agent_config(agent_id: str, req: AgentConfigRequest) -> ApiResponse:
    """Update an agent's configuration (role, model, display_name, strengths)."""
    payload = await _resolve_agent_payload(agent_id)
    if payload is None:
        return ApiResponse(status="error", error=f"Agent not found: {agent_id}")

    agent_name = payload["agent"].get("name") or agent_id
    registry = _get_agent_registry()

    updated_props: dict[str, Any] = {}
    if req.role is not None:
        updated_props["role"] = req.role
    if req.model is not None:
        updated_props["model"] = req.model
    if req.display_name is not None:
        updated_props["display_name"] = req.display_name
    if req.strengths is not None:
        updated_props["strengths"] = req.strengths

    if not updated_props:
        return ApiResponse(data={"agent_id": agent_id, "updated": []})

    try:
        registry.save_agent(agent_name, updated_props)
    except ValueError as exc:
        return ApiResponse(status="error", error=str(exc))

    return ApiResponse(data={"agent_id": agent_id, "updated": list(updated_props.keys())})


@router.websocket("/ws/agents")
async def ws_agents(websocket: WebSocket):
    await manager.connect(websocket, "agents")
    try:
        while True:
            # Send periodic updates
            try:
                swarm = _get_swarm()
                agents = await swarm.list_agents()
                await manager.send_personal(websocket, {
                    "event": "agents_update",
                    "agents": [_agent_to_out(a) for a in agents],
                })
            except Exception:
                logger.debug("Failed to send periodic agent update over WebSocket", exc_info=True)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, "agents")
