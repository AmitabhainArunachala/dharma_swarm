"""Agent management endpoints + WebSocket + Fleet control + Provider status."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from api.models import (
    AgentOut,
    ApiResponse,
    FleetAgentConfig,
    SpawnAgentRequest,
    UpdateAgentConfigRequest,
    UpdateModelProfileRequest,
)
from api.ws import manager

router = APIRouter(prefix="/api", tags=["agents"])

GINKO_AGENTS_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko" / "agents"

_MODEL_PROVIDER_OVERRIDES = {
    "qwen/qwen3.5-122b-a10b": "nvidia_nim",
}


def _get_swarm():
    from api.main import get_swarm
    return get_swarm()


def _read_ginko_identity(name: str) -> dict | None:
    """Read identity.json from Ginko agent registry."""
    identity_path = GINKO_AGENTS_DIR / name / "identity.json"
    if identity_path.exists():
        try:
            return json.loads(identity_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _iter_ginko_identities() -> list[dict[str, Any]]:
    """Return every readable Ginko identity."""
    if not GINKO_AGENTS_DIR.exists():
        return []

    identities: list[dict[str, Any]] = []
    try:
        identity_paths = sorted(GINKO_AGENTS_DIR.glob("*/identity.json"))
    except Exception:
        return []

    for identity_path in identity_paths:
        try:
            payload = json.loads(identity_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            identities.append(payload)
    return identities


def _find_ginko_identity(agent_id: str) -> dict | None:
    """Resolve an agent from the Ginko registry by directory or declared name."""
    direct = _read_ginko_identity(agent_id)
    if direct:
        return direct

    for identity in _iter_ginko_identities():
        if str(identity.get("name", "")).strip() == agent_id:
            return identity
    return None


def _resolve_provider_from_model(model_id: str) -> str:
    """Extract provider from a model ID like 'anthropic/claude-opus-4' -> 'openrouter'.

    Also checks command fleet for authoritative provider mapping.
    """
    if model_id in _MODEL_PROVIDER_OVERRIDES:
        return _MODEL_PROVIDER_OVERRIDES[model_id]

    try:
        from dharma_swarm.model_pool import get_model

        model = get_model(model_id)
        if model is not None and model.routes:
            first_route = model.routes[0]
            return first_route.value if hasattr(first_route, "value") else str(first_route)
    except Exception:
        pass

    try:
        from dharma_swarm.command_fleet import COMMAND_FLEET
        for fc in COMMAND_FLEET:
            if fc["model"] == model_id:
                return fc["provider"].value if hasattr(fc["provider"], 'value') else str(fc["provider"])
    except Exception:
        pass
    # Fallback: guess from model ID prefix
    if '/' in model_id:
        prefix = model_id.split('/')[0].lower()
        provider_map = {
            'anthropic': 'openrouter', 'openai': 'openrouter', 'meta-llama': 'openrouter',
            'deepseek': 'openrouter', 'mistralai': 'openrouter', 'qwen': 'openrouter',
            'moonshotai': 'openrouter', 'z-ai': 'openrouter', 'nvidia': 'nvidia_nim',
            'google': 'openrouter',
        }
        return provider_map.get(prefix, 'openrouter')
    return ''


def _ginko_identity_to_out(identity: dict[str, Any]) -> dict:
    """Convert a Ginko identity into the dashboard AgentOut shape."""
    name = str(identity.get("name", "")).strip()
    model = str(identity.get("model", "")).strip()
    provider = _resolve_provider_from_model(model)

    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return AgentOut(
        id=name,
        name=name,
        role=str(identity.get("role", "")).strip() or "general",
        status=str(identity.get("status", "")).strip() or "idle",
        current_task=identity.get("current_task"),
        started_at=str(identity.get("created_at", "")).strip() or None,
        last_heartbeat=str(identity.get("last_active", "")).strip() or None,
        turns_used=_safe_int(identity.get("total_calls")),
        tasks_completed=_safe_int(identity.get("tasks_completed")),
        provider=provider,
        model=model,
        error=identity.get("error"),
    ).model_dump()


def _agent_to_out(agent) -> dict:
    provider = getattr(agent, 'provider', '') or ''
    model = getattr(agent, 'model', '') or ''

    # Bridge: Ginko registry is the source of truth for persistent agent config.
    # Always prefer Ginko identity over in-memory state (which may be stale).
    ginko = _read_ginko_identity(agent.name)
    if ginko:
        ginko_model = ginko.get('model', '')
        if ginko_model:
            model = ginko_model
            provider = _resolve_provider_from_model(ginko_model)

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
        provider=provider,
        model=model,
        error=agent.error,
    ).model_dump()


# ── List / Get ────────────────────────────────────────────────────────────


@router.get("/agents")
async def list_agents() -> ApiResponse:
    swarm = _get_swarm()
    try:
        agents = await swarm.list_agents()
        # Deduplicate: if an agent name appears twice (dead + alive from respawn),
        # keep the live one and drop the dead one.
        by_name: dict[str, list] = {}
        for a in agents:
            by_name.setdefault(a.name, []).append(a)
        deduped = []
        for name, group in by_name.items():
            if len(group) == 1:
                deduped.append(group[0])
            else:
                # Prefer non-dead agent
                live = [a for a in group if getattr(a, 'status', None) != 'dead' and str(getattr(a, 'status', '')).lower() != 'dead']
                deduped.append(live[0] if live else group[-1])
        out = [_agent_to_out(a) for a in deduped]
        live_names = {item["name"] for item in out}
        for identity in _iter_ginko_identities():
            name = str(identity.get("name", "")).strip()
            if not name or name in live_names:
                continue
            out.append(_ginko_identity_to_out(identity))
        return ApiResponse(data=out)
    except Exception as e:
        return ApiResponse(data=[], error=str(e))


@router.get("/agents/observatory")
async def get_observatory() -> ApiResponse:
    """Fleet-wide observatory: per-agent fitness, cost, anomalies, timeline."""
    try:
        from dharma_swarm.agent_registry import get_registry
        from api.main import get_monitor

        reg = get_registry()
        all_agents = reg.list_agents()

        # Per-agent fitness + cost + task counts
        agent_summaries = []
        total_cost = 0.0
        fitness_values = []

        for identity in all_agents:
            name = identity.get("name", "")
            if not name:
                continue

            fitness = reg.get_agent_fitness(name)
            budget = reg.check_budget(name)

            # Read fitness history for sparkline
            fh_path = GINKO_AGENTS_DIR / name / "fitness_history.jsonl"
            fitness_hist = _read_jsonl_tail(fh_path, 20)
            sparkline = [round(e.get("composite_fitness", 0.0), 3) for e in fitness_hist]

            cost_usd = fitness.get("total_cost_usd", 0.0)
            total_cost += cost_usd
            comp_fitness = fitness.get("composite_fitness", 0.0)
            if fitness.get("total_calls", 0) > 0:
                fitness_values.append(comp_fitness)

            # Task history for timeline
            th_path = GINKO_AGENTS_DIR / name / "task_log.jsonl"
            recent_tasks = _read_jsonl_tail(th_path, 5)

            agent_summaries.append({
                "name": name,
                "model": identity.get("model", ""),
                "role": identity.get("role", ""),
                "status": identity.get("status", "idle"),
                "last_active": identity.get("last_active", ""),
                "composite_fitness": round(comp_fitness, 4),
                "success_rate": round(fitness.get("success_rate", 0.0), 4),
                "avg_latency": round(fitness.get("avg_latency", 0.0), 1),
                "total_calls": fitness.get("total_calls", 0),
                "total_tokens": fitness.get("total_tokens", 0),
                "total_cost_usd": round(cost_usd, 6),
                "speed_score": round(fitness.get("speed_score", 0.0), 4),
                "daily_spent": round(budget.get("daily_spent", 0.0), 6),
                "weekly_spent": round(budget.get("weekly_spent", 0.0), 6),
                "budget_status": budget.get("status", "OK"),
                "sparkline": sparkline,
                "recent_tasks": recent_tasks,
            })

        # Sort by composite fitness descending
        agent_summaries.sort(key=lambda a: a["composite_fitness"], reverse=True)

        # Fleet-wide stats
        fleet_fitness = round(
            sum(fitness_values) / len(fitness_values) if fitness_values else 0.0, 4
        )

        # Anomalies from SystemMonitor
        anomalies = []
        try:
            monitor = get_monitor()
            health = await monitor.check_health()
            for anom in getattr(health, "anomalies", []):
                anomalies.append({
                    "id": getattr(anom, "id", ""),
                    "detected_at": getattr(anom, "detected_at", ""),
                    "anomaly_type": getattr(anom, "anomaly_type", ""),
                    "severity": getattr(anom, "severity", ""),
                    "description": getattr(anom, "description", ""),
                })
        except Exception:
            pass

        # Timeline: last 30 task entries across all agents
        all_recent = []
        for summary in agent_summaries:
            for task in summary.get("recent_tasks", []):
                task["agent"] = summary["name"]
                all_recent.append(task)
        all_recent.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
        timeline = all_recent[:30]

        return ApiResponse(data={
            "agents": agent_summaries,
            "fleet_fitness": fleet_fitness,
            "total_cost_usd": round(total_cost, 6),
            "agent_count": len(agent_summaries),
            "anomalies": anomalies,
            "timeline": timeline,
            "top_performer": agent_summaries[0]["name"] if agent_summaries else "",
            "struggling": [
                a["name"] for a in agent_summaries
                if a["composite_fitness"] < 0.5 and a["total_calls"] > 0
            ],
        })
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> ApiResponse:
    swarm = _get_swarm()
    try:
        agents = await swarm.list_agents()
        for a in agents:
            if a.id == agent_id or a.name == agent_id:
                return ApiResponse(data=_agent_to_out(a))
        identity = _find_ginko_identity(agent_id)
        if identity:
            return ApiResponse(data=_ginko_identity_to_out(identity))
        return ApiResponse(status="error", error=f"Agent not found: {agent_id}")
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


# ── Extended Detail ───────────────────────────────────────────────────────


def _read_jsonl_tail(path: Path, limit: int = 20) -> list[dict]:
    """Read last N entries from a JSONL file."""
    entries: list[dict] = []
    if not path.exists():
        return entries
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return entries[-limit:]


@router.get("/agents/{agent_id}/detail")
async def get_agent_detail(agent_id: str) -> ApiResponse:
    """Extended agent view: base data + config + traces + health + tasks + fitness + cost + files."""
    swarm = _get_swarm()
    try:
        try:
            agents = await swarm.list_agents()
        except Exception:
            agents = []
        agent = None
        for a in agents:
            if a.id == agent_id or a.name == agent_id:
                agent = a
                break
        identity = None
        if agent is not None:
            out = _agent_to_out(agent)
            agent_name = agent.name
        else:
            identity = _find_ginko_identity(agent_id)
            if identity is None:
                return ApiResponse(status="error", error=f"Agent not found: {agent_id}")
            out = _ginko_identity_to_out(identity)
            agent_name = out["name"]

        # ── Config (from fleet + Ginko) ──────────────────────────────
        config: dict = {}
        try:
            from dharma_swarm.command_fleet import COMMAND_FLEET
            for fc in COMMAND_FLEET:
                if fc["name"] == agent_name:
                    config = {
                        "provider": fc["provider"].value if hasattr(fc["provider"], 'value') else str(fc["provider"]),
                        "model": fc["model"],
                        "role": fc["role"].value if hasattr(fc["role"], 'value') else str(fc["role"]),
                        "thread": fc.get("thread", ""),
                        "display_name": fc.get("display_name", ""),
                        "tier": fc.get("tier", ""),
                        "strengths": list(fc.get("strengths", ())),
                    }
                    break
        except Exception:
            pass
        # Fallback to Ginko identity
        if not config:
            ginko = identity or _find_ginko_identity(agent_name)
            if ginko:
                config = {
                    "provider": _resolve_provider_from_model(str(ginko.get("model", ""))),
                    "model": ginko.get("model", ""),
                    "role": ginko.get("role", ""),
                    "thread": "",
                    "display_name": agent_name,
                    "tier": "",
                    "strengths": [],
                }

        # ── Traces ────────────────────────────────────────────────────
        recent_traces: list[dict] = []
        try:
            from api.main import get_trace_store
            store = get_trace_store()
            all_traces = await store.get_recent(limit=200)
            for t in all_traces:
                t_agent = getattr(t, 'agent', '') or ''
                if t_agent == agent_name:
                    recent_traces.append({
                        "id": getattr(t, 'id', ''),
                        "timestamp": str(getattr(t, 'timestamp', '')),
                        "action": getattr(t, 'action', ''),
                        "state": getattr(t, 'state', 'active'),
                        "metadata": getattr(t, 'metadata', {}),
                    })
                    if len(recent_traces) >= 30:
                        break
        except Exception:
            pass

        # ── Health stats ──────────────────────────────────────────────
        health_stats: dict = {}
        try:
            from api.main import get_monitor
            monitor = get_monitor()
            health = await monitor.check_health()
            for ah in getattr(health, 'agent_health', []):
                if getattr(ah, 'agent_name', '') == agent_name:
                    health_stats = {
                        "total_actions": ah.total_actions,
                        "failures": ah.failures,
                        "success_rate": ah.success_rate,
                        "last_seen": ah.last_seen,
                    }
                    break
        except Exception:
            pass

        # ── Assigned tasks ────────────────────────────────────────────
        assigned_tasks: list[dict] = []
        try:
            all_tasks = await swarm.list_tasks()
            for task in all_tasks:
                if getattr(task, 'assigned_to', None) in (agent_name, agent.id):
                    assigned_tasks.append({
                        "id": task.id,
                        "title": task.title,
                        "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
                        "priority": getattr(task, 'priority', 'normal'),
                        "created_at": str(getattr(task, 'created_at', '')),
                        "result": getattr(task, 'result', None),
                    })
        except Exception:
            pass

        # ── Fitness history (from Ginko) ──────────────────────────────
        fitness_history: list[dict] = []
        try:
            fh_path = GINKO_AGENTS_DIR / agent_name / "fitness_history.jsonl"
            fitness_history = _read_jsonl_tail(fh_path, 20)
        except Exception:
            pass

        # ── Cost (from Ginko agent_registry) ──────────────────────────
        cost: dict = {}
        try:
            from dharma_swarm.agent_registry import get_registry
            reg = get_registry()
            budget = reg.check_budget(agent_name)
            cost = {
                "daily_spent": budget.get("daily_spent", 0.0),
                "weekly_spent": budget.get("weekly_spent", 0.0),
                "budget_status": budget.get("status", "OK"),
            }
        except Exception:
            pass

        # ── Core files (from stigmergy marks) ─────────────────────────
        core_files: list[dict] = []
        try:
            marks_path = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "stigmergy" / "marks.jsonl"
            if marks_path.exists():
                file_counts: dict[str, dict] = {}
                for entry in _read_jsonl_tail(marks_path, 1000):
                    if entry.get("agent") == agent_name:
                        fp = entry.get("file_path", "")
                        if fp:
                            if fp not in file_counts:
                                file_counts[fp] = {"count": 0, "last_touch": "", "salience": 0.0}
                            file_counts[fp]["count"] += 1
                            file_counts[fp]["last_touch"] = entry.get("timestamp", "")
                            file_counts[fp]["salience"] = max(
                                file_counts[fp]["salience"],
                                entry.get("salience", 0.5),
                            )
                core_files = sorted(
                    [
                        {"file_path": fp, **data}
                        for fp, data in file_counts.items()
                    ],
                    key=lambda x: x["salience"],
                    reverse=True,
                )[:15]
        except Exception:
            pass

        # ── Available models ──────────────────────────────────────────
        available_models: list[dict] = []
        try:
            from dharma_swarm.model_pool import list_models, model_profile

            for slot in list_models(available_only=True):
                profile = model_profile(slot.id)
                available_models.append({
                    "provider": slot.provider.value,
                    "model_id": slot.id,
                    "label": profile["ui_label"],
                    "tier": slot.tier.value if hasattr(slot.tier, 'value') else str(slot.tier),
                    "strengths": list(slot.strengths),
                })
        except Exception:
            pass

        # ── Available roles ───────────────────────────────────────────
        available_roles: list[str] = []
        try:
            from dharma_swarm.models import AgentRole
            available_roles = [r.value for r in AgentRole]
        except Exception:
            pass

        # ── Provider status ───────────────────────────────────────────
        provider_status: dict = {"available": False}
        try:
            from dharma_swarm.model_pool import provider_available
            from dharma_swarm.models import ProviderType
            agent_provider_str = out.get("provider", "")
            if agent_provider_str:
                try:
                    pt = ProviderType(agent_provider_str)
                    provider_status = {"available": provider_available(pt)}
                except ValueError:
                    pass
        except Exception:
            pass

        # ── Task history (from Ginko) ─────────────────────────────────
        task_history: list[dict] = []
        try:
            th_path = GINKO_AGENTS_DIR / agent_name / "task_log.jsonl"
            task_history = _read_jsonl_tail(th_path, 20)
        except Exception:
            pass

        return ApiResponse(data={
            "agent": out,
            "config": config,
            "recent_traces": recent_traces,
            "health_stats": health_stats,
            "assigned_tasks": assigned_tasks,
            "fitness_history": fitness_history,
            "cost": cost,
            "core_files": core_files,
            "available_models": available_models,
            "available_roles": available_roles,
            "provider_status": provider_status,
            "task_history": task_history,
        })
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


# ── Spawn / Stop ──────────────────────────────────────────────────────────


@router.post("/agents/spawn")
async def spawn_agent(req: SpawnAgentRequest) -> ApiResponse:
    swarm = _get_swarm()
    try:
        from dharma_swarm.model_pool import get_model, provider_available
        from dharma_swarm.models import AgentRole, ProviderType
        try:
            role = AgentRole(req.role)
        except ValueError:
            role = AgentRole.GENERAL

        kwargs: dict = {"name": req.name, "role": role}
        if req.provider:
            try:
                kwargs["provider_type"] = ProviderType(req.provider)
            except ValueError:
                pass
        if req.model:
            kwargs["model"] = req.model

        agent = await swarm.spawn_agent(**kwargs)
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


# ── Fleet Config ──────────────────────────────────────────────────────────


@router.get("/fleet/config")
async def get_fleet_config() -> ApiResponse:
    """Return the 10-agent fleet definition with availability status."""
    try:
        from dharma_swarm.command_fleet import COMMAND_FLEET
        from dharma_swarm.model_pool import model_profile, provider_available

        result = []
        for fc in COMMAND_FLEET:
            provider = fc["provider"]
            available = provider_available(provider)
            profile = model_profile(fc["model"])
            result.append(FleetAgentConfig(
                name=fc["name"],
                role=fc["role"].value if hasattr(fc["role"], 'value') else str(fc["role"]),
                provider=provider.value if hasattr(provider, 'value') else str(provider),
                model=fc["model"],
                display_name=fc.get("display_name", ""),
                model_display_name=profile["ui_label"],
                tier=fc.get("tier", ""),
                strengths=list(fc.get("strengths", ())),
                available=available,
                tool_name=fc.get("tool_name", ""),
                thread=fc.get("thread", ""),
            ).model_dump())
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.patch("/agents/{agent_id}/config")
async def update_agent_config(agent_id: str, req: UpdateAgentConfigRequest) -> ApiResponse:
    """Update an agent's model or role. Stops and respawns with new config."""
    swarm = _get_swarm()
    try:
        # Find agent
        agents = await swarm.list_agents()
        agent = None
        for a in agents:
            if a.id == agent_id or a.name == agent_id:
                agent = a
                break
        if not agent:
            return ApiResponse(status="error", error=f"Agent not found: {agent_id}")

        from dharma_swarm.models import AgentRole, ProviderType

        # Stop existing
        try:
            await swarm.stop_agent(agent.id)
        except Exception:
            pass

        # Determine new config
        new_role = agent.role
        if req.role:
            try:
                new_role = AgentRole(req.role)
            except ValueError:
                pass

        new_model = req.model or getattr(agent, 'model', '') or ''
        new_provider = ProviderType.OPENROUTER  # default
        if req.provider:
            try:
                new_provider = ProviderType(req.provider)
            except ValueError:
                pass
        elif new_model:
            resolved = get_model(new_model)
            if resolved is not None and resolved.routes:
                for route in resolved.routes:
                    if provider_available(route):
                        new_provider = route
                        break
                else:
                    new_provider = resolved.routes[0]

        # Respawn
        new_agent = await swarm.spawn_agent(
            name=agent.name,
            role=new_role,
            thread="mechanistic",
            provider_type=new_provider,
            model=new_model,
        )
        out = _agent_to_out(new_agent)
        await manager.broadcast("agents", {"event": "agent_respawned", "agent": out})
        return ApiResponse(data=out)
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.post("/fleet/respawn")
async def respawn_fleet() -> ApiResponse:
    """Restart entire fleet from command fleet config."""
    swarm = _get_swarm()
    try:
        from dharma_swarm.command_fleet import spawn_command_fleet
        agents = await spawn_command_fleet(swarm)
        return ApiResponse(data={
            "spawned": len(agents),
            "agents": [_agent_to_out(a) for a in agents],
        })
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


