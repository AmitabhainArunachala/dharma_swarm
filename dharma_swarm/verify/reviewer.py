"""Generate structured PR reviews from scored diffs.

Orchestrates: parse diff -> score -> generate structured review -> verdict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from dharma_swarm.verify.scorer import DiffScore, score_diff

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------

_APPROVE_THRESHOLD = 0.8
_COMMENT_THRESHOLD = 0.5


@dataclass
class ReviewResult:
    """Complete review of a pull request or diff.

    Attributes:
        score: The underlying DiffScore with per-dimension breakdown.
        review_text: Full structured review as plain text.
        verdict: One of APPROVE, REQUEST_CHANGES, COMMENT.
        files_reviewed: List of file paths found in the diff.
        comprehension_debt: 1.0 - overall_score; how much understanding is missing.
        suggestions: Consolidated improvement suggestions.
    """

    score: DiffScore = field(default_factory=DiffScore)
    review_text: str = ""
    verdict: str = "COMMENT"
    files_reviewed: list[str] = field(default_factory=list)
    comprehension_debt: float = 1.0
    suggestions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Diff parsing (extract files list)
# ---------------------------------------------------------------------------

def _extract_files(diff_text: str) -> list[str]:
    """Extract file paths from a unified diff."""
    import re

    files: list[str] = []
    for line in diff_text.splitlines():
        m = re.match(r"^diff --git a/(.*?) b/(.*?)$", line)
        if m:
            path = m.group(2)
            if path not in files:
                files.append(path)
            continue
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            path = m.group(1)
            if path not in files:
                files.append(path)
    return files


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

def _determine_verdict(overall: float, issues: list[str]) -> str:
    """Determine review verdict from score and issues.

    Args:
        overall: Composite score in [0.0, 1.0].
        issues: List of issues found.

    Returns:
        One of: APPROVE, COMMENT, REQUEST_CHANGES.
    """
    has_critical = any("CRITICAL" in issue for issue in issues)

    if has_critical:
        return "REQUEST_CHANGES"
    if overall >= _APPROVE_THRESHOLD:
        return "APPROVE"
    if overall >= _COMMENT_THRESHOLD:
        return "COMMENT"
    return "REQUEST_CHANGES"


# ---------------------------------------------------------------------------
# Review text generation
# ---------------------------------------------------------------------------

def _severity_tag(issue: str) -> str:
    """Assign a severity tag based on issue text."""
    upper = issue.upper()
    if "CRITICAL" in upper:
        return "critical"
    if "WARNING" in upper:
        return "warning"
    return "info"


def _build_review_text(
    diff_score: DiffScore,
    verdict: str,
    pr_title: str,
    pr_body: str,
    files: list[str],
) -> str:
    """Build the full structured review text.

    Sections:
        - Summary (1-2 sentences)
        - Score breakdown by dimension
        - Issues found with severity
        - Suggestions for improvement
        - Verdict
    """
    sections: list[str] = []

    # --- Summary ---
    file_count = len(files)
    issue_count = len(diff_score.issues)
    summary = (
        f"Reviewed {file_count} file(s) with an overall quality score "
        f"of {diff_score.overall:.0%}."
    )
    if issue_count > 0:
        summary += f" Found {issue_count} issue(s) requiring attention."
    else:
        summary += " No significant issues detected."

    if pr_title:
        sections.append(f"PR: {pr_title}")
    sections.append(f"Summary: {summary}")
    sections.append("")

    # --- Score breakdown ---
    sections.append("Score Breakdown:")
    for dim_name, dim_score in sorted(diff_score.dimensions.items()):
        bar_filled = int(dim_score * 10)
        bar = "#" * bar_filled + "-" * (10 - bar_filled)
        sections.append(f"  {dim_name:<14s} [{bar}] {dim_score:.0%}")
    sections.append(f"  {'OVERALL':<14s} [{('#' * int(diff_score.overall * 10)) + ('-' * (10 - int(diff_score.overall * 10)))}] {diff_score.overall:.0%}")
    sections.append("")

    # --- Issues ---
    if diff_score.issues:
        sections.append("Issues:")
        for issue in diff_score.issues:
            tag = _severity_tag(issue)
            sections.append(f"  [{tag}] {issue}")
        sections.append("")

    # --- Suggestions ---
    if diff_score.suggestions:
        sections.append("Suggestions:")
        for suggestion in diff_score.suggestions:
            sections.append(f"  - {suggestion}")
        sections.append("")

    # --- Verdict ---
    sections.append(f"Verdict: {verdict}")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_pr(
    diff_text: str,
    pr_title: str = "",
    pr_body: str = "",
    context: str = "",
) -> ReviewResult:
    """Review a pull request or diff and produce a structured result.

    Scores the diff heuristically, generates a structured review with
    sections for summary, score breakdown, issues, suggestions, and
    verdict.

    Args:
        diff_text: Unified diff string (output of git diff).
        pr_title: Title of the pull request (optional).
        pr_body: Body/description of the pull request (optional).
        context: Additional context for scoring (optional).

    Returns:
        ReviewResult with score, review text, verdict, and comprehension debt.
    """
    # 1. Score the diff
    diff_score = score_diff(diff_text, context=context)

    # 2. Extract files
    files = _extract_files(diff_text)

    # 3. Determine verdict
    verdict = _determine_verdict(diff_score.overall, diff_score.issues)

    # 4. Build review text
    review_text = _build_review_text(
        diff_score=diff_score,
        verdict=verdict,
        pr_title=pr_title,
        pr_body=pr_body,
        files=files,
    )

    # 5. Comprehension debt
    comprehension_debt = round(1.0 - diff_score.overall, 4)

    result = ReviewResult(
        score=diff_score,
        review_text=review_text,
        verdict=verdict,
        files_reviewed=files,
        comprehension_debt=comprehension_debt,
        suggestions=list(diff_score.suggestions),
    )

    logger.info(
        "PR review complete: verdict=%s, score=%.2f, files=%d, issues=%d",
        verdict, diff_score.overall, len(files), len(diff_score.issues),
    )

    return result
