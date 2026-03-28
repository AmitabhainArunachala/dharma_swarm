"""Workflow Compiler — Declarative DAGs with checkpointing.

Replaces reactive orchestration with versioned, resumable workflows:

  @workflow("colm_paper")
  async def pipeline(wf):
      config = wf.step("load_config", load_config)
      data = wf.step("gather_data", gather_results, inputs=[config])
      audit = wf.step("audit", audit_claims, inputs=[data])
      draft = wf.step("draft", llm_draft, inputs=[audit], deterministic=False)
      wf.step("archive", archive, inputs=[draft])

Features:
  - Compiles to a DAG before execution
  - Checkpoints at each step boundary (resume on failure)
  - Version-controlled (each workflow has a content hash)
  - Integrates with lineage (auto-records transformations)
  - Integrates with guardrails (input/output checks per step)
  - Deterministic ratio tracking

Integration:
  logic_layer.py  — Steps map to LogicBlocks
  lineage.py      — Auto-records LineageEdges
  guardrails.py   — GuardrailRunner wraps each step
  ontology.py     — Workflow can reference typed objects
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:12]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CACHED = "cached"


class WorkflowStatus(str, Enum):
    DEFINED = "defined"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class WorkflowStep(BaseModel):
    """A single step in a workflow DAG."""
    step_id: str
    name: str
    deterministic: bool = True
    inputs: list[str] = Field(default_factory=list)  # step_ids this depends on
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: str = ""
    duration_seconds: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    checkpoint: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class WorkflowResult(BaseModel):
    """Result of a complete workflow execution."""
    workflow_id: str
    name: str
    version: str = ""
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    steps: list[WorkflowStep] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    deterministic_steps: int = 0
    nondeterministic_steps: int = 0
    deterministic_ratio: float = 1.0
    started_at: str = ""
    finished_at: str = ""
    resumed_from: str = ""


class AutoResearchWorkflowOutcome(BaseModel):
    """Result bundle for an AutoResearch workflow execution."""

    workflow: WorkflowResult
    report: Any
    reward_signal: Any
    trace_ids: list[str] = Field(default_factory=list)
    lineage_edge_id: str = ""

    model_config = {"arbitrary_types_allowed": True}


class TopologyWorkflowOutcome(BaseModel):
    """Result bundle for a topology-genome workflow execution."""

    workflow: WorkflowResult
    outputs: dict[str, Any] = Field(default_factory=dict)
    trace_ids: list[str] = Field(default_factory=list)
    lineage_edge_ids: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WORKFLOW DEFINITION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class StepRef:
    """Reference to a step, used to build dependencies."""

    def __init__(self, step_id: str, name: str) -> None:
        self.step_id = step_id
        self.name = name


class WorkflowDefinition:
    """Accumulates steps during workflow definition.

    Used inside the @workflow decorator or manually:

        wf = WorkflowDefinition("my_pipeline")
        s1 = wf.step("load", load_fn)
        s2 = wf.step("process", process_fn, inputs=[s1])
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._steps: list[tuple[str, str, Callable, list[str], bool]] = []
        self._step_names: set[str] = set()

    def step(
        self,
        name: str,
        func: Callable[..., Any],
        inputs: list[StepRef] | None = None,
        deterministic: bool = True,
    ) -> StepRef:
        """Declare a workflow step."""
        if name in self._step_names:
            raise ValueError(f"Duplicate step name: {name}")

        step_id = _new_id()
        input_ids = [ref.step_id for ref in (inputs or [])]
        self._steps.append((step_id, name, func, input_ids, deterministic))
        self._step_names.add(name)
        return StepRef(step_id, name)

    def compile(self) -> CompiledWorkflow:
        """Compile the definition into an executable workflow."""
        steps: list[WorkflowStep] = []
        funcs: dict[str, Callable] = {}

        for step_id, name, func, input_ids, det in self._steps:
            steps.append(WorkflowStep(
                step_id=step_id,
                name=name,
                deterministic=det,
                inputs=input_ids,
            ))
            funcs[step_id] = func

        # Compute content hash for versioning (based on structure, not IDs)
        # Map step_id -> name for resolving input references
        id_to_name = {sid: name for sid, name, _, _, _ in self._steps}
        hash_input = json.dumps(
            [
                (name, det, [id_to_name.get(inp, inp) for inp in input_ids])
                for _, name, _, input_ids, det in self._steps
            ],
            sort_keys=True,
        )
        version = hashlib.sha256(hash_input.encode()).hexdigest()[:12]

        return CompiledWorkflow(
            name=self.name,
            steps=steps,
            funcs=funcs,
            version=version,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMPILED WORKFLOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CompiledWorkflow:
    """An executable workflow with topological ordering and checkpointing."""

    def __init__(
        self,
        name: str,
        steps: list[WorkflowStep],
        funcs: dict[str, Callable],
        version: str = "",
    ) -> None:
        self.name = name
        self.steps = steps
        self.funcs = funcs
        self.version = version
        self.workflow_id = _new_id()
        self._step_map: dict[str, WorkflowStep] = {s.step_id: s for s in steps}

    def execution_order(self) -> list[list[WorkflowStep]]:
        """Topological sort into parallel waves."""
        in_degree: dict[str, int] = defaultdict(int)
        for step in self.steps:
            if step.step_id not in in_degree:
                in_degree[step.step_id] = 0
            for dep in step.inputs:
                in_degree[step.step_id] += 1

        waves: list[list[WorkflowStep]] = []
        remaining = set(in_degree.keys())

        while remaining:
            wave = [
                self._step_map[sid]
                for sid in remaining
                if in_degree[sid] == 0
            ]
            if not wave:
                # Cycle detected
                logger.error("Cycle in workflow DAG: %s", remaining)
                break

            waves.append(wave)
            for step in wave:
                remaining.discard(step.step_id)
                for other_sid in remaining:
                    other = self._step_map[other_sid]
                    if step.step_id in other.inputs:
                        in_degree[other_sid] -= 1

        return waves

    async def execute(
        self,
        context: dict[str, Any] | None = None,
        checkpoint_dir: Path | None = None,
        on_step_complete: Callable[[WorkflowStep], Any] | None = None,
    ) -> WorkflowResult:
        """Execute the workflow wave by wave."""
        t0 = time.monotonic()
        ctx = dict(context) if context else {}
        step_outputs: dict[str, Any] = {}

        # Load checkpoint if resuming
        resumed_from = ""
        if checkpoint_dir:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            resumed_from = self._load_checkpoint(checkpoint_dir, step_outputs)

        waves = self.execution_order()
        failed = False

        for wave in waves:
            # Separate cached steps from steps that need running
            runnable: list[WorkflowStep] = []
            for step in wave:
                if step.status == StepStatus.COMPLETED:
                    step_outputs[step.step_id] = step.output
                else:
                    runnable.append(step)

            if runnable:
                coros = [self._execute_step(s, step_outputs, ctx) for s in runnable]
                results = await asyncio.gather(*coros, return_exceptions=True)

                for step, result in zip(runnable, results):
                    if isinstance(result, Exception):
                        step.status = StepStatus.FAILED
                        step.error = str(result)
                        failed = True

            # Fire callbacks for all steps in this wave
            if on_step_complete:
                for s in wave:
                    if s.status in (StepStatus.COMPLETED, StepStatus.FAILED):
                        cb = on_step_complete(s)
                        if asyncio.iscoroutine(cb):
                            await cb

            if checkpoint_dir:
                self._save_checkpoint(checkpoint_dir, step_outputs)

            if failed:
                break

        # Compute stats
        det = sum(1 for s in self.steps if s.deterministic and s.status == StepStatus.COMPLETED)
        nondet = sum(1 for s in self.steps if not s.deterministic and s.status == StepStatus.COMPLETED)
        total = det + nondet

        return WorkflowResult(
            workflow_id=self.workflow_id,
            name=self.name,
            version=self.version,
            status=WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED,
            steps=self.steps,
            total_duration_seconds=time.monotonic() - t0,
            deterministic_steps=det,
            nondeterministic_steps=nondet,
            deterministic_ratio=det / total if total > 0 else 1.0,
            started_at=_utc_now().isoformat(),
            finished_at=_utc_now().isoformat(),
            resumed_from=resumed_from,
        )

    async def _execute_step(
        self,
        step: WorkflowStep,
        step_outputs: dict[str, Any],
        ctx: dict[str, Any],
    ) -> None:
        """Execute a single step."""
        t0 = time.monotonic()
        step.status = StepStatus.RUNNING
        step.started_at = _utc_now().isoformat()

        # Gather inputs from upstream steps
        inputs: dict[str, Any] = {}
        for input_id in step.inputs:
            if input_id in step_outputs:
                # Find the step name for this input
                input_step = self._step_map.get(input_id)
                if input_step:
                    inputs[input_step.name] = step_outputs[input_id]

        try:
            func = self.funcs[step.step_id]
            result = func(inputs, ctx)
            if asyncio.iscoroutine(result):
                result = await result

            step.output = result
            step.status = StepStatus.COMPLETED
            step_outputs[step.step_id] = result
        except Exception as exc:  # noqa: BLE001
            step.status = StepStatus.FAILED
            step.error = str(exc)
            raise

        step.duration_seconds = time.monotonic() - t0
        step.finished_at = _utc_now().isoformat()

    def _save_checkpoint(self, checkpoint_dir: Path, step_outputs: dict[str, Any]) -> None:
        """Save current state to checkpoint directory."""
        data = {
            "workflow_id": self.workflow_id,
            "version": self.version,
            "steps": {},
        }
        for step in self.steps:
            data["steps"][step.step_id] = {
                "name": step.name,
                "status": step.status.value,
                "output": _safe_serialize(step_outputs.get(step.step_id)),
            }

        cp_file = checkpoint_dir / f"{self.name}_checkpoint.json"
        cp_file.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")

    def _load_checkpoint(self, checkpoint_dir: Path, step_outputs: dict[str, Any]) -> str:
        """Load checkpoint. Returns workflow_id if resumed, else empty string."""
        cp_file = checkpoint_dir / f"{self.name}_checkpoint.json"
        if not cp_file.exists():
            return ""

        try:
            data = json.loads(cp_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""

        if data.get("version") != self.version:
            logger.info("Checkpoint version mismatch, starting fresh")
            return ""

        # Build name->step mapping for this compiled workflow
        name_to_step = {s.name: s for s in self.steps}

        for _cp_step_id, step_data in data.get("steps", {}).items():
            cp_name = step_data.get("name", "")
            if cp_name in name_to_step and step_data.get("status") == "completed":
                step = name_to_step[cp_name]
                step.status = StepStatus.COMPLETED
                output = step_data.get("output")
                step_outputs[step.step_id] = output
                step.output = output

        return data.get("workflow_id", "")

    def summary(self) -> str:
        """ASCII summary of the workflow structure."""
        waves = self.execution_order()
        lines = [
            f"Workflow: {self.name} (v{self.version})",
            f"Steps: {len(self.steps)}",
            "",
        ]

        for i, wave in enumerate(waves):
            lines.append(f"  Wave {i + 1}:")
            for step in wave:
                det = "DET" if step.deterministic else "LLM"
                deps = ", ".join(
                    self._step_map[d].name for d in step.inputs if d in self._step_map
                ) or "none"
                status = step.status.value.upper()
                lines.append(f"    [{det}] {step.name} (deps: {deps}) [{status}]")

        det = sum(1 for s in self.steps if s.deterministic)
        llm = sum(1 for s in self.steps if not s.deterministic)
        total = det + llm
        ratio = det / total if total > 0 else 1.0
        lines.append("")
        lines.append(f"  {det} deterministic, {llm} LLM — {ratio:.0%} deterministic")
        return "\n".join(lines)


def _safe_serialize(value: Any) -> Any:
    """Make a value JSON-safe for checkpointing."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    return str(value)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DECORATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


_REGISTRY: dict[str, Callable] = {}


def workflow(name: str) -> Callable:
    """Decorator to register a workflow definition function.

    Usage::

        @workflow("colm_paper")
        def define(wf: WorkflowDefinition):
            config = wf.step("load_config", load_config_fn)
            data = wf.step("gather", gather_fn, inputs=[config])
            wf.step("analyze", analyze_fn, inputs=[data], deterministic=False)

        # Later:
        compiled = compile_workflow("colm_paper")
        result = await compiled.execute()
    """
    def decorator(func: Callable) -> Callable:
        _REGISTRY[name] = func
        return func
    return decorator


def compile_workflow(name: str) -> CompiledWorkflow:
    """Compile a registered workflow by name."""
    if name not in _REGISTRY:
        raise ValueError(f"Workflow '{name}' not registered. Available: {sorted(_REGISTRY.keys())}")

    defn = WorkflowDefinition(name)
    _REGISTRY[name](defn)
    return defn.compile()


def list_workflows() -> list[str]:
    """List all registered workflow names."""
    return sorted(_REGISTRY.keys())


async def execute_auto_research_workflow(
    *,
    brief: Any,
    research_engine: Any,
    grade_engine: Any,
    agent_name: str,
    trace_store: Any | None = None,
    lineage_graph: Any | None = None,
    checkpoint_dir: Path | None = None,
    grade_kwargs: dict[str, Any] | None = None,
    runtime_field_names: list[str] | None = None,
) -> AutoResearchWorkflowOutcome:
    """Execute AutoResearch + AutoGrade inside the canonical workflow runtime."""
    from dharma_swarm.traces import auto_research_trace_entry

    workflow_def = WorkflowDefinition("auto_research")
    grade_kwargs = dict(grade_kwargs or {})

    plan_ref = workflow_def.step(
        "plan",
        lambda _inputs, _ctx: research_engine.plan(brief),
    )
    sources_ref = workflow_def.step(
        "sources",
        lambda inputs, _ctx: research_engine.reader.normalize_all(
            list(research_engine.search_backend.search(brief, inputs["plan"]))
        ),
        inputs=[plan_ref],
        deterministic=False,
    )
    claims_ref = workflow_def.step(
        "claim_graph",
        lambda inputs, _ctx: research_engine.claim_graph.build(brief, inputs["sources"]),
        inputs=[sources_ref],
    )
    report_ref = workflow_def.step(
        "report",
        lambda inputs, _ctx: research_engine.reporter.create_report(
            brief=brief,
            queries=inputs["plan"],
            sources=inputs["sources"],
            claims=inputs["claim_graph"],
        ),
        inputs=[plan_ref, sources_ref, claims_ref],
    )
    grade_ref = workflow_def.step(
        "grade",
        lambda inputs, _ctx: grade_engine.grade(
            inputs["report"],
            inputs["sources"],
            **grade_kwargs,
        ),
        inputs=[report_ref, sources_ref],
        deterministic=False,
    )

    compiled = workflow_def.compile()
    trace_ids: list[str] = []

    async def _on_step_complete(step: WorkflowStep) -> None:
        if trace_store is None or step.status != StepStatus.COMPLETED:
            return
        trace_id = await trace_store.log_entry(
            auto_research_trace_entry(
                agent=agent_name,
                task_id=brief.task_id,
                workflow_name=compiled.name,
                step_name=step.name,
                output=step.output,
                runtime_fields=runtime_field_names,
            )
        )
        trace_ids.append(trace_id)

    workflow_result = await compiled.execute(
        context={"task_id": brief.task_id},
        checkpoint_dir=checkpoint_dir,
        on_step_complete=_on_step_complete,
    )
    step_map = {step.name: step.output for step in workflow_result.steps if step.status == StepStatus.COMPLETED}
    report = step_map.get(report_ref.name)
    reward_signal = step_map.get(grade_ref.name)

    lineage_edge_id = ""
    if lineage_graph is not None and report is not None and reward_signal is not None:
        lineage_edge_id = lineage_graph.record_research_run(
            task_id=brief.task_id,
            report_id=report.report_id,
            source_ids=list(report.source_ids),
            agent=agent_name,
            metadata={
                "trace_ids": list(trace_ids),
                "runtime_fields": list(runtime_field_names or []),
                "final_score": reward_signal.grade_card.final_score,
            },
        )

    return AutoResearchWorkflowOutcome(
        workflow=workflow_result,
        report=report,
        reward_signal=reward_signal,
        trace_ids=trace_ids,
        lineage_edge_id=lineage_edge_id,
    )


async def execute_topology_genome_workflow(
    *,
    genome: Any,
    node_functions: dict[str, Callable[..., Any]],
    agent_name: str,
    trace_store: Any | None = None,
    lineage_graph: Any | None = None,
    checkpoint_dir: Path | None = None,
    context: dict[str, Any] | None = None,
) -> TopologyWorkflowOutcome:
    """Execute a topology genome through the canonical workflow runtime."""
    from dharma_swarm.traces import topology_trace_entry

    compiled = genome.compile(node_functions)
    trace_ids: list[str] = []
    lineage_edge_ids: list[str] = []

    async def _on_step_complete(step: WorkflowStep) -> None:
        if step.status != StepStatus.COMPLETED:
            return
        if trace_store is not None:
            trace_ids.append(
                await trace_store.log_entry(
                    topology_trace_entry(
                        agent=agent_name,
                        workflow_name=compiled.name,
                        genome_id=genome.genome_id,
                        step=step,
                        output=step.output,
                    )
                )
            )
        if lineage_graph is not None:
            node_id = str(step.checkpoint.get("topology_node_id") or step.step_id)
            inputs = (
                [f"topology_output:{dep}" for dep in step.inputs]
                if step.inputs
                else [f"topology_entry:{node_id}"]
            )
            lineage_edge_ids.append(
                lineage_graph.record_transformation(
                    task_id=f"topology:{compiled.workflow_id}:{node_id}",
                    inputs=inputs,
                    outputs=[f"topology_output:{node_id}"],
                    agent=agent_name,
                    operation="topology_genome_workflow",
                    pipeline_id=compiled.workflow_id,
                    metadata={
                        "topology_genome_id": genome.genome_id,
                        "topology_node_id": node_id,
                        "topology_edge_ids": list(step.checkpoint.get("topology_edge_ids", [])),
                    },
                )
            )

    workflow_result = await compiled.execute(
        context=dict(context or {"topology_genome_id": genome.genome_id}),
        checkpoint_dir=checkpoint_dir,
        on_step_complete=_on_step_complete,
    )
    outputs = {
        step.step_id: step.output
        for step in workflow_result.steps
        if step.status == StepStatus.COMPLETED
    }
    return TopologyWorkflowOutcome(
        workflow=workflow_result,
        outputs=outputs,
        trace_ids=trace_ids,
        lineage_edge_ids=lineage_edge_ids,
    )
