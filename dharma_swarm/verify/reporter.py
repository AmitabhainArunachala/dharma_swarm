"""Format review results as GitHub-compatible markdown comments.

Produces markdown suitable for posting as a GitHub PR review comment,
with verdict badges, score tables, issue lists, and suggestions.
"""

from __future__ import annotations

from dharma_swarm.verify.reviewer import ReviewResult


# ---------------------------------------------------------------------------
# Verdict badges
# ---------------------------------------------------------------------------

_VERDICT_BADGES: dict[str, str] = {
    "APPROVE": "APPROVED",
    "COMMENT": "COMMENT",
    "REQUEST_CHANGES": "CHANGES REQUESTED",
}

_VERDICT_EMOJI: dict[str, str] = {
    "APPROVE": "✅",
    "COMMENT": "💬",
    "REQUEST_CHANGES": "❌",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_review_comment(review: ReviewResult) -> str:
    """Format a ReviewResult as a GitHub-compatible markdown comment.

    Produces a structured markdown comment with:
        - Header with verdict emoji and badge
        - Overall score as percentage
        - Dimension breakdown table
        - Issues list with severity tags
        - Suggestions as bullet points
        - Footer with dharma_verify attribution

    Args:
        review: The ReviewResult to format.

    Returns:
        Markdown string ready to post as a GitHub PR comment.
    """
    lines: list[str] = []

    # --- Header ---
    emoji = _VERDICT_EMOJI.get(review.verdict, "❓")
    badge = _VERDICT_BADGES.get(review.verdict, review.verdict)
    lines.append(f"## {emoji} {badge}")
    lines.append("")

    # --- Score badge ---
    pct = int(review.score.overall * 100)
    lines.append(f"**Overall Score: {pct}%**")
    lines.append("")

    # --- Dimension table ---
    if review.score.dimensions:
        lines.append("### Score Breakdown")
        lines.append("")
        lines.append("| Dimension | Score |")
        lines.append("|-----------|-------|")
        for dim_name, dim_score in sorted(review.score.dimensions.items()):
            lines.append(f"| {dim_name} | {dim_score:.0%} |")
        lines.append("")

    # --- Files reviewed ---
    if review.files_reviewed:
        lines.append(f"**Files reviewed**: {len(review.files_reviewed)}")
        lines.append("")

    # --- Issues ---
    if review.score.issues:
        lines.append("### Issues")
        lines.append("")
        for issue in review.score.issues:
            severity = _issue_severity_tag(issue)
            lines.append(f"- **[{severity}]** {issue}")
        lines.append("")

    # --- Suggestions ---
    if review.suggestions:
        lines.append("### Suggestions")
        lines.append("")
        for suggestion in review.suggestions:
            lines.append(f"- {suggestion}")
        lines.append("")

    # --- Comprehension debt ---
    if review.comprehension_debt > 0.3:
        debt_pct = int(review.comprehension_debt * 100)
        lines.append(f"**Comprehension debt**: {debt_pct}%")
        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append(
        "*Reviewed by [dharma_verify](https://github.com/dharma-verify) "
        "-- AI Code Verification Platform*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue_severity_tag(issue: str) -> str:
    """Derive a severity tag from issue text."""
    upper = issue.upper()
    if "CRITICAL" in upper:
        return "CRITICAL"
    if "WARNING" in upper:
        return "WARNING"
    return "INFO"
