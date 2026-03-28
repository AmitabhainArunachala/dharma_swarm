"""Tests for dharma_swarm.verify.reviewer and comprehension tracker."""

from __future__ import annotations

import pytest

from dharma_swarm.verify.reviewer import ReviewResult, review_pr
from dharma_swarm.verify.comprehension import ComprehensionTracker


# ---------------------------------------------------------------------------
# Test diffs
# ---------------------------------------------------------------------------

CLEAN_DIFF = (
    "diff --git a/clean.py b/clean.py\n"
    "+++ b/clean.py\n"
    '+"""Clean module."""\n'
    "+\n"
    "+from __future__ import annotations\n"
    "+\n"
    "+\n"
    "+def process(data: list[str]) -> list[str]:\n"
    '+    """Process data safely."""\n'
    "+    try:\n"
    "+        return [d.strip() for d in data]\n"
    "+    except ValueError as exc:\n"
    "+        raise RuntimeError('bad data') from exc\n"
    "+\n"
    "+\n"
    "+def test_process() -> None:\n"
    '+    assert process([" hello "]) == ["hello"]\n'
)

RISKY_DIFF = (
    "diff --git a/danger.py b/danger.py\n"
    "+++ b/danger.py\n"
    '+api_key = "sk-SUPERSECRETKEY1234567890abcdef"\n'
    "+result = eval(user_input)\n"
)

MULTI_FILE_DIFF = (
    "diff --git a/a.py b/a.py\n"
    "+++ b/a.py\n"
    "+x = 1\n"
    "diff --git a/b.py b/b.py\n"
    "+++ b/b.py\n"
    "+y = 2\n"
)


class TestReviewPR:
    """Tests for the review_pr function."""

    def test_returns_review_result(self) -> None:
        review = review_pr(CLEAN_DIFF, pr_title="Clean code")
        assert isinstance(review, ReviewResult)

    def test_verdict_is_valid(self) -> None:
        review = review_pr(CLEAN_DIFF)
        assert review.verdict in ("APPROVE", "COMMENT", "REQUEST_CHANGES")

    def test_review_text_not_empty(self) -> None:
        review = review_pr(CLEAN_DIFF, pr_title="Feature X")
        assert review.review_text
        assert len(review.review_text) > 50

    def test_risky_code_requests_changes(self) -> None:
        review = review_pr(RISKY_DIFF, pr_title="Dangerous code")
        assert review.verdict == "REQUEST_CHANGES"
        assert any("CRITICAL" in i for i in review.score.issues)

    def test_clean_code_does_not_request_changes(self) -> None:
        review = review_pr(CLEAN_DIFF)
        assert review.verdict in ("APPROVE", "COMMENT")
        assert review.score.overall >= 0.4

    def test_comprehension_debt_bounded(self) -> None:
        review = review_pr(CLEAN_DIFF)
        assert 0.0 <= review.comprehension_debt <= 1.0

    def test_comprehension_debt_inverse_of_score(self) -> None:
        review = review_pr(CLEAN_DIFF)
        assert abs(review.comprehension_debt - (1.0 - review.score.overall)) < 0.001

    def test_files_reviewed_extracted(self) -> None:
        review = review_pr(MULTI_FILE_DIFF)
        assert len(review.files_reviewed) == 2
        assert "a.py" in review.files_reviewed
        assert "b.py" in review.files_reviewed

    def test_suggestions_propagated(self) -> None:
        review = review_pr(RISKY_DIFF)
        assert len(review.suggestions) > 0

    def test_review_text_contains_verdict(self) -> None:
        review = review_pr(CLEAN_DIFF)
        assert "Verdict:" in review.review_text

    def test_review_text_contains_score_breakdown(self) -> None:
        review = review_pr(CLEAN_DIFF)
        assert "Score Breakdown" in review.review_text

    def test_pr_title_in_review(self) -> None:
        review = review_pr(CLEAN_DIFF, pr_title="My Feature")
        assert "My Feature" in review.review_text

    def test_empty_diff_review(self) -> None:
        review = review_pr("")
        assert review.score.overall == 0.0
        assert review.verdict == "REQUEST_CHANGES"


class TestComprehensionTracker:
    """Tests for the comprehension debt tracker."""

    def test_record_and_query(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=0.8, files=["a.py"])
        tracker.record("pr#2", score=0.3, files=["b.py"])
        debts = tracker.debt_by_file()
        assert debts["a.py"] < debts["b.py"]

    def test_debt_values_correct(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=0.7, files=["x.py"])
        debts = tracker.debt_by_file()
        assert abs(debts["x.py"] - 0.3) < 0.01

    def test_hotspots_ordering(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=0.9, files=["good.py"])
        tracker.record("pr#2", score=0.1, files=["bad.py"])
        hotspots = tracker.hotspots(top_n=1)
        assert hotspots[0][0] == "bad.py"

    def test_hotspots_respects_top_n(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        for i in range(20):
            tracker.record(f"pr#{i}", score=i / 20.0, files=[f"file_{i}.py"])
        hotspots = tracker.hotspots(top_n=5)
        assert len(hotspots) == 5

    def test_persistence_across_instances(self, tmp_path) -> None:
        path = tmp_path / "debt.jsonl"
        t1 = ComprehensionTracker(persist_path=path)
        t1.record("pr#1", score=0.5, files=["x.py"])

        t2 = ComprehensionTracker(persist_path=path)
        assert "x.py" in t2.debt_by_file()

    def test_trend_insufficient_data(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        assert tracker.trend() == 0.0

    def test_empty_tracker_returns_empty(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        assert tracker.debt_by_file() == {}
        assert tracker.hotspots() == []

    def test_multiple_reviews_same_file(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=0.8, files=["app.py"])
        tracker.record("pr#2", score=0.4, files=["app.py"])
        debts = tracker.debt_by_file()
        # Average debt: (0.2 + 0.6) / 2 = 0.4
        assert abs(debts["app.py"] - 0.4) < 0.01

    def test_score_clamped(self, tmp_path) -> None:
        tracker = ComprehensionTracker(persist_path=tmp_path / "debt.jsonl")
        tracker.record("pr#1", score=1.5, files=["over.py"])
        tracker.record("pr#2", score=-0.5, files=["under.py"])
        debts = tracker.debt_by_file()
        assert debts["over.py"] == 0.0  # score=1.0 -> debt=0.0
        assert debts["under.py"] == 1.0  # score=0.0 -> debt=1.0
