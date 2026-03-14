"""Tests for dharma_swarm.epistemic_telemetry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.epistemic_telemetry import (
    EpistemicIncident,
    EpistemicIssueKind,
    EpistemicIssueSeverity,
    EpistemicTelemetryStore,
    OutputDiagnostics,
    OutputIssue,
    ProviderProbeRecord,
    analyze_output,
    _clamp01,
    _coerce_workspace_roots,
    _extract_path_tokens,
)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestClamp01:
    def test_below_zero_clamps_to_zero(self) -> None:
        assert _clamp01(-5.0) == 0.0

    def test_above_one_clamps_to_one(self) -> None:
        assert _clamp01(99.0) == 1.0

    def test_midpoint_unchanged(self) -> None:
        assert _clamp01(0.5) == 0.5

    def test_zero_boundary(self) -> None:
        assert _clamp01(0.0) == 0.0

    def test_one_boundary(self) -> None:
        assert _clamp01(1.0) == 1.0


class TestCoerceWorkspaceRoots:
    def test_none_returns_empty(self) -> None:
        assert _coerce_workspace_roots(None) == []

    def test_empty_list_returns_empty(self) -> None:
        assert _coerce_workspace_roots([]) == []

    def test_deduplicates_roots(self) -> None:
        roots = _coerce_workspace_roots(["/tmp/foo", "/tmp/foo", "/tmp/bar"])
        assert len(roots) == 2

    def test_expands_home(self) -> None:
        roots = _coerce_workspace_roots(["~"])
        assert len(roots) == 1
        assert not str(roots[0]).startswith("~")


class TestExtractPathTokens:
    def test_extracts_py_filename(self) -> None:
        tokens = _extract_path_tokens("edited dharma_swarm/providers.py to fix import")
        assert any("providers.py" in t for t in tokens)

    def test_extracts_absolute_path(self) -> None:
        tokens = _extract_path_tokens("Updated /tmp/dharma_swarm/config.yaml with new settings")
        assert any("/tmp/dharma_swarm/config.yaml" in t for t in tokens)

    def test_skips_urls(self) -> None:
        tokens = _extract_path_tokens("See https://example.com/docs.md for details")
        assert not any("https://" in t for t in tokens)

    def test_deduplicates_tokens(self) -> None:
        tokens = _extract_path_tokens("providers.py providers.py providers.py")
        count = sum(1 for t in tokens if "providers.py" in t)
        assert count == 1


# ---------------------------------------------------------------------------
# analyze_output
# ---------------------------------------------------------------------------

class TestAnalyzeOutput:
    def test_empty_string_is_critical(self) -> None:
        diag = analyze_output("")
        assert diag.has_blocking_issue
        assert any(i.kind == EpistemicIssueKind.EMPTY_RESPONSE for i in diag.issues)

    def test_whitespace_only_is_critical(self) -> None:
        diag = analyze_output("   \n  ")
        assert diag.has_blocking_issue

    def test_clean_output_no_issues(self) -> None:
        diag = analyze_output("The tests pass and everything looks correct.")
        assert not diag.issues
        assert diag.grounding_score == 1.0

    def test_provider_error_detected(self) -> None:
        diag = analyze_output("Error: provider returned 500 internal server error")
        assert diag.has_blocking_issue
        kinds = [i.kind for i in diag.issues]
        assert EpistemicIssueKind.PROVIDER_ERROR in kinds

    def test_timeout_detected(self) -> None:
        diag = analyze_output("The operation timed out after 30 seconds of waiting")
        kinds = [i.kind for i in diag.issues]
        assert EpistemicIssueKind.TIMEOUT in kinds

    def test_shell_theater_warning_on_many_shell_lines(self) -> None:
        output = "$ echo hello\n$ ls -la\n$ cat file.txt\n$ rm -rf tmp/\n"
        diag = analyze_output(output)
        kinds = [i.kind for i in diag.issues]
        assert EpistemicIssueKind.SHELL_THEATER in kinds

    def test_grounding_score_decreases_with_issues(self) -> None:
        clean = analyze_output("All tests passing successfully.")
        errored = analyze_output("Error: provider returned bad data and failed")
        assert clean.grounding_score > errored.grounding_score

    def test_grounding_score_clamped_between_0_and_1(self) -> None:
        # Many issues could theoretically push score negative
        output = "\n".join([
            "Error: provider returned fatal error",
            "$ echo a\n$ echo b\n$ echo c\n$ echo d\n",
        ])
        diag = analyze_output(output)
        assert 0.0 <= diag.grounding_score <= 1.0

    def test_missing_file_claim_with_workspace_root(self, tmp_path: Path) -> None:
        fake_path = str(tmp_path / "definitely_does_not_exist.py")
        output = f"I created {fake_path} with the implementation"
        diag = analyze_output(output, workspace_roots=[str(tmp_path)])
        kinds = [i.kind for i in diag.issues]
        assert EpistemicIssueKind.MISSING_FILE_CLAIM in kinds

    def test_existing_file_not_flagged(self, tmp_path: Path) -> None:
        real_file = tmp_path / "real_module.py"
        real_file.write_text("# real code\n")
        output = f"I created {real_file} with the implementation"
        diag = analyze_output(output, workspace_roots=[str(tmp_path)])
        kinds = [i.kind for i in diag.issues]
        assert EpistemicIssueKind.MISSING_FILE_CLAIM not in kinds

    def test_failure_class_set_on_error(self) -> None:
        diag = analyze_output("Error: something went badly wrong here")
        assert diag.failure_class != ""

    def test_summary_reflects_issues(self) -> None:
        diag = analyze_output("")
        assert "empty" in diag.summary.lower() or "response" in diag.summary.lower()


# ---------------------------------------------------------------------------
# OutputDiagnostics model
# ---------------------------------------------------------------------------

class TestOutputDiagnostics:
    def test_issue_count_property(self) -> None:
        issues = [
            OutputIssue(kind=EpistemicIssueKind.EMPTY_RESPONSE, severity=EpistemicIssueSeverity.CRITICAL, summary="empty"),
            OutputIssue(kind=EpistemicIssueKind.TIMEOUT, severity=EpistemicIssueSeverity.WARNING, summary="timeout"),
        ]
        diag = OutputDiagnostics(issues=issues)
        assert diag.issue_count == 2

    def test_has_blocking_issue_true_for_error(self) -> None:
        issues = [OutputIssue(kind=EpistemicIssueKind.PROVIDER_ERROR, severity=EpistemicIssueSeverity.ERROR, summary="err")]
        diag = OutputDiagnostics(issues=issues)
        assert diag.has_blocking_issue

    def test_has_blocking_issue_false_for_warning_only(self) -> None:
        issues = [OutputIssue(kind=EpistemicIssueKind.SHELL_THEATER, severity=EpistemicIssueSeverity.WARNING, summary="warn")]
        diag = OutputDiagnostics(issues=issues)
        assert not diag.has_blocking_issue


# ---------------------------------------------------------------------------
# EpistemicTelemetryStore
# ---------------------------------------------------------------------------

class TestEpistemicTelemetryStore:
    def _store(self, tmp_path: Path) -> EpistemicTelemetryStore:
        return EpistemicTelemetryStore(state_dir=tmp_path)

    def test_append_incident_creates_file(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        incident = EpistemicIncident(
            component="test_component",
            kind=EpistemicIssueKind.EMPTY_RESPONSE,
            severity=EpistemicIssueSeverity.CRITICAL,
            summary="Test empty response",
        )
        incident_id = store.append_incident(incident)
        assert store.incidents_path.exists()
        assert isinstance(incident_id, str)

    def test_append_multiple_incidents(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        for i in range(3):
            store.append_incident(EpistemicIncident(
                component=f"comp{i}",
                kind=EpistemicIssueKind.TASK_FAILURE,
                severity=EpistemicIssueSeverity.WARNING,
                summary=f"Task {i} failed",
            ))
        lines = store.incidents_path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_record_output_diagnostics_writes_per_issue(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        diag = analyze_output("")  # triggers EMPTY_RESPONSE issue
        incident_ids = store.record_output_diagnostics(
            diag,
            component="test",
            output_text="",
            agent_name="coder",
            provider="openai",
            model="gpt-4o",
        )
        assert len(incident_ids) == len(diag.issues)
        assert len(incident_ids) > 0

    def test_record_provider_probe_snapshot(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        payload = {
            "openrouter": {
                "status": "ok",
                "model": "llama-3.3-70b",
                "configured_model": "llama-3.3-70b",
                "strongest_verified": "llama-3.3-70b",
                "deployment_mode": "cloud",
                "configured_base_url": "https://openrouter.ai/api",
                "error": "",
            }
        }
        probe_ids = store.record_provider_probe_snapshot(payload)
        assert len(probe_ids) == 1
        assert store.provider_probes_path.exists()

    def test_read_provider_probes_returns_records(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        payload = {
            "anthropic": {"status": "ok", "model": "claude-sonnet-4-6", "error": ""},
            "openai": {"status": "error", "model": "gpt-4o", "error": "api key missing"},
        }
        store.record_provider_probe_snapshot(payload)
        records = store.read_provider_probes()
        assert len(records) == 2
        assert all(isinstance(r, ProviderProbeRecord) for r in records)

    def test_read_provider_probes_filter_by_provider(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        payload = {
            "anthropic": {"status": "ok", "model": "claude-sonnet-4-6", "error": ""},
            "openai": {"status": "ok", "model": "gpt-4o", "error": ""},
        }
        store.record_provider_probe_snapshot(payload)
        anthropic_records = store.read_provider_probes(provider="anthropic")
        assert all(r.provider == "anthropic" for r in anthropic_records)

    def test_read_provider_probes_limit(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        for i in range(5):
            store.record_provider_probe_snapshot({f"provider{i}": {"status": "ok", "model": f"model{i}", "error": ""}})
        records = store.read_provider_probes(limit=3)
        assert len(records) == 3

    def test_read_provider_probes_empty_file(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        records = store.read_provider_probes()
        assert records == []

    def test_incidents_include_metadata(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        diag = analyze_output("Error: provider returned 500 server error")
        store.record_output_diagnostics(
            diag,
            component="router",
            output_text="Error: provider returned 500 server error",
            task_id="t123",
            metadata={"extra_key": "extra_value"},
        )
        raw = store.incidents_path.read_text().strip().splitlines()
        assert len(raw) > 0
        row = json.loads(raw[0])
        assert "grounding_score" in row.get("metadata", {})
