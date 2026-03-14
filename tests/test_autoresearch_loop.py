"""Tests for dharma_swarm.autoresearch_loop -- AutoResearchLoop self-improvement."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.autoresearch_loop import (
    DHARMA_SWARM_ROOT,
    DHARMA_SWARM_SRC,
    IMMUTABLE_DIRS,
    IMMUTABLE_FILES,
    AutoResearchLoop,
    IterationResult,
    LoopConfig,
    _MAX_SANE_LINES,
    get_mutable_modules,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def src_dir(tmp_path: Path) -> Path:
    """Create a fake dharma_swarm source directory with test modules."""
    src = tmp_path / "dharma_swarm"
    src.mkdir()

    # Mutable modules
    (src / "providers.py").write_text(
        '"""Providers module."""\n\ndef get_provider():\n    return None\n',
        encoding="utf-8",
    )
    (src / "context.py").write_text(
        '"""Context engine."""\n\nclass ContextEngine:\n    pass\n',
        encoding="utf-8",
    )
    (src / "orchestrator.py").write_text(
        '"""Orchestrator."""\n\nclass Orchestrator:\n    def run(self): pass\n',
        encoding="utf-8",
    )

    # Immutable modules
    (src / "models.py").write_text(
        '"""Models -- immutable schema."""\n\nclass Task: pass\n',
        encoding="utf-8",
    )
    (src / "telos_gates.py").write_text(
        '"""Telos gates -- immutable."""\n\ndef check(): pass\n',
        encoding="utf-8",
    )
    (src / "__init__.py").write_text('"""Package init."""\n', encoding="utf-8")
    (src / "autoresearch_loop.py").write_text(
        '"""Self -- immutable."""\n\nclass AutoResearchLoop: pass\n',
        encoding="utf-8",
    )

    # Immutable directory
    hooks = src / "hooks"
    hooks.mkdir()
    (hooks / "telos_gate.py").write_text(
        '"""Hook gate -- immutable dir."""\n\ndef gate(): pass\n',
        encoding="utf-8",
    )

    # Stub file (too small, should be excluded)
    (src / "stub.py").write_text("# tiny", encoding="utf-8")

    return src


@pytest.fixture
def root_dir(tmp_path: Path) -> Path:
    """Return the fake project root directory."""
    return tmp_path


@pytest.fixture
def loop_config() -> LoopConfig:
    """Return a default LoopConfig suitable for testing."""
    return LoopConfig(
        fitness_threshold=0.6,
        max_iterations=3,
        sleep_between_sec=0.0,
        test_timeout_sec=10.0,
        dry_run=True,
    )


# ---------------------------------------------------------------------------
# test_get_mutable_modules_excludes_immutable
# ---------------------------------------------------------------------------


def test_get_mutable_modules_excludes_immutable(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify models.py, telos_gates.py, __init__.py, hooks/ are excluded."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )

    modules = get_mutable_modules()
    module_names = {m.name for m in modules}

    # Immutable files must NOT appear
    for immutable in IMMUTABLE_FILES:
        assert immutable not in module_names, f"{immutable} should be excluded"

    # Files inside immutable dirs must NOT appear
    assert "telos_gate.py" not in module_names

    # Stub files (< 50 bytes) must NOT appear
    assert "stub.py" not in module_names

    # Mutable files SHOULD appear
    assert "providers.py" in module_names
    assert "context.py" in module_names
    assert "orchestrator.py" in module_names


def test_get_mutable_modules_nonexistent_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """If DHARMA_SWARM_SRC does not exist, return empty list."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC",
        tmp_path / "nonexistent",
    )
    assert get_mutable_modules() == []


# ---------------------------------------------------------------------------
# test_loop_config_defaults
# ---------------------------------------------------------------------------


def test_loop_config_defaults():
    """Verify default config values are sensible."""
    config = LoopConfig()
    assert config.fitness_threshold == 0.6
    assert config.max_iterations == 10
    assert config.sleep_between_sec == 30.0
    assert config.test_timeout_sec == 300.0
    assert config.target_modules == []
    assert config.dry_run is False


def test_loop_config_custom():
    """Verify custom config values are preserved."""
    config = LoopConfig(
        fitness_threshold=0.8,
        max_iterations=5,
        dry_run=True,
        target_modules=["providers.py"],
    )
    assert config.fitness_threshold == 0.8
    assert config.max_iterations == 5
    assert config.dry_run is True
    assert config.target_modules == ["providers.py"]


# ---------------------------------------------------------------------------
# test_select_module_round_robin
# ---------------------------------------------------------------------------


def test_select_module_round_robin(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify module selection cycles through available modules."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_ROOT", src_dir.parent
    )

    loop = AutoResearchLoop(LoopConfig(dry_run=True))

    # Force-populate the mutable list
    mutable = loop._resolve_mutable()
    assert len(mutable) >= 3

    # Round-robin: iteration 0, 1, 2 should cycle through modules
    selections = []
    for i in range(len(mutable) + 1):
        loop._iteration = i
        selected = loop._select_module()
        selections.append(selected.name)

    # After N modules, the N+1th should wrap to the first
    assert selections[len(mutable)] == selections[0]


