"""Tests for the Guardrails system.

Covers input/output/tool guardrails, blocking/parallel modes,
tripwires, autonomy levels, and the GuardrailRunner orchestrator.
"""

from __future__ import annotations

import pytest

from dharma_swarm.guardrails import (
    ActionTypeGuardrail,
    AutonomyGuardrail,
    AutonomyLevel,
    CallableGuardrail,
    ContentLengthGuardrail,
    GuardrailContext,
    GuardrailMode,
    GuardrailRunner,
    GuardrailVerdict,
    MimicryGuardrail,
    TelosInputGuardrail,
    create_default_runner,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def safe_context():
    return GuardrailContext(
        action="compute R_V metric",
        content="Participation ratio analysis results",
        tool_name="execute_function",
        agent="researcher",
        task_id="t1",
    )


@pytest.fixture()
def harmful_context():
    return GuardrailContext(
        action="rm -rf /important_data",
        content="delete all the things",
        tool_name="bash",
        agent="rogue",
    )


@pytest.fixture()
def runner():
    return GuardrailRunner()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelosInputGuardrail
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTelosInputGuardrail:
    @pytest.mark.asyncio
    async def test_safe_action_passes(self, safe_context):
        g = TelosInputGuardrail()
        result = await g.validate(safe_context)
        assert result.verdict in (GuardrailVerdict.PASS, GuardrailVerdict.WARN)

    @pytest.mark.asyncio
    async def test_harmful_action_fails(self, harmful_context):
        g = TelosInputGuardrail()
        result = await g.validate(harmful_context)
        assert result.verdict == GuardrailVerdict.FAIL

    @pytest.mark.asyncio
    async def test_mode_is_configurable(self):
        g = TelosInputGuardrail(mode=GuardrailMode.PARALLEL)
        assert g.mode == GuardrailMode.PARALLEL


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AutonomyGuardrail
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAutonomyGuardrail:
    @pytest.mark.asyncio
    async def test_within_bounds_passes(self):
        g = AutonomyGuardrail(max_autonomous_level=AutonomyLevel.AUTONOMOUS_ALERT)
        ctx = GuardrailContext(autonomy_level=AutonomyLevel.HUMAN_ON_LOOP)
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS

    @pytest.mark.asyncio
    async def test_exceeds_bounds_fails(self):
        g = AutonomyGuardrail(max_autonomous_level=AutonomyLevel.HUMAN_SUPERVISED)
        ctx = GuardrailContext(autonomy_level=AutonomyLevel.FULLY_AUTONOMOUS)
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.FAIL

    @pytest.mark.asyncio
    async def test_exact_boundary_passes(self):
        g = AutonomyGuardrail(max_autonomous_level=AutonomyLevel.HUMAN_ON_LOOP)
        ctx = GuardrailContext(autonomy_level=AutonomyLevel.HUMAN_ON_LOOP)
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ContentLengthGuardrail
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestContentLengthGuardrail:
    @pytest.mark.asyncio
    async def test_normal_length_passes(self):
        g = ContentLengthGuardrail(min_chars=10, max_chars=1000)
        ctx = GuardrailContext(content="This is a reasonable output with enough detail.")
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS

    @pytest.mark.asyncio
    async def test_too_short_warns(self):
        g = ContentLengthGuardrail(min_chars=100)
        ctx = GuardrailContext(content="short")
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.WARN

    @pytest.mark.asyncio
    async def test_too_long_warns(self):
        g = ContentLengthGuardrail(max_chars=10)
        ctx = GuardrailContext(content="x" * 100)
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.WARN


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MimicryGuardrail
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestMimicryGuardrail:
    @pytest.mark.asyncio
    async def test_empty_content_passes(self):
        g = MimicryGuardrail()
        ctx = GuardrailContext(content="")
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS

    @pytest.mark.asyncio
    async def test_normal_content_passes(self):
        g = MimicryGuardrail()
        ctx = GuardrailContext(content="The R_V metric shows contraction at Layer 27 with Cohen's d=-3.558")
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ActionTypeGuardrail
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestActionTypeGuardrail:
    @pytest.mark.asyncio
    async def test_safe_tool_passes(self):
        g = ActionTypeGuardrail()
        ctx = GuardrailContext(tool_name="read_file", action="read config")
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS

    @pytest.mark.asyncio
    async def test_dangerous_tool_warns(self):
        g = ActionTypeGuardrail()
        ctx = GuardrailContext(tool_name="bash", action="execute command")
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.WARN

    @pytest.mark.asyncio
    async def test_no_tool_passes(self):
        g = ActionTypeGuardrail()
        ctx = GuardrailContext()
        result = await g.validate(ctx)
        assert result.verdict == GuardrailVerdict.PASS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CallableGuardrail
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCallableGuardrail:
    @pytest.mark.asyncio
    async def test_simple_pass(self):
        g = CallableGuardrail("always_pass", lambda ctx: GuardrailVerdict.PASS)
        result = await g.validate(GuardrailContext())
        assert result.verdict == GuardrailVerdict.PASS

    @pytest.mark.asyncio
    async def test_tuple_return(self):
        g = CallableGuardrail(
            "custom_check",
            lambda ctx: (GuardrailVerdict.WARN, "something iffy"),
        )
        result = await g.validate(GuardrailContext())
        assert result.verdict == GuardrailVerdict.WARN
        assert "iffy" in result.reason

    @pytest.mark.asyncio
    async def test_exception_fails(self):
        def explode(ctx):
            raise ValueError("boom")

        g = CallableGuardrail("exploder", explode)
        result = await g.validate(GuardrailContext())
        assert result.verdict == GuardrailVerdict.FAIL
        assert "boom" in result.reason


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GuardrailRunner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGuardrailRunner:
    @pytest.mark.asyncio
    async def test_all_pass(self, runner, safe_context):
        runner.add_input(CallableGuardrail("a", lambda c: GuardrailVerdict.PASS))
        runner.add_input(CallableGuardrail("b", lambda c: GuardrailVerdict.PASS))
        summary = await runner.check_inputs(safe_context)
        assert summary.passed is True
        assert summary.pass_count == 2
        assert summary.fail_count == 0

    @pytest.mark.asyncio
    async def test_blocking_fail_stops_execution(self, runner):
        runner.add_input(CallableGuardrail("fail", lambda c: GuardrailVerdict.FAIL))
        runner.add_input(CallableGuardrail("never", lambda c: GuardrailVerdict.PASS))
        summary = await runner.check_inputs(GuardrailContext())
        assert summary.passed is False
        assert len(summary.results) == 1  # second never ran

    @pytest.mark.asyncio
    async def test_parallel_guardrails_run_after_blocking(self, runner):
        runner.add_input(CallableGuardrail("block_ok", lambda c: GuardrailVerdict.PASS))
        runner.add_input(CallableGuardrail(
            "parallel_ok", lambda c: GuardrailVerdict.PASS,
            mode=GuardrailMode.PARALLEL,
        ))
        summary = await runner.check_inputs(GuardrailContext())
        assert summary.passed is True
        assert summary.blocking_count == 1
        assert summary.parallel_count == 1

    @pytest.mark.asyncio
    async def test_parallel_fail_blocks(self, runner):
        runner.add_input(CallableGuardrail(
            "parallel_fail",
            lambda c: GuardrailVerdict.FAIL,
            mode=GuardrailMode.PARALLEL,
        ))
        summary = await runner.check_inputs(GuardrailContext())
        assert summary.passed is False

    @pytest.mark.asyncio
    async def test_output_guardrails(self, runner):
        runner.add_output(ContentLengthGuardrail(min_chars=10))
        ctx = GuardrailContext(content="This is long enough output")
        summary = await runner.check_outputs(ctx)
        assert summary.passed is True

    @pytest.mark.asyncio
    async def test_tool_guardrails(self, runner):
        runner.add_tool(ActionTypeGuardrail())
        ctx = GuardrailContext(tool_name="read_file")
        summary = await runner.check_tool(ctx)
        assert summary.passed is True

    @pytest.mark.asyncio
    async def test_telos_integration(self, safe_context):
        runner = GuardrailRunner()
        runner.add_input(TelosInputGuardrail())
        summary = await runner.check_inputs(safe_context)
        assert summary.passed is True

    @pytest.mark.asyncio
    async def test_telos_blocks_harm(self, harmful_context):
        runner = GuardrailRunner()
        runner.add_input(TelosInputGuardrail())
        summary = await runner.check_inputs(harmful_context)
        assert summary.passed is False

    def test_summary_output(self, runner):
        runner.add_input(CallableGuardrail("test_in", lambda c: GuardrailVerdict.PASS))
        runner.add_output(ContentLengthGuardrail())
        runner.add_tool(ActionTypeGuardrail())
        text = runner.summary()
        assert "Input (1)" in text
        assert "Output (1)" in text
        assert "Tool (1)" in text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Default Runner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDefaultRunner:
    @pytest.mark.asyncio
    async def test_default_runner_safe(self, safe_context):
        runner = create_default_runner()
        summary = await runner.check_inputs(safe_context)
        assert summary.passed is True

    @pytest.mark.asyncio
    async def test_default_runner_harmful(self, harmful_context):
        runner = create_default_runner()
        summary = await runner.check_inputs(harmful_context)
        assert summary.passed is False

    @pytest.mark.asyncio
    async def test_default_runner_output(self):
        runner = create_default_runner()
        ctx = GuardrailContext(content="Normal output text with substance")
        summary = await runner.check_outputs(ctx)
        assert summary.passed is True

    @pytest.mark.asyncio
    async def test_default_runner_custom_autonomy(self):
        runner = create_default_runner(max_autonomy=AutonomyLevel.HUMAN_SUPERVISED)
        ctx = GuardrailContext(autonomy_level=AutonomyLevel.FULLY_AUTONOMOUS)
        summary = await runner.check_inputs(ctx)
        assert summary.passed is False
