"""Tests for the Deterministic Logic Layer.

Covers all 6 block types, Pipeline execution, PipelineBuilder,
context resolution, failure propagation, and cost tracking.
"""

from __future__ import annotations

import asyncio

import pytest

from dharma_swarm.logic_layer import (
    ApplyAction,
    BlockKind,
    BlockStatus,
    Conditional,
    CreateVariable,
    ExecuteFunction,
    ExecutionContext,
    Loop,
    Pipeline,
    PipelineBuilder,
    UseLLM,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def ctx():
    """Bare execution context."""
    return ExecutionContext()


@pytest.fixture()
def registry():
    """Ontology registry for action tests."""
    from dharma_swarm.ontology import OntologyRegistry
    return OntologyRegistry.create_dharma_registry()


@pytest.fixture()
def ctx_with_registry(registry):
    """Context with ontology registry attached."""
    return ExecutionContext(registry=registry)


@pytest.fixture()
def ctx_with_llm():
    """Context with a mock LLM function."""

    async def mock_llm(prompt: str, config: dict) -> str:
        return f"LLM response to: {prompt[:50]}"

    return ExecutionContext(llm_fn=mock_llm)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CreateVariable
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCreateVariable:
    @pytest.mark.asyncio
    async def test_static_value(self, ctx):
        block = CreateVariable("model", "mistral-7b")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert result.deterministic is True
        assert result.tokens_used == 0
        assert ctx.get("model") == "mistral-7b"

    @pytest.mark.asyncio
    async def test_computed_value(self, ctx):
        ctx.set("a", 10)
        block = CreateVariable("doubled", compute=lambda c: c.get("a") * 2)
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("doubled") == 20

    @pytest.mark.asyncio
    async def test_compute_error(self, ctx):
        block = CreateVariable("bad", compute=lambda c: 1 / 0)
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "division by zero" in result.error


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ExecuteFunction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExecuteFunction:
    @pytest.mark.asyncio
    async def test_sync_function(self, ctx):
        def add(context, a="0", b="0"):
            return int(a) + int(b)

        block = ExecuteFunction(add, args={"a": "3", "b": "7"}, store_as="sum")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert result.deterministic is True
        assert ctx.get("sum") == 10

    @pytest.mark.asyncio
    async def test_async_function(self, ctx):
        async def async_work(context):
            return "done"

        block = ExecuteFunction(async_work, store_as="result")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("result") == "done"

    @pytest.mark.asyncio
    async def test_function_with_context_access(self, ctx):
        ctx.set("items", [1, 2, 3])

        def count_items(context):
            return len(context.get("items", []))

        block = ExecuteFunction(count_items, store_as="count")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("count") == 3

    @pytest.mark.asyncio
    async def test_function_failure(self, ctx):
        def boom(context):
            raise ValueError("kaboom")

        block = ExecuteFunction(boom)
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "kaboom" in result.error

    @pytest.mark.asyncio
    async def test_template_resolution_in_args(self, ctx):
        ctx.set("name", "Alice")

        def greet(context, who=""):
            return f"Hello {who}"

        block = ExecuteFunction(greet, args={"who": "{name}"}, store_as="greeting")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("greeting") == "Hello Alice"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Conditional
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestConditional:
    @pytest.mark.asyncio
    async def test_true_branch(self, ctx):
        ctx.set("ready", True)
        block = Conditional(
            condition=lambda c: c.get("ready"),
            if_true=CreateVariable("path", "true_branch"),
            if_false=CreateVariable("path", "false_branch"),
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("path") == "true_branch"

    @pytest.mark.asyncio
    async def test_false_branch(self, ctx):
        ctx.set("ready", False)
        block = Conditional(
            condition=lambda c: c.get("ready"),
            if_true=CreateVariable("path", "true_branch"),
            if_false=CreateVariable("path", "false_branch"),
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("path") == "false_branch"

    @pytest.mark.asyncio
    async def test_no_else_skipped(self, ctx):
        ctx.set("ready", False)
        block = Conditional(
            condition=lambda c: c.get("ready"),
            if_true=CreateVariable("val", 42),
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SKIPPED
        assert ctx.get("val") is None

    @pytest.mark.asyncio
    async def test_condition_error(self, ctx):
        block = Conditional(
            condition=lambda c: 1 / 0,
            if_true=CreateVariable("val", 1),
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "condition error" in result.error


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLoop:
    @pytest.mark.asyncio
    async def test_basic_loop(self, ctx):
        results_list: list[int] = []

        def collect(context):
            results_list.append(context.get("item"))
            return context.get("item")

        block = Loop(
            items_fn=lambda c: [10, 20, 30],
            body=ExecuteFunction(collect),
            item_var="item",
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert results_list == [10, 20, 30]
        assert result.deterministic is True
        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_loop_max_iterations(self, ctx):
        count = {"n": 0}

        def inc(context):
            count["n"] += 1

        block = Loop(
            items_fn=lambda c: list(range(200)),
            body=ExecuteFunction(inc),
            max_iterations=5,
        )
        result = await block.execute(ctx)
        assert count["n"] == 5

    @pytest.mark.asyncio
    async def test_loop_body_failure_stops(self, ctx):
        calls = {"n": 0}

        def maybe_fail(context):
            calls["n"] += 1
            if context.get("item") == 2:
                raise RuntimeError("fail at 2")

        block = Loop(
            items_fn=lambda c: [1, 2, 3],
            body=ExecuteFunction(maybe_fail),
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert calls["n"] == 2  # stopped at item 2

    @pytest.mark.asyncio
    async def test_loop_items_fn_error(self, ctx):
        block = Loop(
            items_fn=lambda c: [][1],  # IndexError
            body=CreateVariable("x", 1),
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "items_fn error" in result.error

    @pytest.mark.asyncio
    async def test_loop_store_as(self, ctx):
        def double(context):
            return context.get("n") * 2

        block = Loop(
            items_fn=lambda c: [1, 2, 3],
            body=ExecuteFunction(double),
            item_var="n",
            store_as="doubled",
        )
        result = await block.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("doubled") == [2, 4, 6]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ApplyAction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestApplyAction:
    @pytest.mark.asyncio
    async def test_no_registry_fails(self, ctx):
        block = ApplyAction("Experiment", "Design")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "no ontology registry" in result.error

    @pytest.mark.asyncio
    async def test_valid_action(self, ctx_with_registry):
        block = ApplyAction("Experiment", "Design", params={"name": "test"}, store_as="action_result")
        result = await block.execute(ctx_with_registry)
        assert result.status == BlockStatus.SUCCESS
        assert result.deterministic is True
        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_unknown_action(self, ctx_with_registry):
        block = ApplyAction("Experiment", "NonexistentAction")
        result = await block.execute(ctx_with_registry)
        assert result.status == BlockStatus.FAILED
        assert "no action" in result.error

    @pytest.mark.asyncio
    async def test_template_resolution(self, ctx_with_registry):
        ctx_with_registry.set("exp_id", "abc123")
        block = ApplyAction("Experiment", "Design", object_id="{exp_id}")
        result = await block.execute(ctx_with_registry)
        assert result.status == BlockStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_telos_gate_block(self, registry):
        def blocking_gate(action_name: str, params: dict) -> dict[str, str]:
            return {"AHIMSA": "BLOCK"}

        ctx = ExecutionContext(registry=registry, gate_fn=blocking_gate)
        block = ApplyAction("Experiment", "Design")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.BLOCKED
        assert "telos gate blocked" in result.error


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UseLLM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestUseLLM:
    @pytest.mark.asyncio
    async def test_no_llm_fn(self, ctx):
        block = UseLLM("Analyze {data}")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "no llm_fn" in result.error

    @pytest.mark.asyncio
    async def test_basic_call(self, ctx_with_llm):
        ctx_with_llm.set("data", "some metrics")
        block = UseLLM("Analyze {data}", store_as="analysis")
        result = await block.execute(ctx_with_llm)
        assert result.status == BlockStatus.SUCCESS
        assert result.deterministic is False
        assert result.tokens_used > 0
        assert "LLM response to" in ctx_with_llm.get("analysis")

    @pytest.mark.asyncio
    async def test_llm_error(self):
        async def failing_llm(prompt, config):
            raise RuntimeError("API error")

        ctx = ExecutionContext(llm_fn=failing_llm)
        block = UseLLM("test")
        result = await block.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert "API error" in result.error


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPipeline:
    @pytest.mark.asyncio
    async def test_simple_pipeline(self, ctx):
        pipeline = Pipeline(
            blocks=[
                CreateVariable("x", 10),
                CreateVariable("y", compute=lambda c: c.get("x") * 2),
            ],
            label="double",
        )
        result = await pipeline.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert ctx.get("y") == 20
        assert result.deterministic_blocks == 2
        assert result.nondeterministic_blocks == 0
        assert result.deterministic_ratio == 1.0
        assert result.total_tokens == 0

    @pytest.mark.asyncio
    async def test_pipeline_stops_on_failure(self, ctx):
        pipeline = Pipeline(
            blocks=[
                CreateVariable("x", 10),
                ExecuteFunction(lambda c: 1 / 0),  # boom
                CreateVariable("y", 20),  # should never run
            ],
        )
        result = await pipeline.execute(ctx)
        assert result.status == BlockStatus.FAILED
        assert len(result.block_results) == 2
        assert ctx.get("y") is None

    @pytest.mark.asyncio
    async def test_pipeline_continue_on_failure(self, ctx):
        pipeline = Pipeline(
            blocks=[
                CreateVariable("x", 10),
                ExecuteFunction(lambda c: 1 / 0),
                CreateVariable("y", 20),
            ],
            stop_on_failure=False,
        )
        result = await pipeline.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert len(result.block_results) == 3
        assert ctx.get("y") == 20

    @pytest.mark.asyncio
    async def test_pipeline_with_llm(self, ctx_with_llm):
        pipeline = Pipeline(
            blocks=[
                CreateVariable("data", "metrics"),
                UseLLM("Analyze: {data}", store_as="analysis"),
                CreateVariable("done", True),
            ],
            label="with_llm",
        )
        result = await pipeline.execute(ctx_with_llm)
        assert result.status == BlockStatus.SUCCESS
        assert result.deterministic_blocks == 2
        assert result.nondeterministic_blocks == 1
        assert abs(result.deterministic_ratio - 2 / 3) < 0.01

    @pytest.mark.asyncio
    async def test_pipeline_callback(self, ctx):
        completed: list[str] = []

        def on_complete(br):
            completed.append(br.block_id)

        pipeline = Pipeline(
            blocks=[
                CreateVariable("a", 1),
                CreateVariable("b", 2),
            ],
        )
        await pipeline.execute(ctx, on_block_complete=on_complete)
        assert len(completed) == 2

    @pytest.mark.asyncio
    async def test_block_summary(self, ctx_with_llm):
        pipeline = Pipeline(
            blocks=[
                CreateVariable("x", 1, label="set x"),
                ExecuteFunction(lambda c: None, label="compute"),
                Conditional(
                    condition=lambda c: True,
                    if_true=CreateVariable("y", 2, label="set y"),
                    label="check",
                ),
                UseLLM("test", label="analyze"),
            ],
            label="test_pipeline",
        )
        summary = pipeline.block_summary()
        assert "test_pipeline" in summary
        assert "[DET]" in summary
        assert "[LLM]" in summary
        assert "75%" in summary  # 3 det, 1 llm


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PipelineBuilder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPipelineBuilder:
    @pytest.mark.asyncio
    async def test_fluent_build(self, ctx_with_llm):
        def get_items(context):
            return [1, 2, 3]

        pipeline = (
            PipelineBuilder("fluent_test")
            .set("model", "mistral-7b")
            .call(get_items, store_as="items")
            .branch(
                condition=lambda c: c.get("items") is not None,
                if_true=CreateVariable("has_items", True),
            )
            .llm("Analyze {items}", store_as="analysis")
            .build()
        )
        result = await pipeline.execute(ctx_with_llm)
        assert result.status == BlockStatus.SUCCESS
        assert ctx_with_llm.get("model") == "mistral-7b"
        assert ctx_with_llm.get("has_items") is True
        assert "LLM response" in ctx_with_llm.get("analysis", "")

    @pytest.mark.asyncio
    async def test_builder_with_loop(self, ctx):
        accumulated: list[int] = []

        def collect(context):
            accumulated.append(context.get("n"))

        pipeline = (
            PipelineBuilder("loop_test")
            .set("numbers", [10, 20, 30])
            .loop(
                items_fn=lambda c: c.get("numbers"),
                body=ExecuteFunction(collect),
                item_var="n",
            )
            .build()
        )
        result = await pipeline.execute(ctx)
        assert result.status == BlockStatus.SUCCESS
        assert accumulated == [10, 20, 30]

    @pytest.mark.asyncio
    async def test_builder_with_action(self, ctx_with_registry):
        pipeline = (
            PipelineBuilder("action_test")
            .action("Experiment", "Design", params={"name": "test"})
            .build()
        )
        result = await pipeline.execute(ctx_with_registry)
        assert result.status == BlockStatus.SUCCESS

    def test_builder_add_arbitrary_block(self):
        custom = CreateVariable("custom", 42)
        pipeline = PipelineBuilder("custom").add(custom).build()
        assert len(pipeline.blocks) == 1
        assert pipeline.blocks[0] is custom


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ExecutionContext
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExecutionContext:
    def test_resolve_template(self):
        ctx = ExecutionContext(state={"name": "Alice", "count": 42})
        assert ctx.resolve("Hello {name}, you have {count} items") == "Hello Alice, you have 42 items"

    def test_resolve_no_match(self):
        ctx = ExecutionContext()
        assert ctx.resolve("Hello {unknown}") == "Hello {unknown}"

    def test_resolve_dict(self):
        ctx = ExecutionContext(state={"model": "mistral"})
        resolved = ctx.resolve_dict({"name": "{model}", "count": 5})
        assert resolved["name"] == "mistral"
        assert resolved["count"] == 5

    def test_metadata_immutable_pattern(self):
        ctx = ExecutionContext(metadata={"run_id": "abc"})
        assert ctx.metadata["run_id"] == "abc"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Integration: Pipeline + Ontology
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestIntegration:
    @pytest.mark.asyncio
    async def test_experiment_pipeline(self, registry):
        """Simulates the experiment pipeline from the PALANTIR_UPGRADE_PROMPT.md spec."""

        def load_prompts(context):
            return ["prompt_1", "prompt_2", "prompt_3"] * 10  # 30 prompts

        def compute_metrics(context):
            prompts = context.get("prompts", [])
            return {"rv_mean": 0.73, "n_prompts": len(prompts)}

        async def mock_llm(prompt: str, config: dict) -> str:
            return "R_V shows contraction in Layer 27"

        ctx = ExecutionContext(
            registry=registry,
            llm_fn=mock_llm,
            metadata={"executed_by": "test"},
        )

        pipeline = (
            PipelineBuilder("rv_experiment")
            .set("model", "mistral-7b")
            .call(load_prompts, store_as="prompts", label="load prompts")
            .branch(
                condition=lambda c: len(c.get("prompts", [])) >= 20,
                if_true=ExecuteFunction(compute_metrics, store_as="results", label="compute R_V"),
                if_false=ApplyAction("Experiment", "Fail", label="fail: too few prompts"),
                label="check prompt count",
            )
            .llm(
                "Analyze R_V measurements: {results}. What patterns?",
                store_as="analysis",
                label="interpret results",
            )
            .action(
                "Experiment", "Archive",
                params={"results": "{results}", "analysis": "{analysis}"},
                label="archive experiment",
            )
            .build()
        )

        result = await pipeline.execute(ctx)

        assert result.status == BlockStatus.SUCCESS
        assert result.deterministic_ratio > 0.5
        assert ctx.get("model") == "mistral-7b"
        assert ctx.get("results")["rv_mean"] == 0.73
        assert "contraction" in ctx.get("analysis", "")

        summary = pipeline.block_summary()
        assert "rv_experiment" in summary
        assert "80%" in summary  # 4 det blocks, 1 LLM = 80%

    @pytest.mark.asyncio
    async def test_telos_blocked_pipeline(self, registry):
        """Pipeline stops when telos gate blocks an action."""

        def blocking_gate(action_name: str, params: dict) -> dict[str, str]:
            return {"AHIMSA": "BLOCK"}

        ctx = ExecutionContext(
            registry=registry,
            gate_fn=blocking_gate,
        )

        pipeline = Pipeline(
            blocks=[
                CreateVariable("x", 1),
                ApplyAction("Experiment", "Design"),
                CreateVariable("y", 2),  # should not run
            ],
        )
        result = await pipeline.execute(ctx)
        assert result.status == BlockStatus.BLOCKED
        assert ctx.get("y") is None
        assert len(result.block_results) == 2
