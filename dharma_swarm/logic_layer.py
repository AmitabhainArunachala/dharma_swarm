"""Deterministic Logic Layer — Palantir AIP Logic for dharma_swarm.

Six block types, five deterministic, one non-deterministic:

  ApplyAction     — Ontology mutation via typed ActionDef.  No tokens.
  ExecuteFunction — Deterministic callable.                 No tokens.
  Conditional     — If/else branching on context state.     No tokens.
  Loop            — Iterate over items with a body block.   No tokens.
  CreateVariable  — Set a value in context.                 No tokens.
  UseLLM          — NON-DETERMINISTIC.  Uses tokens.        Use sparingly.

Pipeline chains blocks sequentially.  ExecutionContext carries state.
Every block records its result in the audit trail.  Every pipeline
records the ratio of deterministic vs LLM blocks actually executed.

The goal: 80% deterministic, 20% LLM.  Palantir proved this works
at nation-state scale.  We take the precision, add telos gates.

Integration:
  ontology.py      — ApplyAction calls registry.execute_action()
  decision_router  — route() determines reflex/deliberative/escalate
  telos_gates      — gate checks wired into ApplyAction
  dag_executor     — Pipeline can be used as a runner_fn
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
# ENUMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BlockKind(str, Enum):
    """Discriminant for the 6 logic block types."""
    APPLY_ACTION = "apply_action"
    EXECUTE_FUNCTION = "execute_function"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    CREATE_VARIABLE = "create_variable"
    USE_LLM = "use_llm"


class BlockStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXECUTION CONTEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ExecutionContext:
    """Mutable state bag threaded through a pipeline.

    Carries:
      state     — key/value store (variables, intermediate results)
      registry  — ontology registry reference (optional)
      gate_fn   — telos gate function (optional)
      llm_fn    — async callable for LLM inference (optional)
      metadata  — immutable pipeline-level config
    """

    def __init__(
        self,
        state: dict[str, Any] | None = None,
        registry: Any | None = None,
        gate_fn: Callable[[str, dict[str, Any]], dict[str, str]] | None = None,
        llm_fn: (
            Callable[[str, dict[str, Any]], Coroutine[Any, Any, str]] | None
        ) = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.state: dict[str, Any] = dict(state) if state else {}
        self.registry = registry
        self.gate_fn = gate_fn
        self.llm_fn = llm_fn
        self.metadata: dict[str, Any] = dict(metadata) if metadata else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def resolve(self, template: str) -> str:
        """Resolve {variable} references in a string template."""
        result = template
        for key, value in self.state.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result

    def resolve_dict(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve {variable} references in dict values."""
        resolved: dict[str, Any] = {}
        for k, v in params.items():
            if isinstance(v, str) and "{" in v and "}" in v:
                resolved[k] = self.resolve(v)
            else:
                resolved[k] = v
        return resolved


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK RESULT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BlockResult(BaseModel):
    """Result of executing a single logic block."""
    block_id: str
    kind: BlockKind
    status: BlockStatus
    output: Any = None
    error: str = ""
    duration_seconds: float = 0.0
    deterministic: bool = True
    tokens_used: int = 0
    started_at: str = ""
    finished_at: str = ""
    child_results: list["BlockResult"] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABSTRACT BASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LogicBlock(ABC):
    """Base for all logic blocks.

    Every block has:
      - A kind (discriminant)
      - A unique ID
      - An optional label for audit trails
      - execute(context) -> BlockResult
    """

    def __init__(
        self,
        kind: BlockKind,
        label: str = "",
        block_id: str | None = None,
        store_as: str = "",
    ) -> None:
        self.kind = kind
        self.block_id = block_id or _new_id()
        self.label = label
        self.store_as = store_as  # if set, output stored in context.state[store_as]

    @abstractmethod
    async def execute(self, context: ExecutionContext) -> BlockResult:
        ...

    def _start_result(self) -> BlockResult:
        return BlockResult(
            block_id=self.block_id,
            kind=self.kind,
            status=BlockStatus.RUNNING,
            started_at=_utc_now().isoformat(),
        )

    def _finish(
        self,
        result: BlockResult,
        *,
        status: BlockStatus,
        output: Any = None,
        error: str = "",
        tokens: int = 0,
        context: ExecutionContext | None = None,
    ) -> BlockResult:
        result.status = status
        result.output = output
        result.error = error
        result.tokens_used = tokens
        result.finished_at = _utc_now().isoformat()
        if self.store_as and context and status == BlockStatus.SUCCESS:
            context.set(self.store_as, output)
        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK 1: APPLY ACTION  (deterministic ontology mutation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ApplyAction(LogicBlock):
    """Execute a typed ontology action.  No LLM.  No tokens.

    Calls registry.execute_action() with the resolved params.
    Telos gates run if gate_fn is set on the context.
    """

    def __init__(
        self,
        object_type: str,
        action_name: str,
        object_id: str = "",
        params: dict[str, Any] | None = None,
        *,
        label: str = "",
        block_id: str | None = None,
        store_as: str = "",
    ) -> None:
        super().__init__(BlockKind.APPLY_ACTION, label=label, block_id=block_id, store_as=store_as)
        self.object_type = object_type
        self.action_name = action_name
        self.object_id = object_id  # can be "{var}" template
        self.params = params or {}

    async def execute(self, context: ExecutionContext) -> BlockResult:
        t0 = time.monotonic()
        result = self._start_result()

        registry = context.registry
        if registry is None:
            return self._finish(result, status=BlockStatus.FAILED, error="no ontology registry in context")

        resolved_obj_id = context.resolve(self.object_id) if self.object_id else ""
        resolved_params = context.resolve_dict(self.params)

        try:
            execution = registry.execute_action(
                object_type=self.object_type,
                action_name=self.action_name,
                object_id=resolved_obj_id,
                params=resolved_params,
                executed_by=context.metadata.get("executed_by", "logic_layer"),
                gate_check=context.gate_fn,
            )
            result.duration_seconds = time.monotonic() - t0

            if execution.result == "blocked":
                return self._finish(
                    result,
                    status=BlockStatus.BLOCKED,
                    error=execution.error,
                    output={"gate_results": execution.gate_results},
                    context=context,
                )
            if execution.result == "failed":
                return self._finish(result, status=BlockStatus.FAILED, error=execution.error, context=context)

            return self._finish(
                result,
                status=BlockStatus.SUCCESS,
                output={
                    "action": self.action_name,
                    "object_id": resolved_obj_id,
                    "gate_results": execution.gate_results,
                },
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.FAILED, error=str(exc), context=context)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK 2: EXECUTE FUNCTION  (deterministic callable)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ExecuteFunction(LogicBlock):
    """Execute a deterministic function.  No LLM.  No tokens.

    The function receives the ExecutionContext and returns any value.
    Supports both sync and async callables.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        args: dict[str, Any] | None = None,
        *,
        label: str = "",
        block_id: str | None = None,
        store_as: str = "",
    ) -> None:
        super().__init__(BlockKind.EXECUTE_FUNCTION, label=label, block_id=block_id, store_as=store_as)
        self.func = func
        self.args = args or {}

    async def execute(self, context: ExecutionContext) -> BlockResult:
        t0 = time.monotonic()
        result = self._start_result()

        resolved = context.resolve_dict(self.args)

        try:
            ret = self.func(context, **resolved)
            if asyncio.iscoroutine(ret):
                ret = await ret
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.SUCCESS, output=ret, context=context)
        except Exception as exc:  # noqa: BLE001
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.FAILED, error=str(exc), context=context)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK 3: CONDITIONAL  (if/else branching)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Conditional(LogicBlock):
    """Branch execution based on a predicate.  No LLM.  No tokens.

    If condition(context) is truthy, runs if_true block.
    Otherwise runs if_false block (if provided, else skips).
    """

    def __init__(
        self,
        condition: Callable[[ExecutionContext], bool],
        if_true: LogicBlock,
        if_false: LogicBlock | None = None,
        *,
        label: str = "",
        block_id: str | None = None,
        store_as: str = "",
    ) -> None:
        super().__init__(BlockKind.CONDITIONAL, label=label, block_id=block_id, store_as=store_as)
        self.condition = condition
        self.if_true = if_true
        self.if_false = if_false

    async def execute(self, context: ExecutionContext) -> BlockResult:
        t0 = time.monotonic()
        result = self._start_result()

        try:
            branch = self.condition(context)
        except Exception as exc:  # noqa: BLE001
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.FAILED, error=f"condition error: {exc}", context=context)

        chosen = self.if_true if branch else self.if_false
        if chosen is None:
            result.duration_seconds = time.monotonic() - t0
            return self._finish(
                result, status=BlockStatus.SKIPPED, output={"branch": branch, "note": "no else block"}, context=context
            )

        child_result = await chosen.execute(context)
        result.duration_seconds = time.monotonic() - t0
        result.child_results = [child_result]
        result.tokens_used = child_result.tokens_used
        result.deterministic = child_result.deterministic
        return self._finish(
            result,
            status=child_result.status,
            output={"branch": branch, "child_output": child_result.output},
            context=context,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK 4: LOOP  (iterate with a body block)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Loop(LogicBlock):
    """Iterate over items, running body for each.  No LLM (unless body uses one).

    items_fn(context) returns the iterable.  Each item is set as
    context.state[item_var] before running the body block.
    """

    def __init__(
        self,
        items_fn: Callable[[ExecutionContext], list[Any]],
        body: LogicBlock,
        item_var: str = "item",
        max_iterations: int = 100,
        *,
        label: str = "",
        block_id: str | None = None,
        store_as: str = "",
    ) -> None:
        super().__init__(BlockKind.LOOP, label=label, block_id=block_id, store_as=store_as)
        self.items_fn = items_fn
        self.body = body
        self.item_var = item_var
        self.max_iterations = max_iterations

    async def execute(self, context: ExecutionContext) -> BlockResult:
        t0 = time.monotonic()
        result = self._start_result()

        try:
            items = self.items_fn(context)
        except Exception as exc:  # noqa: BLE001
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.FAILED, error=f"items_fn error: {exc}", context=context)

        child_results: list[BlockResult] = []
        total_tokens = 0
        all_deterministic = True
        outputs: list[Any] = []

        for i, item in enumerate(items):
            if i >= self.max_iterations:
                logger.warning("Loop %s hit max_iterations=%d", self.block_id, self.max_iterations)
                break

            context.set(self.item_var, item)
            context.set(f"{self.item_var}_index", i)
            child = await self.body.execute(context)
            child_results.append(child)
            total_tokens += child.tokens_used
            if not child.deterministic:
                all_deterministic = False
            outputs.append(child.output)

            if child.status in (BlockStatus.FAILED, BlockStatus.BLOCKED):
                result.duration_seconds = time.monotonic() - t0
                result.child_results = child_results
                result.tokens_used = total_tokens
                result.deterministic = all_deterministic
                return self._finish(
                    result,
                    status=child.status,
                    error=f"loop iteration {i} {child.status.value}: {child.error}",
                    output=outputs,
                    context=context,
                )

        result.duration_seconds = time.monotonic() - t0
        result.child_results = child_results
        result.tokens_used = total_tokens
        result.deterministic = all_deterministic
        return self._finish(result, status=BlockStatus.SUCCESS, output=outputs, context=context)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK 5: CREATE VARIABLE  (set state)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CreateVariable(LogicBlock):
    """Set a variable in context state.  No LLM.  No tokens.

    Supports both static values and computed values (callable).
    """

    def __init__(
        self,
        name: str,
        value: Any = None,
        compute: Callable[[ExecutionContext], Any] | None = None,
        *,
        label: str = "",
        block_id: str | None = None,
    ) -> None:
        super().__init__(BlockKind.CREATE_VARIABLE, label=label, block_id=block_id, store_as=name)
        self.name = name
        self.value = value
        self.compute = compute

    async def execute(self, context: ExecutionContext) -> BlockResult:
        t0 = time.monotonic()
        result = self._start_result()

        try:
            if self.compute is not None:
                val = self.compute(context)
            else:
                val = self.value
            context.set(self.name, val)
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.SUCCESS, output=val, context=context)
        except Exception as exc:  # noqa: BLE001
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.FAILED, error=str(exc), context=context)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCK 6: USE LLM  (the ONE non-deterministic block)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class UseLLM(LogicBlock):
    """NON-DETERMINISTIC.  Calls an LLM.  Uses tokens.  Use sparingly.

    The prompt_template is resolved against context state.
    The llm_fn on context is called with (prompt, config).
    The response is stored in context.state[store_as].
    """

    def __init__(
        self,
        prompt_template: str,
        *,
        max_tokens: int = 1024,
        provider: str = "",
        model: str = "",
        temperature: float = 0.7,
        tools: list[str] | None = None,
        label: str = "",
        block_id: str | None = None,
        store_as: str = "llm_output",
    ) -> None:
        super().__init__(BlockKind.USE_LLM, label=label, block_id=block_id, store_as=store_as)
        self.prompt_template = prompt_template
        self.max_tokens = max_tokens
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.tools = tools or []

    async def execute(self, context: ExecutionContext) -> BlockResult:
        t0 = time.monotonic()
        result = self._start_result()
        result.deterministic = False

        if context.llm_fn is None:
            return self._finish(
                result, status=BlockStatus.FAILED, error="no llm_fn in context", context=context
            )

        prompt = context.resolve(self.prompt_template)
        config = {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "tools": self.tools,
        }
        if self.provider:
            config["provider"] = self.provider
        if self.model:
            config["model"] = self.model

        try:
            response = await context.llm_fn(prompt, config)
            result.duration_seconds = time.monotonic() - t0
            return self._finish(
                result, status=BlockStatus.SUCCESS, output=response,
                tokens=self.max_tokens, context=context,
            )
        except Exception as exc:  # noqa: BLE001
            result.duration_seconds = time.monotonic() - t0
            return self._finish(result, status=BlockStatus.FAILED, error=str(exc), context=context)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PIPELINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PipelineResult(BaseModel):
    """Result of executing a full pipeline."""
    pipeline_id: str
    label: str = ""
    status: BlockStatus = BlockStatus.SUCCESS
    block_results: list[BlockResult] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    total_tokens: int = 0
    deterministic_blocks: int = 0
    nondeterministic_blocks: int = 0
    deterministic_ratio: float = 1.0
    started_at: str = ""
    finished_at: str = ""


class Pipeline:
    """Sequential chain of LogicBlocks with shared context.

    Blocks run in order.  Each block's output is available to subsequent
    blocks via context.state.  If any block fails or is blocked, the
    pipeline stops and propagates the failure.

    Usage::

        pipeline = Pipeline(
            blocks=[
                CreateVariable("model", "mistral-7b"),
                ExecuteFunction(load_prompts, store_as="prompts"),
                Conditional(
                    condition=lambda ctx: len(ctx.get("prompts", [])) >= 20,
                    if_true=ExecuteFunction(compute_metrics, store_as="results"),
                    if_false=ApplyAction("Experiment", "Fail", params={"reason": "insufficient prompts"}),
                ),
                UseLLM("Analyze: {results}", store_as="analysis"),
                ApplyAction("Experiment", "Archive", params={"results": "{results}"}),
            ],
            label="rv_experiment",
        )
        result = await pipeline.execute(context)
        print(f"Deterministic ratio: {result.deterministic_ratio:.0%}")
    """

    def __init__(
        self,
        blocks: list[LogicBlock],
        label: str = "",
        pipeline_id: str | None = None,
        stop_on_failure: bool = True,
    ) -> None:
        self.blocks = blocks
        self.label = label
        self.pipeline_id = pipeline_id or _new_id()
        self.stop_on_failure = stop_on_failure

    async def execute(
        self,
        context: ExecutionContext,
        on_block_complete: Callable[[BlockResult], Any] | None = None,
    ) -> PipelineResult:
        """Execute all blocks sequentially."""
        t0 = time.monotonic()
        result = PipelineResult(
            pipeline_id=self.pipeline_id,
            label=self.label,
            started_at=_utc_now().isoformat(),
        )

        det_count = 0
        nondet_count = 0
        total_tokens = 0

        for block in self.blocks:
            br = await block.execute(context)
            result.block_results.append(br)
            total_tokens += br.tokens_used

            if br.deterministic:
                det_count += 1
            else:
                nondet_count += 1

            if on_block_complete:
                cb_ret = on_block_complete(br)
                if asyncio.iscoroutine(cb_ret):
                    await cb_ret

            if br.status in (BlockStatus.FAILED, BlockStatus.BLOCKED) and self.stop_on_failure:
                result.status = br.status
                break
        else:
            result.status = BlockStatus.SUCCESS

        result.total_duration_seconds = time.monotonic() - t0
        result.total_tokens = total_tokens
        result.deterministic_blocks = det_count
        result.nondeterministic_blocks = nondet_count
        total_executed = det_count + nondet_count
        result.deterministic_ratio = det_count / total_executed if total_executed > 0 else 1.0
        result.finished_at = _utc_now().isoformat()
        return result

    def block_summary(self) -> str:
        """ASCII summary of the pipeline structure."""
        lines = [f"Pipeline: {self.label or self.pipeline_id}", ""]
        for i, block in enumerate(self.blocks, 1):
            det_marker = "LLM" if block.kind == BlockKind.USE_LLM else "DET"
            label = block.label or block.kind.value
            lines.append(f"  {i}. [{det_marker}] {label}")
            if isinstance(block, Conditional):
                t_label = block.if_true.label or block.if_true.kind.value
                lines.append(f"       if true  -> {t_label}")
                if block.if_false:
                    f_label = block.if_false.label or block.if_false.kind.value
                    lines.append(f"       if false -> {f_label}")
            elif isinstance(block, Loop):
                b_label = block.body.label or block.body.kind.value
                lines.append(f"       body -> {b_label} (max {block.max_iterations})")

        det = sum(1 for b in self.blocks if b.kind != BlockKind.USE_LLM)
        llm = sum(1 for b in self.blocks if b.kind == BlockKind.USE_LLM)
        total = det + llm
        ratio = det / total if total > 0 else 1.0
        lines.append("")
        lines.append(f"  {det} deterministic, {llm} LLM — {ratio:.0%} deterministic")
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PIPELINE BUILDER (convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PipelineBuilder:
    """Fluent builder for pipelines.

    Usage::

        pipeline = (
            PipelineBuilder("experiment_run")
            .set("model", "mistral-7b")
            .call(load_config, store_as="config")
            .branch(
                condition=lambda ctx: ctx.get("config") is not None,
                if_true=ExecuteFunction(run_metrics, store_as="results"),
                if_false=ApplyAction("Experiment", "Fail"),
            )
            .llm("Analyze: {results}", store_as="analysis")
            .action("Experiment", "Archive", params={"data": "{results}"})
            .build()
        )
    """

    def __init__(self, label: str = "") -> None:
        self._blocks: list[LogicBlock] = []
        self._label = label

    def set(self, name: str, value: Any = None, compute: Callable | None = None) -> PipelineBuilder:
        """Add a CreateVariable block."""
        self._blocks.append(CreateVariable(name, value=value, compute=compute))
        return self

    def call(
        self, func: Callable, args: dict[str, Any] | None = None, *, store_as: str = "", label: str = ""
    ) -> PipelineBuilder:
        """Add an ExecuteFunction block."""
        self._blocks.append(ExecuteFunction(func, args=args, store_as=store_as, label=label))
        return self

    def action(
        self,
        object_type: str,
        action_name: str,
        object_id: str = "",
        params: dict[str, Any] | None = None,
        *,
        store_as: str = "",
        label: str = "",
    ) -> PipelineBuilder:
        """Add an ApplyAction block."""
        self._blocks.append(
            ApplyAction(object_type, action_name, object_id=object_id, params=params, store_as=store_as, label=label)
        )
        return self

    def branch(
        self,
        condition: Callable[[ExecutionContext], bool],
        if_true: LogicBlock,
        if_false: LogicBlock | None = None,
        *,
        store_as: str = "",
        label: str = "",
    ) -> PipelineBuilder:
        """Add a Conditional block."""
        self._blocks.append(
            Conditional(condition, if_true, if_false, store_as=store_as, label=label)
        )
        return self

    def loop(
        self,
        items_fn: Callable[[ExecutionContext], list],
        body: LogicBlock,
        item_var: str = "item",
        max_iterations: int = 100,
        *,
        store_as: str = "",
        label: str = "",
    ) -> PipelineBuilder:
        """Add a Loop block."""
        self._blocks.append(
            Loop(items_fn, body, item_var=item_var, max_iterations=max_iterations, store_as=store_as, label=label)
        )
        return self

    def llm(
        self,
        prompt: str,
        *,
        store_as: str = "llm_output",
        max_tokens: int = 1024,
        provider: str = "",
        model: str = "",
        label: str = "",
    ) -> PipelineBuilder:
        """Add a UseLLM block."""
        self._blocks.append(
            UseLLM(prompt, store_as=store_as, max_tokens=max_tokens, provider=provider, model=model, label=label)
        )
        return self

    def add(self, block: LogicBlock) -> PipelineBuilder:
        """Add an arbitrary LogicBlock."""
        self._blocks.append(block)
        return self

    def build(self) -> Pipeline:
        """Build the pipeline."""
        return Pipeline(blocks=list(self._blocks), label=self._label)
