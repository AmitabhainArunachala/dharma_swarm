"""Canonical live-agent registration across telemetry, bus presence, and KaizenOps."""

from __future__ import annotations

import os
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dharma_swarm.certified_lanes import CertifiedLane, match_certified_lane
from dharma_swarm.integrations import KaizenOpsClient
from dharma_swarm.models import AgentState
from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    TeamRosterRecord,
    TelemetryPlaneStore,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_COMMUNICATION_TOPICS = (
    "orchestrator.lifecycle",
    "operator.bridge.lifecycle",
)
DEFAULT_TEAM_ID = "dharma_swarm"
DEFAULT_DEPARTMENT = "swarm"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=True))


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _default_telemetry_db_path() -> Path | None:
    raw = (
        os.getenv("DGC_ROUTER_TELEMETRY_DB", "").strip()
        or os.getenv("DHARMA_RUNTIME_DB", "").strip()
    )
    return Path(raw) if raw else None


def bus_agent_id(agent: AgentState) -> str:
    return _normalize_text(getattr(agent, "name", None)) or _normalize_text(
        getattr(agent, "id", None)
    )


def communication_topics(
    extra_topics: Iterable[str] | None = None,
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in (*DEFAULT_COMMUNICATION_TOPICS, *(extra_topics or ())):
        topic = _normalize_text(raw)
        if not topic or topic in seen:
            continue
        seen.add(topic)
        ordered.append(topic)
    return tuple(ordered)


def _default_bus_observation(required_topics: tuple[str, ...]) -> dict[str, Any]:
    return {
        "bus_status": "unavailable",
        "communication_ready": False,
        "missing_topics": list(required_topics),
        "observed_topics": [],
    }


async def _observe_bus_contract(
    agent: AgentState,
    *,
    required_topics: tuple[str, ...],
    message_bus: Any | None = None,
) -> dict[str, Any]:
    if message_bus is None or not hasattr(message_bus, "get_agent_status"):
        return _default_bus_observation(required_topics)

    agent_name = bus_agent_id(agent)
    try:
        status = await message_bus.get_agent_status(agent_name)
    except Exception:
        status = None

    if not status:
        observation = _default_bus_observation(required_topics)
        observation["bus_status"] = "missing"
        return observation

    observed_topics: list[str] = []
    if hasattr(message_bus, "list_subscriptions"):
        try:
            observed_topics = list(await message_bus.list_subscriptions(agent_name))
        except Exception:
            observed_topics = []
    if not observed_topics:
        metadata_topics = status.get("metadata", {}).get("communication_topics") or []
        observed_topics = list(communication_topics(metadata_topics))

    observed_set = {str(topic).strip() for topic in observed_topics if str(topic).strip()}
    missing_topics = [topic for topic in required_topics if topic not in observed_set]
    bus_status = _normalize_text(status.get("status")) or "unknown"
    return {
        "bus_status": bus_status,
        "communication_ready": bus_status == "online" and not missing_topics,
        "missing_topics": missing_topics,
        "observed_topics": sorted(observed_set),
    }


def _slug(value: str) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return collapsed or "agent"


def _role_name(agent: AgentState) -> str:
    role = getattr(agent, "role", "")
    return role.value if hasattr(role, "value") else str(role or "general")


def _status_name(agent: AgentState) -> str:
    status = getattr(agent, "status", "")
    return status.value if hasattr(status, "value") else str(status or "unknown")


def resolve_team_id(
    *,
    thread: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    meta = metadata or {}
    return (
        _normalize_text(meta.get("team_id"))
        or _normalize_text(os.getenv("DGC_AGENT_TEAM_ID"))
        or (f"thread-{_slug(thread)}" if _normalize_text(thread) else "")
        or DEFAULT_TEAM_ID
    )


def resolve_squad_id(
    agent: AgentState,
    *,
    thread: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    meta = metadata or {}
    return (
        _normalize_text(meta.get("squad_id"))
        or _normalize_text(thread)
        or _role_name(agent)
        or "general"
    )


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _normalize_text(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _registered_lane(
    agent: AgentState,
    *,
    metadata: dict[str, Any] | None = None,
) -> CertifiedLane | None:
    meta = metadata or {}
    provider = (
        _normalize_text(meta.get("provider"))
        or _normalize_text(getattr(agent, "provider", None))
    )
    model = (
        _normalize_text(meta.get("model"))
        or _normalize_text(getattr(agent, "model", None))
    )
    profile_id = (
        _normalize_text(meta.get("profile_id"))
        or _normalize_text(meta.get("registered_lane_profile_id"))
    )
    alias = (
        _normalize_text(meta.get("registered_lane_codename"))
        or _normalize_text(meta.get("name"))
        or bus_agent_id(agent)
    )
    return match_certified_lane(
        profile_id=profile_id,
        provider=provider or None,
        model=model or None,
        alias=alias or None,
    )


def _identity_metadata(
    agent: AgentState,
    *,
    thread: str | None = None,
    metadata: dict[str, Any] | None = None,
    bus_observation: dict[str, Any] | None = None,
    registered_lane: CertifiedLane | None = None,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    topics = communication_topics(meta.get("communication_topics") or ())
    bus_meta = bus_observation or _default_bus_observation(topics)
    meta.update(
        {
            "runtime_agent_id": _normalize_text(getattr(agent, "id", None)),
            "bus_agent_id": bus_agent_id(agent),
            "provider": _normalize_text(getattr(agent, "provider", None)),
            "model": _normalize_text(getattr(agent, "model", None)),
            "role": _role_name(agent),
            "thread": _normalize_text(thread),
            "communication_topics": list(topics),
            "observed_topics": list(bus_meta.get("observed_topics") or []),
            "missing_topics": list(bus_meta.get("missing_topics") or []),
            "communication_ready": bool(bus_meta.get("communication_ready")),
            "bus_status": _normalize_text(bus_meta.get("bus_status")) or "unavailable",
            "source": meta.get("source") or "contracts.intelligence_agents",
        }
    )
    if registered_lane is not None:
        meta.update(
            {
                "registered_lane_id": registered_lane.registration_id,
                "registered_lane_profile_id": registered_lane.profile_id,
                "registered_lane_codename": registered_lane.codename,
                "registered_lane_display_name": registered_lane.display_name,
                "registered_lane_label": registered_lane.label,
                "registered_lane_certified": True,
            }
        )
    return meta


def agent_state_to_telemetry_identity(
    agent: AgentState,
    *,
    thread: str | None = None,
    metadata: dict[str, Any] | None = None,
    bus_observation: dict[str, Any] | None = None,
    status: str | None = None,
    now: datetime | None = None,
) -> AgentIdentityRecord:
    observed_at = now or _utc_now()
    role_name = _role_name(agent)
    registered_lane = _registered_lane(agent, metadata=metadata)
    last_active = (
        getattr(agent, "last_heartbeat", None)
        or getattr(agent, "started_at", None)
        or observed_at
    )
    return AgentIdentityRecord(
        agent_id=bus_agent_id(agent),
        codename=registered_lane.codename if registered_lane is not None else bus_agent_id(agent),
        serial=_normalize_text(getattr(agent, "id", None)),
        department=_normalize_text((metadata or {}).get("department")) or DEFAULT_DEPARTMENT,
        squad_id=resolve_squad_id(agent, thread=thread, metadata=metadata),
        specialization=role_name,
        level=max(1, int(getattr(agent, "tasks_completed", 0) or 0) // 10 + 1),
        xp=float(getattr(agent, "tasks_completed", 0) or 0),
        status=_normalize_text(status) or _status_name(agent),
        last_active=last_active,
        metadata=_identity_metadata(
            agent,
            thread=thread,
            metadata=metadata,
            bus_observation=bus_observation,
            registered_lane=registered_lane,
        ),
        created_at=observed_at,
        updated_at=observed_at,
    )


def agent_state_to_team_roster(
    agent: AgentState,
    *,
    thread: str | None = None,
    metadata: dict[str, Any] | None = None,
    bus_observation: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> TeamRosterRecord:
    observed_at = now or _utc_now()
    team_id = resolve_team_id(thread=thread, metadata=metadata)
    agent_name = bus_agent_id(agent)
    roster_id = f"roster:{_slug(team_id)}:{_slug(agent_name)}"
    registered_lane = _registered_lane(agent, metadata=metadata)
    identity_meta = _identity_metadata(
        agent,
        thread=thread,
        metadata=metadata,
        bus_observation=bus_observation,
        registered_lane=registered_lane,
    )
    identity_meta["team_id"] = team_id
    return TeamRosterRecord(
        roster_id=roster_id,
        team_id=team_id,
        agent_id=agent_name,
        role=_role_name(agent),
        active=_status_name(agent) not in {"dead", "stopping"},
        metadata=identity_meta,
        created_at=observed_at,
        updated_at=observed_at,
    )


def agent_registration_to_kaizenops_events(
    identity: AgentIdentityRecord,
    roster: TeamRosterRecord,
) -> list[dict[str, Any]]:
    timestamp = _utc_now_iso()
    trace_id = identity.serial or identity.agent_id
    payload = _json_safe({
        "identity": asdict(identity),
        "roster": asdict(roster),
    })
    return [
        {
            "agent_id": identity.agent_id,
            "session_id": f"team:{roster.team_id}",
            "trace_id": trace_id,
            "task_id": None,
            "category": "agent_registry",
            "intent": "register_agent",
            "timestamp": timestamp,
            "duration_sec": 0.0,
            "estimated_cost_usd": 0.0,
            "source_format": "canonical",
            "deliverables": [],
            "metadata": {
                "team_id": roster.team_id,
                "role": roster.role,
                "status": identity.status,
                "provider": str(identity.metadata.get("provider") or ""),
                "model": str(identity.metadata.get("model") or ""),
                "registered_lane_id": str(
                    identity.metadata.get("registered_lane_id") or ""
                ),
                "registered_lane_profile_id": str(
                    identity.metadata.get("registered_lane_profile_id") or ""
                ),
                "registered_lane_codename": str(
                    identity.metadata.get("registered_lane_codename") or ""
                ),
                "registered_lane_label": str(
                    identity.metadata.get("registered_lane_label") or ""
                ),
                "communication_topics": list(
                    identity.metadata.get("communication_topics") or []
                ),
            },
            "raw_payload": payload,
        },
        {
            "agent_id": identity.agent_id,
            "session_id": f"team:{roster.team_id}",
            "trace_id": trace_id,
            "task_id": None,
            "category": "team_roster",
            "intent": "assign_agent_to_team",
            "timestamp": timestamp,
            "duration_sec": 0.0,
            "estimated_cost_usd": 0.0,
            "source_format": "canonical",
            "deliverables": [],
            "metadata": {
                "team_id": roster.team_id,
                "roster_id": roster.roster_id,
                "active": roster.active,
                "registered_lane_id": str(
                    roster.metadata.get("registered_lane_id") or ""
                ),
                "registered_lane_profile_id": str(
                    roster.metadata.get("registered_lane_profile_id") or ""
                ),
                "registered_lane_codename": str(
                    roster.metadata.get("registered_lane_codename") or ""
                ),
            },
            "raw_payload": payload,
        },
    ]


def _kaizenops_sync_enabled(include_kaizenops: bool | None) -> bool:
    if include_kaizenops is not None:
        return include_kaizenops
    return _truthy_env("DGC_KAIZENOPS_SYNC_AGENTS")


@dataclass(frozen=True, slots=True)
class AgentRegistrationSyncResult:
    agent_identity: AgentIdentityRecord
    roster_entry: TeamRosterRecord
    kaizenops_attempted: bool = False
    kaizenops_ok: bool = False
    kaizenops_response: dict[str, Any] | None = None
    kaizenops_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_identity.agent_id,
            "team_id": self.roster_entry.team_id,
            "role": self.roster_entry.role,
            "status": self.agent_identity.status,
            "communication_ready": bool(
                self.agent_identity.metadata.get("communication_ready")
            ),
            "bus_status": str(self.agent_identity.metadata.get("bus_status") or "unavailable"),
            "kaizenops_attempted": self.kaizenops_attempted,
            "kaizenops_ok": self.kaizenops_ok,
            "kaizenops_error": self.kaizenops_error,
            "kaizenops_response": self.kaizenops_response,
            "communication_topics": list(
                self.agent_identity.metadata.get("communication_topics") or []
            ),
            "registered_lane_id": str(
                self.agent_identity.metadata.get("registered_lane_id") or ""
            ),
            "registered_lane_profile_id": str(
                self.agent_identity.metadata.get("registered_lane_profile_id") or ""
            ),
            "registered_lane_codename": str(
                self.agent_identity.metadata.get("registered_lane_codename") or ""
            ),
            "registered_lane_label": str(
                self.agent_identity.metadata.get("registered_lane_label") or ""
            ),
            "observed_topics": list(
                self.agent_identity.metadata.get("observed_topics") or []
            ),
            "missing_topics": list(
                self.agent_identity.metadata.get("missing_topics") or []
            ),
        }


async def reconcile_live_agent_presence(
    *,
    telemetry: TelemetryPlaneStore,
    live_agent_ids: set[str],
    team_ids: Iterable[str] | None = None,
    source: str = "contracts.intelligence_agents.sync_live_agent_registrations",
) -> None:
    """Retire stale live-agent records for the managed teams."""

    managed_team_ids = _ordered_unique(team_ids or (resolve_team_id(),))
    observed_at = _utc_now()
    stale_agent_ids: set[str] = set()

    for team_id in managed_team_ids:
        roster_entries = await telemetry.list_team_roster(
            team_id=team_id,
            active_only=True,
            limit=1000,
        )
        for roster in roster_entries:
            if roster.agent_id in live_agent_ids:
                continue
            stale_agent_ids.add(roster.agent_id)
            metadata = dict(roster.metadata)
            metadata["live_sync"] = {
                "status": "retired",
                "source": source,
                "team_id": team_id,
                "observed_at": observed_at.isoformat(),
            }
            await telemetry.record_team_roster(
                replace(
                    roster,
                    active=False,
                    metadata=metadata,
                    updated_at=observed_at,
                )
            )

    for agent_id in stale_agent_ids:
        identity = await telemetry.get_agent_identity(agent_id)
        if identity is None or identity.status in {"dead", "retired", "stopping"}:
            continue
        metadata = dict(identity.metadata)
        metadata["live_sync"] = {
            "status": "retired",
            "source": source,
            "observed_at": observed_at.isoformat(),
        }
        await telemetry.upsert_agent_identity(
            replace(
                identity,
                status="retired",
                metadata=metadata,
                updated_at=observed_at,
            )
        )


async def sync_live_agent_registration(
    agent: AgentState,
    *,
    telemetry: TelemetryPlaneStore | None = None,
    thread: str | None = None,
    metadata: dict[str, Any] | None = None,
    message_bus: Any | None = None,
    include_kaizenops: bool | None = None,
    kaizen_client: KaizenOpsClient | None = None,
) -> AgentRegistrationSyncResult:
    store = telemetry or TelemetryPlaneStore(_default_telemetry_db_path())
    required_topics = communication_topics((metadata or {}).get("communication_topics") or ())
    bus_observation = await _observe_bus_contract(
        agent,
        required_topics=required_topics,
        message_bus=message_bus,
    )
    identity = agent_state_to_telemetry_identity(
        agent,
        thread=thread,
        metadata=metadata,
        bus_observation=bus_observation,
    )
    roster = agent_state_to_team_roster(
        agent,
        thread=thread,
        metadata=metadata,
        bus_observation=bus_observation,
    )

    identity = await store.upsert_agent_identity(identity)
    roster = await store.record_team_roster(roster)

    kaizenops_attempted = _kaizenops_sync_enabled(include_kaizenops)
    kaizenops_ok = False
    kaizenops_response: dict[str, Any] | None = None
    kaizenops_error: str | None = None

    if kaizenops_attempted:
        client = kaizen_client or KaizenOpsClient()
        try:
            kaizenops_response = await client.ingest_events(
                agent_registration_to_kaizenops_events(identity, roster)
            )
            kaizenops_ok = True
        except Exception as exc:  # pragma: no cover - best effort
            kaizenops_error = str(exc)

        sync_metadata = dict(identity.metadata)
        sync_metadata["kaizenops_sync"] = {
            "attempted": True,
            "ok": kaizenops_ok,
            "error": kaizenops_error or "",
            "response": kaizenops_response or {},
            "synced_at": _utc_now_iso(),
        }
        identity = await store.upsert_agent_identity(
            replace(
                identity,
                metadata=sync_metadata,
                updated_at=_utc_now(),
            )
        )

    return AgentRegistrationSyncResult(
        agent_identity=identity,
        roster_entry=roster,
        kaizenops_attempted=kaizenops_attempted,
        kaizenops_ok=kaizenops_ok,
        kaizenops_response=kaizenops_response,
        kaizenops_error=kaizenops_error,
    )


async def sync_live_agent_registrations(
    agents: Iterable[AgentState],
    *,
    telemetry: TelemetryPlaneStore | None = None,
    thread_by_agent_id: dict[str, str | None] | None = None,
    metadata_by_agent_id: dict[str, dict[str, Any]] | None = None,
    message_bus: Any | None = None,
    include_kaizenops: bool | None = None,
    kaizen_client: KaizenOpsClient | None = None,
    managed_team_ids: Iterable[str] | None = None,
) -> list[AgentRegistrationSyncResult]:
    """Sync all live agents, then retire stale active records for the same teams."""

    store = telemetry or TelemetryPlaneStore(_default_telemetry_db_path())
    results: list[AgentRegistrationSyncResult] = []
    live_agent_ids: set[str] = set()
    synced_team_ids: list[str] = list(managed_team_ids or ())

    for agent in agents:
        thread = (thread_by_agent_id or {}).get(agent.id)
        metadata = dict((metadata_by_agent_id or {}).get(agent.id) or {})
        synced_team_ids.append(resolve_team_id(thread=thread, metadata=metadata))
        result = await sync_live_agent_registration(
            agent,
            telemetry=store,
            thread=thread,
            metadata=metadata,
            message_bus=message_bus,
            include_kaizenops=include_kaizenops,
            kaizen_client=kaizen_client,
        )
        results.append(result)
        live_agent_ids.add(result.agent_identity.agent_id)

    await reconcile_live_agent_presence(
        telemetry=store,
        live_agent_ids=live_agent_ids,
        team_ids=synced_team_ids,
    )
    return results


__all__ = [
    "AgentRegistrationSyncResult",
    "DEFAULT_COMMUNICATION_TOPICS",
    "agent_registration_to_kaizenops_events",
    "agent_state_to_team_roster",
    "agent_state_to_telemetry_identity",
    "bus_agent_id",
    "communication_topics",
    "reconcile_live_agent_presence",
    "resolve_team_id",
    "sync_live_agent_registration",
    "sync_live_agent_registrations",
]