def test_select_module_raises_when_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """RuntimeError raised when no mutable modules are found."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC",
        tmp_path / "nonexistent",
    )

    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    with pytest.raises(RuntimeError, match="No mutable modules"):
        loop._select_module()


# ---------------------------------------------------------------------------
# test_read_module_context_includes_source
# ---------------------------------------------------------------------------


def test_read_module_context_includes_source(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify context includes the file's source code content."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_ROOT", src_dir.parent
    )

    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    module_path = src_dir / "providers.py"

    context = loop._read_module_context(module_path)

    assert isinstance(context, str)
    assert "providers.py" in context
    assert "get_provider" in context
    assert "===" in context  # header formatting


def test_read_module_context_missing_file(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Context for a missing file should contain an error message."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_ROOT", src_dir.parent
    )

    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    fake_path = src_dir / "nonexistent.py"

    context = loop._read_module_context(fake_path)
    assert "ERROR" in context


# ---------------------------------------------------------------------------
# test_compute_fitness_with_tests_passing
# ---------------------------------------------------------------------------


def test_compute_fitness_with_tests_passing(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mock test pass should give a reasonable fitness score (> 0.5)."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )

    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    module_path = src_dir / "providers.py"

    fitness = loop._compute_fitness(module_path, test_passed=True)

    # test_score=1.0 * 0.5 = 0.5 minimum, plus elegance and size
    assert fitness >= 0.5
    assert fitness <= 1.0


# ---------------------------------------------------------------------------
# test_compute_fitness_with_tests_failing
# ---------------------------------------------------------------------------


def test_compute_fitness_with_tests_failing(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mock test fail should give a low fitness score."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )

    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    module_path = src_dir / "providers.py"

    fitness = loop._compute_fitness(module_path, test_passed=False)

    # test_score=0.0 * 0.5 = 0.0 for that component
    assert fitness < 0.5


def test_compute_fitness_oversized_file(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """A very large file should receive a size penalty."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )

    # Create an oversized file
    big_file = src_dir / "giant.py"
    big_file.write_text("# line\n" * (_MAX_SANE_LINES * 2), encoding="utf-8")

    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    fitness = loop._compute_fitness(big_file, test_passed=True)

    # Size score should be 0.0 at 2x the limit, dragging down overall fitness
    assert fitness < 0.8


# ---------------------------------------------------------------------------
# test_iteration_result_model
# ---------------------------------------------------------------------------


def test_iteration_result_model():
    """Verify IterationResult fields have correct types and defaults."""
    result = IterationResult(iteration=1, module="test_module.py")

    assert result.iteration == 1
    assert result.module == "test_module.py"
    assert result.proposal_id == ""
    assert result.description == ""
    assert result.fitness == 0.0
    assert result.accepted is False
    assert result.test_passed is False
    assert result.error == ""
    assert result.duration_sec == 0.0


def test_iteration_result_with_values():
    """Verify IterationResult accepts custom values."""
    result = IterationResult(
        iteration=5,
        module="orchestrator.py",
        proposal_id="abc123",
        description="Improved routing logic",
        fitness=0.85,
        accepted=True,
        test_passed=True,
        duration_sec=12.5,
    )
    assert result.fitness == 0.85
    assert result.accepted is True
    assert result.test_passed is True


# ---------------------------------------------------------------------------
# test_report_format
# ---------------------------------------------------------------------------


def test_report_format_no_iterations():
    """Report with no iterations should state that clearly."""
    loop = AutoResearchLoop(LoopConfig(dry_run=True))
    report = loop.report()
    assert "no iterations run" in report


def test_report_format_with_results():
    """Verify report() produces readable output after iterations."""
    loop = AutoResearchLoop(LoopConfig(dry_run=True))

    # Manually populate results to avoid needing real filesystem/LLM
    loop._results = [
        IterationResult(
            iteration=1,
            module="providers.py",
            fitness=0.75,
            accepted=True,
            test_passed=True,
            duration_sec=1.5,
        ),
        IterationResult(
            iteration=2,
            module="context.py",
            fitness=0.45,
            accepted=False,
            test_passed=True,
            duration_sec=2.0,
        ),
        IterationResult(
            iteration=3,
            module="orchestrator.py",
            fitness=0.0,
            accepted=False,
            test_passed=False,
            error="Unexpected error: test timeout",
            duration_sec=300.0,
        ),
    ]

    report = loop.report()

    assert isinstance(report, str)
    assert "AUTORESEARCH LOOP REPORT" in report
    assert "Iterations:" in report
    assert "Accepted:" in report
    assert "Rejected:" in report
    assert "Avg fitness:" in report
    assert "Per-Module Breakdown" in report
    assert "providers.py" in report
    assert "context.py" in report
    assert "Errors" in report
    assert "test timeout" in report


# ---------------------------------------------------------------------------
# test_run_iteration_dry_run
# ---------------------------------------------------------------------------


async def test_run_iteration_dry_run(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Dry-run iteration should skip tests and produce a valid result."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_ROOT", src_dir.parent
    )

    # Mock the traces to avoid filesystem operations
    mock_traces = MagicMock()
    mock_traces.init = AsyncMock()
    mock_traces.log_entry = AsyncMock()

    loop = AutoResearchLoop(LoopConfig(dry_run=True, max_iterations=1))
    loop._traces = mock_traces

    result = await loop.run_iteration()

    assert isinstance(result, IterationResult)
    assert result.iteration == 1
    assert result.module != ""
    assert result.test_passed is True  # dry_run skips tests -> True
    assert result.fitness > 0.0
    assert result.duration_sec >= 0.0
    assert result.error == ""


# ---------------------------------------------------------------------------
# test_target_modules_filter
# ---------------------------------------------------------------------------


def test_target_modules_filter(
    src_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """When target_modules is set, only those modules are included."""
    monkeypatch.setattr(
        "dharma_swarm.autoresearch_loop.DHARMA_SWARM_SRC", src_dir
    )

    loop = AutoResearchLoop(
        LoopConfig(dry_run=True, target_modules=["providers.py"])
    )
    mutable = loop._resolve_mutable()
    assert len(mutable) == 1
    assert mutable[0].name == "providers.py"
