"""Steelman gate for proposal counterargument quality.

Ensures that proposals have considered counterarguments (steel-manning
opposing views) before proceeding. A proposal with no counterarguments
fails outright; one with only trivial counterarguments gets a warning.
"""

from __future__ import annotations

from pydantic import BaseModel

from dharma_swarm.models import GateResult


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class SteelmanCheck(BaseModel):
    """Input for a steelman counterargument check."""

    counterarguments: list[str] = []
    min_substantive_length: int = 20


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class SteelmanResult(BaseModel):
    """Result of a steelman counterargument check."""

    gate_result: GateResult
    total_counterarguments: int
    substantive_counterarguments: int
    reason: str


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def check_steelman(check: SteelmanCheck) -> SteelmanResult:
    """Evaluate whether a proposal includes substantive counterarguments.

    Args:
        check: A SteelmanCheck containing the list of counterarguments
            and the minimum character length for substantive status.

    Returns:
        SteelmanResult with gate verdict, counts, and reason.
    """
    total = len(check.counterarguments)
    substantive = sum(
        1
        for arg in check.counterarguments
        if len(arg.strip()) >= check.min_substantive_length
    )

    if total == 0:
        return SteelmanResult(
            gate_result=GateResult.FAIL,
            total_counterarguments=total,
            substantive_counterarguments=substantive,
            reason="No counterarguments provided; steelman requirement not met",
        )

    if substantive == 0:
        return SteelmanResult(
            gate_result=GateResult.WARN,
            total_counterarguments=total,
            substantive_counterarguments=substantive,
            reason=(
                f"Counterarguments present but none are substantive "
                f"(min {check.min_substantive_length} chars)"
            ),
        )

    return SteelmanResult(
        gate_result=GateResult.PASS,
        total_counterarguments=total,
        substantive_counterarguments=substantive,
        reason=f"{substantive} substantive counterargument(s) provided",
    )
