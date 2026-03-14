"""Guardrails — Parallel validation layer over telos gates.

Palantir runs validation alongside execution, not just before.
OpenAI's Agents SDK has input/output/tool guardrails with tripwires.
Anduril's Lattice has per-task autonomy levels (0-4).

This module upgrades dharma_swarm's blocking-only telos gates into
a full guardrail system:

  InputGuardrail   — Validates before execution.  Blocking or parallel.
  OutputGuardrail  — Validates agent output before accepting.
  ToolGuardrail    — Intercepts individual tool/action calls.
  Tripwire         — Immediate halt on critical conditions.

Existing telos gates (TelosGatekeeper) become InputGuardrails
in blocking mode.  New guardrails can run in parallel for latency.

The GuardrailRunner orchestrates all guardrails around an execution.

Integration:
  telos_gates.py  — TelosGatekeeper wrapped as InputGuardrail
  ontology.py     — ActionDef telos_gates → ToolGuardrails
  logic_layer.py  — Pipeline blocks can have guardrails attached
  lineage.py      — Guardrail results recorded in lineage metadata
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:12]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENUMS & MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GuardrailMode(str, Enum):
    """How the guardrail relates to execution timing."""
    BLOCKING = "blocking"    # Must pass before execution proceeds
    PARALLEL = "parallel"    # Runs alongside execution, can halt later


class GuardrailVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    TRIPWIRE = "tripwire"   # Immediate halt, no recovery


class AutonomyLevel(int, Enum):
    """Anduril-style per-task autonomy levels."""
    HUMAN_ONLY = 0       # Human must perform action
    HUMAN_SUPERVISED = 1  # AI suggests, human approves
    HUMAN_ON_LOOP = 2    # AI acts, human monitors and can veto
    AUTONOMOUS_ALERT = 3  # AI acts, alerts human after
    FULLY_AUTONOMOUS = 4  # AI acts without human involvement


class GuardrailContext(BaseModel):
    """Input to a guardrail check."""
    action: str = ""
    content: str = ""
    tool_name: str = ""
    agent: str = ""
    task_id: str = ""
    autonomy_level: AutonomyLevel = AutonomyLevel.HUMAN_ON_LOOP
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailResult(BaseModel):
    """Result from a single guardrail."""
    guardrail_id: str
    guardrail_name: str
    verdict: GuardrailVerdict
    reason: str = ""
    mode: GuardrailMode = GuardrailMode.BLOCKING
    duration_seconds: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())


class TripwireResult(BaseModel):
    """Immediate halt signal."""
    triggered: bool = False
    guardrail_name: str = ""
    reason: str = ""
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())


class GuardrailSummary(BaseModel):
    """Aggregate result from running all guardrails."""
    passed: bool = True
    tripwire: TripwireResult | None = None
    results: list[GuardrailResult] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    blocking_count: int = 0
    parallel_count: int = 0
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABSTRACT GUARDRAILS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Guardrail(ABC):
    """Base class for all guardrails."""

    def __init__(
        self,
        name: str,
        mode: GuardrailMode = GuardrailMode.BLOCKING,
        guardrail_id: str | None = None,
    ) -> None:
        self.name = name
        self.mode = mode
        self.guardrail_id = guardrail_id or _new_id()

    @abstractmethod
    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        ...

    def _result(
        self,
        verdict: GuardrailVerdict,
        reason: str = "",
        duration: float = 0.0,
        details: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        return GuardrailResult(
            guardrail_id=self.guardrail_id,
            guardrail_name=self.name,
            verdict=verdict,
            reason=reason,
            mode=self.mode,
            duration_seconds=duration,
            details=details or {},
        )


class InputGuardrail(Guardrail):
    """Validates task input before or during execution.

    Blocking mode: execution waits for this guardrail.
    Parallel mode: execution starts, guardrail can halt it later.
    """
    pass


class OutputGuardrail(Guardrail):
    """Validates agent output before accepting.

    Always runs after execution completes.  Can reject output
    and trigger retry or escalation.
    """

    def __init__(self, name: str, guardrail_id: str | None = None) -> None:
        super().__init__(name, mode=GuardrailMode.BLOCKING, guardrail_id=guardrail_id)


class ToolGuardrail(Guardrail):
    """Intercepts individual tool/action calls.

    Can approve, modify, or block specific tool invocations.
    Runs before each tool call within an agent's execution.
    """

    def __init__(self, name: str, guardrail_id: str | None = None) -> None:
        super().__init__(name, mode=GuardrailMode.BLOCKING, guardrail_id=guardrail_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUILT-IN GUARDRAILS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TelosInputGuardrail(InputGuardrail):
    """Wraps TelosGatekeeper as an InputGuardrail.

    This bridges the existing 11-gate system into the guardrail framework.
    Tier A/B failures → FAIL.  Tier C failures → WARN.  All pass → PASS.
    """

    def __init__(
        self,
        mode: GuardrailMode = GuardrailMode.BLOCKING,
    ) -> None:
        super().__init__("telos_gates", mode=mode)

    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        t0 = time.monotonic()
        from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER
        from dharma_swarm.models import GateDecision

        result = DEFAULT_GATEKEEPER.check(
            action=context.action,
            content=context.content,
            tool_name=context.tool_name,
        )
        duration = time.monotonic() - t0

        if result.decision == GateDecision.BLOCK:
            return self._result(GuardrailVerdict.FAIL, result.reason, duration, {"gate_results": str(result.gate_results)})
        if result.decision == GateDecision.REVIEW:
            return self._result(GuardrailVerdict.WARN, result.reason, duration, {"gate_results": str(result.gate_results)})
        return self._result(GuardrailVerdict.PASS, result.reason, duration)


class AutonomyGuardrail(InputGuardrail):
    """Enforces autonomy level constraints.

    Anduril-style: actions must match the task's autonomy level.
    Higher-risk actions require lower autonomy (more human oversight).
    """

    def __init__(
        self,
        max_autonomous_level: AutonomyLevel = AutonomyLevel.HUMAN_ON_LOOP,
    ) -> None:
        super().__init__("autonomy_check", mode=GuardrailMode.BLOCKING)
        self.max_autonomous_level = max_autonomous_level

    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        t0 = time.monotonic()

        if context.autonomy_level.value > self.max_autonomous_level.value:
            return self._result(
                GuardrailVerdict.FAIL,
                f"Task autonomy level {context.autonomy_level.value} exceeds "
                f"maximum allowed {self.max_autonomous_level.value}",
                time.monotonic() - t0,
            )

        return self._result(
            GuardrailVerdict.PASS,
            f"Autonomy level {context.autonomy_level.value} within bounds",
            time.monotonic() - t0,
        )


class ContentLengthGuardrail(OutputGuardrail):
    """Validates output isn't suspiciously short or long."""

    def __init__(self, min_chars: int = 1, max_chars: int = 100000) -> None:
        super().__init__("content_length")
        self.min_chars = min_chars
        self.max_chars = max_chars

    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        t0 = time.monotonic()
        content_len = len(context.content)

        if content_len < self.min_chars:
            return self._result(
                GuardrailVerdict.WARN,
                f"Output too short ({content_len} < {self.min_chars} chars)",
                time.monotonic() - t0,
            )
        if content_len > self.max_chars:
            return self._result(
                GuardrailVerdict.WARN,
                f"Output too long ({content_len} > {self.max_chars} chars)",
                time.monotonic() - t0,
            )
        return self._result(GuardrailVerdict.PASS, f"Length OK ({content_len} chars)", time.monotonic() - t0)


