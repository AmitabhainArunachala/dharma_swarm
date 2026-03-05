"""Tests for dharma_swarm TUI and splash modules."""

from rich.text import Text

from dharma_swarm.splash import SPLASH, SPLASH_COMPACT, get_splash


def test_splash_full():
    s = get_splash(compact=False)
    assert isinstance(s, Text)
    plain = s.plain
    assert "Godel" in plain or "DHARMIC" in plain or "▓" in plain
    assert "Sx" in plain
    assert "TELOS" in plain
    assert "SWARM" in plain
    assert "Godel" in plain


def test_splash_compact():
    s = get_splash(compact=True)
    assert isinstance(s, Text)
    assert len(s.plain) < len(get_splash(compact=False).plain)


def test_splash_has_gates():
    plain = get_splash().plain
    assert "AHIMSA" in plain
    assert "WITNESS" in plain


def test_splash_has_architecture():
    plain = get_splash().plain
    assert "MEMORY" in plain
    assert "CONTEXT" in plain
    assert "PULSE" in plain
    assert "TRISHULA" in plain


def test_tui_imports():
    """Verify TUI classes can be imported."""
    from dharma_swarm.tui import DGCApp, SplashScreen, run_tui
    assert DGCApp is not None
    assert SplashScreen is not None
    assert callable(run_tui)


def test_tui_helpers():
    """Test TUI helper functions."""
    from dharma_swarm.tui import _file_age_str, _read_json
    from pathlib import Path

    assert _read_json(Path("/nonexistent/file.json")) == {}
    assert _file_age_str(Path("/nonexistent")) == "n/a"


def test_build_status_text():
    """Status text builder should not crash and contain key sections."""
    from dharma_swarm.tui import _build_status_text
    text = _build_status_text()
    assert isinstance(text, str)
    lower = text.lower()
    assert "pulse" in lower or "memory" in lower or "gates" in lower
    assert "DGC STATUS" in text


def test_count_git_status_parser():
    """Parse git porcelain counts deterministically."""
    from dharma_swarm.tui import _count_git_status

    porcelain = "\n".join(
        [
            " M unstaged_only.py",
            "M  staged_only.py",
            "MM both_changed.py",
            "A  added.py",
            " D deleted_worktree.py",
            "?? new_file.py",
        ]
    )
    counts = _count_git_status(porcelain)
    assert counts["staged"] == 3
    assert counts["unstaged"] == 3
    assert counts["untracked"] == 1


def test_runtime_git_truth_builders():
    """Runtime/git/truth builders should render without crashing."""
    from dharma_swarm.tui import _build_runtime_text, _build_git_text, _build_truth_report

    runtime = _build_runtime_text()
    git_text = _build_git_text()
    truth = _build_truth_report()

    assert "Runtime Control Plane" in runtime
    assert "Git Reality" in git_text
    assert "Truth Report" in truth
