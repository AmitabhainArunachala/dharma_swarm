"""Tests for the Workflow Compiler.

Covers definition, compilation, execution, checkpointing,
resumption, DAG ordering, and the decorator API.
"""

from __future__ import annotations

import pytest

from dharma_swarm.workflow import (
    CompiledWorkflow,
    StepStatus,
    WorkflowDefinition,
    WorkflowStatus,
    _REGISTRY,
    compile_workflow,
    list_workflows,
    workflow,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear workflow registry between tests."""
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WorkflowDefinition
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDefinition:
    def test_basic_definition(self):
        wf = WorkflowDefinition("test")
        s1 = wf.step("load", lambda i, c: "data")
        s2 = wf.step("process", lambda i, c: "result", inputs=[s1])
        compiled = wf.compile()
        assert compiled.name == "test"
        assert len(compiled.steps) == 2
        assert compiled.version  # has a hash

    def test_duplicate_step_name_raises(self):
        wf = WorkflowDefinition("test")
        wf.step("load", lambda i, c: None)
        with pytest.raises(ValueError, match="Duplicate"):
            wf.step("load", lambda i, c: None)

    def test_version_changes_with_structure(self):
        wf1 = WorkflowDefinition("v1")
        wf1.step("a", lambda i, c: None)
        c1 = wf1.compile()

        wf2 = WorkflowDefinition("v2")
        wf2.step("a", lambda i, c: None)
        wf2.step("b", lambda i, c: None)
        c2 = wf2.compile()

        assert c1.version != c2.version

    def test_deterministic_flag(self):
        wf = WorkflowDefinition("test")
        wf.step("det", lambda i, c: None, deterministic=True)
        wf.step("llm", lambda i, c: None, deterministic=False)
        compiled = wf.compile()
        assert compiled.steps[0].deterministic is True
        assert compiled.steps[1].deterministic is False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Execution
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExecution:
    @pytest.mark.asyncio
    async def test_simple_pipeline(self):
        wf = WorkflowDefinition("simple")
        wf.step("load", lambda inputs, ctx: {"model": "mistral"})
        wf.step("compute", lambda inputs, ctx: {"rv": 0.73})

        compiled = wf.compile()
        result = await compiled.execute()

        assert result.status == WorkflowStatus.COMPLETED
        assert result.deterministic_steps == 2
        assert result.deterministic_ratio == 1.0

    @pytest.mark.asyncio
    async def test_dependency_chain(self):
        """Steps receive outputs from their declared dependencies."""
        received: dict[str, dict] = {}

        def load(inputs, ctx):
            received["load"] = inputs
            return {"data": [1, 2, 3]}

        def process(inputs, ctx):
            received["process"] = inputs
            return {"count": len(inputs.get("load", {}).get("data", []))}

        wf = WorkflowDefinition("chain")
        s1 = wf.step("load", load)
        wf.step("process", process, inputs=[s1])

        compiled = wf.compile()
        result = await compiled.execute()

        assert result.status == WorkflowStatus.COMPLETED
        assert received["process"]["load"]["data"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_parallel_wave(self):
        """Independent steps run in the same wave."""
        order: list[str] = []

        def step_a(inputs, ctx):
            order.append("a")
            return "a"

        def step_b(inputs, ctx):
            order.append("b")
            return "b"

        def step_c(inputs, ctx):
            order.append("c")
            return "c"

        wf = WorkflowDefinition("parallel")
        s1 = wf.step("a", step_a)
        s2 = wf.step("b", step_b)
        wf.step("c", step_c, inputs=[s1, s2])

        compiled = wf.compile()
        waves = compiled.execution_order()

        # a and b should be in wave 1, c in wave 2
        wave1_names = {s.name for s in waves[0]}
        assert "a" in wave1_names
        assert "b" in wave1_names
        assert waves[1][0].name == "c"

    @pytest.mark.asyncio
    async def test_async_step(self):
        async def async_load(inputs, ctx):
            return {"async": True}

        wf = WorkflowDefinition("async_test")
        wf.step("load", async_load)
        compiled = wf.compile()
        result = await compiled.execute()
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_failure(self):
        def fail(inputs, ctx):
            raise RuntimeError("bad data")

        wf = WorkflowDefinition("failing")
        wf.step("load", lambda i, c: "ok")
        wf.step("fail", fail)

        compiled = wf.compile()
        result = await compiled.execute()
        assert result.status == WorkflowStatus.FAILED

    @pytest.mark.asyncio
    async def test_context_passed_to_steps(self):
        received_ctx = {}

        def check_ctx(inputs, ctx):
            received_ctx.update(ctx)
            return "ok"

        wf = WorkflowDefinition("ctx_test")
        wf.step("check", check_ctx)
        compiled = wf.compile()
        await compiled.execute(context={"model": "mistral", "seed": 42})

        assert received_ctx["model"] == "mistral"
        assert received_ctx["seed"] == 42

    @pytest.mark.asyncio
    async def test_deterministic_ratio(self):
        wf = WorkflowDefinition("ratio")
        wf.step("det1", lambda i, c: 1)
        wf.step("det2", lambda i, c: 2)
        wf.step("det3", lambda i, c: 3)
        wf.step("llm1", lambda i, c: "ai", deterministic=False)

        compiled = wf.compile()
        result = await compiled.execute()
        assert result.deterministic_steps == 3
        assert result.nondeterministic_steps == 1
        assert abs(result.deterministic_ratio - 0.75) < 0.01

    @pytest.mark.asyncio
    async def test_callback(self):
        completed: list[str] = []

        def on_complete(step):
            completed.append(step.name)

        wf = WorkflowDefinition("callback")
        wf.step("a", lambda i, c: 1)
        wf.step("b", lambda i, c: 2)

        compiled = wf.compile()
        await compiled.execute(on_step_complete=on_complete)
        assert len(completed) >= 1  # at least some steps completed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Checkpointing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCheckpointing:
    @pytest.mark.asyncio
    async def test_checkpoint_written(self, tmp_path):
        wf = WorkflowDefinition("cp_test")
        wf.step("load", lambda i, c: "data")
        compiled = wf.compile()
        await compiled.execute(checkpoint_dir=tmp_path)

        cp_file = tmp_path / "cp_test_checkpoint.json"
        assert cp_file.exists()

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, tmp_path):
        call_count = {"n": 0}

        def expensive(inputs, ctx):
            call_count["n"] += 1
            return "expensive_result"

        # First run
        wf1 = WorkflowDefinition("resume")
        wf1.step("expensive", expensive)
        wf1.step("cheap", lambda i, c: "cheap")
        c1 = wf1.compile()
        await c1.execute(checkpoint_dir=tmp_path)
        assert call_count["n"] == 1

        # Second run with same version — expensive step should be cached
        call_count["n"] = 0
        wf2 = WorkflowDefinition("resume")
        wf2.step("expensive", expensive)
        wf2.step("cheap", lambda i, c: "cheap")
        c2 = wf2.compile()
        result = await c2.execute(checkpoint_dir=tmp_path)
        assert call_count["n"] == 0  # cached from checkpoint
        assert result.resumed_from != ""

    @pytest.mark.asyncio
    async def test_version_mismatch_restarts(self, tmp_path):
        call_count = {"n": 0}

        def tracked(inputs, ctx):
            call_count["n"] += 1
            return "result"

        # First run
        wf1 = WorkflowDefinition("versioned")
        wf1.step("step1", tracked)
        c1 = wf1.compile()
        await c1.execute(checkpoint_dir=tmp_path)

        # Second run with different structure (different version hash)
        call_count["n"] = 0
        wf2 = WorkflowDefinition("versioned")
        wf2.step("step1", tracked)
        wf2.step("step2", lambda i, c: None)  # new step changes version
        c2 = wf2.compile()
        await c2.execute(checkpoint_dir=tmp_path)
        assert call_count["n"] == 1  # had to re-run because version changed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSummary:
    def test_summary_output(self):
        wf = WorkflowDefinition("summary_test")
        s1 = wf.step("load", lambda i, c: None)
        s2 = wf.step("process", lambda i, c: None, inputs=[s1])
        wf.step("analyze", lambda i, c: None, inputs=[s2], deterministic=False)

        compiled = wf.compile()
        text = compiled.summary()
        assert "summary_test" in text
        assert "load" in text
        assert "process" in text
        assert "analyze" in text
        assert "[DET]" in text
        assert "[LLM]" in text
        assert "67%" in text  # 2 det, 1 llm


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Decorator API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDecoratorAPI:
    def test_register_workflow(self):
        @workflow("test_wf")
        def define(wf):
            wf.step("a", lambda i, c: 1)

        assert "test_wf" in list_workflows()

    @pytest.mark.asyncio
    async def test_compile_and_run(self):
        @workflow("runnable")
        def define(wf):
            s1 = wf.step("load", lambda i, c: {"x": 42})
            wf.step("use", lambda i, c: i.get("load", {}).get("x", 0) * 2, inputs=[s1])

        compiled = compile_workflow("runnable")
        result = await compiled.execute()
        assert result.status == WorkflowStatus.COMPLETED

    def test_compile_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not registered"):
            compile_workflow("nonexistent")

    def test_list_workflows(self):
        @workflow("wf_a")
        def a(wf):
            pass

        @workflow("wf_b")
        def b(wf):
            pass

        assert list_workflows() == ["wf_a", "wf_b"]
