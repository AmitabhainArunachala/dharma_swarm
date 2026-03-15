"""Tests for dharma_swarm.planner — plan-before-execute module."""

import pytest

from dharma_swarm.models import LLMResponse, Task
from dharma_swarm.planner import Planner, PlanStep, TaskPlan


# === TEST 1: test_create_plan_basic ===


def test_create_plan_basic():
    """Create a plan with read and modify files; verify structure."""
    task = Task(title="Fix bug", description="Fix the selector")
    planner = Planner()
    plan = planner.create_plan(
        task,
        files_to_read=["selector.py"],
        files_to_modify=["selector.py"],
    )
    assert len(plan.steps) >= 3  # read, modify, verify
    assert plan.task_id == task.id
    assert plan.complexity_rating >= 1
    assert plan.task_title == "Fix bug"
    assert plan.summary == "Plan for: Fix bug"


# === TEST 2: test_format_plan_for_injection ===


def test_format_plan_for_injection():
    """Formatted plan contains expected markers."""
    plan = TaskPlan(
        task_title="Test task",
        summary="Testing plan formatting",
        steps=[
            PlanStep(index=1, description="Read files", files_to_read=["a.py"]),
            PlanStep(index=2, description="Modify code", files_to_modify=["b.py"]),
            PlanStep(index=3, description="Verify changes", verification="Tests pass"),
        ],
        think_notes="Careful approach needed",
        complexity_rating=3,
    )
    result = Planner.format_plan_for_injection(plan)
    assert "EXECUTION PLAN" in result
    assert "Read files" in result
    assert "Modify code" in result
    assert "Verify changes" in result
    assert "Follow this plan step by step" in result
    assert "a.py" in result
    assert "b.py" in result


# === TEST 3: test_update_step_status ===


def test_update_step_status():
    """Updating a step status leaves other steps unchanged."""
    plan = TaskPlan(
        steps=[
            PlanStep(index=1, description="Step one"),
            PlanStep(index=2, description="Step two"),
            PlanStep(index=3, description="Step three"),
        ],
    )
    updated = Planner.update_step_status(plan, 1, "completed")
    assert updated.steps[0].status == "completed"
    assert updated.steps[1].status == "pending"
    assert updated.steps[2].status == "pending"


# === TEST 4: test_memory_survival_directive_injected ===


def test_memory_survival_directive_injected():
    """build_agent_context injects the memory survival directive."""
    from dharma_swarm.context import build_agent_context

    result = build_agent_context(role="surgeon")
    assert "CONTEXT WILL BE DESTROYED" in result
    assert "externalize" in result.lower()


# === TEST 5: test_build_prompt_with_plan ===


@pytest.mark.timeout(60)
def test_build_prompt_with_plan():
    """Plan context is injected into the LLM request user message."""
    from dharma_swarm.agent_runner import _build_prompt
    from dharma_swarm.models import AgentConfig, AgentRole

    task = Task(title="Test task", description="Do something")
    config = AgentConfig(name="test-agent", role=AgentRole.CODER)

    plan = TaskPlan(
        task_title="Test task",
        steps=[PlanStep(index=1, description="Step one")],
        think_notes="Test notes",
    )
    formatted = Planner.format_plan_for_injection(plan)

    request = _build_prompt(task, config, plan_context=formatted)
    user_content = request.messages[0]["content"]
    assert "EXECUTION PLAN" in user_content
    assert "Test task" in user_content


# === TEST 6: test_plan_step_has_verification ===


def test_plan_step_has_verification():
    """Each modification step has non-empty verification field."""
    task = Task(title="Modify files", description="Edit code")
    planner = Planner()
    plan = planner.create_plan(
        task,
        files_to_modify=["foo.py"],
    )
    # The modification step and the final verify step should have verification
    for step in plan.steps:
        if step.files_to_modify:
            assert step.verification, f"Step {step.index} has no verification"


# === TEST 7: test_complexity_rating_scales_with_files ===


def test_complexity_rating_scales_with_files():
    """Complexity rating scales with number of files to modify, capped at 10."""
    planner = Planner()

    plan_1 = planner.create_plan(
        Task(title="Small"),
        files_to_modify=["a.py"],
    )
    assert plan_1.complexity_rating == 1

    plan_5 = planner.create_plan(
        Task(title="Medium"),
        files_to_modify=[f"f{i}.py" for i in range(5)],
    )
    assert plan_5.complexity_rating == 5

    plan_15 = planner.create_plan(
        Task(title="Large"),
        files_to_modify=[f"f{i}.py" for i in range(15)],
    )
    assert plan_15.complexity_rating == 10  # capped


# === Additional tests ===


def test_create_plan_no_files():
    """Plan with no files to read or modify still has a verify step."""
    task = Task(title="Review", description="Review the design")
    planner = Planner()
    plan = planner.create_plan(task)
    assert len(plan.steps) >= 1
    assert plan.steps[-1].description == "Run tests and verify all changes"


def test_plan_step_status_marks_in_format():
    """Formatted plan shows correct status marks."""
    plan = TaskPlan(
        task_title="Status test",
        steps=[
            PlanStep(index=1, description="Pending step", status="pending"),
            PlanStep(index=2, description="Active step", status="in_progress"),
            PlanStep(index=3, description="Done step", status="completed"),
            PlanStep(index=4, description="Skipped step", status="skipped"),
        ],
    )
    result = Planner.format_plan_for_injection(plan)
    assert "[ ] 1." in result
    assert "[>] 2." in result
    assert "[x] 3." in result
    assert "[-] 4." in result


@pytest.mark.asyncio
async def test_create_plan_with_provider():
    """LLM-powered plan creation with mock provider."""

    class MockProvider:
        async def complete(self, request):
            return LLMResponse(
                content="1. Read the code\n2. Fix the bug\n3. Test",
                model="mock",
            )

    task = Task(title="Fix bug", description="Fix selector crash")
    planner = Planner()
    plan = await planner.create_plan_with_provider(task, MockProvider())
    assert plan.task_id == task.id
    assert plan.planner_agent == "llm_planner"
    assert "Read the code" in plan.think_notes


def test_update_step_status_nonexistent_index():
    """Updating a non-existent step index is a no-op."""
    plan = TaskPlan(
        steps=[PlanStep(index=1, description="Only step")],
    )
    updated = Planner.update_step_status(plan, 999, "completed")
    assert updated.steps[0].status == "pending"


@pytest.mark.timeout(60)
def test_build_prompt_without_plan():
    """_build_prompt works normally without plan_context (backward compat)."""
    from dharma_swarm.agent_runner import _build_prompt
    from dharma_swarm.models import AgentConfig, AgentRole

    task = Task(title="No plan", description="Just do it")
    config = AgentConfig(name="test-agent", role=AgentRole.CODER)
    request = _build_prompt(task, config)
    user_content = request.messages[0]["content"]
    assert "No plan" in user_content
    assert "EXECUTION PLAN" not in user_content
