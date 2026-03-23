"""Shared runtime access to the persisted ontology registry."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import RLock

from dharma_swarm.ontology import (
    ActionExecution,
    Link,
    OntologyObj,
    OntologyRegistry,
)
from dharma_swarm.ontology_hub import OntologyHub

_ONTOLOGY_PATH_ENV = "DHARMA_ONTOLOGY_PATH"
_LOCK = RLock()
_LEGACY_IMPORT_META_KEY = "legacy_json_imported_from"
_SHARED_REGISTRY: OntologyRegistry | None = None
_SHARED_REGISTRY_PATH: Path | None = None
_SHARED_HUB: OntologyHub | None = None

logger = logging.getLogger(__name__)


def _configured_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser()

    configured = os.getenv(_ONTOLOGY_PATH_ENV)
    if configured:
        return Path(configured).expanduser()

    local_state_dir = Path.cwd() / ".dharma"
    if local_state_dir.exists():
        return local_state_dir / "ontology.db"

    return Path.home() / ".dharma" / "ontology.db"


def ontology_path(path: str | Path | None = None) -> Path:
    """Resolve the canonical ontology database path.

    Compatibility rule:
    if the configured path ends in ``.json``, treat it as the legacy import
    path and persist the runtime store to a sibling ``.db`` file.
    """
    resolved = _configured_path(path)
    if resolved.suffix.lower() == ".json":
        return resolved.with_suffix(".db")
    return resolved


def _legacy_ontology_json_path(path: str | Path | None = None) -> Path:
    resolved = _configured_path(path)
    if resolved.suffix.lower() == ".json":
        return resolved
    return resolved.with_suffix(".json")


def _ensure_shared_hub(db_path: Path) -> OntologyHub:
    global _SHARED_HUB, _SHARED_REGISTRY_PATH
    if _SHARED_HUB is None or _SHARED_REGISTRY_PATH != db_path:
        if _SHARED_HUB is not None:
            _SHARED_HUB.close()
        _SHARED_HUB = OntologyHub(db_path=db_path)
    return _SHARED_HUB


def _import_legacy_json_if_needed(
    registry: OntologyRegistry,
    hub: OntologyHub,
    legacy_path: Path,
) -> None:
    if not hub.is_empty():
        return
    if hub.get_meta(_LEGACY_IMPORT_META_KEY) is not None:
        return
    if not legacy_path.exists():
        return

    try:
        raw = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to import legacy ontology JSON %s: %s", legacy_path, exc)
        return

    imported = 0
    for obj_id, obj_data in raw.get("objects", {}).items():
        payload = dict(obj_data)
        payload.setdefault("id", obj_id)
        obj = OntologyObj.model_validate(payload)
        registry._objects[obj.id] = obj
        imported += 1

    for link_id, link_data in raw.get("link_instances", {}).items():
        payload = dict(link_data)
        payload.setdefault("id", link_id)
        link = Link.model_validate(payload)
        registry._link_instances[link.id] = link
        imported += 1

    for execution_data in raw.get("action_log", []):
        registry._action_log.append(ActionExecution.model_validate(execution_data))
        imported += 1

    if imported:
        hub.sync_from_registry(registry)
        hub.set_meta(_LEGACY_IMPORT_META_KEY, str(legacy_path))
        logger.info("Imported %d legacy ontology rows from %s", imported, legacy_path)


def get_shared_registry(
    path: str | Path | None = None,
    *,
    force_reload: bool = False,
) -> OntologyRegistry:
    """Load the canonical registry once and reuse it across API/runtime callers."""
    resolved_path = ontology_path(path)
    legacy_path = _legacy_ontology_json_path(path)

    with _LOCK:
        global _SHARED_REGISTRY, _SHARED_REGISTRY_PATH
        if (
            force_reload
            or _SHARED_REGISTRY is None
            or _SHARED_REGISTRY_PATH != resolved_path
        ):
            hub = _ensure_shared_hub(resolved_path)
            registry = OntologyRegistry.create_dharma_registry()
            _import_legacy_json_if_needed(registry, hub, legacy_path)
            hub.load_into_registry(registry)
            _SHARED_REGISTRY = registry
            _SHARED_REGISTRY_PATH = resolved_path
        return _SHARED_REGISTRY


def persist_shared_registry(
    registry: OntologyRegistry | None = None,
    path: str | Path | None = None,
) -> Path:
    """Persist the shared registry and keep the in-process singleton aligned."""
    resolved_path = ontology_path(path)
    configured_path = _configured_path(path)
    legacy_path = _legacy_ontology_json_path(path)

    with _LOCK:
        global _SHARED_REGISTRY, _SHARED_REGISTRY_PATH
        current = registry or get_shared_registry(resolved_path)
        hub = _ensure_shared_hub(resolved_path)
        hub.sync_from_registry(current)
        if configured_path.suffix.lower() == ".json":
            current.save(legacy_path)
        _SHARED_REGISTRY = current
        _SHARED_REGISTRY_PATH = resolved_path
        return resolved_path


def reset_shared_registry() -> None:
    """Clear the in-process singleton so tests or new configs can reload cleanly."""
    with _LOCK:
        global _SHARED_HUB, _SHARED_REGISTRY, _SHARED_REGISTRY_PATH
        if _SHARED_HUB is not None:
            _SHARED_HUB.close()
            _SHARED_HUB = None
        _SHARED_REGISTRY = None
        _SHARED_REGISTRY_PATH = None
