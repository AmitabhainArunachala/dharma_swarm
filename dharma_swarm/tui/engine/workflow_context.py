"""Helpers for attaching stable workflow metadata to DGC sessions."""

from __future__ import annotations

import os
from typing import Any

from dharma_swarm.mode_pack import load_mode_pack


_UI_MODE_TO_WORKFLOW_MODE = {
    "N": "ship",
    "A": "ship",
    "P": "eng-review",
    "S": "ceo-review",
}

_UI_MODE_LABELS = {
    "N": "normal",
    "A": "auto",
    "P": "plan",
    "S": "sage",
}


def _clean_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mode_slug(value: object) -> str | None:
    text = _clean_value(value)
    if text is None:
        return None
    return text.lower().replace("_", "-").replace(" ", "-")


def _extract_nested_workflow(source: dict[str, Any]) -> dict[str, Any]:
    nested = source.get("workflow")
    if isinstance(nested, dict):
        return dict(nested)
    return {}


def default_workflow_owner() -> str:
    for key in ("DGC_WORKFLOW_OWNER", "USER", "LOGNAME"):
        value = _clean_value(os.getenv(key))
        if value is not None:
            return value
    return "operator"


def default_handoff_for_mode(mode_slug: str | None) -> str | None:
    if mode_slug is None:
        return None
    try:
        mode = load_mode_pack().get_mode(mode_slug)
    except Exception:
        return None
    if not mode.handoff_to:
        return None
    return _mode_slug(mode.handoff_to[0])


def build_workflow_context(
    *sources: dict[str, Any] | None,
    ui_mode: str | None = None,
    default_readiness_state: str | None = None,
) -> dict[str, Any]:
    """Merge workflow hints into a stable payload for logs and session meta."""
    workflow_mode: str | None = None
    owner: str | None = None
    handoff_to: str | None = None
    readiness_state: str | None = None
    ui_mode_label: str | None = _clean_value(_UI_MODE_LABELS.get(str(ui_mode or "").upper()))

    for source in sources:
        if not isinstance(source, dict):
            continue
        nested = _extract_nested_workflow(source)
        workflow_mode = workflow_mode or _mode_slug(
            nested.get("mode")
            or nested.get("workflow_mode")
            or source.get("mode")
            or source.get("workflow_mode")
            or source.get("workflow_lane")
        )
        owner = owner or _clean_value(
            nested.get("owner")
            or source.get("owner")
            or source.get("mode_owner")
            or source.get("operator")
        )
        handoff_to = handoff_to or _mode_slug(
            nested.get("handoff_to")
            or source.get("handoff_to")
            or source.get("next_mode")
            or source.get("route_target")
        )
        readiness_state = readiness_state or _mode_slug(
            nested.get("readiness_state")
            or source.get("readiness_state")
            or source.get("workflow_state")
        )
        if ui_mode_label is None:
            ui_mode_label = _clean_value(
                nested.get("ui_mode")
                or source.get("ui_mode")
                or _UI_MODE_LABELS.get(str(source.get("mode_key", "")).upper())
            )

    workflow_mode = workflow_mode or _mode_slug(_UI_MODE_TO_WORKFLOW_MODE.get(str(ui_mode or "").upper()))
    owner = owner or default_workflow_owner()
    handoff_to = handoff_to or default_handoff_for_mode(workflow_mode)
    readiness_state = readiness_state or _mode_slug(default_readiness_state)

    workflow: dict[str, Any] = {}
    if workflow_mode is not None:
        workflow["mode"] = workflow_mode
    if owner is not None:
        workflow["owner"] = owner
    if handoff_to is not None:
        workflow["handoff_to"] = handoff_to
    if readiness_state is not None:
        workflow["readiness_state"] = readiness_state
    if ui_mode_label is not None:
        workflow["ui_mode"] = ui_mode_label

    result: dict[str, Any] = {}
    if workflow_mode is not None:
        result["mode"] = workflow_mode
    if owner is not None:
        result["owner"] = owner
    if handoff_to is not None:
        result["handoff_to"] = handoff_to
    if readiness_state is not None:
        result["readiness_state"] = readiness_state
    if ui_mode_label is not None:
        result["ui_mode"] = ui_mode_label
    if workflow:
        result["workflow"] = workflow
    return result
