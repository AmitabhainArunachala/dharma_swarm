"""GitHub App webhook handler for dharma_verify.

Receives GitHub webhook events (pull_request opened/synchronized),
verifies HMAC-SHA256 signatures, extracts diffs, runs the review
pipeline, and returns structured results.

The handler does NOT post comments back to GitHub -- that requires
a GitHub API client with installation tokens which will be added
in a later layer. This module focuses on:
    1. Webhook signature verification
    2. Payload parsing and routing
    3. Orchestrating the review pipeline
    4. Returning structured results for the caller to act on
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# -- Models ------------------------------------------------------------------


class WebhookResult(BaseModel):
    """Result of processing a webhook event."""

    event_type: str = ""
    action: str = ""
    processed: bool = False
    review: dict[str, Any] | None = None
    error: str = ""
    duration_ms: float = 0.0


class PREventContext(BaseModel):
    """Extracted context from a pull_request webhook event."""

    action: str = ""
    pr_number: int = 0
    pr_title: str = ""
    pr_body: str = ""
    repo_full_name: str = ""
    sender: str = ""
    head_sha: str = ""
    base_branch: str = ""
    head_branch: str = ""
    diff_url: str = ""
    patch_content: str = ""


# -- Handler -----------------------------------------------------------------


class VerifyWebhookHandler:
    """GitHub App webhook handler for dharma_verify.

    Verifies HMAC-SHA256 signatures on incoming payloads, routes
    events to the appropriate handler, and orchestrates the review
    pipeline for pull_request events.

    Args:
        app_id: GitHub App ID. Falls back to DHARMA_VERIFY_APP_ID env var.
        private_key: GitHub App private key (PEM). Falls back to
            DHARMA_VERIFY_PRIVATE_KEY env var.
        webhook_secret: Webhook signing secret. Falls back to
            DHARMA_VERIFY_WEBHOOK_SECRET env var.
    """

    # PR actions we actually want to review
    REVIEWABLE_ACTIONS: frozenset[str] = frozenset({
        "opened",
        "synchronize",
        "reopened",
    })

    def __init__(
        self,
        app_id: str = "",
        private_key: str = "",
        webhook_secret: str = "",
    ) -> None:
        self.app_id = app_id or os.environ.get("DHARMA_VERIFY_APP_ID", "")
        self.private_key = private_key or os.environ.get(
            "DHARMA_VERIFY_PRIVATE_KEY", ""
        )
        self.webhook_secret = webhook_secret or os.environ.get(
            "DHARMA_VERIFY_WEBHOOK_SECRET", ""
        )

        # In-memory stats (reset on restart -- persistent stats belong in DB)
        self._review_count: int = 0
        self._total_score: float = 0.0
        self._total_debt: float = 0.0

    # -- Signature verification ----------------------------------------------

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature.

        Args:
            payload: Raw request body bytes.
            signature: The X-Hub-Signature-256 header value
                (format: ``sha256=<hex>``).

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not self.webhook_secret:
            logger.warning(
                "DHARMA_VERIFY_WEBHOOK_SECRET not configured -- "
                "skipping signature verification (UNSAFE in production)"
            )
            return True

        if not signature or not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        received = signature[7:]  # strip "sha256=" prefix
        return hmac.compare_digest(expected, received)

    # -- Event routing -------------------------------------------------------

    async def handle_webhook(
        self,
        request_body: bytes,
        signature: str,
        event_type: str,
    ) -> WebhookResult:
        """Main entry point: verify signature and route to handler.

        Args:
            request_body: Raw bytes of the webhook POST body.
            signature: X-Hub-Signature-256 header value.
            event_type: X-GitHub-Event header value.

        Returns:
            WebhookResult with processing outcome.
        """
        start = time.monotonic()

        if not self.verify_signature(request_body, signature):
            return WebhookResult(
                event_type=event_type,
                processed=False,
                error="Invalid webhook signature",
                duration_ms=_elapsed_ms(start),
            )

        try:
            event = json.loads(request_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return WebhookResult(
                event_type=event_type,
                processed=False,
                error=f"Malformed JSON payload: {exc}",
                duration_ms=_elapsed_ms(start),
            )

        # Route by event type
        handler = self._event_handlers.get(event_type)
        if handler is None:
            return WebhookResult(
                event_type=event_type,
                action=event.get("action", ""),
                processed=False,
                error=f"Unhandled event type: {event_type}",
                duration_ms=_elapsed_ms(start),
            )

        result = await handler(self, event)
        result.duration_ms = _elapsed_ms(start)
        return result

    # -- Pull request handler ------------------------------------------------

    async def handle_pull_request(self, event: dict[str, Any]) -> WebhookResult:
        """Handle pull_request webhook events.

        Extracts diff content from the event payload, runs the review
        pipeline, and returns the result. Does not post comments to
        GitHub (that requires an authenticated API client).

        Args:
            event: Parsed webhook JSON payload.

        Returns:
            WebhookResult with review data if the PR was reviewed.
        """
        action = event.get("action", "")

        if action not in self.REVIEWABLE_ACTIONS:
            return WebhookResult(
                event_type="pull_request",
                action=action,
                processed=False,
                error=f"Skipped non-reviewable action: {action}",
            )

        # Extract PR context
        ctx = _extract_pr_context(event)

        # Get diff text -- in a real deployment this would fetch from
        # the GitHub API using an installation token. For now we use
        # whatever patch content is embedded in the event or provided
        # by the caller.
        diff_text = ctx.patch_content
        if not diff_text:
            return WebhookResult(
                event_type="pull_request",
                action=action,
                processed=False,
                error=(
                    "No diff content available in event payload. "
                    "GitHub API diff fetch not yet implemented."
                ),
            )

        # Run the review pipeline
        from dharma_swarm.verify.reviewer import review_pr

        review = review_pr(
            diff_text=diff_text,
            pr_title=ctx.pr_title,
            pr_body=ctx.pr_body,
        )

        # Update stats
        self._review_count += 1
        self._total_score += review.score.overall
        self._total_debt += review.comprehension_debt

        logger.info(
            "Reviewed PR #%d (%s) via webhook: verdict=%s, score=%.2f",
            ctx.pr_number,
            ctx.repo_full_name,
            review.verdict,
            review.score.overall,
        )

        return WebhookResult(
            event_type="pull_request",
            action=action,
            processed=True,
            review=asdict(review),
        )

    # -- Ping handler --------------------------------------------------------

    async def handle_ping(self, event: dict[str, Any]) -> WebhookResult:
        """Handle ping events (sent when a webhook is first configured)."""
        zen = event.get("zen", "")
        hook_id = event.get("hook_id", 0)
        logger.info("Webhook ping received: hook_id=%s, zen=%s", hook_id, zen)
        return WebhookResult(
            event_type="ping",
            action="ping",
            processed=True,
        )

    # -- Stats ---------------------------------------------------------------

    @property
    def stats(self) -> dict[str, Any]:
        """Return in-memory review statistics."""
        avg_score = (
            round(self._total_score / self._review_count, 4)
            if self._review_count > 0
            else 0.0
        )
        avg_debt = (
            round(self._total_debt / self._review_count, 4)
            if self._review_count > 0
            else 0.0
        )
        return {
            "review_count": self._review_count,
            "average_score": avg_score,
            "average_comprehension_debt": avg_debt,
        }

    # -- Event handler registry (class-level) --------------------------------

    _event_handlers: dict[str, Any] = {
        "pull_request": handle_pull_request,
        "ping": handle_ping,
    }


# -- Helpers -----------------------------------------------------------------


def _elapsed_ms(start: float) -> float:
    """Milliseconds elapsed since *start* (monotonic clock)."""
    return round((time.monotonic() - start) * 1000, 2)


def _extract_pr_context(event: dict[str, Any]) -> PREventContext:
    """Extract structured PR context from a webhook event payload."""
    pr = event.get("pull_request", {})
    repo = event.get("repository", {})
    head = pr.get("head", {})
    base = pr.get("base", {})

    return PREventContext(
        action=event.get("action", ""),
        pr_number=pr.get("number", 0),
        pr_title=pr.get("title", ""),
        pr_body=pr.get("body", "") or "",
        repo_full_name=repo.get("full_name", ""),
        sender=event.get("sender", {}).get("login", ""),
        head_sha=head.get("sha", ""),
        base_branch=base.get("ref", ""),
        head_branch=head.get("ref", ""),
        diff_url=pr.get("diff_url", ""),
        patch_content=event.get("_patch_content", ""),
    )
