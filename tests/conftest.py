"""Shared test fixtures for DHARMA SWARM."""

import asyncio
import os
import tempfile
from pathlib import Path

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
def _isolate_cost_ledger(request, monkeypatch):
    """Prevent real budget state from blocking test runs.

    CostLedger reads from ~/.dharma/costs/ — production data.
    Tests that specifically test budget behavior can opt out with
    @pytest.mark.real_budget.
    """
    if "real_budget" in request.keywords:
        return
    monkeypatch.setattr(
        "dharma_swarm.cost_ledger.CostLedger.should_stop",
        lambda self: False,
    )


@pytest.fixture(autouse=True)
def _isolate_memory_plane(request, monkeypatch):
    """Prevent agent_runner from reading the production memory plane DB.

    The real ~/.dharma/db/memory_plane.db can be large and cause timeouts
    in the unified_index read path. Tests that specifically test memory
    context can opt out with @pytest.mark.real_memory.
    """
    if "real_memory" in request.keywords:
        return
    try:
        monkeypatch.setattr(
            "dharma_swarm.context.read_memory_context",
            lambda *args, **kwargs: "",
        )
        monkeypatch.setattr(
            "dharma_swarm.context.read_latent_gold_context",
            lambda *args, **kwargs: "",
        )
    except (AttributeError, ImportError):
        pass  # context module may not be importable in all test environments


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
