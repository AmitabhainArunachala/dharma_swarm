"""Shared test fixtures for DHARMA SWARM."""

import asyncio
import tempfile
from pathlib import Path

import pytest


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
