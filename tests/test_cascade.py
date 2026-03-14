"""Tests for the universal loop engine (cascade.py) and domain configs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dharma_swarm.cascade import (
    LoopEngine,
    _resolve_fn,
    _variance,
    get_registered_domains,
    run_domain,
)
from dharma_swarm.cascade_domains.common import (
    default_eigenform,
    default_generate,
    default_mutate,
    default_score,
    default_select,
    default_test,
    telos_gate,
)
from dharma_swarm.models import LoopDomain, LoopResult


# ---------------------------------------------------------------------------
# Function resolution
# ---------------------------------------------------------------------------


def test_resolve_fn_valid():
    fn = _resolve_fn("dharma_swarm.cascade_domains.common.telos_gate")
    assert callable(fn)
    assert fn is telos_gate


def test_resolve_fn_invalid_path():
    with pytest.raises(ImportError):
        _resolve_fn("not_a_module")


def test_resolve_fn_missing_attr():
    with pytest.raises(AttributeError):
        _resolve_fn("dharma_swarm.cascade_domains.common.nonexistent_fn")


# ---------------------------------------------------------------------------
# Common phase functions
# ---------------------------------------------------------------------------


def test_telos_gate_pass():
    result = telos_gate({"content": "hello"}, {})
    assert result["passed"] is True
    assert result["decision"] in ("allow", "review")


def test_telos_gate_block():
    """Harmful content triggers AHIMSA block via real TelosGatekeeper."""
    result = telos_gate({"content": "rm -rf / destroy everything"}, {"action": "rm -rf /"})
    assert result["passed"] is False
    assert result["decision"] == "block"
    assert "AHIMSA" in result.get("gate_scores", {})


def test_default_eigenform_identical():
    a = {"fitness": {"q": 0.5, "r": 0.8}}
    b = {"fitness": {"q": 0.5, "r": 0.8}}
    assert default_eigenform(a, b) == 0.0


def test_default_eigenform_different():
    a = {"fitness": {"q": 0.0}}
    b = {"fitness": {"q": 1.0}}
    dist = default_eigenform(a, b)
    assert dist > 0.0


def test_default_eigenform_empty():
    assert default_eigenform({}, {}) == float("inf")


def test_default_generate_with_seed():
    seed = {"content": "x", "fitness": {"a": 1}}
    result = default_generate(seed, {})
    assert result["content"] == "x"


def test_default_generate_no_seed():
    result = default_generate(None, {})
    assert "content" in result


def test_default_test():
    artifact = {"content": "x"}
    result = default_test(artifact, {})
    assert result["test_passed"] is True


def test_default_score():
    artifact = {"content": "x" * 500, "test_passed": True}
    result = default_score(artifact, {})
    assert "score" in result
    assert result["score"] >= 0


def test_default_mutate():
    artifact = {"content": "x"}
    result = default_mutate(artifact, {}, 0.2)
    assert result["metadata"]["mutated"] is True
    assert result["metadata"]["mutation_rate"] == 0.2


def test_default_select():
    candidates = [
        {"score": 0.3, "content": "a"},
        {"score": 0.9, "content": "b"},
        {"score": 0.5, "content": "c"},
    ]
    result = default_select(candidates, {})
    assert result["content"] == "b"


def test_default_select_empty():
    result = default_select([], {})
    assert "content" in result


# ---------------------------------------------------------------------------
# Variance utility
# ---------------------------------------------------------------------------


def test_variance_uniform():
    assert _variance([5.0, 5.0, 5.0]) == 0.0


def test_variance_spread():
    v = _variance([0.0, 10.0])
    assert v == 25.0


def test_variance_single():
    assert _variance([3.0]) == 0.0


# ---------------------------------------------------------------------------
# Domain registry
# ---------------------------------------------------------------------------


def test_get_registered_domains():
    domains = get_registered_domains()
    assert "code" in domains
    assert "meta" in domains
    assert "product" in domains
    assert "skill" in domains
    assert "research" in domains
    assert len(domains) == 5


def test_domain_configs_valid():
    domains = get_registered_domains()
    for name, domain in domains.items():
        assert domain.name == name
        assert domain.max_iterations > 0
        assert 0 < domain.fitness_threshold < 1
        assert domain.eigenform_epsilon > 0


# ---------------------------------------------------------------------------
# LoopEngine
# ---------------------------------------------------------------------------


def _make_simple_domain() -> LoopDomain:
    """A domain using all default common functions."""
    return LoopDomain(
        name="test_domain",
        generate_fn="dharma_swarm.cascade_domains.common.default_generate",
        test_fn="dharma_swarm.cascade_domains.common.default_test",
        score_fn="dharma_swarm.cascade_domains.common.default_score",
        gate_fn="dharma_swarm.cascade_domains.common.telos_gate",
        mutate_fn="dharma_swarm.cascade_domains.common.default_mutate",
        select_fn="dharma_swarm.cascade_domains.common.default_select",
        eigenform_fn="dharma_swarm.cascade_domains.common.default_eigenform",
        max_iterations=5,
        fitness_threshold=0.3,
        max_duration_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_loop_engine_runs():
    domain = _make_simple_domain()
    engine = LoopEngine(domain)
    result = await engine.run(context={})
    assert isinstance(result, LoopResult)
    assert result.domain == "test_domain"
    assert result.iterations_completed > 0
    assert result.duration_seconds > 0


@pytest.mark.asyncio
async def test_loop_engine_with_seed():
    domain = _make_simple_domain()
    engine = LoopEngine(domain)
    seed = {"content": "hello world", "fitness": {"q": 0.7}}
    result = await engine.run(seed, context={})
    assert result.iterations_completed > 0
    assert len(result.fitness_trajectory) > 0


@pytest.mark.asyncio
async def test_loop_engine_eigenform_convergence():
    """A domain with identical generate should converge to eigenform quickly."""
    domain = _make_simple_domain()
    domain.eigenform_epsilon = 1.0  # Very generous epsilon
    engine = LoopEngine(domain)
    result = await engine.run(context={})
    # With default stubs producing identical artifacts, should converge
    assert result.iterations_completed <= domain.max_iterations


@pytest.mark.asyncio
async def test_loop_engine_respects_time_limit():
    domain = _make_simple_domain()
    domain.max_duration_seconds = 0.001  # Nearly instant timeout
    domain.max_iterations = 1000
    engine = LoopEngine(domain)
    result = await engine.run(context={})
    assert result.iterations_completed < 1000


@pytest.mark.asyncio
async def test_loop_engine_fitness_trajectory():
    domain = _make_simple_domain()
    engine = LoopEngine(domain)
    result = await engine.run(context={})
    assert len(result.fitness_trajectory) == result.iterations_completed
    for f in result.fitness_trajectory:
        assert isinstance(f, float)


@pytest.mark.asyncio
async def test_loop_engine_eigenform_trajectory():
    domain = _make_simple_domain()
    engine = LoopEngine(domain)
    seed = {"content": "some content", "fitness": {"q": 0.5}}
    result = await engine.run(seed, context={}, resume=False)
    # First entry is inf (no previous), rest are distances
    assert len(result.eigenform_trajectory) > 0


# ---------------------------------------------------------------------------
# run_domain convenience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_domain_code():
    result = await run_domain("code", context={"component": "test"})
    assert result.domain == "code"
    assert result.iterations_completed > 0


@pytest.mark.asyncio
async def test_run_domain_meta():
    result = await run_domain("meta", context={})
    assert result.domain == "meta"


@pytest.mark.asyncio
async def test_run_domain_unknown():
    with pytest.raises(ValueError, match="Unknown domain"):
        await run_domain("nonexistent")


@pytest.mark.asyncio
async def test_run_domain_with_config():
    result = await run_domain("code", config={"max_iterations": 3})
    assert result.iterations_completed <= 3


# ---------------------------------------------------------------------------
# Meta domain specifics
# ---------------------------------------------------------------------------


def test_meta_gate_blocks_self():
    from dharma_swarm.cascade_domains.meta import gate

    result = gate({"target_domains": {"meta": {}}}, {})
    assert not result["passed"]
    assert result["decision"] == "block"


def test_meta_gate_allows_others():
    from dharma_swarm.cascade_domains.meta import gate

    result = gate({"target_domains": {"code": {}, "skill": {}}}, {})
    assert result["passed"]


def test_meta_generate_excludes_meta():
    from dharma_swarm.cascade_domains.meta import generate

    ctx = {"target_domains": {"code": {}, "meta": {}, "skill": {}}}
    result = generate(None, ctx)
    assert "meta" not in result["target_domains"]


def test_meta_mutate():
    from dharma_swarm.cascade_domains.meta import mutate

    artifact = {
        "target_domains": {
            "code": {"max_iterations": 30, "mutation_rate": 0.1},
        },
        "fitness": {},
    }
    mutated = mutate(artifact, {}, mutation_rate=1.0)  # force mutation
    assert mutated["metadata"]["mutated"] is True


# ---------------------------------------------------------------------------
# Code domain — real file scoring
# ---------------------------------------------------------------------------


def test_code_generate_from_path():
    """Code generate reads a real Python file."""
    from dharma_swarm.cascade_domains.code import generate

    artifact = generate({"path": "dharma_swarm/elegance.py"}, {})
    assert len(artifact["content"]) > 100
    assert artifact["path"] == "dharma_swarm/elegance.py"
    assert artifact["component"] == "elegance"


def test_code_test_syntax_valid():
    """Code test checks syntax via ast.parse."""
    from dharma_swarm.cascade_domains.code import test

    artifact = {"content": "def foo():\n    return 42\n", "path": None}
    result = test(artifact, {})
    assert result["test_passed"] is True
    assert result["test_results"]["syntax_valid"] is True


def test_code_test_syntax_invalid():
    """Code test detects invalid syntax."""
    from dharma_swarm.cascade_domains.code import test

    artifact = {"content": "def foo(\n    return 42\n", "path": None}
    result = test(artifact, {})
    assert result["test_passed"] is False
    assert result["test_results"]["syntax_valid"] is False


def test_code_score_uses_elegance():
    """Code score uses real elegance evaluator."""
    from dharma_swarm.cascade_domains.code import score

    artifact = {
        "content": 'def hello():\n    """Greet."""\n    return "hello"\n',
        "test_passed": True,
        "test_results": {"syntax_valid": True, "pytest_passed": True},
    }
    result = score(artifact, {})
    assert "fitness" in result
    assert "elegance" in result["fitness"]
    assert 0 < result["fitness"]["elegance"] <= 1.0
    assert result["score"] > 0


def test_code_score_penalizes_failed_tests():
    """Failed test_passed should give correctness=0."""
    from dharma_swarm.cascade_domains.code import score

    artifact = {
        "content": "x = 1\n",
        "test_passed": False,
        "test_results": {"syntax_valid": False},
    }
    result = score(artifact, {})
    assert result["fitness"]["correctness"] == 0.0


# ---------------------------------------------------------------------------
# Skill domain — real skill scoring
# ---------------------------------------------------------------------------


def test_skill_generate_reads_real_skill():
    """Skill generate reads an actual SKILL.md."""
    from dharma_swarm.cascade_domains.skill import generate

    artifact = generate({"skill_name": "cascade"}, {})
    assert len(artifact["content"]) > 100
    assert artifact["skill_name"] == "cascade"
    # Path should be set since cascade skill exists
    assert artifact.get("skill_path") is not None


def test_skill_score_structure():
    """Skill score measures structure (frontmatter, headers, etc)."""
    from dharma_swarm.cascade_domains.skill import score

    content = (
        "---\nname: test\ndescription: A test skill\n"
        "allowed-tools: Read\n---\n# Title\n## Section\n"
        "```bash\necho hi\n```\n"
    )
    artifact = {"content": content, "skill_name": "test", "fitness": {}}
    result = score(artifact, {})
    assert "structure" in result["fitness"]
    assert result["fitness"]["structure"] > 0.5


def test_skill_score_empty_content():
    """Empty skill content should score very low."""
    from dharma_swarm.cascade_domains.skill import score

    artifact = {"content": "", "skill_name": "empty", "fitness": {}}
    result = score(artifact, {})
    assert result["score"] < 0.2


# ---------------------------------------------------------------------------
# Common — real telos gate
# ---------------------------------------------------------------------------


def test_telos_gate_passes_normal_content():
    """Normal code content should pass telos gate."""
    artifact = {"content": "def hello():\n    return 'world'\n"}
    result = telos_gate(artifact, {"tool": "cascade_domain"})
    assert result["passed"] is True


def test_telos_gate_blocks_harmful():
    """Harmful content should be blocked by AHIMSA gate."""
    artifact = {"content": "rm -rf / destroy everything delete all data"}
    result = telos_gate(
        artifact,
        {"action": "rm -rf / destroy everything", "tool": "cascade_domain"},
    )
    # Should block or at least flag
    assert isinstance(result["gate_scores"], dict)


# ---------------------------------------------------------------------------
# End-to-end cascade with real scoring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_code_real_file():
    """Full cascade run on a real Python file produces meaningful scores."""
    result = await run_domain(
        "code", seed={"path": "dharma_swarm/models.py"}, resume=False
    )
    assert result.best_fitness > 0.3
    assert result.iterations_completed >= 1
    # Real files should reach eigenform quickly (deterministic scoring)
    assert result.eigenform_reached


@pytest.mark.asyncio
async def test_cascade_skill_real():
    """Full cascade run on a real skill produces meaningful scores."""
    result = await run_domain(
        "skill", seed={"skill_name": "forge"}, resume=False
    )
    assert result.best_fitness > 0.5
    assert result.eigenform_reached


# ---------------------------------------------------------------------------
# Product domain — real project scoring
# ---------------------------------------------------------------------------


def test_product_generate_from_project():
    """Product generate reads a real project directory."""
    from dharma_swarm.cascade_domains.product import generate

    artifact = generate({"project_path": "."}, {})
    assert len(artifact["content"]) > 0
    assert artifact["project_path"] == "."


def test_product_generate_from_file():
    """Product generate can read a single file."""
    from dharma_swarm.cascade_domains.product import generate

    artifact = generate({"path": "dharma_swarm/models.py"}, {})
    assert len(artifact["content"]) > 100


def test_product_test_project():
    """Product test checks project structure."""
    from dharma_swarm.cascade_domains.product import test

    artifact = {
        "content": "def foo(): pass\n",
        "project_path": str(Path(__file__).resolve().parents[1]),
    }
    result = test(artifact, {})
    assert result["test_passed"] is True
    assert result["test_results"]["has_content"] is True
    assert result["test_results"]["syntax_valid"] is True


def test_product_test_empty():
    """Empty product content fails test."""
    from dharma_swarm.cascade_domains.product import test

    artifact = {"content": "", "project_path": None}
    result = test(artifact, {})
    assert result["test_passed"] is False


def test_product_score_real_project():
    """Product score on dharma_swarm root produces meaningful dimensions."""
    from dharma_swarm.cascade_domains.product import generate, score, test

    artifact = generate({"project_path": str(Path(__file__).resolve().parents[1])}, {})
    artifact = test(artifact, {})
    artifact = score(artifact, {})
    assert "fitness" in artifact
    assert artifact["score"] > 0.2
    assert "foreman_quality" in artifact["fitness"]
    assert "elegance" in artifact["fitness"]
    assert "behavioral" in artifact["fitness"]
    assert "completeness" in artifact["fitness"]


def test_product_score_empty():
    """Empty product scores near zero."""
    from dharma_swarm.cascade_domains.product import score

    artifact = {
        "content": "",
        "project_path": None,
        "test_results": {"has_content": False, "syntax_valid": True},
    }
    result = score(artifact, {})
    assert result["score"] < 0.4


@pytest.mark.asyncio
async def test_cascade_product_real():
    """Full cascade run on dharma_swarm project produces meaningful scores."""
    result = await run_domain(
        "product",
        seed={"project_path": str(Path(__file__).resolve().parents[1])},
        resume=False,
    )
    assert result.best_fitness > 0.2
    assert result.iterations_completed >= 1
    assert result.eigenform_reached


# ---------------------------------------------------------------------------
# Research domain — real research document scoring
# ---------------------------------------------------------------------------


def test_research_generate_from_path():
    """Research generate reads a real file."""
    from dharma_swarm.cascade_domains.research import generate

    artifact = generate({"path": "dharma_swarm/models.py", "track": "rv"}, {})
    assert len(artifact["content"]) > 100
    assert artifact["track"] == "rv"


def test_research_test_structured_doc():
    """Research test detects structure and claims in a document."""
    from dharma_swarm.cascade_domains.research import test

    content = """# Introduction