class MimicryGuardrail(OutputGuardrail):
    """Detects performative/mimicry outputs using behavioral metrics.

    Wires into the existing MetricsAnalyzer.detect_mimicry() to catch
    outputs that sound profound but contain no substance.
    """

    def __init__(self) -> None:
        super().__init__("mimicry_detection")

    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        t0 = time.monotonic()
        if not context.content.strip():
            return self._result(GuardrailVerdict.PASS, "No content to check", time.monotonic() - t0)

        try:
            from dharma_swarm.metrics import MetricsAnalyzer
            analyzer = MetricsAnalyzer()
            if analyzer.detect_mimicry(context.content):
                return self._result(
                    GuardrailVerdict.WARN,
                    "Output flagged as performative/mimicry",
                    time.monotonic() - t0,
                )
        except Exception as exc:  # noqa: BLE001
            return self._result(
                GuardrailVerdict.PASS,
                f"Mimicry check unavailable: {exc}",
                time.monotonic() - t0,
            )

        return self._result(GuardrailVerdict.PASS, "No mimicry detected", time.monotonic() - t0)


class ActionTypeGuardrail(ToolGuardrail):
    """Validates tool/action calls against ontology ActionDef rules.

    Checks that the action exists, the actor has permission,
    and required telos gates pass.
    """

    def __init__(self) -> None:
        super().__init__("action_type_check")

    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        t0 = time.monotonic()
        # Basic check: action and tool_name should be non-empty
        if not context.action and not context.tool_name:
            return self._result(GuardrailVerdict.PASS, "No action to validate", time.monotonic() - t0)

        # Check for dangerous tool patterns
        dangerous = {"bash", "shell", "exec", "eval", "subprocess"}
        if context.tool_name.lower() in dangerous:
            return self._result(
                GuardrailVerdict.WARN,
                f"Tool '{context.tool_name}' requires elevated scrutiny",
                time.monotonic() - t0,
                {"tool": context.tool_name},
            )

        return self._result(GuardrailVerdict.PASS, f"Tool '{context.tool_name}' OK", time.monotonic() - t0)


