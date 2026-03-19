"""Tests for prompt_registry — production prompt template management.

Covers: PromptTemplate CRUD, TPP assembly, versioning, inheritance,
invocation tracking, A/B testing, auditing, and fitness regression.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.prompt_registry import (
    CanaryVerdict,
    PromptAuditResult,
    PromptAuditor,
    PromptExperiment,
    PromptInvocation,
    PromptRegistry,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
    TPPLevel,
    TPPSection,
    create_base_templates,
    get_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_registry(tmp_path: Path) -> PromptRegistry:
    """Create a PromptRegistry backed by a temp directory."""
    return PromptRegistry(base_path=tmp_path / "prompts")


@pytest.fixture
def sample_template() -> PromptTemplate:
    """A minimal valid prompt template."""
    return PromptTemplate(
        name="test_coder",
        version=PromptVersion(major=1, minor=0, patch=0),
        status=PromptStatus.ACTIVE,
        description="Test coder prompt",
        tags=["coder", "test"],
        agent_roles=["coder"],
        task_types=["code"],
        sections=[
            TPPSection(
                level=TPPLevel.TELOS,
                content="Serve Jagat Kalyan through correct, tested code.",
                required=True,
            ),
            TPPSection(
                level=TPPLevel.IDENTITY,
                content="You are a coder agent in the DHARMA SWARM. Follow v7 rules.",
                required=True,
            ),
            TPPSection(
                level=TPPLevel.CONTEXT,
                content="Current project: dharma_swarm. Language: Python 3.11+.",
                required=False,
            ),
            TPPSection(
                level=TPPLevel.TASK,
                content="Implement the requested feature with tests.",
                required=True,
            ),
            TPPSection(
                level=TPPLevel.TECHNICAL,
                content="Output: Python code in ```python``` blocks. Include type hints.",
                required=False,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# PromptVersion tests
# ---------------------------------------------------------------------------


class TestPromptVersion:
    def test_str(self):
        v = PromptVersion(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

    def test_parse(self):
        v = PromptVersion.parse("2.1.0")
        assert v.major == 2
        assert v.minor == 1
        assert v.patch == 0

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            PromptVersion.parse("1.2")

    def test_bump_major(self):
        v = PromptVersion(major=1, minor=3, patch=5)
        bumped = v.bump_major()
        assert str(bumped) == "2.0.0"

    def test_bump_minor(self):
        v = PromptVersion(major=1, minor=3, patch=5)
        bumped = v.bump_minor()
        assert str(bumped) == "1.4.0"

    def test_bump_patch(self):
        v = PromptVersion(major=1, minor=3, patch=5)
        bumped = v.bump_patch()
        assert str(bumped) == "1.3.6"

    def test_ordering(self):
        v1 = PromptVersion(major=1, minor=0, patch=0)
        v2 = PromptVersion(major=1, minor=1, patch=0)
        v3 = PromptVersion(major=2, minor=0, patch=0)
        assert v1 < v2 < v3

    def test_equality(self):
        v1 = PromptVersion(major=1, minor=0, patch=0)
        v2 = PromptVersion(major=1, minor=0, patch=0)
        assert v1 == v2
        assert hash(v1) == hash(v2)


# ---------------------------------------------------------------------------
# PromptTemplate tests
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    def test_compute_hash(self, sample_template: PromptTemplate):
        h1 = sample_template.compute_hash()
        assert len(h1) == 16
        # Hash is deterministic
        h2 = sample_template.compute_hash()
        assert h1 == h2

    def test_hash_changes_with_content(self, sample_template: PromptTemplate):
        h1 = sample_template.compute_hash()
        sample_template.sections[0].content = "Different telos content"
        h2 = sample_template.compute_hash()
        assert h1 != h2

    def test_total_token_estimate(self, sample_template: PromptTemplate):
        tokens = sample_template.total_token_estimate()
        assert tokens > 0
        # All sections have content, so estimate should be reasonable
        total_chars = sum(len(s.content) for s in sample_template.sections)
        expected = total_chars // 4
        assert abs(tokens - expected) <= len(sample_template.sections)  # Rounding margin

    def test_assemble_default_order(self, sample_template: PromptTemplate):
        assembled = sample_template.assemble()
        # Telos comes first
        assert assembled.startswith("Serve Jagat Kalyan")
        # Technical comes last
        assert assembled.endswith("Include type hints.")
        # All sections present
        assert "coder agent" in assembled
        assert "dharma_swarm" in assembled
        assert "Implement" in assembled

    def test_assemble_with_overrides(self, sample_template: PromptTemplate):
        overrides = {
            TPPLevel.CONTEXT: "OVERRIDE: Working on prompt_registry.py",
        }
        assembled = sample_template.assemble(context_overrides=overrides)
        assert "OVERRIDE: Working on prompt_registry.py" in assembled
        assert "Current project" not in assembled  # Original context replaced

    def test_get_section(self, sample_template: PromptTemplate):
        telos = sample_template.get_section(TPPLevel.TELOS)
        assert telos is not None
        assert "Jagat Kalyan" in telos.content

        missing = sample_template.get_section(TPPLevel.TELOS)
        assert missing is not None  # TELOS exists

    def test_record_fitness(self, sample_template: PromptTemplate):
        assert sample_template.invocation_count == 0
        assert sample_template.mean_fitness == 0.0

        sample_template.record_fitness(0.8)
        assert sample_template.invocation_count == 1
        assert sample_template.mean_fitness == 0.8

        sample_template.record_fitness(0.6)
        assert sample_template.invocation_count == 2
        assert abs(sample_template.mean_fitness - 0.7) < 0.001

    def test_fitness_samples_capped(self, sample_template: PromptTemplate):
        for i in range(150):
            sample_template.record_fitness(0.5)
        assert len(sample_template.fitness_samples) == 100


# ---------------------------------------------------------------------------
# PromptRegistry CRUD tests
# ---------------------------------------------------------------------------


class TestPromptRegistryCRUD:
    def test_register_and_get(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tid = tmp_registry.register(sample_template)
        assert tid == sample_template.id

        retrieved = tmp_registry.get("test_coder")
        assert retrieved is not None
        assert retrieved.name == "test_coder"
        assert str(retrieved.version) == "1.0.0"

    def test_register_duplicate_version_raises(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)
        with pytest.raises(ValueError, match="already exists"):
            tmp_registry.register(sample_template)

    def test_get_specific_version(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        # Register v1.1.0
        v2 = sample_template.model_copy(deep=True)
        v2.id = "new_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        v2.sections[0].content = "Updated telos"
        tmp_registry.register(v2)

        # Get specific version
        retrieved = tmp_registry.get("test_coder", "1.0.0")
        assert retrieved is not None
        assert "Jagat Kalyan" in retrieved.sections[0].content

        retrieved_v2 = tmp_registry.get("test_coder", "1.1.0")
        assert retrieved_v2 is not None
        assert "Updated telos" in retrieved_v2.sections[0].content

    def test_get_nonexistent(self, tmp_registry: PromptRegistry):
        assert tmp_registry.get("nonexistent") is None

    def test_list_templates(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        all_templates = tmp_registry.list_templates()
        assert len(all_templates) == 1

        # Filter by tag
        coder_templates = tmp_registry.list_templates(tags=["coder"])
        assert len(coder_templates) == 1

        # Filter by non-matching tag
        research_templates = tmp_registry.list_templates(tags=["research"])
        assert len(research_templates) == 0

    def test_list_templates_by_role(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        coder = tmp_registry.list_templates(agent_role="coder")
        assert len(coder) == 1

        researcher = tmp_registry.list_templates(agent_role="researcher")
        assert len(researcher) == 0

    def test_list_versions(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "v2_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        tmp_registry.register(v2)

        versions = tmp_registry.list_versions("test_coder")
        assert len(versions) == 2
        assert versions[0] < versions[1]

    def test_promote(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "v2_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        v2.status = PromptStatus.DRAFT
        v2.sections[0].content = "New telos"
        tmp_registry.register(v2)

        assert tmp_registry.promote("test_coder", "1.1.0")

        active = tmp_registry.get("test_coder")
        assert active is not None
        assert str(active.version) == "1.1.0"
        assert active.status == PromptStatus.ACTIVE

    def test_deprecate(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)
        assert tmp_registry.deprecate("test_coder", "1.0.0")

        template = tmp_registry.get("test_coder", "1.0.0")
        assert template is not None
        assert template.status == PromptStatus.DEPRECATED


# ---------------------------------------------------------------------------
# Assembly with inheritance tests
# ---------------------------------------------------------------------------


class TestPromptAssembly:
    def test_assemble_with_inheritance(self, tmp_registry: PromptRegistry):
        # Register parent
        parent = PromptTemplate(
            name="base_agent",
            version=PromptVersion(major=1, minor=0, patch=0),
            status=PromptStatus.ACTIVE,
            sections=[
                TPPSection(level=TPPLevel.TELOS, content="Serve Jagat Kalyan."),
                TPPSection(level=TPPLevel.IDENTITY, content="You follow v7 rules."),
            ],
        )
        tmp_registry.register(parent)

        # Register child extending parent
        child = PromptTemplate(
            name="coder_agent",
            version=PromptVersion(major=1, minor=0, patch=0),
            status=PromptStatus.ACTIVE,
            parent_name="base_agent",
            parent_version="1.0.0",
            sections=[
                TPPSection(level=TPPLevel.IDENTITY, content="You are a coder. Write clean Python."),
                TPPSection(level=TPPLevel.TASK, content="Fix the bug described below."),
            ],
        )
        tmp_registry.register(child)

        # Assemble with inheritance
        assembled = tmp_registry.assemble("coder_agent", parent_chain=True)
        assert assembled is not None
        # Telos comes from parent
        assert "Jagat Kalyan" in assembled
        # Identity overridden by child
        assert "coder" in assembled
        assert "v7 rules" not in assembled  # Parent identity overridden
        # Task from child
        assert "Fix the bug" in assembled

    def test_assemble_without_inheritance(self, tmp_registry: PromptRegistry):
        parent = PromptTemplate(
            name="base",
            status=PromptStatus.ACTIVE,
            sections=[TPPSection(level=TPPLevel.TELOS, content="Parent telos")],
        )
        child = PromptTemplate(
            name="child",
            status=PromptStatus.ACTIVE,
            parent_name="base",
            parent_version="1.0.0",
            sections=[TPPSection(level=TPPLevel.TASK, content="Child task")],
        )
        tmp_registry.register(parent)
        tmp_registry.register(child)

        assembled = tmp_registry.assemble("child", parent_chain=False)
        assert assembled is not None
        assert "Parent telos" not in assembled
        assert "Child task" in assembled


# ---------------------------------------------------------------------------
# Invocation tracking tests
# ---------------------------------------------------------------------------


class TestInvocationTracking:
    def test_log_and_retrieve(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        inv = PromptInvocation(
            prompt_id=sample_template.id,
            prompt_name="test_coder",
            prompt_version="1.0.0",
            prompt_hash=sample_template.content_hash,
            agent_id="agent_001",
            agent_role="coder",
            task_id="task_001",
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            latency_ms=1500.0,
            success=True,
            fitness_score=0.85,
        )

        inv_id = tmp_registry.log_invocation(inv)
        assert inv_id

        invocations = tmp_registry.get_invocations(prompt_name="test_coder", days=1)
        assert len(invocations) == 1
        assert invocations[0].agent_id == "agent_001"
        assert invocations[0].fitness_score == 0.85

    def test_invocation_updates_template_fitness(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        for score in [0.8, 0.9, 0.7]:
            inv = PromptInvocation(
                prompt_id=sample_template.id,
                prompt_name="test_coder",
                prompt_version="1.0.0",
                prompt_hash="abc",
                agent_id="agent_001",
                fitness_score=score,
            )
            tmp_registry.log_invocation(inv)

        template = tmp_registry.get("test_coder")
        assert template is not None
        assert abs(template.mean_fitness - 0.8) < 0.001


# ---------------------------------------------------------------------------
# A/B Testing tests
# ---------------------------------------------------------------------------


class TestABTesting:
    def test_create_experiment(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "canary_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        v2.sections[0].content = "Improved telos"
        tmp_registry.register(v2)

        exp = tmp_registry.create_experiment(
            control_name="test_coder",
            canary_name="test_coder",
            canary_version="1.1.0",
            canary_traffic_pct=20.0,
        )

        assert exp.verdict == CanaryVerdict.RUNNING
        assert exp.canary_traffic_pct == 20.0

    def test_experiment_resolution_promote(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "canary_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        tmp_registry.register(v2)

        exp = tmp_registry.create_experiment(
            control_name="test_coder",
            canary_name="test_coder",
            canary_version="1.1.0",
            min_observations=5,
        )

        # Add observations -- canary is better
        for _ in range(10):
            exp.record_observation("control", 0.6)
            exp.record_observation("canary", 0.9)

        # Force ready
        assert exp.is_ready_to_resolve()

        verdict = exp.resolve()
        assert verdict == CanaryVerdict.PROMOTE
        assert exp.canary_mean > exp.control_mean

    def test_experiment_resolution_rollback(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "canary_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        tmp_registry.register(v2)

        exp = tmp_registry.create_experiment(
            control_name="test_coder",
            canary_name="test_coder",
            canary_version="1.1.0",
            min_observations=5,
        )

        # Canary is worse
        for _ in range(10):
            exp.record_observation("control", 0.85)
            exp.record_observation("canary", 0.4)

        verdict = exp.resolve()
        assert verdict == CanaryVerdict.ROLLBACK

    def test_experiment_inconclusive(self):
        exp = PromptExperiment(
            control_prompt_id="c1",
            control_prompt_name="test",
            control_version="1.0.0",
            canary_prompt_id="c2",
            canary_prompt_name="test",
            canary_version="1.1.0",
            min_observations=5,
        )
        # Not enough data
        exp.record_observation("control", 0.7)
        verdict = exp.resolve()
        assert verdict == CanaryVerdict.INCONCLUSIVE

    def test_route_experiment(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "canary_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        tmp_registry.register(v2)

        exp = tmp_registry.create_experiment(
            control_name="test_coder",
            canary_name="test_coder",
            canary_version="1.1.0",
            canary_traffic_pct=50.0,  # 50% for easy testing
        )

        # Route many times, should get both groups
        groups = set()
        for _ in range(100):
            version, group, exp_id = tmp_registry.route_experiment("test_coder")
            groups.add(group)
            assert exp_id == exp.id

        assert "control" in groups
        assert "canary" in groups

    def test_no_experiment_default_routing(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)
        version, group, exp_id = tmp_registry.route_experiment("test_coder")
        assert group == "default"
        assert exp_id is None

    def test_get_active_experiments(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        v2 = sample_template.model_copy(deep=True)
        v2.id = "canary_id"
        v2.version = PromptVersion(major=1, minor=1, patch=0)
        tmp_registry.register(v2)

        tmp_registry.create_experiment(
            control_name="test_coder",
            canary_name="test_coder",
            canary_version="1.1.0",
        )

        active = tmp_registry.get_active_experiments()
        assert len(active) == 1


# ---------------------------------------------------------------------------
# Prompt Auditor tests
# ---------------------------------------------------------------------------


class TestPromptAuditor:
    def test_valid_template_passes(self, sample_template: PromptTemplate):
        auditor = PromptAuditor()
        result = auditor.audit(sample_template)
        assert result.passed
        assert result.checks["tpp_complete"]
        assert result.checks["injection_safe"]

    def test_excessive_tokens_fails(self):
        huge = PromptTemplate(
            name="huge",
            sections=[
                TPPSection(
                    level=TPPLevel.TASK,
                    content="x" * 100_000,  # Way over budget
                    required=True,
                ),
            ],
        )
        auditor = PromptAuditor(max_total_tokens=1000)
        result = auditor.audit(huge)
        assert not result.passed
        assert not result.checks["within_token_budget"]

    def test_empty_section_warning(self):
        template = PromptTemplate(
            name="sparse",
            sections=[
                TPPSection(level=TPPLevel.TELOS, content="OK telos", required=True),
                TPPSection(level=TPPLevel.TASK, content="x", required=True),  # Too short
            ],
        )
        auditor = PromptAuditor(min_section_chars=5)
        result = auditor.audit(template)
        assert len(result.warnings) > 0

    def test_missing_telos_warning(self):
        template = PromptTemplate(
            name="no_telos",
            sections=[
                TPPSection(level=TPPLevel.TASK, content="Just do the thing.", required=True),
            ],
        )
        auditor = PromptAuditor()
        result = auditor.audit(template)
        assert any("TELOS" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Fitness report and regression tests
# ---------------------------------------------------------------------------


class TestObservability:
    def test_fitness_report(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        tmp_registry.register(sample_template)

        # Log several invocations
        for score in [0.8, 0.85, 0.9, 0.75, 0.82]:
            inv = PromptInvocation(
                prompt_id=sample_template.id,
                prompt_name="test_coder",
                prompt_version="1.0.0",
                prompt_hash="abc",
                agent_id="agent_001",
                total_tokens=500,
                fitness_score=score,
            )
            tmp_registry.log_invocation(inv)

        report = tmp_registry.fitness_report("test_coder", days=1)
        assert report["invocations"] == 5
        assert report["mean_fitness"] > 0.7
        assert report["total_tokens"] == 2500

    def test_fitness_report_empty(self, tmp_registry: PromptRegistry):
        report = tmp_registry.fitness_report("nonexistent")
        assert report["invocations"] == 0
        assert report["trend"] == "unknown"

    def test_regression_check(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        # Set historical fitness high
        for _ in range(20):
            sample_template.record_fitness(0.9)
        tmp_registry.register(sample_template)

        # Log recent low-fitness invocations
        for score in [0.5, 0.45, 0.55]:
            inv = PromptInvocation(
                prompt_id=sample_template.id,
                prompt_name="test_coder",
                prompt_version="1.0.0",
                prompt_hash="abc",
                agent_id="agent_001",
                fitness_score=score,
            )
            tmp_registry.log_invocation(inv)

        regressions = tmp_registry.regression_check(threshold=0.1)
        assert len(regressions) >= 1
        assert regressions[0]["name"] == "test_coder"
        assert regressions[0]["delta"] < 0


# ---------------------------------------------------------------------------
# Darwin Engine integration tests
# ---------------------------------------------------------------------------


class TestDarwinEngineIntegration:
    def test_as_evolvable_artifact(self, tmp_registry: PromptRegistry, sample_template: PromptTemplate):
        sample_template.record_fitness(0.82)
        sample_template.compute_hash()
        tmp_registry.register(sample_template)

        artifact = tmp_registry.as_evolvable_artifact("test_coder")
        assert artifact is not None
        assert artifact["artifact_type"] == "prompt_template"
        assert artifact["fitness"] > 0
        assert artifact["token_estimate"] > 0
        assert "coder" in artifact["tags"]

    def test_stigmergy_mark(self, sample_template: PromptTemplate):
        sample_template.mean_fitness = 0.92
        sample_template.invocation_count = 50
        sample_template.compute_hash()

        registry = PromptRegistry()
        mark = registry.emit_stigmergy_mark(sample_template)

        assert mark["agent"] == "prompt_registry"
        assert "prompt:" in mark["file_path"]
        assert mark["salience"] >= 0.9
        assert "High-fitness" in mark["observation"]


# ---------------------------------------------------------------------------
# Base template creation tests
# ---------------------------------------------------------------------------


class TestBaseTemplates:
    def test_create_base_templates(self):
        templates = create_base_templates()
        assert len(templates) >= 2  # Universal + at least one role

        # Universal base exists
        universal = [t for t in templates if t.name == "universal_base"]
        assert len(universal) == 1
        assert universal[0].get_section(TPPLevel.TELOS) is not None
        assert "Jagat Kalyan" in universal[0].get_section(TPPLevel.TELOS).content

    def test_role_templates_inherit_from_universal(self):
        templates = create_base_templates()
        role_templates = [t for t in templates if t.parent_name == "universal_base"]
        assert len(role_templates) >= 1

        for rt in role_templates:
            assert rt.parent_version == "1.0.0"
            assert len(rt.agent_roles) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_registry_operations(self, tmp_registry: PromptRegistry):
        assert tmp_registry.list_templates() == []
        assert tmp_registry.list_versions("nonexistent") == []
        assert tmp_registry.get("nonexistent") is None
        assert tmp_registry.assemble("nonexistent") is None
        assert not tmp_registry.promote("nonexistent", "1.0.0")
        assert not tmp_registry.deprecate("nonexistent", "1.0.0")

    def test_template_with_no_sections(self, tmp_registry: PromptRegistry):
        empty = PromptTemplate(name="empty", sections=[])
        tmp_registry.register(empty)
        assembled = tmp_registry.assemble("empty")
        assert assembled == ""

    def test_factory_function(self, tmp_path: Path):
        registry = get_registry(base_path=tmp_path / "reg")
        assert isinstance(registry, PromptRegistry)

    def test_concurrent_version_registration(self, tmp_registry: PromptRegistry):
        """Register multiple versions of the same template."""
        for minor in range(5):
            t = PromptTemplate(
                name="multi_version",
                version=PromptVersion(major=1, minor=minor, patch=0),
                status=PromptStatus.DRAFT if minor < 4 else PromptStatus.ACTIVE,
                sections=[
                    TPPSection(level=TPPLevel.TASK, content=f"Version {minor} task"),
                ],
            )
            tmp_registry.register(t)

        versions = tmp_registry.list_versions("multi_version")
        assert len(versions) == 5

    def test_experiment_with_equal_fitness(self):
        """When control and canary are equal, should be inconclusive."""
        exp = PromptExperiment(
            control_prompt_id="c1",
            control_prompt_name="test",
            control_version="1.0.0",
            canary_prompt_id="c2",
            canary_prompt_name="test",
            canary_version="1.1.0",
            min_observations=5,
            significance_level=0.05,
        )

        for _ in range(20):
            exp.record_observation("control", 0.75)
            exp.record_observation("canary", 0.75)

        verdict = exp.resolve()
        # Equal means no significant difference
        assert verdict in (CanaryVerdict.INCONCLUSIVE, CanaryVerdict.RUNNING)
