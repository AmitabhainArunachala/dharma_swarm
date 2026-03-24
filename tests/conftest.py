"""Shared test fixtures for DHARMA SWARM."""

import os

import pytest
try:
    from hypothesis import settings, Verbosity

    # Configure Hypothesis profiles for property-based testing
    settings.register_profile("ci", max_examples=100, verbosity=Verbosity.verbose)
    settings.register_profile("dev", max_examples=20, verbosity=Verbosity.normal)
    settings.register_profile("deep", max_examples=1000, deadline=None)

    # Use dev profile by default, CI profile in GitHub Actions
    if os.getenv("CI"):
        settings.load_profile("ci")
    else:
        settings.load_profile("dev")
except ImportError:
    pass  # hypothesis not installed — property-based tests will be skipped


@pytest.fixture
def tmp_path_factory_custom(tmp_path):
    """Provide a temporary directory for test databases and state."""
    return tmp_path


@pytest.fixture
def state_dir(tmp_path):
    """Create a temporary .dharma state directory."""
    d = tmp_path / ".dharma"
    d.mkdir()
    (d / "memory").mkdir()
    (d / "tasks").mkdir()
    (d / "messages").mkdir()
    return d


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary SQLite database path."""
    return tmp_path / "test.db"


# Prefixes whose env vars leak runtime config into routing/scheduling tests.
_DGC_LEAK_PREFIXES = ("DGC_ROUTER_", "DGC_AGENT_")


@pytest.fixture(autouse=True)
def _isolate_dgc_env(monkeypatch):
    """Strip DGC_ROUTER_* and DGC_AGENT_* env vars so tests don't inherit runtime config."""
    for key in list(os.environ):
        if any(key.startswith(prefix) for prefix in _DGC_LEAK_PREFIXES):
            monkeypatch.delenv(key)


@pytest.fixture(autouse=True)
def _isolate_stigmergy(tmp_path, monkeypatch):
    """Redirect StigmergyStore to a tmpdir so tests never pollute ~/.dharma/stigmergy/marks.jsonl."""
    test_base = tmp_path / "_stigmergy_isolated"
    monkeypatch.setattr("dharma_swarm.stigmergy._DEFAULT_BASE", test_base)
    # Reset module-level singleton so each test gets a fresh store with the redirected path
    monkeypatch.setattr("dharma_swarm.stigmergy._default_store", None)


@pytest.fixture
def fast_gate():
    """Mock telos gate to return ALLOW instantly.

    Use in tests that don't care about gate behavior to avoid
    the ~10s overhead of the full reflective reroute cycle.
    """
    from unittest.mock import patch
    from dharma_swarm.models import GateCheckResult, GateDecision
    from dharma_swarm.telos_gates import ReflectiveGateOutcome

    allow = ReflectiveGateOutcome(
        result=GateCheckResult(
            decision=GateDecision.ALLOW,
            reason="All gates passed (test mock)",
        ),
    )
    with patch(
        "dharma_swarm.agent_runner.check_with_reflective_reroute",
        return_value=allow,
    ):
        yield allow
