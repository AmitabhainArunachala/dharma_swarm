"""dharma_verify API endpoints.

Exposes the verify pipeline as REST endpoints:
    POST /api/verify/review   -- full PR review from diff text
    POST /api/verify/score    -- score-only (no verdict)
    GET  /api/verify/health   -- verify subsystem health
    GET  /api/verify/stats    -- review statistics
    POST /api/verify/webhook  -- GitHub App webhook receiver
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/verify", tags=["verify"])


# -- Request / Response Models -----------------------------------------------


class ReviewRequest(BaseModel):
    """Request body for the /review endpoint."""

    diff: str = Field(..., description="Unified diff text to review")
    title: str = Field("", description="PR title (optional)")
    body: str = Field("", description="PR description (optional)")
    context: str = Field("", description="Extra context for scoring (optional)")


class ScoreRequest(BaseModel):
    """Request body for the /score endpoint."""

    diff: str = Field(..., description="Unified diff text to score")
    context: str = Field("", description="Extra context for scoring (optional)")


class ReviewResponse(BaseModel):
    """Structured review result."""

    status: str = "ok"
    review: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class ScoreResponse(BaseModel):
    """Structured score result."""

    status: str = "ok"
    score: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class HealthResponse(BaseModel):
    """Verify subsystem health."""

    status: str = "ok"
    version: str = "0.1.0"
    subsystem: str = "dharma_verify"


class StatsResponse(BaseModel):
    """Review statistics."""

    status: str = "ok"
    review_count: int = 0
    average_score: float = 0.0
    average_comprehension_debt: float = 0.0


# -- Singleton handler -------------------------------------------------------


_webhook_handler = None


def _get_webhook_handler():
    """Lazy-load the VerifyWebhookHandler singleton."""
    global _webhook_handler
    if _webhook_handler is None:
        from dharma_swarm.verify.github_app import VerifyWebhookHandler

        _webhook_handler = VerifyWebhookHandler()
    return _webhook_handler


def reset_webhook_handler() -> None:
    """Reset the singleton (for testing)."""
    global _webhook_handler
    _webhook_handler = None


# -- Endpoints ---------------------------------------------------------------


@router.get("/health")
async def verify_health() -> HealthResponse:
    """Health check for the dharma_verify subsystem."""
    return HealthResponse()


@router.get("/stats")
async def verify_stats() -> StatsResponse:
    """Return review statistics from the webhook handler."""
    handler = _get_webhook_handler()
    stats = handler.stats
    return StatsResponse(
        review_count=stats["review_count"],
        average_score=stats["average_score"],
        average_comprehension_debt=stats["average_comprehension_debt"],
    )


@router.post("/review")
async def verify_review(req: ReviewRequest) -> ReviewResponse:
    """Review a diff and return full review with verdict.

    Accepts a unified diff string and optional PR metadata.
    Returns the complete review including scores, verdict,
    review text, and comprehension debt.
    """
    if not req.diff.strip():
        return ReviewResponse(
            status="error",
            error="Empty diff provided",
        )

    try:
        from dharma_swarm.verify.reviewer import review_pr

        review = review_pr(
            diff_text=req.diff,
            pr_title=req.title,
            pr_body=req.body,
            context=req.context,
        )
        return ReviewResponse(review=asdict(review))
    except Exception as exc:
        logger.exception("Review failed")
        return ReviewResponse(
            status="error",
            error=f"Review failed: {exc}",
        )


@router.post("/score")
async def verify_score(req: ScoreRequest) -> ScoreResponse:
    """Score a diff without the full review pipeline.

    Returns just the thinkodynamic dimension scores and issues,
    without verdict or formatted review text.
    """
    if not req.diff.strip():
        return ScoreResponse(
            status="error",
            error="Empty diff provided",
        )

    try:
        from dharma_swarm.verify.scorer import score_diff

        score = score_diff(req.diff, context=req.context)
        return ScoreResponse(score=asdict(score))
    except Exception as exc:
        logger.exception("Scoring failed")
        return ScoreResponse(
            status="error",
            error=f"Scoring failed: {exc}",
        )


@router.post("/webhook")
async def verify_webhook(
    request: Request,
    x_hub_signature_256: str = Header("", alias="X-Hub-Signature-256"),
    x_github_event: str = Header("", alias="X-GitHub-Event"),
) -> Any:
    """GitHub App webhook receiver.

    Verifies the HMAC-SHA256 signature, parses the event, and
    routes to the appropriate handler. Returns a structured result.

    The X-Hub-Signature-256 and X-GitHub-Event headers are required
    by the GitHub webhook protocol.
    """
    body = await request.body()
    handler = _get_webhook_handler()

    result = await handler.handle_webhook(
        request_body=body,
        signature=x_hub_signature_256,
        event_type=x_github_event,
    )

    # Return 401 for invalid signatures
    if result.error and not result.processed:
        if "Invalid webhook signature" in result.error:
            return Response(
                content=result.model_dump_json(),
                status_code=401,
                media_type="application/json",
            )

    return result.model_dump()
