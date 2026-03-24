"""Tests for dharma_verify reviewer + reporter + comprehension tracker."""

from __future__ import annotations

from dharma_swarm.verify.reviewer import ReviewResult, review_pr
from dharma_swarm.verify.reporter import format_review_comment
from dharma_swarm.verify.comprehension import ComprehensionTracker


class TestReviewPR:
    def test_basic_review(self):
        diff = (
            "diff --git a/app.py b/app.py\n"
            "+++ b/app.py\n"
            "+def hello():\n"
            "+    return 'world'\n"
        )
        review = review_pr(diff, pr_title="Add hello")
        assert isinstance(review, ReviewResult)
        assert review.verdict in ("APPROVE", "COMMENT", "REQUEST_CHANGES")
        assert review.review_text
        assert review.score.overall > 0.0

    def test_risky_pr_requests_changes(self):
        diff = (
            "diff --git a/danger.py b/danger.py\n"
            "+++ b/danger.py\n"
            "+api_key = 'sk-SUPERSECRETKEY1234567890abcdef'\n"
            "+result = eval(user_input)\n"
        )
        review = review_pr(diff, pr_title="Dangerous code")
        assert review.verdict == "REQUEST_CHANGES"
        assert any("CRITICAL" in i for i in review.score.issues)

    def test_clean_pr_approves(self):
        diff = (
            "diff --git a/clean.py b/clean.py\n"
            "+++ b/clean.py\n"
            '+\"\"\"Clean module.\"\"\"\n'
            "+\n"
            "+from __future__ import annotations\n"
            "+\n"
            "+\n"
            "+def process(data: list[str]) -> list[str]:\n"
            '+    \"\"\"Process data safely.\"\"\"\n'
            "+    try:\n"
            "+        return [d.strip() for d in data]\n"
            "+    except ValueError as exc:\n"
            "+        raise RuntimeError('bad data') from exc\n"
            "+\n"
            "+\n"
            "+def test_process() -> None:\n"
            '+    assert process([\" hello \"]) == [\"hello\"]\n'
        )
        review = review_pr(diff)
        # Should score well enough to at least COMMENT (not REQUEST_CHANGES)
        assert review.verdict in ("APPROVE", "COMMENT")
        assert review.score.overall >= 0.4

    def test_comprehension_debt(self):
        diff = (
            "diff --git a/x.py b/x.py\n"
            "+++ b/x.py\n"
            "+x = 1\n"
        )
        review = review_pr(diff)
        assert 0.0 <= review.comprehension_debt <= 1.0

    def test_files_reviewed(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "+++ b/a.py\n"
            "+x = 1\n"
            "diff --git a/b.py b/b.py\n"
            "+++ b/b.py\n"
            "+y = 2\n"
        )
        review = review_pr(diff)
        assert len(review.files_reviewed) == 2


class TestReporter:
    def test_format_approve(self):
        diff = (
            "diff --git a/ok.py b/ok.py\n"
            "+++ b/ok.py\n"
            '+\"\"\"Module.\"\"\"\n'
            "+def f(x: int) -> int:\n"
            '+    \"\"\"Return x.\"\"\"\n'
            "+    return x\n"
            "+def test_f():\n"
            "+    assert f(1) == 1\n"
        )
        review = review_pr(diff)
        comment = format_review_comment(review)
        assert "dharma_verify" in comment.lower() or "dharma" in comment.lower()
        assert "Score" in comment or "score" in comment

    def test_format_request_changes(self):
        diff = (
            "diff --git a/bad.py b/bad.py\n"
            "+++ b/bad.py\n"
            "+eval(input())\n"
        )
        review = review_pr(diff)
        comment = format_review_comment(review)
        assert "CRITICAL" in comment or "CHANGES" in comment or "❌" in comment


class TestComprehensionTracker:
    def test_record_and_debt(self, tmp_path):
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=0.8, files=["a.py"])
        tracker.record("pr#2", score=0.3, files=["b.py"])
        debts = tracker.debt_by_file()
        assert debts["a.py"] < debts["b.py"]

    def test_hotspots(self, tmp_path):
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=0.9, files=["good.py"])
        tracker.record("pr#2", score=0.1, files=["bad.py"])
        hotspots = tracker.hotspots(top_n=1)
        assert hotspots[0][0] == "bad.py"

    def test_persistence(self, tmp_path):
        path = tmp_path / "debt.jsonl"
        t1 = ComprehensionTracker(persist_path=path)
        t1.record("pr#1", score=0.5, files=["x.py"])

        t2 = ComprehensionTracker(persist_path=path)
        assert "x.py" in t2.debt_by_file()
