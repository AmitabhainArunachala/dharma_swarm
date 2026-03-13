"""Tests for the Repo X-Ray product."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.xray import (
    FileInfo,
    FunctionInfo,
    MAX_RISK_FLAGS,
    RiskFlag,
    XRayReport,
    analyze_python_file,
    analyze_js_file,
    analyze_repo,
    analyze_repo_summary,
    build_service_packet,
    discover_files,
    render_markdown,
    render_service_brief,
    run_xray,
    run_xray_packet,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_repo(tmp_path):
    """Create a minimal synthetic Python repo for testing."""
    pkg = tmp_path / "mypackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""My package."""\n')

    (pkg / "core.py").write_text('''\
"""Core module with some functions."""

from typing import Optional


class Engine:
    """Main engine class."""

    def run(self, data: list[int]) -> int:
        """Process data and return result."""
        total = 0
        for item in data:
            if item > 0:
                total += item
            elif item < -100:
                total -= item
        return total

    def validate(self, x: int) -> bool:
        return x > 0


def helper(name: str) -> str:
    return f"Hello, {name}"
''')

    (pkg / "utils.py").write_text('''\
"""Utility functions."""

import os
import json
from mypackage import core


def load_config(path: str) -> dict:
    """Load a JSON config file."""
    with open(path) as f:
        return json.load(f)


def undocumented_func(x):
    return x * 2
''')

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_core.py").write_text('''\
"""Tests for core module."""

from mypackage.core import Engine


def test_engine_run():
    e = Engine()
    assert e.run([1, 2, 3]) == 6


def test_engine_validate():
    e = Engine()
    assert e.validate(1) is True
    assert e.validate(-1) is False
''')

    # Add a README
    (tmp_path / "README.md").write_text("# My Package\nA test package.\n")

    return tmp_path


@pytest.fixture
def empty_repo(tmp_path):
    """An empty directory."""
    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    """A repo with JS files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.js").write_text('''\
import express from 'express';
const app = express();
app.get('/', (req, res) => res.send('Hello'));
app.listen(3000);
''')
    (src / "utils.ts").write_text('''\