# ── Provider Status ───────────────────────────────────────────────────────


@router.get("/providers/status")
async def get_provider_status() -> ApiResponse:
    """Check each provider's availability."""
    try:
        from dharma_swarm.model_pool import list_providers

        result = [
            {
                "provider": provider["type"],
                "available": provider["available"],
                "model_count": provider["model_count"],
                "availability_kind": provider["availability_kind"],
            }
            for provider in list_providers()
        ]
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


# ── Model Pool (single source of truth) ───────────────────────────────────


@router.get("/pool")
async def get_model_pool(live: bool = True) -> ApiResponse:
    """THE single source of truth. Top 10, providers, discovered models, agents."""
    try:
        from dharma_swarm.model_pool import get_pool
        return ApiResponse(data=get_pool(live=live))
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.get("/pool/top10")
async def get_top10() -> ApiResponse:
    """Top 10 most powerful models with fallback chain resolution."""
    try:
        from dharma_swarm.model_pool import resolve_top10
        return ApiResponse(data=resolve_top10())
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.get("/pool/models")
async def get_pool_models(
    provider: str | None = None,
    free_only: bool = False,
    search: str | None = None,
    limit: int = 50,
) -> ApiResponse:
    """Search the full ~570 model catalog."""
    try:
        from dharma_swarm.model_pool import get_pool_models as _query
        return ApiResponse(data=_query(provider=provider, free_only=free_only,
                                        search=search, limit=limit))
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.get("/pool/top10/status")
async def get_top10_status(live: bool = True) -> ApiResponse:
    """Curated top-ten with links, custom labels, and latest verification state."""
    try:
        from dharma_swarm.model_pool import top10_status

        return ApiResponse(data=top10_status(live=live))
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.post("/pool/top10/verify")
async def verify_top10_models() -> ApiResponse:
    """Run live verification across the curated top ten."""
    try:
        from dharma_swarm.model_pool import verify_top10

        return ApiResponse(data=await verify_top10())
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


