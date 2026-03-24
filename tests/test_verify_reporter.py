"""Tests for dharma_swarm.verify.reporter."""

from __future__ import annotations

from dharma_swarm.verify.reviewer import ReviewResult, review_pr
from dharma_swarm.verify.reporter import format_review_comment
from dharma_swarm.verify.scorer import DiffScore


# ---------------------------------------------------------------------------
# Test diffs
# ---------------------------------------------------------------------------

CLEAN_DIFF = (
    "diff --git a/ok.py b/ok.py\n"
    "+++ b/ok.py\n"
    '+"""Module."""\n'
    "+def f(x: int) -> int:\n"
    '+    """Return x."""\n'
    "+    return x\n"
    "+def test_f():\n"
    "+    assert f(1) == 1\n"
)

RISKY_DIFF = (
    "diff --git a/bad.py b/bad.py\n"
    "+++ b/bad.py\n"
    "+eval(input())\n"
)


class TestFormatReviewComment:
    """Tests for markdown comment formatting."""

    def test_returns_string(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        assert isinstance(comment, str)

    def test_contains_dharma_verify_attribution(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        assert "dharma_verify" in comment or "dharma-verify" in comment

    def test_contains_score(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        assert "Score" in comment

    def test_contains_verdict_badge_approve_or_comment(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        assert "APPROVED" in comment or "COMMENT" in comment

    def test_contains_verdict_badge_changes(self) -> None:
        review = review_pr(RISKY_DIFF)
        comment = format_review_comment(review)
        assert "CHANGES REQUESTED" in comment or "CRITICAL" in comment

    def test_dimension_table_present(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        # Markdown table markers
        assert "Dimension" in comment
        assert "|" in comment

    def test_issues_section_when_issues_exist(self) -> None:
        review = review_pr(RISKY_DIFF)
        comment = format_review_comment(review)
        assert "Issues" in comment
        assert "CRITICAL" in comment

    def test_suggestions_section_when_suggestions_exist(self) -> None:
        review = review_pr(RISKY_DIFF)
        comment = format_review_comment(review)
        assert "Suggestion" in comment

    def test_no_issues_section_when_clean(self) -> None:
        # Build a ReviewResult manually with no issues
        score = DiffScore(overall=0.9, dimensions={"safety": 1.0}, issues=[], suggestions=[])
        review = ReviewResult(
            score=score,
            review_text="Clean",
            verdict="APPROVE",
            files_reviewed=["clean.py"],
            comprehension_debt=0.1,
            suggestions=[],
        )
        comment = format_review_comment(review)
        assert "Issues" not in comment

    def test_markdown_valid_structure(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        # Should start with a markdown header
        assert comment.startswith("## ")
        # Should end with footer
        assert comment.rstrip().endswith("*")

    def test_files_reviewed_count(self) -> None:
        review = review_pr(CLEAN_DIFF)
        comment = format_review_comment(review)
        assert "Files reviewed" in comment

    def test_comprehension_debt_shown_when_high(self) -> None:
        score = DiffScore(overall=0.3, dimensions={}, issues=[], suggestions=[])
        review = ReviewResult(
            score=score,
            review_text="Bad",
            verdict="REQUEST_CHANGES",
            files_reviewed=["x.py"],
            comprehension_debt=0.7,
            suggestions=[],
        )
        comment = format_review_comment(review)
        assert "Comprehension debt" in comment or "70%" in comment
