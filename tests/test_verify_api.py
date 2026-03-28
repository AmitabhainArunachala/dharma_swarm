"""Tests for dharma_verify API endpoints and GitHub App webhook.

Uses FastAPI TestClient with mocked verify core modules so tests
exercise the API/webhook layer without depending on ThinkodynamicScorer
or any LLM calls.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dharma_swarm.verify.reviewer import ReviewResult
from dharma_swarm.verify.scorer import DiffScore


# -- Fixtures ----------------------------------------------------------------


SAMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,5 @@
+import os
+
 def hello():
-    pass
+    print("hello")
"""

MOCK_DIFF_SCORE = DiffScore(
    overall=0.68,
    dimensions={
        "correctness": 0.5,
        "clarity": 0.8,
        "safety": 1.0,
        "completeness": 0.33,
        "efficiency": 0.8,
        "governance": 1.0,
    },
    issues=["No tests accompany this change"],
    suggestions=["Add tests covering the new/modified code paths"],
)

MOCK_REVIEW_RESULT = ReviewResult(
    score=MOCK_DIFF_SCORE,
    review_text="PR: Test PR\nSummary: Reviewed 1 file(s)...\nVerdict: COMMENT",
    verdict="COMMENT",
    files_reviewed=["foo.py"],
    comprehension_debt=0.32,
    suggestions=["Add tests covering the new/modified code paths"],
)

WEBHOOK_SECRET = "test-secret-key-for-dharma-verify"