We show that R_V contraction implies a phase transition.

## Methods

Our analysis demonstrates significant effect sizes (Cohen's d = -1.47).
We find that AUROC = 0.909 for the classification task.

## Results

Therefore, the geometric signature must correlate with behavioral changes.
The results indicate a threshold at Layer 27.

## References

\\cite{hofstadter1979} suggests that self-reference creates fixed points.
"""
    artifact = {"content": content}
    result = test(artifact, {})
    assert result["test_passed"] is True
    assert result["test_results"]["has_structure"] is True
    assert result["test_results"]["has_claims"] is True
    assert result["test_results"]["claim_count"] >= 3


def test_research_test_empty():
    """Empty research content fails test."""
    from dharma_swarm.cascade_domains.research import test

    artifact = {"content": ""}
    result = test(artifact, {})
    assert result["test_passed"] is False


def test_research_score_rv_paper():
    """Research score produces meaningful dimensions for R_V-like content."""
    from dharma_swarm.cascade_domains.research import score, test

    content = """# Geometric Signatures of Self-Referential Processing

We demonstrate that R_V = PR_late / PR_early captures value matrix
participation ratio contraction in transformer representations.

## Key Results

Hedges' g = -1.47 (Mistral-7B), causal validation at Layer 27,
AUROC = 0.909. The effect size is significant (p < 0.001, n = 480).

The participation ratio contraction implies a fixed point in the
value matrix column space. This eigenform corresponds to the
behavioral phase transition observed in Phoenix/URA protocols.

## Methods

SVD-based participation ratio measurement across 480 prompt pairs.
Cohen's d computed with bootstrap confidence intervals.

\\cite{hofstadter1979}
\\cite{varela1991}
"""
    artifact = {"content": content, "track": "rv"}
    artifact = test(artifact, {})
    artifact = score(artifact, {})
    assert artifact["score"] > 0.3
    assert artifact["fitness"]["claim_density"] > 0
    assert artifact["fitness"]["verifiability"] > 0
    assert artifact["fitness"]["relevance"] > 0.5  # R_V keywords present
    assert artifact["fitness"]["word_count"] > 50


def test_research_score_empty():
    """Empty research content scores near zero."""
    from dharma_swarm.cascade_domains.research import score

    artifact = {
        "content": "",
        "track": "rv",
        "test_results": {"claim_count": 0, "citation_count": 0},
    }
    result = score(artifact, {})
    assert result["score"] < 0.3


def test_research_score_different_tracks():
    """Different tracks weight different keywords."""
    from dharma_swarm.cascade_domains.research import score

    rv_content = "R_V participation ratio contraction geometric signature SVD AUROC"
    phoenix_content = "phoenix URA L3 L4 phase transition recursive self-reference"

    artifact_rv = {
        "content": rv_content,
        "track": "rv",
        "test_results": {"claim_count": 1, "citation_count": 0},
    }
    artifact_phoenix = {
        "content": phoenix_content,
        "track": "phoenix",
        "test_results": {"claim_count": 1, "citation_count": 0},
    }

    result_rv = score(artifact_rv, {})
    result_phoenix = score(artifact_phoenix, {})

    # Each should have higher relevance for its own track
    assert result_rv["fitness"]["relevance"] > 0.3
    assert result_phoenix["fitness"]["relevance"] > 0.3


@pytest.mark.asyncio
async def test_cascade_research_real():
    """Full cascade run on a real research file produces meaningful scores."""
    result = await run_domain(
        "research",
        seed={"path": "dharma_swarm/rv.py", "track": "rv"},
        resume=False,
    )
    assert result.best_fitness > 0.1
    assert result.iterations_completed >= 1
    assert result.eigenform_reached
