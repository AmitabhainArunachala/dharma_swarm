"""dharma_verify — AI Code Verification Platform.

Scores AI-generated code against thinkodynamic quality dimensions,
tracks comprehension debt, and produces structured PR reviews.

Built on dharma_swarm's existing governance stack:
    thinkodynamic_scorer → 6-dimension quality scoring
    telos_gates → 11-gate governance with reflective reroute
    guardrails → 4 types, 5 autonomy levels
    trajectory_collector → full provenance tracking
"""

from dharma_swarm.verify.scorer import DiffScore, score_diff, score_diff_with_llm
from dharma_swarm.verify.reviewer import ReviewResult, review_pr
from dharma_swarm.verify.reporter import format_review_comment
from dharma_swarm.verify.comprehension import ComprehensionTracker

__all__ = [
    "DiffScore",
    "score_diff",
    "score_diff_with_llm",
    "ReviewResult",
    "review_pr",
    "format_review_comment",
    "ComprehensionTracker",
]
