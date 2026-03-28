"""Tests for constitutional size check enforcement."""

import pytest
from pathlib import Path
from dharma_swarm.constitutional_size_check import (
    check_constitutional_size,
    count_lines_of_code,
    enforce_constitutional_size,
)


def test_count_lines_of_code_nonexistent_file():
    """Non-existent files return 0."""
    result = count_lines_of_code(Path("/nonexistent/file.py"))
    assert result == 0


def test_count_lines_of_code_ignores_comments(tmp_path):
    """Comment-only lines are not counted."""
    file = tmp_path / "test.py"
    file.write_text("# This is a comment\n# Another comment\nactual_code = 1\n")
    
    result = count_lines_of_code(file)
    assert result == 1  # Only the actual_code line


def test_count_lines_of_code_ignores_blank_lines(tmp_path):
    """Blank lines are not counted."""
    file = tmp_path / "test.py"
    file.write_text("code = 1\n\n\nmore_code = 2\n")
    
    result = count_lines_of_code(file)
    assert result == 2  # Only the code lines


def test_check_constitutional_size_returns_tuple():
    """check_constitutional_size returns (bool, str)."""
    passed, message = check_constitutional_size()
    
    assert isinstance(passed, bool)
    assert isinstance(message, str)
    assert len(message) > 0


def test_check_constitutional_size_layer0_smaller_than_layer3():
    """Layer 0 should be smaller than Layer 3 in real repo."""
    passed, message = check_constitutional_size()
    
    # This should pass in the real repo
    assert passed, f"Constitutional size check failed:\n{message}"
    assert "Layer 0 (Kernel):" in message
    assert "Layer 3 (Living):" in message


def test_check_constitutional_size_reports_ratio():
    """Check reports the ratio of Layer 0 to Layer 3."""
    passed, message = check_constitutional_size()
    
    assert "Ratio:" in message or "ratio" in message.lower()


def test_enforce_constitutional_size_passes():
    """enforce_constitutional_size should not raise in real repo."""
    # This should not raise
    enforce_constitutional_size()


def test_enforce_constitutional_size_logs_result(caplog):
    """enforce_constitutional_size logs the check result."""
    import logging
    caplog.set_level(logging.INFO)
    
    enforce_constitutional_size()
    
    assert len(caplog.records) > 0
    # Should log the check message
    assert any("Layer 0" in rec.message for rec in caplog.records)


def test_constitutional_size_check_cli():
    """CLI test can be run standalone."""
    import subprocess
    
    result = subprocess.run(
        ["python3", "-m", "dharma_swarm.constitutional_size_check"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0
    assert "Layer 0" in result.stdout
    assert "Layer 3" in result.stdout
