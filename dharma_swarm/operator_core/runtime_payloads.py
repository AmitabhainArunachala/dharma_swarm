"""JSON-ready runtime payload builders for the shared operator core."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .adapters import runtime_snapshot_from_operator_snapshot

RUNTIME_PAYLOAD_VERSION = "v1"
RUNTIME_SNAPSHOT_DOMAIN = "runtime_snapshot"


def build_runtime_snapshot_payload(
    snapshot: dict[str, Any],
    *,
    repo_root: str,
    bridge_status: str,
    supervisor_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical runtime snapshot payload from operator snapshot truth."""

    canonical = runtime_snapshot_from_operator_snapshot(
        snapshot,
        repo_root=repo_root,
        bridge_status=bridge_status,
        supervisor_preview=supervisor_preview,
    )
    return {
        "version": RUNTIME_PAYLOAD_VERSION,
        "domain": RUNTIME_SNAPSHOT_DOMAIN,
        "snapshot": asdict(canonical),
    }
