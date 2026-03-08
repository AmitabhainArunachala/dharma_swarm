"""Tests for Skill Composer -- DAG-based skill composition."""

from __future__ import annotations

import pytest

from dharma_swarm.skill_composer import (
    CompositionPlan,
    HandoffArtifact,
    SkillComposer,
    SkillStep,
    MAX_STEPS,
)


# -- SkillStep defaults ---------------------------------------------------


class TestSkillStepDefaults:
    """Test SkillStep model defaults."""

    def test_timeout_default(self):
        step = SkillStep(skill_name="builder", task="implement feature")
        assert step.timeout == 300.0

    def test_retry_default(self):
        step = SkillStep(skill_name="builder", task="implement feature")
        assert step.retry == 0

    def test_depends_on_default(self):
        step = SkillStep(skill_name="builder", task="implement feature")
        assert step.depends_on == []


# -- Single-step plan creation ---------------------------------------------


class TestSingleStepPlan:
    """Test creation of trivial single-step plans."""

    def test_single_step_plan(self):
        composer = SkillComposer()
        plan = composer.compose("implement a cache module")
        assert isinstance(plan, CompositionPlan)
        assert len(plan.steps) >= 1
        assert plan.status == "pending"
        assert plan.task == "implement a cache module"


# -- Multi-step plans with dependencies ------------------------------------


class TestMultiStepPlans:
    """Test plans with explicit dependencies between steps."""

    def test_compose_from_steps_with_deps(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "scan then fix then test",
            [
                {"skill_name": "cartographer", "task": "scan ecosystem", "step_id": "scan-0"},
                {"skill_name": "surgeon", "task": "fix bugs", "step_id": "fix-0", "depends_on": ["scan-0"]},
                {"skill_name": "validator", "task": "run tests", "step_id": "test-0", "depends_on": ["fix-0"]},
            ],
        )
        assert len(plan.steps) == 3
        assert plan.steps[1].depends_on == ["scan-0"]
        assert plan.steps[2].depends_on == ["fix-0"]

    def test_step_ids_auto_generated(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "two steps",
            [
                {"skill_name": "builder", "task": "build it"},
                {"skill_name": "validator", "task": "test it"},
            ],
        )
        assert plan.steps[0].step_id == "builder-0"
        assert plan.steps[1].step_id == "validator-1"


# -- Topological sort (execution_order) ------------------------------------


class TestExecutionOrder:
    """Test topological sort into parallel waves."""

    def test_linear_chain_produces_sequential_waves(self):
        plan = CompositionPlan(
            task="chain",
            steps=[
                SkillStep(skill_name="a", task="step a", step_id="a-0"),
                SkillStep(skill_name="b", task="step b", step_id="b-0", depends_on=["a-0"]),
                SkillStep(skill_name="c", task="step c", step_id="c-0", depends_on=["b-0"]),
            ],
        )
        waves = plan.execution_order()
        assert len(waves) == 3
        assert waves[0][0].step_id == "a-0"
        assert waves[1][0].step_id == "b-0"
        assert waves[2][0].step_id == "c-0"

    def test_independent_steps_in_same_wave(self):
        plan = CompositionPlan(
            task="parallel",
            steps=[
                SkillStep(skill_name="a", task="scan a", step_id="a-0"),
                SkillStep(skill_name="b", task="scan b", step_id="b-0"),
                SkillStep(skill_name="c", task="merge", step_id="c-0", depends_on=["a-0", "b-0"]),
            ],
        )
        waves = plan.execution_order()
        assert len(waves) == 2
        first_ids = {s.step_id for s in waves[0]}
        assert first_ids == {"a-0", "b-0"}
        assert waves[1][0].step_id == "c-0"

    def test_circular_dependency_raises(self):
        plan = CompositionPlan(
            task="cycle",
            steps=[
                SkillStep(skill_name="a", task="a", step_id="a-0", depends_on=["b-0"]),
                SkillStep(skill_name="b", task="b", step_id="b-0", depends_on=["a-0"]),
            ],
        )
        with pytest.raises(ValueError, match="Circular dependency"):
            plan.execution_order()


# -- Parallel group detection ----------------------------------------------


class TestParallelGroups:
    """Test parallel_group field on steps."""

    def test_compose_sets_parallel_groups(self):
        """Steps classified into the same phase share a parallel_group."""
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "parallel scan",
            [
                {"skill_name": "a", "task": "scan A", "parallel_group": "research"},
                {"skill_name": "b", "task": "scan B", "parallel_group": "research"},
            ],
        )
        assert plan.steps[0].parallel_group == plan.steps[1].parallel_group == "research"


# -- ready_steps() ---------------------------------------------------------


class TestReadySteps:
    """Test that ready_steps returns only unblocked steps."""

    def test_no_deps_all_ready(self):
        plan = CompositionPlan(
            task="all ready",
            steps=[
                SkillStep(skill_name="a", task="a", step_id="a-0"),
                SkillStep(skill_name="b", task="b", step_id="b-0"),
            ],
        )
        ready = plan.ready_steps()
        assert len(ready) == 2

    def test_blocked_step_not_ready(self):
        plan = CompositionPlan(
            task="blocked",
            steps=[
                SkillStep(skill_name="a", task="a", step_id="a-0"),
                SkillStep(skill_name="b", task="b", step_id="b-0", depends_on=["a-0"]),
            ],
        )
        ready = plan.ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "a-0"

    def test_step_becomes_ready_after_artifact(self):
        plan = CompositionPlan(
            task="unblock",
            steps=[
                SkillStep(skill_name="a", task="a", step_id="a-0"),
                SkillStep(skill_name="b", task="b", step_id="b-0", depends_on=["a-0"]),
            ],
        )
        # Record artifact for a-0
        composer = SkillComposer()
        composer.record_artifact(plan, "a-0", "analysis", "done")
        ready = plan.ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "b-0"


