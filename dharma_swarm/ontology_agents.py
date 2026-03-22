"""Helpers for projecting live runtime agents into the shared ontology."""

from __future__ import annotations

import re
from typing import Any

from dharma_swarm.ontology import OntologyObj, OntologyRegistry
from dharma_swarm.ontology_runtime import get_shared_registry, persist_shared_registry


def agent_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "agent"


def agent_display_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "Agent"
    if " " in raw:
        return raw
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", raw) if part)


def model_label(model: str) -> str:
    raw = (model or "").strip()
    if not raw:
        return ""
    return raw.split("/")[-1]


def canonical_model_key(provider: str, model: str) -> str:
    provider_name = (provider or "").strip().lower()
    model_name = (model or "").strip()
    if provider_name and model_name:
        return f"{provider_name}::{model_name}"
    return model_name or provider_name


def find_agent_identity(
    registry: OntologyRegistry,
    *,
    agent_id: str | None = None,
    name: str | None = None,
) -> OntologyObj | None:
    """Find the canonical AgentIdentity object by runtime ID or name."""
    identities = registry.get_objects_by_type("AgentIdentity")
    for obj in identities:
        if agent_id and obj.properties.get("agent_id") == agent_id:
            return obj
    for obj in identities:
        if name and obj.properties.get("name") == name:
            return obj
    return None


def _stringify_timestamp(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_agent_identity_properties(agent: Any) -> dict[str, Any]:
    """Normalize a live agent/runtime payload into ontology properties."""
    name = getattr(agent, "name", None) or getattr(agent, "id", None) or "agent"
    if not isinstance(name, str):
        name = "agent"
    provider = str(getattr(agent, "provider", "") or "").strip()
    model = str(getattr(agent, "model", "") or "").strip()
    role = getattr(agent, "role", "")
    status = getattr(agent, "status", "")

    return {
        "name": name,
        "agent_id": str(getattr(agent, "id", "") or "").strip(),
        "agent_slug": agent_slug(name),
        "display_name": agent_display_name(name),
        "role": role.value if hasattr(role, "value") else str(role or "general"),
        "status": status.value if hasattr(status, "value") else str(status or "unknown"),
        "provider": provider,
        "model": model,
        "model_key": canonical_model_key(provider, model),
        "current_task": str(getattr(agent, "current_task", "") or ""),
        "started_at": _stringify_timestamp(getattr(agent, "started_at", None)),
        "last_heartbeat": _stringify_timestamp(getattr(agent, "last_heartbeat", None)),
        "capabilities": [],
        "tasks_completed": int(getattr(agent, "tasks_completed", 0) or 0),
        "fitness_average": float(getattr(agent, "fitness_average", 0.0) or 0.0),
    }


def upsert_agent_identity(
    agent: Any,
    *,
    registry: OntologyRegistry | None = None,
    persist: bool = True,
) -> OntologyObj | None:
    """Project a live agent into the canonical AgentIdentity ontology type."""
    shared_registry = registry or get_shared_registry()
    properties = build_agent_identity_properties(agent)
    existing = find_agent_identity(
        shared_registry,
        agent_id=properties.get("agent_id") or None,
        name=properties["name"],
    )

    if existing is None:
        obj, errors = shared_registry.create_object(
            "AgentIdentity",
            properties=properties,
            created_by="agent_api",
        )
        if obj is None or errors:
            return None
    else:
        updates = {key: value for key, value in properties.items() if key != "name"}
        obj, errors = shared_registry.update_object(
            existing.id,
            updates,
            updated_by="agent_api",
        )
        if obj is None or errors:
            return None

    if persist and registry is None:
        persist_shared_registry(shared_registry)
    return obj


def mark_agent_retiring(
    agent_id: str,
    *,
    name: str | None = None,
    registry: OntologyRegistry | None = None,
    persist: bool = True,
) -> OntologyObj | None:
    """Mark an AgentIdentity as stopping/retiring when a stop signal is issued."""
    shared_registry = registry or get_shared_registry()
    existing = find_agent_identity(shared_registry, agent_id=agent_id, name=name)
    if existing is None:
        return None

    obj, errors = shared_registry.update_object(
        existing.id,
        {"status": "stopping"},
        updated_by="agent_api",
    )
    if obj is None or errors:
        return None

    if persist and registry is None:
        persist_shared_registry(shared_registry)
    return obj