@router.patch("/pool/models/{model_id:path}/profile")
async def patch_model_profile(
    model_id: str,
    req: UpdateModelProfileRequest,
) -> ApiResponse:
    """Persist UI label overrides for a model."""
    try:
        from dharma_swarm.model_pool import update_model_profile

        return ApiResponse(
            data=update_model_profile(
                model_id,
                custom_label=req.custom_label,
                short_name=req.short_name,
            )
        )
    except KeyError as e:
        return ApiResponse(status="error", error=str(e))
    except Exception as e:
        return ApiResponse(status="error", error=str(e))


# ── Observatory ─────────────────────────────────────────────────────────


class DispatchRequest(BaseModel):
    title: str
    description: str = ""


# ── Dispatch (Autonomous Task Execution) ──────────────────────────────────


@router.post("/agents/{agent_name}/dispatch")
async def dispatch_task(agent_name: str, req: DispatchRequest):
    """Dispatch a task to a specific agent. Returns SSE stream of execution."""
    from datetime import datetime, timezone
    from fastapi.responses import StreamingResponse

    async def _dispatch_stream():
        """Run the agentic tool loop for the dispatched task."""
        start_time = datetime.now(timezone.utc)
        task_desc = f"{req.title}: {req.description}" if req.description else req.title
        total_tokens = 0
        success = True

        try:
            # Resolve agent profile
            from api.routers.chat import (
                _call_chat_provider,
                _get_chat_settings,
                _resident_operator_binding,
            )
            from api.chat_tools import execute_tool

            # Map agent name to profile
            profile_map = {
                "glm5-researcher": "glm5_researcher",
                "glm5_researcher": "glm5_researcher",
                "qwen35-surgeon": "qwen35_surgeon",
                "qwen35_surgeon": "qwen35_surgeon",
                "claude-opus": "claude_opus",
                "opus-primus": "claude_opus",
                "codex-operator": "codex_operator",
                "codex-primus": "codex_operator",
            }
            profile_id = profile_map.get(agent_name, "glm5_researcher")
            settings = _get_chat_settings(profile_id)
            resident_binding = _resident_operator_binding(settings.provider)

            if not settings.api_key:
                missing_error = (
                    resident_binding[2]
                    if resident_binding is not None
                    else f"No API key for profile {profile_id}"
                )
                yield f"data: {json.dumps({'error': missing_error})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Build messages
            from api.routers.chat import _gather_brief_context, _get_profile_spec
            brief = await _gather_brief_context()
            profile = _get_profile_spec(profile_id)
            system_prompt = (
                profile.system_prompt
                + f"\n\n[Live: {brief}]"
                + f"\n\n[DISPATCHED TASK: {task_desc}]"
                + "\nComplete this task using your tools. Be thorough and report results."
            )

            messages: list[dict] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_desc},
            ]

            yield f"data: {json.dumps({'status': 'started', 'task': task_desc, 'agent': agent_name})}\n\n"

            if resident_binding is not None:
                operator, client_id, _, not_running_error = resident_binding
                if not operator._running:
                    yield f"data: {json.dumps({'error': not_running_error})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                resident_session_id = f"dispatch-{agent_name}-{int(start_time.timestamp() * 1000)}"
                async for event in operator.handle_message(
                    resident_session_id,
                    task_desc,
                    client_id,
                ):
                    if event.event_type == "text_delta":
                        if event.content:
                            yield f"data: {json.dumps({'content': event.content})}\n\n"
                        continue

                    if event.event_type == "tool_call":
                        try:
                            parsed = json.loads(event.content or "{}")
                        except json.JSONDecodeError:
                            parsed = {"name": event.metadata.get("tool", "unknown"), "args": {}}
                        tool_name = str(parsed.get("name", "") or event.metadata.get("tool", "unknown"))
                        tool_args = parsed.get("args", {})
                        yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args}})}\n\n"
                        continue

                    if event.event_type == "tool_result":
                        tool_name = str(event.metadata.get("tool", "") or "")
                        summary = str(event.content or "")
                        yield f"data: {json.dumps({'tool_result': {'name': tool_name, 'summary': summary}})}\n\n"
                        continue

                    if event.event_type == "error":
                        success = False
                        yield f"data: {json.dumps({'error': event.content})}\n\n"
                        continue
                # Resident operators own their own tool loop, so dispatch is complete here.
            else:

                # Tool loop (same pattern as _agentic_stream)
                max_rounds = settings.max_tool_rounds
                for _round in range(max_rounds):
                    result = await _call_chat_provider(messages, settings)

                    if result.get("_error"):
                        yield f"data: {json.dumps({'error': result['_error']})}\n\n"
                        success = False
                        break

                    choice = result.get("choices", [{}])[0]
                    msg = choice.get("message", {})
                    tool_calls = msg.get("tool_calls")

                    if tool_calls:
                        messages.append({
                            "role": "assistant",
                            "content": msg.get("content") or None,
                            "tool_calls": tool_calls,
                        })

                        if msg.get("content"):
                            yield f"data: {json.dumps({'content': msg['content']})}\n\n"

                        for tc in tool_calls:
                            fn = tc.get("function", {})
                            tool_name = fn.get("name", "")
                            try:
                                tool_args = json.loads(fn.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                tool_args = {}
                            tool_id = tc.get("id", "")

                            yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args}})}\n\n"

                            tool_result = await execute_tool(tool_name, tool_args)
                            if len(tool_result) > settings.tool_result_max_chars:
                                tool_result = tool_result[:settings.tool_result_max_chars] + "\n... (truncated)"

                            summary = tool_result[:150].replace("\n", " ")
                            yield f"data: {json.dumps({'tool_result': {'name': tool_name, 'summary': summary}})}\n\n"

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": tool_result,
                            })
                        continue

                    # Final text response
                    final_content = msg.get("content", "")
                    if final_content:
                        chunk_size = 40
                        for i in range(0, len(final_content), chunk_size):
                            yield f"data: {json.dumps({'content': final_content[i:i+chunk_size]})}\n\n"
                    break

            # Log to Ginko
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            try:
                from dharma_swarm.agent_registry import get_registry
                reg = get_registry()
                reg.log_task(
                    agent_name,
                    task=task_desc,
                    success=success,
                    tokens=total_tokens,
                    latency_ms=elapsed_ms,
                    response_preview="",
                )
            except Exception:
                pass

            # Emit fitness signal
            try:
                from dharma_swarm.signal_bus import SignalBus
                from dharma_swarm.agent_registry import get_registry as _get_reg
                fitness = None
                try:
                    fitness = _get_reg().get_agent_fitness(agent_name)
                except Exception:
                    pass
                SignalBus.get().emit({
                    "type": "FITNESS_SIGNAL",
                    "agent": agent_name,
                    "composite_fitness": fitness.get("composite_fitness", 0.0) if fitness else 0.0,
                    "task": task_desc,
                    "success": success,
                })
            except Exception:
                pass

            yield f"data: {json.dumps({'status': 'completed', 'success': success, 'elapsed_ms': round(elapsed_ms)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _dispatch_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── WebSocket ─────────────────────────────────────────────────────────────


@router.websocket("/ws/agents")
async def ws_agents(websocket: WebSocket):
    await manager.connect(websocket, "agents")
    try:
        while True:
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