export function add(a: number, b: number): number {
    return a + b;
}
''')
    return tmp_path


# ── File Discovery ───────────────────────────────────────────────────


class TestDiscoverFiles:
    def test_finds_python_files(self, synthetic_repo):
        files = discover_files(synthetic_repo)
        py_files = [f for f in files if f.suffix == ".py"]
        assert len(py_files) >= 4  # __init__, core, utils, test_core

    def test_skips_pycache(self, synthetic_repo):
        cache = synthetic_repo / "mypackage" / "__pycache__"
        cache.mkdir()
        (cache / "core.cpython-312.pyc").write_text("fake")
        files = discover_files(synthetic_repo)
        assert not any("__pycache__" in str(f) for f in files)

    def test_empty_dir(self, empty_repo):
        files = discover_files(empty_repo)
        assert files == []

    def test_finds_js_files(self, js_repo):
        files = discover_files(js_repo)
        assert any(f.suffix == ".js" for f in files)
        assert any(f.suffix == ".ts" for f in files)


# ── Python Analysis ──────────────────────────────────────────────────


class TestAnalyzePythonFile:
    def test_basic_analysis(self, synthetic_repo):
        core_path = synthetic_repo / "mypackage" / "core.py"
        info, funcs = analyze_python_file(core_path, synthetic_repo)
        assert info is not None
        assert info.language == "python"
        assert info.num_classes == 1
        assert info.num_functions >= 3  # run, validate, helper
        assert info.has_docstring is True
        assert info.docstring_ratio > 0
        assert info.lines > 0

    def test_extracts_functions(self, synthetic_repo):
        core_path = synthetic_repo / "mypackage" / "core.py"
        _, funcs = analyze_python_file(core_path, synthetic_repo)
        assert len(funcs) >= 3
        names = {f.name for f in funcs}
        assert "run" in names
        assert "helper" in names

    def test_detects_test_file(self, synthetic_repo):
        test_path = synthetic_repo / "tests" / "test_core.py"
        info, _ = analyze_python_file(test_path, synthetic_repo)
        assert info.is_test is True

    def test_handles_syntax_error(self, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(\n")
        info, funcs = analyze_python_file(bad, tmp_path)
        assert info is not None
        assert info.lines > 0
        assert funcs == []


# ── JS Analysis ──────────────────────────────────────────────────────


class TestAnalyzeJsFile:
    def test_js_file(self, js_repo):
        info = analyze_js_file(js_repo / "src" / "index.js", js_repo)
        assert info is not None
        assert info.language == "javascript"
        assert info.lines > 0
        assert "express" in info.imports

    def test_ts_file(self, js_repo):
        info = analyze_js_file(js_repo / "src" / "utils.ts", js_repo)
        assert info is not None
        assert info.language == "typescript"


# ── Full Repo Analysis ───────────────────────────────────────────────


class TestAnalyzeRepo:
    def test_synthetic_repo(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        assert report.repo_name == synthetic_repo.name
        assert report.total_files > 0
        assert report.total_lines > 0
        assert "python" in report.language_breakdown
        assert report.test_file_count >= 1
        assert report.test_ratio > 0
        assert len(report.recommendations) > 0

    def test_empty_repo(self, empty_repo):
        report = analyze_repo(empty_repo)
        assert len(report.risk_flags) > 0
        assert report.risk_flags[0].category == "empty"

    def test_quality_signals(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        assert 0.0 <= report.avg_docstring_ratio <= 1.0
        assert 0.0 <= report.avg_naming_score <= 1.0
        assert report.avg_complexity >= 0

    def test_detects_external_deps(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        # os and json are stdlib, should not appear as external
        # (depends on Python version having stdlib_module_names)
        assert isinstance(report.external_deps, list)

    def test_complexity_hotspots(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        assert isinstance(report.complexity_hotspots, list)

    def test_js_repo(self, js_repo):
        report = analyze_repo(js_repo)
        assert report.total_files > 0
        assert any(
            lang in report.language_breakdown
            for lang in ("javascript", "typescript")
        )


# ── Markdown Rendering ───────────────────────────────────────────────


class TestRenderMarkdown:
    def test_renders_all_sections(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        md = render_markdown(report)
        assert "# Repo X-Ray:" in md
        assert "## Overview" in md
        assert "## Architecture" in md
        assert "## Code Quality Signals" in md
        assert "Overall Grade:" in md
        assert "## Recommended Next Steps" in md

    def test_grade_present(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        md = render_markdown(report)
        # Grade should be one of A-F
        assert any(f"Overall Grade: {g}" in md for g in "ABCDF")


# ── run_xray ─────────────────────────────────────────────────────────


class TestRunXray:
    def test_generates_markdown(self, synthetic_repo):
        out = run_xray(synthetic_repo)
        assert out.exists()
        assert out.suffix == ".md"
        content = out.read_text()
        assert "Repo X-Ray" in content

    def test_generates_json(self, synthetic_repo):
        out = run_xray(synthetic_repo, as_json=True)
        assert out.exists()
        assert out.suffix == ".json"
        import json
        data = json.loads(out.read_text())
        assert "repo_name" in data
        assert "total_files" in data

    def test_custom_output(self, synthetic_repo, tmp_path):
        custom = tmp_path / "my_report.md"
        out = run_xray(synthetic_repo, output_path=custom)
        assert out == custom
        assert custom.exists()

    def test_invalid_path(self):
        with pytest.raises(ValueError, match="Not a directory"):
            run_xray("/nonexistent/path/xyz")

    def test_on_dharma_swarm(self):
        """Smoke test: X-Ray the dharma_swarm repo itself."""
        dharma = Path(__file__).resolve().parent.parent
        report = analyze_repo(dharma)
        assert report.total_files > 50
        assert report.total_lines > 10000
        assert "python" in report.language_breakdown
        assert report.test_file_count > 20

    def test_exclude_patterns(self, synthetic_repo):
        out = run_xray(synthetic_repo, exclude_patterns={"tests"})
        content = out.read_text()
        assert "Repo X-Ray" in content


class TestServicePacket:
    def test_build_service_packet(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        packet = build_service_packet(report, buyer="Technical founder")

        assert packet.repo_name == synthetic_repo.name
        assert packet.buyer == "Technical founder"
        assert packet.sprint_name == "Repo X-Ray Sprint"
        assert packet.price_floor_usd > 0
        assert packet.price_target_usd >= packet.price_floor_usd
        assert packet.swarm_plan

    def test_render_service_brief(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        packet = build_service_packet(report)
        md = render_service_brief(packet)

        assert "# Repo X-Ray Sprint Brief:" in md
        assert "## Swarm Plan" in md
        assert "codex-primus" in md
        assert "## Fixed-Scope Offer" in md

    def test_run_xray_packet(self, synthetic_repo, tmp_path):
        out_dir = tmp_path / "packet"
        outputs = run_xray_packet(synthetic_repo, output_dir=out_dir, buyer="CTO")

        assert outputs["output_dir"] == out_dir
        assert outputs["report_markdown"].exists()
        assert outputs["report_json"].exists()
        assert outputs["service_brief"].exists()
        assert outputs["service_packet"].exists()
        assert outputs["mission_brief"].exists()
        assert "Swarm Mission" in outputs["mission_brief"].read_text()


# ── Exclude Patterns ─────────────────────────────────────────────────


class TestExcludePatterns:
    def test_discover_respects_exclude(self, synthetic_repo):
        all_files = discover_files(synthetic_repo)
        excluded = discover_files(synthetic_repo, exclude_patterns={"tests"})
        assert len(excluded) < len(all_files)
        assert not any("tests" in str(f) for f in excluded)

    def test_analyze_repo_with_exclude(self, synthetic_repo):
        full = analyze_repo(synthetic_repo)
        partial = analyze_repo(synthetic_repo, exclude_patterns={"tests"})
        assert partial.total_files <= full.total_files
        assert partial.test_file_count <= full.test_file_count


# ── Capped Risk Flags ────────────────────────────────────────────────


class TestCappedRisks:
    def test_risk_flags_capped(self, synthetic_repo):
        report = analyze_repo(synthetic_repo)
        assert len(report.risk_flags) <= MAX_RISK_FLAGS


# ── Summary Function ─────────────────────────────────────────────────


class TestAnalyzeRepoSummary:
    def test_returns_expected_keys(self, synthetic_repo):
        summary = analyze_repo_summary(synthetic_repo)
        assert "grade" in summary
        assert "score" in summary
        assert "dimensions" in summary
        assert "top_risks" in summary
        assert "top_actions" in summary
        assert summary["grade"] in ("A", "B", "C", "D", "F")
        assert 0.0 <= summary["score"] <= 1.0

    def test_dimensions_present(self, synthetic_repo):
        summary = analyze_repo_summary(synthetic_repo)
        dims = summary["dimensions"]
        assert "has_tests" in dims
        assert "documented" in dims

    def test_invalid_path_returns_error(self):
        summary = analyze_repo_summary("/nonexistent/path")
        assert summary["grade"] == "F"
        assert "error" in summary

    def test_with_exclude(self, synthetic_repo):
        summary = analyze_repo_summary(synthetic_repo, exclude_patterns={"tests"})
        assert summary["grade"] in ("A", "B", "C", "D", "F")
