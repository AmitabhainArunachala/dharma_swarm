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