def _make_signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Compute a valid X-Hub-Signature-256 header value."""
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


@pytest.fixture()
def client():
    """Create a TestClient using the dashboard API app.

    Resets the webhook handler singleton between tests so each test
    gets a clean handler with fresh stats.
    """
    from api.routers.verify import reset_webhook_handler

    reset_webhook_handler()

    from api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    reset_webhook_handler()


# -- Health ------------------------------------------------------------------


class TestVerifyHealth:
    def test_health_endpoint(self, client: TestClient):
        resp = client.get("/api/verify/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert data["subsystem"] == "dharma_verify"

    def test_health_no_auth_required(self, client: TestClient, monkeypatch):
        """Verify health endpoint works even with Bearer auth enabled."""
        monkeypatch.setenv("DASHBOARD_API_KEY", "some-api-key")
        resp = client.get("/api/verify/health")
        assert resp.status_code == 200


# -- Review ------------------------------------------------------------------


class TestVerifyReview:
    @patch("dharma_swarm.verify.reviewer.review_pr")
    def test_review_endpoint(self, mock_review, client: TestClient):
        mock_review.return_value = MOCK_REVIEW_RESULT

        resp = client.post(
            "/api/verify/review",
            json={"diff": SAMPLE_DIFF, "title": "Test PR", "body": "Test body"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        review = data["review"]
        assert review["verdict"] == "COMMENT"
        assert review["score"]["overall"] == 0.68
        assert review["comprehension_debt"] == 0.32
        assert "foo.py" in review["files_reviewed"]

    def test_review_empty_diff(self, client: TestClient):
        resp = client.post(
            "/api/verify/review",
            json={"diff": "   ", "title": "Empty"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "Empty diff" in data["error"]

    @patch(
        "dharma_swarm.verify.reviewer.review_pr",
        side_effect=ValueError("boom"),
    )
    def test_review_handles_exception(self, mock_review, client: TestClient):
        resp = client.post(
            "/api/verify/review",
            json={"diff": SAMPLE_DIFF},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "boom" in data["error"]


# -- Score -------------------------------------------------------------------


class TestVerifyScore:
    @patch("dharma_swarm.verify.scorer.score_diff")
    def test_score_endpoint(self, mock_score, client: TestClient):
        mock_score.return_value = MOCK_DIFF_SCORE

        resp = client.post(
            "/api/verify/score",
            json={"diff": SAMPLE_DIFF},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        score = data["score"]
        assert score["overall"] == 0.68
        assert "correctness" in score["dimensions"]
        assert "safety" in score["dimensions"]

    def test_score_empty_diff(self, client: TestClient):
        resp = client.post(
            "/api/verify/score",
            json={"diff": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "Empty diff" in data["error"]


# -- Stats -------------------------------------------------------------------


class TestVerifyStats:
    def test_stats_initial(self, client: TestClient):
        resp = client.get("/api/verify/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["review_count"] == 0
        assert data["average_score"] == 0.0
        assert data["average_comprehension_debt"] == 0.0


# -- Webhook Signature -------------------------------------------------------


class TestWebhookSignature:
    def test_valid_signature(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("DHARMA_VERIFY_WEBHOOK_SECRET", WEBHOOK_SECRET)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        payload = json.dumps({"zen": "testing", "hook_id": 42}).encode()
        sig = _make_signature(payload)

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is True
        assert data["event_type"] == "ping"

    def test_invalid_signature(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("DHARMA_VERIFY_WEBHOOK_SECRET", WEBHOOK_SECRET)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        payload = json.dumps({"zen": "testing"}).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["processed"] is False
        assert "Invalid webhook signature" in data["error"]

    def test_missing_signature_header(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("DHARMA_VERIFY_WEBHOOK_SECRET", WEBHOOK_SECRET)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        payload = json.dumps({"zen": "testing"}).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_no_secret_configured_passes(self, client: TestClient, monkeypatch):
        """When no secret is configured, signature check is skipped."""
        monkeypatch.delenv("DHARMA_VERIFY_WEBHOOK_SECRET", raising=False)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        payload = json.dumps({"zen": "open door", "hook_id": 1}).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is True


# -- Webhook PR Event --------------------------------------------------------


class TestWebhookPREvent:
    @patch("dharma_swarm.verify.reviewer.review_pr")
    def test_pr_opened_event(self, mock_review, client: TestClient, monkeypatch):
        monkeypatch.delenv("DHARMA_VERIFY_WEBHOOK_SECRET", raising=False)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        mock_review.return_value = MOCK_REVIEW_RESULT

        event = {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Add feature",
                "body": "Adding a new feature",
                "diff_url": "https://github.com/test/repo/pull/42.diff",
                "head": {"sha": "abc123", "ref": "feature-branch"},
                "base": {"ref": "main"},
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "testuser"},
            "_patch_content": SAMPLE_DIFF,
        }

        payload = json.dumps(event).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is True
        assert data["event_type"] == "pull_request"
        assert data["action"] == "opened"
        assert data["review"]["verdict"] == "COMMENT"
        assert data["review"]["score"]["overall"] == 0.68

    def test_pr_closed_event_skipped(self, client: TestClient, monkeypatch):
        monkeypatch.delenv("DHARMA_VERIFY_WEBHOOK_SECRET", raising=False)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        event = {
            "action": "closed",
            "pull_request": {"number": 1, "title": "x"},
            "repository": {"full_name": "t/r"},
        }

        payload = json.dumps(event).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is False
        assert "non-reviewable" in data["error"]

    def test_unhandled_event_type(self, client: TestClient, monkeypatch):
        monkeypatch.delenv("DHARMA_VERIFY_WEBHOOK_SECRET", raising=False)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        payload = json.dumps({"action": "created"}).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is False
        assert "Unhandled event type" in data["error"]

    def test_pr_no_patch_content(self, client: TestClient, monkeypatch):
        """PR event without _patch_content returns an error."""
        monkeypatch.delenv("DHARMA_VERIFY_WEBHOOK_SECRET", raising=False)

        from api.routers.verify import reset_webhook_handler

        reset_webhook_handler()

        event = {
            "action": "opened",
            "pull_request": {
                "number": 99,
                "title": "No diff",
                "body": "",
                "head": {"sha": "def456", "ref": "branch"},
                "base": {"ref": "main"},
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "user"},
        }

        payload = json.dumps(event).encode()

        resp = client.post(
            "/api/verify/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is False
        assert "No diff content" in data["error"]
