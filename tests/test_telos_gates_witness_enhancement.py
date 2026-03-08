"""Tests for dharma_swarm.telos_gates_witness_enhancement -- WitnessGateEnhancement."""

import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.models import GateResult
from dharma_swarm.telos_gates_witness_enhancement import WitnessGateEnhancement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_marks_file(tmp_dir: Path, entries: list[dict]) -> Path:
    """Write JSONL stigmergy marks in a temp directory and return marks.jsonl path."""
    marks_file = tmp_dir / "marks.jsonl"
    with open(marks_file, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return marks_file


def _write_flicker_log(entries: list[dict]) -> str:
    """Write a temp flicker log and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for entry in entries:
        f.write(json.dumps(entry) + "\n")
    f.flush()
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Non-reading operations bypass gate
# ---------------------------------------------------------------------------


def test_non_reading_operation_passes():
    gate = WitnessGateEnhancement()
    result, msg = gate.evaluate(
        action="Write /some/file.py",
        content="code here",
        tool_name="Write",
    )
    assert result == GateResult.PASS
    assert "Not a reading operation" in msg


def test_non_tool_name_passes():
    gate = WitnessGateEnhancement()
    result, msg = gate.evaluate(
        action="Bash ls -la",
        tool_name="Bash",
    )
    assert result == GateResult.PASS


def test_read_tool_variants():
    """All recognized read tool names should trigger evaluation."""
    gate = WitnessGateEnhancement()
    for tool_name in ["Read", "read", "read_file"]:
        result, msg = gate.evaluate(
            action="Read /some/file.md",
            tool_name=tool_name,
        )
        assert "Not a reading operation" not in msg


# ---------------------------------------------------------------------------
# File path extraction
# ---------------------------------------------------------------------------


def test_extract_file_path_md():
    gate = WitnessGateEnhancement()
    path = gate._extract_file_path("Read /Users/dhyana/test.md")
    assert path == "/Users/dhyana/test.md"


def test_extract_file_path_py():
    gate = WitnessGateEnhancement()
    path = gate._extract_file_path("Read /home/user/code.py some other text")
    assert path == "/home/user/code.py"


def test_extract_file_path_json():
    gate = WitnessGateEnhancement()
    path = gate._extract_file_path("Opening ~/config/settings.json for review")
    assert path == "~/config/settings.json"


def test_extract_file_path_no_match():
    gate = WitnessGateEnhancement()
    path = gate._extract_file_path("just some random text without paths")
    assert path is None


def test_no_file_path_passes():
    gate = WitnessGateEnhancement()
    result, msg = gate.evaluate(
        action="Read some text with no file path",
        tool_name="Read",
    )
    assert result == GateResult.PASS
    assert "No file path detected" in msg


# ---------------------------------------------------------------------------
# Stigmergic mark checks
# ---------------------------------------------------------------------------


def test_no_stigmergy_file_returns_false():
    gate = WitnessGateEnhancement(stigmergy_base=Path("/nonexistent/path"))
    assert gate._check_stigmergic_mark("/some/file.md") is False


def test_stigmergy_mark_found(tmp_path):
    _write_marks_file(tmp_path, [
        {"file_path": "/path/to/THE_CATCH.md", "observation": "important"},
    ])
    gate = WitnessGateEnhancement(stigmergy_base=tmp_path)
    assert gate._check_stigmergic_mark("/path/to/THE_CATCH.md") is True


def test_stigmergy_mark_not_found(tmp_path):
    _write_marks_file(tmp_path, [
        {"file_path": "/path/to/other.md", "observation": "something"},
    ])
    gate = WitnessGateEnhancement(stigmergy_base=tmp_path)
    assert gate._check_stigmergic_mark("/path/to/unknown.md") is False


# ---------------------------------------------------------------------------
# Hyperlink checks
# ---------------------------------------------------------------------------


def test_hyperlinks_no_content():
    gate = WitnessGateEnhancement()
    assert gate._check_hyperlinks_followed("/file.md", "") is True


def test_hyperlinks_no_links_in_content():
    gate = WitnessGateEnhancement()
    assert gate._check_hyperlinks_followed("/file.md", "plain text no links") is True


def test_hyperlinks_with_wikilinks_no_stigmergy():
    gate = WitnessGateEnhancement(stigmergy_base=Path("/nonexistent"))
    content = "See [[Related Note]] and [[Another Note]] for details."
    assert gate._check_hyperlinks_followed("/file.md", content) is False


def test_hyperlinks_with_wikilinks_stigmergy_found(tmp_path):
    _write_marks_file(tmp_path, [
        {"file_path": "Related Note", "linked": True},
    ])
    gate = WitnessGateEnhancement(stigmergy_base=tmp_path)
    content = "See [[Related Note]] for details."
    assert gate._check_hyperlinks_followed("/file.md", content) is True


def test_hyperlinks_with_markdown_links_not_found(tmp_path):
    _write_marks_file(tmp_path, [])
    gate = WitnessGateEnhancement(stigmergy_base=tmp_path)
    content = "Read [this doc](reference.md) for context."
    assert gate._check_hyperlinks_followed("/file.md", content) is False


# ---------------------------------------------------------------------------
# Flicker log checks
# ---------------------------------------------------------------------------


def test_flicker_log_no_file():
    gate = WitnessGateEnhancement(flicker_log_path="/nonexistent/path.jsonl")
    assert gate._check_flicker_log("/some/file.md") is False


def test_flicker_log_file_found():
    path = _write_flicker_log([
        {"trigger_file": "/path/to/important.md", "timestamp": "2026-03-07"},
    ])
    gate = WitnessGateEnhancement(flicker_log_path=path)
    assert gate._check_flicker_log("/path/to/important.md") is True


def test_flicker_log_file_not_found():
    path = _write_flicker_log([
        {"trigger_file": "/path/to/other.md", "timestamp": "2026-03-07"},
    ])
    gate = WitnessGateEnhancement(flicker_log_path=path)
    assert gate._check_flicker_log("/path/to/important.md") is False


def test_flicker_log_corrupt_json():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    f.write("not valid json\n")
    f.flush()
    f.close()
    gate = WitnessGateEnhancement(flicker_log_path=f.name)
    assert gate._check_flicker_log("/some/file.md") is False


# ---------------------------------------------------------------------------
# _describe_awareness
# ---------------------------------------------------------------------------


def test_describe_awareness_all_true():
    gate = WitnessGateEnhancement()
    desc = gate._describe_awareness(True, True, True)
    assert "mark left" in desc
    assert "links followed" in desc
    assert "flicker detected" in desc


def test_describe_awareness_none():
    gate = WitnessGateEnhancement()
    desc = gate._describe_awareness(False, False, False)
    assert desc == "none"


def test_describe_awareness_partial():
    gate = WitnessGateEnhancement()
    desc = gate._describe_awareness(True, False, False)
    assert desc == "mark left"


# ---------------------------------------------------------------------------
# Full evaluate integration
# ---------------------------------------------------------------------------


def test_evaluate_reading_without_awareness():
    """Reading with no marks, no links followed, no flicker -> WARN."""
    gate = WitnessGateEnhancement(stigmergy_base=Path("/nonexistent"))
    result, msg = gate.evaluate(
        action="Read /Users/dhyana/test.md",
        content="See [[Some Link]] for details.",
        tool_name="Read",
    )
    assert result == GateResult.WARN
    assert "without awareness" in msg


def test_evaluate_reading_with_mark(tmp_path):
    """Reading with stigmergic mark -> PASS."""
    _write_marks_file(tmp_path, [
        {"file_path": "/Users/dhyana/test.md", "observation": "marked"},
    ])
    gate = WitnessGateEnhancement(stigmergy_base=tmp_path)
    result, msg = gate.evaluate(
        action="Read /Users/dhyana/test.md",
        content="no links here",
        tool_name="Read",
    )
    assert result == GateResult.PASS


def test_evaluate_reading_with_full_awareness(tmp_path):
    """Reading with mark + links + flicker -> PASS with full awareness."""
    flicker_path = _write_flicker_log([
        {"trigger_file": "/Users/dhyana/test.md"},
    ])
    _write_marks_file(tmp_path, [
        {"file_path": "/Users/dhyana/test.md", "observation": "marked"},
        {"file_path": "Reference Note", "linked": True},
    ])
    gate = WitnessGateEnhancement(
        stigmergy_base=tmp_path,
        flicker_log_path=flicker_path,
    )
    result, msg = gate.evaluate(
        action="Read /Users/dhyana/test.md",
        content="See [[Reference Note]] for more.",
        tool_name="Read",
    )
    assert result == GateResult.PASS
    assert "Full recursive awareness" in msg
