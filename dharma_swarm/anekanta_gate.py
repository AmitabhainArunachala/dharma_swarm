"""Anekanta (many-sidedness) epistemological gate.

Checks that proposals consider multiple epistemological frames:
mechanistic, phenomenological, and systems-level. Rooted in the
Jain principle of Anekantavada -- reality is perceived differently
from different vantage points, and no single view is complete.
"""

from __future__ import annotations

from pydantic import BaseModel

from dharma_swarm.models import GateResult

# ---------------------------------------------------------------------------
# Keyword sets for each epistemological frame
# ---------------------------------------------------------------------------

MECHANISTIC_KEYWORDS: frozenset[str] = frozenset({
    "mechanism", "circuit", "activation", "gradient", "weight",
    "layer", "neuron", "parameter", "computation", "optimization",
    "loss", "architecture",
})

PHENOMENOLOGICAL_KEYWORDS: frozenset[str] = frozenset({
    "experience", "awareness", "consciousness", "perception", "witness",
    "observer", "subjective", "phenomenal", "qualia", "first-person",
    "introspection", "recognition",
})

SYSTEMS_KEYWORDS: frozenset[str] = frozenset({
    "emergence", "feedback", "self-organization", "complexity",
    "adaptation", "interaction", "holistic", "network", "ecosystem",
    "integration", "dynamics", "resilience",
})

_FRAME_MAP: dict[str, frozenset[str]] = {
    "mechanistic": MECHANISTIC_KEYWORDS,
    "phenomenological": PHENOMENOLOGICAL_KEYWORDS,
    "systems": SYSTEMS_KEYWORDS,
}

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class AnekantaResult(BaseModel):
    """Result of an Anekanta epistemological diversity check."""

    gate_result: GateResult
    frames_detected: list[str]
    frame_count: int
    reason: str


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def evaluate_anekanta(description: str, content: str = "") -> AnekantaResult:
    """Evaluate epistemological diversity of a proposal.

    Args:
        description: Short description of the proposal.
        content: Optional longer body / diff / code content.

    Returns:
        AnekantaResult with gate verdict, detected frames, and reason.
    """
    combined = f"{description} {content}".lower()

    frames_detected: list[str] = []
    for frame_name, keywords in _FRAME_MAP.items():
        if any(kw in combined for kw in keywords):
            frames_detected.append(frame_name)

    frame_count = len(frames_detected)

    if frame_count == 3:
        return AnekantaResult(
            gate_result=GateResult.PASS,
            frames_detected=frames_detected,
            frame_count=frame_count,
            reason="All three epistemological frames represented",
        )

    if frame_count == 2:
        all_frames = set(_FRAME_MAP.keys())
        missing = (all_frames - set(frames_detected)).pop()
        return AnekantaResult(
            gate_result=GateResult.WARN,
            frames_detected=frames_detected,
            frame_count=frame_count,
            reason=f"Missing {missing} frame",
        )

    return AnekantaResult(
        gate_result=GateResult.FAIL,
        frames_detected=frames_detected,
        frame_count=frame_count,
        reason=f"Insufficient epistemological diversity: only {frame_count} frame(s)",
    )
