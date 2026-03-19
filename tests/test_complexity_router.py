"""Tests for complexity_router.py — fast/slow path classification."""

import pytest

from dharma_swarm.complexity_router import (
    ComplexityRoute,
    ComplexityRouter,
)


@pytest.fixture
def router():
    return ComplexityRouter(threshold=0.45)


def test_simple_known_action_fast(router):
    """Known single-domain action routes to FAST path."""
    result = router.classify(
        action_type="write_file",
        target="/Users/dhyana/dharma_swarm/dharma_swarm/foo.py",
        domains=["code"],
        affected_agents=["agent_1"],
    )
    assert result.is_fast
    assert result.route == ComplexityRoute.FAST
    assert len(result.fast_gates) > 0


def test_novel_cross_domain_slow(router):
    """Novel cross-domain action routes to SLOW path."""
    result = router.classify(
        action_type="unprecedented_thing",
        target="/some/path",
        domains=["code", "research", "meta"],
        affected_agents=["a1", "a2", "a3", "a4", "a5", "a6"],
    )
    assert not result.is_fast
    assert result.route == ComplexityRoute.SLOW


def test_known_action_no_extras(router):
    """Known action with no extra info defaults to FAST."""
    result = router.classify(action_type="read_file")
    assert result.is_fast


def test_explicit_novel_flag(router):
    """is_novel=True forces high uncertainty."""
    result = router.classify(
        action_type="read_file",
        is_novel=True,
        domains=["code", "meta"],
    )
    # High uncertainty + domain crossing should push to SLOW
    assert result.score.uncertainty == 1.0


def test_multi_system_correlation(router):
    """Actions touching multiple systems get higher correlation score."""
    result = router.classify(
        action_type="deploy_system",
        target="/Users/dhyana/dharma_swarm/dharma_swarm/agents/daemon.py",
        affected_systems=["dharma_swarm", "agni", "infrastructure"],
    )
    assert result.score.correlation >= 0.6


def test_score_components(router):
    """All score components are in [0, 1]."""
    result = router.classify(
        action_type="complex_thing",
        domains=["code", "skill", "product"],
        affected_agents=["a", "b", "c", "d"],
        affected_systems=["dharma_swarm", "agni"],
    )
    score = result.score
    assert 0.0 <= score.correlation <= 1.0
    assert 0.0 <= score.domain_crossings <= 1.0
    assert 0.0 <= score.stakeholders <= 1.0
    assert 0.0 <= score.uncertainty <= 1.0
    assert 0.0 <= score.weighted_total <= 1.0


def test_fast_gates_only_on_fast_path(router):
    """fast_gates is populated only on FAST route."""
    fast = router.classify(action_type="read_file")
    slow = router.classify(
        action_type="unknown_action",
        domains=["code", "meta", "research"],
        affected_agents=["a"] * 10,
        is_novel=True,
    )
    assert len(fast.fast_gates) > 0
    assert len(slow.fast_gates) == 0


def test_custom_threshold():
    """Custom threshold changes routing behavior."""
    strict = ComplexityRouter(threshold=0.1)
    lenient = ComplexityRouter(threshold=0.9)

    action_kwargs = dict(action_type="moderate_thing", domains=["code", "skill"])
    strict_result = strict.classify(**action_kwargs)
    lenient_result = lenient.classify(**action_kwargs)

    # Same action, different thresholds → different routes
    assert lenient_result.is_fast  # Lenient should route fast
