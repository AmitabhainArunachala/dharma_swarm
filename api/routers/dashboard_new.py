"""Dashboard endpoints for conversation log, eval harness, audit, and loop supervisor.

Serves JSONL-backed data as JSON arrays.  All imports are try/excepted so the
API still starts even if a backing module is missing or broken.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Query

from api.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])

# ---------------------------------------------------------------------------
# Safe imports — return sensible defaults if module unavailable
# ---------------------------------------------------------------------------

_conversation_log = None
_eval_harness = None
_harness_audit = None
_loop_supervisor_mod = None

try:
    from dharma_swarm import conversation_log as _conversation_log
except Exception as exc:
    logger.warning("conversation_log unavailable: %s", exc)

try:
    from dharma_swarm import ecc_eval_harness as _eval_harness
except Exception as exc:
    logger.warning("ecc_eval_harness unavailable: %s", exc)

try:
    from dharma_swarm import harness_audit as _harness_audit
except Exception as exc:
    logger.warning("harness_audit unavailable: %s", exc)

try:
    from dharma_swarm import loop_supervisor as _loop_supervisor_mod
except Exception as exc:
    logger.warning("loop_supervisor unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Conversation Log
# ---------------------------------------------------------------------------

@router.get("/conversation-log/recent")
async def conversation_recent(
    hours: float = Query(24, ge=0.1, le=8760, description="Look-back window in hours"),
    role: Optional[str] = Query(None, description="Filter by role: user, assistant, system"),
) -> ApiResponse:
    """Return recent conversation entries from the unified log."""
    if _conversation_log is None:
        return ApiResponse(data=[], error="conversation_log module unavailable")
    try:
        entries = _conversation_log.load_recent(hours=hours, role=role)
        return ApiResponse(data=entries)
    except Exception as e:
        logger.exception("conversation-log/recent failed")
        return ApiResponse(data=[], error=str(e))


@router.get("/conversation-log/promises")
async def conversation_promises(
    hours: float = Query(24, ge=0.1, le=8760, description="Look-back window in hours"),
) -> ApiResponse:
    """Return detected promises from assistant responses."""
    if _conversation_log is None:
        return ApiResponse(data=[], error="conversation_log module unavailable")
    try:
        promises = _conversation_log.load_promises(hours=hours)
        return ApiResponse(data=promises)
    except Exception as e:
        logger.exception("conversation-log/promises failed")
        return ApiResponse(data=[], error=str(e))


@router.get("/conversation-log/stats")
async def conversation_stats(
    hours: float = Query(168, ge=0.1, le=8760, description="Stats window in hours (default 7 days)"),
) -> ApiResponse:
    """Return conversation statistics (counts by role, interface, session, promises)."""
    if _conversation_log is None:
        return ApiResponse(data={}, error="conversation_log module unavailable")
    try:
        s = _conversation_log.stats(hours=hours)
        return ApiResponse(data=s)
    except Exception as e:
        logger.exception("conversation-log/stats failed")
        return ApiResponse(data={}, error=str(e))


# ---------------------------------------------------------------------------
# Eval Harness
# ---------------------------------------------------------------------------

@router.get("/eval/latest")
async def eval_latest() -> ApiResponse:
    """Return the most recent eval harness report."""
    if _eval_harness is None:
        return ApiResponse(data=None, error="ecc_eval_harness module unavailable")
    try:
        latest = _eval_harness.load_latest()
        if latest is None:
            return ApiResponse(data=None, error="No eval results yet. Run: dgc eval run")
        return ApiResponse(data=latest)
    except Exception as e:
        logger.exception("eval/latest failed")
        return ApiResponse(data=None, error=str(e))


@router.get("/eval/trend")
async def eval_trend(
    last_n: int = Query(20, ge=1, le=200, description="Number of recent runs to return"),
) -> ApiResponse:
    """Return eval history for trend charting."""
    if _eval_harness is None:
        return ApiResponse(data=[], error="ecc_eval_harness module unavailable")
    try:
        history = _eval_harness.load_history()
        # Return most recent N entries
        recent = history[-last_n:] if len(history) > last_n else history
        return ApiResponse(data=recent)
    except Exception as e:
        logger.exception("eval/trend failed")
        return ApiResponse(data=[], error=str(e))


# ---------------------------------------------------------------------------
# Harness Audit
# ---------------------------------------------------------------------------

@router.get("/audit/latest")
async def audit_latest() -> ApiResponse:
    """Return the most recent 7-dimension audit scorecard."""
    if _harness_audit is None:
        return ApiResponse(data=None, error="harness_audit module unavailable")
    try:
        latest = _harness_audit.load_latest_audit()
        if latest is None:
            return ApiResponse(data=None, error="No audit results yet. Run: dgc audit")
        return ApiResponse(data=latest)
    except Exception as e:
        logger.exception("audit/latest failed")
        return ApiResponse(data=None, error=str(e))


@router.get("/audit/trend")
async def audit_trend(
    last_n: int = Query(20, ge=1, le=200, description="Number of recent audits to return"),
) -> ApiResponse:
    """Return audit history for trend charting."""
    if _harness_audit is None:
        return ApiResponse(data=[], error="harness_audit module unavailable")
    try:
        history = _harness_audit.load_audit_history()
        recent = history[-last_n:] if len(history) > last_n else history
        return ApiResponse(data=recent)
    except Exception as e:
        logger.exception("audit/trend failed")
        return ApiResponse(data=[], error=str(e))


# ---------------------------------------------------------------------------
# Loop Supervisor
# ---------------------------------------------------------------------------

@router.get("/supervisor/status")
async def supervisor_status() -> ApiResponse:
    """Return the loop supervisor state (stalls, alerts, tick counts)."""
    if _loop_supervisor_mod is None:
        return ApiResponse(data=None, error="loop_supervisor module unavailable")
    try:
        state = _loop_supervisor_mod.LoopSupervisor.load_state()
        if state is None:
            return ApiResponse(
                data={"loops": {}, "recent_alerts": [], "total_alerts": 0},
                error="No supervisor state yet. Start the orchestrator to generate data.",
            )
        return ApiResponse(data=state)
    except Exception as e:
        logger.exception("supervisor/status failed")
        return ApiResponse(data=None, error=str(e))
