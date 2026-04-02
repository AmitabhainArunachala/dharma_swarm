"""Shell-neutral session catalog and detail builders for the shared operator core."""

from __future__ import annotations

from typing import Any

from .session_payloads import build_session_catalog_payload, build_session_detail_payload
from .session_store import SessionStore


def build_session_catalog(
    store: SessionStore,
    *,
    cwd: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Build a normalized session catalog for TUI or dashboard shells."""
    return build_session_catalog_payload(store, cwd=cwd, limit=limit)


def build_session_detail(
    store: SessionStore,
    session_id: str,
    *,
    transcript_limit: int = 80,
) -> dict[str, Any]:
    """Build detailed session truth including replay state and compaction preview."""
    return build_session_detail_payload(store, session_id, transcript_limit=transcript_limit)
