"""Tests for ginko_audit.py — continuous audit system for Dharmic Quant."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.ginko_audit import (
    AuditReport,
    CheckResult,
    Enhancement,
    FixPatch,
    GinkoAuditor,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_creation(self):
        r = CheckResult(
            check_id="TEST-01", category="test", claim="X works",
            status="PASS", severity="LOW", finding="all good",
        )
        assert r.check_id == "TEST-01"
        assert r.status == "PASS"
        assert r.fix_available is False
        assert r.fix_id is None

    def test_emoji_pass(self):
        r = CheckResult("id", "cat", "claim", "PASS", "LOW", "f")
        assert r.emoji == "+"

    def test_emoji_fail(self):
        r = CheckResult("id", "cat", "claim", "FAIL", "HIGH", "f")
        assert r.emoji == "X"

    def test_emoji_warn(self):
        r = CheckResult("id", "cat", "claim", "WARN", "MEDIUM", "f")
        assert r.emoji == "!"

    def test_emoji_skip(self):
        r = CheckResult("id", "cat", "claim", "SKIP", "LOW", "f")
        assert r.emoji == "o"

    def test_emoji_unknown(self):
        r = CheckResult("id", "cat", "claim", "OTHER", "LOW", "f")
        assert r.emoji == "?"

    def test_fix_metadata(self):
        r = CheckResult("id", "cat", "claim", "FAIL", "HIGH", "f",
                         fix_available=True, fix_id="FIX-01")
        assert r.fix_available is True
        assert r.fix_id == "FIX-01"


class TestFixPatch:
    def test_creation(self):
        f = FixPatch(
            fix_id="FIX-01", description="patch x",
            target_file="/path", action="shell", content="echo hello",
        )
        assert f.fix_id == "FIX-01"
        assert f.safe is True
        assert f.applied is False

    def test_unsafe_patch(self):
        f = FixPatch("FIX-02", "desc", "/path", "verify_or_insert", "code", safe=False)
        assert f.safe is False


class TestEnhancement:
    def test_creation(self):
        e = Enhancement(
            id="ENH-01", title="API keys",
            description="Pre-flight check", impact="10x",
            effort="trivial", category="infra",
        )
        assert e.id == "ENH-01"
        assert e.dependencies == []
        assert e.agent_spec == ""

    def test_with_dependencies(self):
        e = Enhancement("ENH-05", "Backtest", "desc", "100x", "medium", "alpha",
                         dependencies=["ginko_paper_trade.py"])
        assert len(e.dependencies) == 1


class TestAuditReport:
    def _make_report(self):
        results = [
            CheckResult("R-1", "test", "c1", "PASS", "LOW", "ok"),
            CheckResult("R-2", "test", "c2", "FAIL", "HIGH", "bad"),
            CheckResult("R-3", "test", "c3", "WARN", "MEDIUM", "hmm"),
            CheckResult("R-4", "test", "c4", "SKIP", "LOW", "n/a"),
        ]
        return AuditReport(timestamp="2026-03-22T00:00:00Z", mode="test", results=results)

    def test_counts(self):
        report = self._make_report()
        assert report.passed == 1
        assert report.failed == 1
        assert report.warned == 1
        assert report.skipped == 1

    def test_empty_report(self):
        report = AuditReport(timestamp="now", mode="test")
        assert report.passed == 0
        assert report.failed == 0


# ---------------------------------------------------------------------------
# GinkoAuditor — individual checks (mocked filesystem)
# ---------------------------------------------------------------------------


class TestCheckFileManifest:
    def test_missing_files_report_fail(self, monkeypatch, tmp_path):
        """When expected files don't exist, all manifest checks should FAIL."""
        src = tmp_path / "dharma_swarm"
        tests = tmp_path / "tests"
        src.mkdir()
        tests.mkdir()
        monkeypatch.setattr("dharma_swarm.ginko_audit.DHARMA_SWARM_ROOT", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", src)
        monkeypatch.setattr("dharma_swarm.ginko_audit.TEST_DIR", tests)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        # Rebuild file lists relative to tmp_path
        monkeypatch.setattr("dharma_swarm.ginko_audit.EXPECTED_NEW_FILES", [
            src / "ginko_agents.py",
            tests / "test_ginko_integration.py",
        ])
        monkeypatch.setattr("dharma_swarm.ginko_audit.EXPECTED_MODIFIED_FILES", [
            src / "ginko_signals.py",
        ])
        (tmp_path / "audit").mkdir(parents=True)

        auditor = GinkoAuditor()
        results = auditor.check_file_manifest()
        assert len(results) > 0
        # All should fail since files don't exist
        for r in results:
            assert r.status == "FAIL", f"{r.check_id} was {r.status}"

    def test_existing_files_pass(self, monkeypatch, tmp_path):
        """When files exist with >100 bytes, manifest checks PASS."""
        monkeypatch.setattr("dharma_swarm.ginko_audit.DHARMA_SWARM_ROOT", tmp_path)
        src = tmp_path / "dharma_swarm"
        tests = tmp_path / "tests"
        docs = tmp_path / "docs"
        src.mkdir()
        tests.mkdir()
        docs.mkdir()
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", src)
        monkeypatch.setattr("dharma_swarm.ginko_audit.TEST_DIR", tests)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        # Build the expected new file list with tmp_path base
        from dharma_swarm.ginko_audit import EXPECTED_NEW_FILES, EXPECTED_MODIFIED_FILES
        monkeypatch.setattr("dharma_swarm.ginko_audit.EXPECTED_NEW_FILES", [
            src / "ginko_agents.py",
        ])
        monkeypatch.setattr("dharma_swarm.ginko_audit.EXPECTED_MODIFIED_FILES", [
            src / "ginko_signals.py",
        ])

        # Create files with content > 100 bytes
        (src / "ginko_agents.py").write_text("x" * 200)
        (src / "ginko_signals.py").write_text("y" * 200)

        auditor = GinkoAuditor()
        results = auditor.check_file_manifest()
        assert all(r.status == "PASS" for r in results)


class TestCheckDependencies:
    def test_importable_deps_pass(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir(parents=True)

        auditor = GinkoAuditor()
        results = auditor.check_dependencies()
        # httpx and pydantic should be importable in our test env
        httpx_result = [r for r in results if "httpx" in r.check_id]
        assert len(httpx_result) == 1
        assert httpx_result[0].status == "PASS"


class TestCheckFacts:
    def test_fc02_agent_registry_exists(self, monkeypatch, tmp_path):
        """FC-02 checks agent_registry.py follows identity.json pattern."""
        monkeypatch.setattr("dharma_swarm.ginko_audit.DHARMA_SWARM_ROOT", tmp_path)
        src = tmp_path / "dharma_swarm"
        src.mkdir()
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", src)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        # Create agent_registry.py with expected patterns
        (src / "agent_registry.py").write_text(
            "from pathlib import Path\n"
            "DHARMA_HOME = '.dharma'\n"
            "identity_path = 'identity.json'\n"
        )

        auditor = GinkoAuditor()
        result = auditor._fc02_agent_registry_design()
        assert result.status == "PASS"

    def test_fc02_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        auditor = GinkoAuditor()
        result = auditor._fc02_agent_registry_design()
        assert result.status == "WARN"

    def test_fc04_deps_in_pyproject(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.DHARMA_SWARM_ROOT", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", tmp_path / "src")
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        (tmp_path / "pyproject.toml").write_text(
            "[project]\ndependencies = ['httpx', 'fastapi', 'uvicorn', 'numpy']\n"
        )
        auditor = GinkoAuditor()
        result = auditor._fc04_dependencies()
        assert result.status == "PASS"

    def test_fc04_missing_deps(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.DHARMA_SWARM_ROOT", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
        auditor = GinkoAuditor()
        result = auditor._fc04_dependencies()
        assert result.status == "FAIL"

    def test_fc11_test_count(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.TEST_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        # Create some test files
        for i in range(12):
            (tmp_path / f"test_ginko_{i}.py").write_text(f"# test {i}")

        auditor = GinkoAuditor()
        result = auditor._fc11_test_count()
        assert result.status == "PASS"

    def test_fc11_too_few_tests(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.TEST_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        (tmp_path / "test_ginko_one.py").write_text("# test")

        auditor = GinkoAuditor()
        result = auditor._fc11_test_count()
        assert result.status == "FAIL"


class TestDetectGaps:
    def test_returns_gap_checks(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", tmp_path / "src")
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        auditor = GinkoAuditor()
        gaps = auditor.detect_gaps()
        assert len(gaps) >= 5
        assert all(r.category == "gap" for r in gaps)

    def test_backtesting_gap_when_missing(self, monkeypatch, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", src)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        auditor = GinkoAuditor()
        gaps = auditor.detect_gaps()
        bt_gap = [g for g in gaps if g.check_id == "GAP-03"]
        assert len(bt_gap) == 1
        assert bt_gap[0].status == "FAIL"

    def test_backtesting_gap_when_exists(self, monkeypatch, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "ginko_backtest.py").write_text("# backtest engine")
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", src)
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        auditor = GinkoAuditor()
        gaps = auditor.detect_gaps()
        bt_gap = [g for g in gaps if g.check_id == "GAP-03"]
        assert bt_gap[0].status == "PASS"


class TestScoreEnhancements:
    def test_returns_ranked_list(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        auditor = GinkoAuditor()
        enhancements = auditor.score_enhancements()
        assert len(enhancements) >= 10
        # Should be sorted: first item has highest impact*effort score
        assert enhancements[0].impact in ("1000x", "100x")


# ---------------------------------------------------------------------------
# Fix generation and application
# ---------------------------------------------------------------------------


class TestFixes:
    def test_generate_fixes_from_results(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.DHARMA_SWARM_ROOT", tmp_path)
        monkeypatch.setattr("dharma_swarm.ginko_audit.SRC_DIR", tmp_path / "src")
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        results = [
            CheckResult("FC-01", "fact", "position limit", "FAIL", "HIGH", "no limit",
                         fix_available=True, fix_id="FIX-01"),
            CheckResult("FC-04", "fact", "deps", "FAIL", "HIGH", "missing",
                         fix_available=True, fix_id="FIX-04"),
            CheckResult("FC-05", "fact", "tabs", "PASS", "MEDIUM", "ok"),
        ]

        auditor = GinkoAuditor()
        fixes = auditor.generate_fixes(results)
        assert len(fixes) == 2
        assert fixes[0].fix_id == "FIX-01"

    def test_apply_fixes_dry_run(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        fixes = [
            FixPatch("FIX-01", "patch", "/path", "verify_or_insert", "code", safe=False),
            FixPatch("FIX-DEP-numpy", "install numpy", "N/A", "shell", "pip install numpy", safe=True),
        ]

        auditor = GinkoAuditor()
        actions = auditor.apply_fixes(fixes, dry_run=True)
        assert len(actions) == 2
        assert actions[0]["status"] == "SKIPPED"  # unsafe in dry-run
        assert actions[1]["status"] == "DRY_RUN"  # shell in dry-run


# ---------------------------------------------------------------------------
# Report building and formatting
# ---------------------------------------------------------------------------


class TestReportFormatting:
    def test_format_terminal_report(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", tmp_path / "audit")
        (tmp_path / "audit").mkdir()

        report = AuditReport(
            timestamp="2026-03-22T00:00:00Z",
            mode="test",
            results=[
                CheckResult("R-1", "test", "claim1", "PASS", "LOW", "ok"),
                CheckResult("R-2", "fact", "claim2", "FAIL", "HIGH", "bad"),
            ],
            enhancements=[
                Enhancement("ENH-01", "API keys", "Pre-flight", "10x", "trivial", "infra"),
            ],
        )

        auditor = GinkoAuditor()
        text = auditor.format_terminal_report(report)
        assert "DHARMIC QUANT" in text
        assert "1 PASS" in text
        assert "1 FAIL" in text
        assert "API keys" in text

    def test_save_report(self, monkeypatch, tmp_path):
        audit_dir = tmp_path / "audit"
        monkeypatch.setattr("dharma_swarm.ginko_audit.AUDIT_HOME", audit_dir)
        audit_dir.mkdir(parents=True)

        report = AuditReport(
            timestamp="2026-03-22T00:00:00Z",
            mode="test",
            results=[CheckResult("R-1", "test", "c", "PASS", "LOW", "f")],
        )

        auditor = GinkoAuditor()
        path = auditor.save_report(report)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["summary"]["passed"] == 1

        # Latest pointer should also exist
        latest = audit_dir / "latest.json"
        assert latest.exists()