# -- Artifact recording and retrieval -------------------------------------


class TestArtifacts:
    """Test artifact lifecycle."""

    def test_record_and_retrieve(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "artifact test",
            [{"skill_name": "builder", "task": "build", "step_id": "b-0"}],
        )
        artifact = composer.record_artifact(plan, "b-0", "code_diff", "diff content", {"file": "x.py"})
        assert isinstance(artifact, HandoffArtifact)
        assert artifact.step_id == "b-0"
        assert artifact.skill_name == "builder"
        assert artifact.artifact_type == "code_diff"
        assert artifact.content == "diff content"
        assert artifact.metadata == {"file": "x.py"}
        assert "b-0" in plan.artifacts

    def test_record_invalid_step_raises(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "bad step",
            [{"skill_name": "builder", "task": "build", "step_id": "b-0"}],
        )
        with pytest.raises(ValueError, match="not found"):
            composer.record_artifact(plan, "nonexistent", "analysis", "oops")


# -- Context assembly from upstream artifacts ------------------------------


class TestContextAssembly:
    """Test get_context_for_step builds context from upstream artifacts."""

    def test_context_from_upstream(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "context test",
            [
                {"skill_name": "cartographer", "task": "scan", "step_id": "scan-0"},
                {"skill_name": "builder", "task": "build", "step_id": "build-0", "depends_on": ["scan-0"]},
            ],
        )
        composer.record_artifact(plan, "scan-0", "analysis", "found 3 modules")
        ctx = composer.get_context_for_step(plan, plan.steps[1])
        assert "found 3 modules" in ctx
        assert "analysis" in ctx
        assert "cartographer" in ctx

    def test_no_upstream_artifacts_returns_empty(self):
        composer = SkillComposer()
        step = SkillStep(skill_name="builder", task="build", step_id="b-0")
        plan = CompositionPlan(task="empty ctx", steps=[step])
        ctx = composer.get_context_for_step(plan, step)
        assert ctx == ""


# -- compose() auto-decomposition -----------------------------------------


class TestAutoCompose:
    """Test compose() with IntentRouter integration."""

    def test_compose_auto_decomposes(self):
        from dharma_swarm.intent_router import IntentRouter

        router = IntentRouter()
        composer = SkillComposer(router=router)
        plan = composer.compose("scan the ecosystem then fix the bugs then test everything")
        assert len(plan.steps) >= 2
        assert plan.status == "pending"

    def test_compose_without_router(self):
        composer = SkillComposer()
        plan = composer.compose("just build something")
        assert len(plan.steps) == 1
        assert plan.steps[0].skill_name == "builder"


# -- Max steps enforcement ------------------------------------------------


class TestMaxSteps:
    """Test the 7-step ceiling."""

    def test_max_steps_enforced(self):
        composer = SkillComposer()
        too_many = [{"skill_name": f"s{i}", "task": f"task {i}"} for i in range(10)]
        with pytest.raises(ValueError, match="maximum"):
            composer.compose_from_steps("too many", too_many)


# -- Empty task handling ---------------------------------------------------


class TestEmptyTask:
    """Test handling of empty or whitespace-only tasks."""

    def test_empty_task_raises(self):
        composer = SkillComposer()
        with pytest.raises(ValueError, match="empty"):
            composer.compose("")

    def test_whitespace_task_raises(self):
        composer = SkillComposer()
        with pytest.raises(ValueError, match="empty"):
            composer.compose("   ")

    def test_empty_compose_from_steps_raises(self):
        composer = SkillComposer()
        with pytest.raises(ValueError, match="empty"):
            composer.compose_from_steps("", [{"skill_name": "a", "task": "a"}])


# -- Plan status transitions -----------------------------------------------


class TestPlanStatus:
    """Test that plan status transitions correctly."""

    def test_initial_status_pending(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "status test",
            [{"skill_name": "a", "task": "a", "step_id": "a-0"}],
        )
        assert plan.status == "pending"

    def test_status_running_after_partial(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "status test",
            [
                {"skill_name": "a", "task": "a", "step_id": "a-0"},
                {"skill_name": "b", "task": "b", "step_id": "b-0"},
            ],
        )
        composer.record_artifact(plan, "a-0", "analysis", "done")
        assert plan.status == "running"

    def test_status_completed_when_all_done(self):
        composer = SkillComposer()
        plan = composer.compose_from_steps(
            "status test",
            [
                {"skill_name": "a", "task": "a", "step_id": "a-0"},
                {"skill_name": "b", "task": "b", "step_id": "b-0"},
            ],
        )
        composer.record_artifact(plan, "a-0", "analysis", "done")
        composer.record_artifact(plan, "b-0", "code_diff", "patched")
        assert plan.status == "completed"