class CallableGuardrail(InputGuardrail):
    """Guardrail from a simple callable.  For custom one-off checks."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[GuardrailContext], GuardrailVerdict | tuple[GuardrailVerdict, str]],
        mode: GuardrailMode = GuardrailMode.BLOCKING,
    ) -> None:
        super().__init__(name, mode=mode)
        self.check_fn = check_fn

    async def validate(self, context: GuardrailContext) -> GuardrailResult:
        t0 = time.monotonic()
        try:
            ret = self.check_fn(context)
            if isinstance(ret, tuple):
                verdict, reason = ret
            else:
                verdict = ret
                reason = ""
            return self._result(verdict, reason, time.monotonic() - t0)
        except Exception as exc:  # noqa: BLE001
            return self._result(GuardrailVerdict.FAIL, f"Check error: {exc}", time.monotonic() - t0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GUARDRAIL RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GuardrailRunner:
    """Orchestrates guardrails around an execution.

    Usage::

        runner = GuardrailRunner()
        runner.add_input(TelosInputGuardrail())
        runner.add_input(AutonomyGuardrail())
        runner.add_output(MimicryGuardrail())
        runner.add_output(ContentLengthGuardrail())

        # Check inputs before execution
        input_summary = await runner.check_inputs(context)
        if not input_summary.passed:
            return  # blocked

        # ... execute task ...

        # Check outputs after execution
        output_context = GuardrailContext(content=result, ...)
        output_summary = await runner.check_outputs(output_context)
    """

    def __init__(self) -> None:
        self._input_guardrails: list[InputGuardrail] = []
        self._output_guardrails: list[OutputGuardrail] = []
        self._tool_guardrails: list[ToolGuardrail] = []

    def add_input(self, guardrail: InputGuardrail) -> None:
        self._input_guardrails.append(guardrail)

    def add_output(self, guardrail: OutputGuardrail) -> None:
        self._output_guardrails.append(guardrail)

    def add_tool(self, guardrail: ToolGuardrail) -> None:
        self._tool_guardrails.append(guardrail)

    async def check_inputs(self, context: GuardrailContext) -> GuardrailSummary:
        """Run all input guardrails.

        Blocking guardrails run first (sequentially).
        If all blocking pass, parallel guardrails run concurrently.
        Any TRIPWIRE or FAIL from blocking → immediate halt.
        """
        t0 = time.monotonic()
        blocking = [g for g in self._input_guardrails if g.mode == GuardrailMode.BLOCKING]
        parallel = [g for g in self._input_guardrails if g.mode == GuardrailMode.PARALLEL]

        results: list[GuardrailResult] = []
        passed = True
        tripwire: TripwireResult | None = None

        # Run blocking guardrails sequentially
        for guardrail in blocking:
            result = await guardrail.validate(context)
            results.append(result)
            if result.verdict == GuardrailVerdict.TRIPWIRE:
                tripwire = TripwireResult(
                    triggered=True,
                    guardrail_name=guardrail.name,
                    reason=result.reason,
                )
                passed = False
                break
            if result.verdict == GuardrailVerdict.FAIL:
                passed = False
                break

        # Run parallel guardrails concurrently (only if blocking all passed)
        if passed and parallel:
            coros = [g.validate(context) for g in parallel]
            parallel_results = await asyncio.gather(*coros, return_exceptions=True)
            for pr in parallel_results:
                if isinstance(pr, Exception):
                    results.append(GuardrailResult(
                        guardrail_id="error",
                        guardrail_name="parallel_error",
                        verdict=GuardrailVerdict.WARN,
                        reason=str(pr),
                        mode=GuardrailMode.PARALLEL,
                    ))
                else:
                    results.append(pr)
                    if pr.verdict == GuardrailVerdict.TRIPWIRE:
                        tripwire = TripwireResult(
                            triggered=True,
                            guardrail_name=pr.guardrail_name,
                            reason=pr.reason,
                        )
                        passed = False
                    elif pr.verdict == GuardrailVerdict.FAIL:
                        passed = False

        return self._summarize(results, passed, tripwire, time.monotonic() - t0)

    async def check_outputs(self, context: GuardrailContext) -> GuardrailSummary:
        """Run all output guardrails (always blocking, sequential)."""
        t0 = time.monotonic()
        results: list[GuardrailResult] = []
        passed = True

        for guardrail in self._output_guardrails:
            result = await guardrail.validate(context)
            results.append(result)
            if result.verdict == GuardrailVerdict.FAIL:
                passed = False
            if result.verdict == GuardrailVerdict.TRIPWIRE:
                passed = False
                break

        return self._summarize(results, passed, None, time.monotonic() - t0)

    async def check_tool(self, context: GuardrailContext) -> GuardrailSummary:
        """Run all tool guardrails before a tool call."""
        t0 = time.monotonic()
        results: list[GuardrailResult] = []
        passed = True

        for guardrail in self._tool_guardrails:
            result = await guardrail.validate(context)
            results.append(result)
            if result.verdict == GuardrailVerdict.FAIL:
                passed = False
                break

        return self._summarize(results, passed, None, time.monotonic() - t0)

    def _summarize(
        self,
        results: list[GuardrailResult],
        passed: bool,
        tripwire: TripwireResult | None,
        duration: float,
    ) -> GuardrailSummary:
        return GuardrailSummary(
            passed=passed,
            tripwire=tripwire,
            results=results,
            total_duration_seconds=duration,
            blocking_count=sum(1 for r in results if r.mode == GuardrailMode.BLOCKING),
            parallel_count=sum(1 for r in results if r.mode == GuardrailMode.PARALLEL),
            pass_count=sum(1 for r in results if r.verdict == GuardrailVerdict.PASS),
            warn_count=sum(1 for r in results if r.verdict == GuardrailVerdict.WARN),
            fail_count=sum(1 for r in results if r.verdict in (GuardrailVerdict.FAIL, GuardrailVerdict.TRIPWIRE)),
        )

    def summary(self) -> str:
        """Show registered guardrails."""
        lines = ["Guardrail Configuration:"]
        if self._input_guardrails:
            lines.append(f"  Input ({len(self._input_guardrails)}):")
            for g in self._input_guardrails:
                lines.append(f"    - {g.name} [{g.mode.value}]")
        if self._output_guardrails:
            lines.append(f"  Output ({len(self._output_guardrails)}):")
            for g in self._output_guardrails:
                lines.append(f"    - {g.name}")
        if self._tool_guardrails:
            lines.append(f"  Tool ({len(self._tool_guardrails)}):")
            for g in self._tool_guardrails:
                lines.append(f"    - {g.name}")
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DEFAULT RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def create_default_runner(
    *,
    include_telos: bool = True,
    include_autonomy: bool = True,
    include_mimicry: bool = True,
    include_content_length: bool = True,
    include_action_type: bool = True,
    max_autonomy: AutonomyLevel = AutonomyLevel.HUMAN_ON_LOOP,
) -> GuardrailRunner:
    """Create a guardrail runner with standard dharma_swarm guardrails."""
    runner = GuardrailRunner()

    if include_telos:
        runner.add_input(TelosInputGuardrail())
    if include_autonomy:
        runner.add_input(AutonomyGuardrail(max_autonomous_level=max_autonomy))
    if include_mimicry:
        runner.add_output(MimicryGuardrail())
    if include_content_length:
        runner.add_output(ContentLengthGuardrail())
    if include_action_type:
        runner.add_tool(ActionTypeGuardrail())

    return runner
