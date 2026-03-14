"""Tests for dharma_swarm.conversation_distiller."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.conversation_distiller import (
    _compute_salience,
    _ensure_dirs,
    _extract_ideas,
    _find_recent_dashboard_logs,
    _find_recent_transcripts,
    _load_last_distill_time,
    _parse_dashboard_log,
    _parse_transcript,
    _save_distill_time,
    _write_distill_report,
    _write_ideas_log,
    _write_latest_synthesis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript_file(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "session.jsonl"
    lines = [json.dumps(r) for r in records]
    p.write_text("\n".join(lines))
    return p


def _make_dashboard_file(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "dashboard.jsonl"
    lines = [json.dumps(r) for r in records]
    p.write_text("\n".join(lines))
    return p


# ---------------------------------------------------------------------------
# _parse_transcript
# ---------------------------------------------------------------------------

class TestParseTranscript:
    def test_parses_user_and_assistant_turns(self, tmp_path: Path) -> None:
        records = [
            {"type": "user", "message": {"role": "user", "content": "what if we redesign the architecture here"}, "timestamp": "2024-01-01T00:00:00Z", "sessionId": "s1"},
            {"type": "assistant", "message": {"role": "assistant", "content": "The plan is to use async providers for better throughput"}, "timestamp": "2024-01-01T00:01:00Z", "sessionId": "s1"},
        ]
        path = _make_transcript_file(tmp_path, records)
        turns = _parse_transcript(path)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"
        assert turns[0]["source"] == "claude_code"

    def test_skips_short_content(self, tmp_path: Path) -> None:
        records = [
            {"type": "user", "message": {"role": "user", "content": "ok"}, "timestamp": "", "sessionId": "s1"},
            {"type": "user", "message": {"role": "user", "content": "this is a proper long sentence that passes the threshold"}, "timestamp": "", "sessionId": "s1"},
        ]
        path = _make_transcript_file(tmp_path, records)
        turns = _parse_transcript(path)
        assert len(turns) == 1

    def test_flattens_list_content(self, tmp_path: Path) -> None:
        content_blocks = [
            {"type": "text", "text": "This is a sufficiently long text block for testing purposes"},
            {"type": "tool_use", "id": "tool1"},
        ]
        records = [
            {"type": "user", "message": {"role": "user", "content": content_blocks}, "timestamp": "", "sessionId": "s2"},
        ]
        path = _make_transcript_file(tmp_path, records)
        turns = _parse_transcript(path)
        assert len(turns) == 1
        assert "sufficiently long text block" in turns[0]["content"]

    def test_skips_non_conversation_types(self, tmp_path: Path) -> None:
        records = [
            {"type": "tool_result", "message": {"role": "tool", "content": "some tool output that is long enough to pass length check"}, "timestamp": "", "sessionId": "s3"},
        ]
        path = _make_transcript_file(tmp_path, records)
        turns = _parse_transcript(path)
        assert len(turns) == 0

    def test_handles_invalid_json_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.jsonl"
        p.write_text('{"type":"user","message":{"role":"user","content":"valid long sentence here for testing"},"sessionId":"x"}\nNOT_JSON\n')
        turns = _parse_transcript(p)
        assert len(turns) == 1


# ---------------------------------------------------------------------------
# _parse_dashboard_log
# ---------------------------------------------------------------------------

class TestParseDashboardLog:
    def test_parses_valid_records(self, tmp_path: Path) -> None:
        records = [
            {"role": "user", "content": "We decided to use OpenRouter as the default provider", "timestamp": "t1", "session_id": "d1"},
            {"role": "assistant", "content": "The architecture pattern uses async generators for streaming", "timestamp": "t2", "session_id": "d1"},
        ]
        path = _make_dashboard_file(tmp_path, records)
        turns = _parse_dashboard_log(path)
        assert len(turns) == 2
        assert turns[0]["source"] == "dashboard"
        assert turns[1]["session_id"] == "d1"

    def test_skips_short_content(self, tmp_path: Path) -> None:
        records = [
            {"role": "user", "content": "hi", "timestamp": "", "session_id": "d2"},
        ]
        path = _make_dashboard_file(tmp_path, records)
        turns = _parse_dashboard_log(path)
        assert len(turns) == 0


# ---------------------------------------------------------------------------
# _extract_ideas
# ---------------------------------------------------------------------------

class TestExtractIdeas:
    def _turn(self, content: str, role: str = "user") -> dict:
        return {
            "role": role,
            "content": content,
            "timestamp": "2024-01-01T00:00:00Z",
            "session_id": "sess1",
            "source": "claude_code",
        }

    def test_detects_hypothesis_pattern(self) -> None:
        turns = [self._turn("What if we redesigned the routing layer to use a policy compiler instead of hard-coded rules?")]
        ideas = _extract_ideas(turns)
        assert any(i["type"] == "hypothesis" for i in ideas)

    def test_detects_decision_pattern(self) -> None:
        turns = [self._turn("We decided to go with the async approach for all I/O bound operations going forward")]
        ideas = _extract_ideas(turns)
        assert any(i["type"] == "decision" for i in ideas)

    def test_detects_bug_pattern(self) -> None:
        turns = [self._turn("Bug: the test fails because env vars are leaking between test cases in conftest")]
        ideas = _extract_ideas(turns)
        assert any(i["type"] == "bug" for i in ideas)

    def test_detects_todo_pattern(self) -> None:
        turns = [self._turn("Need to add a proper autouse fixture to isolate DGC env vars before every test run")]
        ideas = _extract_ideas(turns)
        assert any(i["type"] == "todo" for i in ideas)

    def test_deduplicates_by_hash(self) -> None:
        text = "Decided to use async providers for all I/O bound operations in the routing layer"
        turns = [self._turn(text), self._turn(text)]
        ideas = _extract_ideas(turns)
        assert len(ideas) == 1

    def test_truncates_long_paragraphs(self) -> None:
        long_text = "What if " + ("x " * 400)
        turns = [self._turn(long_text)]
        ideas = _extract_ideas(turns)
        if ideas:
            assert len(ideas[0]["text"]) <= 503  # 500 + "..."

    def test_empty_turns_returns_empty(self) -> None:
        assert _extract_ideas([]) == []


# ---------------------------------------------------------------------------
# _compute_salience
# ---------------------------------------------------------------------------

class TestComputeSalience:
    def _idea(self, idea_type: str, text: str = "some text here for testing", role: str = "user") -> dict:
        return {
            "type": idea_type,
            "text": text,
            "role": role,
            "timestamp": "",
            "session_id": "",
            "source": "claude_code",
        }

    def test_decision_scores_higher_than_hypothesis(self) -> None:
        d = _compute_salience(self._idea("decision"))
        h = _compute_salience(self._idea("hypothesis"))
        assert d > h

    def test_score_clamped_to_1(self) -> None:
        long_text = "error: " + "x " * 300
        idea = self._idea("bug", text=long_text)
        assert _compute_salience(idea) <= 1.0

    def test_score_at_least_0(self) -> None:
        idea = self._idea("hypothesis", text="short")
        assert _compute_salience(idea) >= 0.0

    def test_user_role_bonus(self) -> None:
        user_idea = self._idea("insight", role="user")
        assistant_idea = self._idea("insight", role="assistant")
        assert _compute_salience(user_idea) >= _compute_salience(assistant_idea)

    def test_longer_text_bonus(self) -> None:
        short_idea = self._idea("insight", text="x" * 50)
        long_idea = self._idea("insight", text="x" * 250)
        assert _compute_salience(long_idea) >= _compute_salience(short_idea)


# ---------------------------------------------------------------------------
# _write_ideas_log and _write_distill_report
# ---------------------------------------------------------------------------

class TestWriteOutput:
    def _idea(self, idea_type: str = "decision", text: str = "Test decision text that is long enough") -> dict:
        h = hashlib.sha256(text[:200].encode()).hexdigest()[:16]
        return {
            "type": idea_type,
            "text": text,
            "role": "user",
            "timestamp": "2024-01-01",
            "session_id": "s1",
            "source": "claude_code",
            "hash": h,
        }

    def test_write_ideas_log_appends_jsonl(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log_path = tmp_path / "ideas.jsonl"
        monkeypatch.setattr("dharma_swarm.conversation_distiller.IDEAS_LOG", log_path)
        ideas = [self._idea("decision"), self._idea("bug", text="Bug found in routing layer that causes tests to fail")]
        _write_ideas_log(ideas)
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "salience" in data
            assert "distilled_at" in data

    def test_write_ideas_log_noop_on_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log_path = tmp_path / "ideas.jsonl"
        monkeypatch.setattr("dharma_swarm.conversation_distiller.IDEAS_LOG", log_path)
        _write_ideas_log([])
        assert not log_path.exists()

    def test_write_distill_report_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dharma_swarm.conversation_distiller.DISTILLED_DIR", tmp_path)
        ideas = [self._idea("decision"), self._idea("insight", text="Found that async improves throughput significantly")]
        report_path = _write_distill_report(ideas, sources_processed=3)
        assert report_path is not None
        assert report_path.exists()
        content = report_path.read_text()
        assert "Conversation Distillation" in content
        assert "Sources processed" in content


# ---------------------------------------------------------------------------
# _load_last_distill_time / _save_distill_time
# ---------------------------------------------------------------------------

class TestDistillTimeState:
    def test_returns_24h_ago_when_no_state_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        state_file = tmp_path / ".last_distill"
        monkeypatch.setattr("dharma_swarm.conversation_distiller.STATE_FILE", state_file)
        ts = _load_last_distill_time()
        now = datetime.now(timezone.utc)
        diff = now - ts
        assert 23 < diff.total_seconds() / 3600 < 25

    def test_save_and_load_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        state_file = tmp_path / ".last_distill"
        monkeypatch.setattr("dharma_swarm.conversation_distiller.STATE_FILE", state_file)
        _save_distill_time()
        ts = _load_last_distill_time()
        now = datetime.now(timezone.utc)
        assert (now - ts).total_seconds() < 5

    def test_handles_corrupt_state_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        state_file = tmp_path / ".last_distill"
        state_file.write_text("not-a-datetime")
        monkeypatch.setattr("dharma_swarm.conversation_distiller.STATE_FILE", state_file)
        ts = _load_last_distill_time()
        # Should fall back to 24h ago
        now = datetime.now(timezone.utc)
        assert (now - ts).total_seconds() / 3600 > 20


# ---------------------------------------------------------------------------
# _find_recent_transcripts and _find_recent_dashboard_logs
# ---------------------------------------------------------------------------

class TestFindRecent:
    def test_find_transcripts_missing_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        missing = tmp_path / "nonexistent"
        monkeypatch.setattr("dharma_swarm.conversation_distiller.CLAUDE_PROJECTS_DIR", missing)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = _find_recent_transcripts(since)
        assert result == []

    def test_find_dashboard_logs_missing_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        missing = tmp_path / "nonexistent"
        monkeypatch.setattr("dharma_swarm.conversation_distiller.DASHBOARD_CONVERSATIONS_DIR", missing)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = _find_recent_dashboard_logs(since)
        assert result == []
