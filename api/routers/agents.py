"""Agent management endpoints + WebSocket."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.models import AgentOut, ApiResponse, SpawnAgentRequest
from api.ws import manager

router = APIRouter(prefix="/api", tags=["agents"])


def _get_swarm():
    from api.main import get_swarm
    return get_swarm()


def _agent_to_out(agent) -> dict:
    return AgentOut(
        id=agent.id,
        name=agent.name,
        role=agent.role.value if hasattr(agent.role, 'value') else str(agent.role),
        status=agent.status.value if hasattr(agent.status, 'value') else str(agent.status),
        current_task=agent.current_task,
        started_at=str(agent.started_at) if agent.started_at else None,
        last_heartbeat=str(agent.last_heartbeat) if agent.last_heartbeat else None,
        turns_used=agent.turns_used,
        tasks_completed=agent.tasks_completed,
        error=agent.error,
    ).model_dump()


@router.get("/agents")
async def list_agents() -> ApiResponse:
    swarm = _get_swarm()
    try:
        agents = await swarm.list_agents()
        return ApiResponse(data=[_agent_to_out(a) for a in agents])
    except Exception as e:
        return ApiResponse(data=[], error=str(e))


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> ApiResponse:
    swarm = _get_swarm()
    try:
        agents = await swarm.list_agents()
        for a in agents:
            if a.id == agent_id or a.name == agent_id:
                return ApiResponse(data=_agent_to_out(a))
        return ApiResponse(status="error", error=f"Agent not found: {agent_id}")
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.post("/agents/spawn")
async def spawn_agent(req: SpawnAgentRequest) -> ApiResponse:
    swarm = _get_swarm()
    try:
        from dharma_swarm.models import AgentRole
        try:
            role = AgentRole(req.role)
        except ValueError:
            role = AgentRole.GENERAL

        agent = await swarm.spawn_agent(name=req.name, role=role)
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
        await manager.broadcast("agents", {"event": "agent_stopped", "agent_id": agent_id})
        return ApiResponse(data={"stopped": agent_id})
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


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
                pass
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, "agents")
