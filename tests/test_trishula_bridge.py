"""Tests for dharma_swarm.trishula_bridge -- TrishulaBridge message classification."""

import json
from pathlib import Path

import pytest

from dharma_swarm.models import TaskPriority, TaskStatus
from dharma_swarm.trishula_bridge import (
    MessageClassification,
    TrishulaBridge,
    PROCESSED_LOG,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    """Create and return a temporary inbox directory."""
    d = tmp_path / "inbox"
    d.mkdir()
    return d


@pytest.fixture
def bridge(inbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TrishulaBridge:
    """Return a TrishulaBridge pointing at the temporary inbox.

    Also patches PROCESSED_LOG to avoid touching the real filesystem.
    """
    processed_log = tmp_path / "trishula_processed.json"
    monkeypatch.setattr(
        "dharma_swarm.trishula_bridge.PROCESSED_LOG", processed_log
    )
    return TrishulaBridge(inbox=inbox)


def _write_message(inbox: Path, name: str, content: str) -> Path:
    """Write a message file to the inbox and return its path."""
    fpath = inbox / name
    fpath.write_text(content, encoding="utf-8")
    return fpath


def _write_json_message(inbox: Path, name: str, data: dict) -> Path:
    """Write a JSON message file to the inbox."""
    fpath = inbox / name
    fpath.write_text(json.dumps(data), encoding="utf-8")
    return fpath


# ---------------------------------------------------------------------------
# test_classify_ack_message
# ---------------------------------------------------------------------------


def test_classify_ack_message(bridge: TrishulaBridge, inbox: Path):
    """Message with 'ack' + 'comms_check' in filename is classified as ack_noise."""
    path = _write_message(inbox, "ack_comms_check_001.md", "acknowledged")
    cls = bridge.classify(path)
    assert cls.category == "ack_noise"


def test_classify_ack_body(bridge: TrishulaBridge, inbox: Path):
    """Short body containing only 'ack' boilerplate is classified as ack_noise."""
    path = _write_message(inbox, "response_042.txt", "acknowledged.")
    cls = bridge.classify(path)
    assert cls.category == "ack_noise"


def test_classify_ack_json_type(bridge: TrishulaBridge, inbox: Path):
    """JSON message with type='ack' is classified as ack_noise."""
    path = _write_json_message(inbox, "ping_reply.json", {
        "type": "ack",
        "body": "pong",
    })
    cls = bridge.classify(path)
    assert cls.category == "ack_noise"


# ---------------------------------------------------------------------------
# test_classify_actionable_message
# ---------------------------------------------------------------------------


def test_classify_actionable_todo(bridge: TrishulaBridge, inbox: Path):
    """Message containing 'TODO' is classified as actionable."""
    path = _write_message(
        inbox,
        "task_request.md",
        "# Request\nTODO: implement the multi-token R_V bridge experiment.",
    )
    cls = bridge.classify(path)
    assert cls.category == "actionable"
    assert cls.priority is not None


def test_classify_actionable_blocking(bridge: TrishulaBridge, inbox: Path):
    """Message containing 'BLOCKING' is classified as actionable with URGENT priority."""
    path = _write_message(
        inbox,
        "blocker.md",
        "This is BLOCKING the pipeline. We need to resolve the import issue.",
    )
    cls = bridge.classify(path)
    assert cls.category == "actionable"
    assert cls.priority == TaskPriority.URGENT


# ---------------------------------------------------------------------------
# test_classify_informational
# ---------------------------------------------------------------------------


def test_classify_informational(bridge: TrishulaBridge, inbox: Path):
    """Technical content with no action words is classified as informational."""
    path = _write_message(
        inbox,
        "research_update.md",
        (
            "# R_V Layer 27 Analysis\n"
            "The activation_patching results at Layer 27 show a Cohen's d of -3.558. "
            "Mistral architecture exhibits the strongest contraction signature. "
            "AUROC remains at 0.909 across the test bank."
        ),
    )
    cls = bridge.classify(path)
    assert cls.category == "informational"


# ---------------------------------------------------------------------------
# test_process_inbox_creates_tasks
# ---------------------------------------------------------------------------


def test_process_inbox_creates_tasks(bridge: TrishulaBridge, inbox: Path):
    """Create inbox with mixed messages, verify correct task creation."""
    # Actionable
    _write_message(inbox, "task_a.md", "TODO: run the P0 canonical pipeline on base model")
    # Ack noise
    _write_message(inbox, "ack_comms_check_01.md", "acknowledged")
    # Informational
    _write_message(
        inbox,
        "report.md",
        "Mistral Layer 27 causal validation shows strong R_V contraction.",
    )
    # Actionable with URGENT
    _write_message(inbox, "urgent_fix.md", "URGENT: deploy the patching fix immediately")

    result = bridge.process_inbox()

    assert result["actionable"] == 2
    assert result["ack_noise"] >= 1
    assert result["informational"] >= 1
    tasks = result["tasks_created"]
    assert len(tasks) == 2
    assert all(t.status == TaskStatus.PENDING for t in tasks)


# ---------------------------------------------------------------------------
# test_already_processed_skipped
# ---------------------------------------------------------------------------


def test_already_processed_skipped(bridge: TrishulaBridge, inbox: Path):
    """Process twice -- second run should skip all."""
    _write_message(inbox, "first.md", "TODO: implement something important")
    _write_message(inbox, "second.md", "Another TODO item for the pipeline")

    result1 = bridge.process_inbox()
    assert result1["actionable"] == 2
    assert result1["already_processed"] == 0

    result2 = bridge.process_inbox()
    assert result2["already_processed"] == 2
    assert result2["actionable"] == 0
    assert len(result2["tasks_created"]) == 0


# ---------------------------------------------------------------------------
# test_task_has_correct_metadata
# ---------------------------------------------------------------------------


def test_task_has_correct_metadata(bridge: TrishulaBridge, inbox: Path):
    """Verify task.metadata includes source information."""
    _write_message(inbox, "deploy_request.md", "TODO: deploy the new swarm version")

    result = bridge.process_inbox()
    tasks = result["tasks_created"]
    assert len(tasks) == 1

    task = tasks[0]
    assert task.metadata["source"] == "trishula"
    assert task.metadata["source_file"] == "deploy_request.md"
    assert task.metadata["classified_as"] == "actionable"
    assert task.created_by == "trishula_bridge"
    assert task.title.startswith("[trishula] ")


# ---------------------------------------------------------------------------
# test_urgent_priority_detection
# ---------------------------------------------------------------------------


def test_urgent_priority_detection(bridge: TrishulaBridge, inbox: Path):
    """'URGENT' in content should result in URGENT priority."""
    path = _write_message(
        inbox,
        "escalation.md",
        "URGENT: the daemon crashed overnight, needs immediate restart.",
    )
    cls = bridge.classify(path)
    assert cls.category == "actionable"
    assert cls.priority == TaskPriority.URGENT


def test_high_priority_detection(bridge: TrishulaBridge, inbox: Path):
    """'deadline' in content should result in HIGH priority."""
    path = _write_message(
        inbox,
        "deadline_notice.md",
        "There is a deadline on March 26 for the COLM abstract submission.",
    )
    cls = bridge.classify(path)
    assert cls.category == "actionable"
    assert cls.priority == TaskPriority.HIGH


# ---------------------------------------------------------------------------
# test_triage_report_format
# ---------------------------------------------------------------------------


def test_triage_report_format(bridge: TrishulaBridge, inbox: Path):
    """Verify the triage report is a human-readable string."""
    _write_message(inbox, "action.md", "TODO: complete the R_V paper Table 1")
    _write_message(inbox, "noise.md", "ack")

    report = bridge.triage_report()

    assert isinstance(report, str)
    assert "Trishula Inbox Triage Report" in report
    assert "Total files:" in report
    assert "Actionable:" in report
    assert "Ack noise:" in report


# ---------------------------------------------------------------------------
# test_empty_inbox
# ---------------------------------------------------------------------------


def test_empty_inbox(bridge: TrishulaBridge, inbox: Path):
    """No files in inbox should produce empty result."""
    result = bridge.process_inbox()

    assert result["total_scanned"] == 0
    assert result["actionable"] == 0
    assert result["informational"] == 0
    assert result["ack_noise"] == 0
    assert result["tasks_created"] == []
    assert result["already_processed"] == 0


def test_empty_inbox_triage_report(bridge: TrishulaBridge, inbox: Path):
    """Empty inbox triage report should still be a valid string."""
    report = bridge.triage_report()
    assert isinstance(report, str)
    assert "Total files:" in report
