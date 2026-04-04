"""Tests for dharma_swarm.dual_audit."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.dual_audit import (
    AuditReport,
    DualAudit,
    _build_prompt,
    _compare,
    _normalize_finding,
    _parse_json_response,
)


def test_parse_json_clean():
    raw = json.dumps({"findings": [{"title": "x"}], "summary": "ok"})
    result = _parse_json_response(raw)
    assert result["summary"] == "ok"
    assert len(result["findings"]) == 1


def test_parse_json_fenced():
    raw = '```json\n{"findings": [], "summary": "clean"}\n```'
    result = _parse_json_response(raw)
    assert result["summary"] == "clean"


def test_parse_json_with_preamble():
    raw = 'Here is my analysis:\n{"findings": [{"title": "bug"}], "summary": "found one"}'
    result = _parse_json_response(raw)
    assert result["summary"] == "found one"


def test_parse_json_garbage():
    raw = "this is not json at all"
    result = _parse_json_response(raw)
    assert result["findings"] == []
    assert "(parse error)" in result["summary"]


def test_normalize_finding():
    f = {"category": "Security", "location": "foo.py:10", "title": "SQL injection"}
    assert _normalize_finding(f) == "security:foo.py:10:sql injection"


def test_compare_agreement():
    claude = {
        "findings": [
            {"category": "security", "location": "a.py:1", "title": "xss", "detail": "c detail"},
        ],
    }
    codex = {
        "findings": [
            {"category": "security", "location": "a.py:1", "title": "xss", "detail": "x detail"},
        ],
    }
    agreed, c_only, x_only = _compare(claude, codex)
    assert len(agreed) == 1
    assert agreed[0]["source"] == "both"
    assert agreed[0]["codex_detail"] == "x detail"
    assert len(c_only) == 0
    assert len(x_only) == 0


def test_compare_disjoint():
    claude = {"findings": [{"category": "security", "location": "a:1", "title": "xss"}]}
    codex = {"findings": [{"category": "perf", "location": "b:2", "title": "slow"}]}
    agreed, c_only, x_only = _compare(claude, codex)
    assert len(agreed) == 0
    assert len(c_only) == 1
    assert len(x_only) == 1


def test_build_prompt_contains_categories():
    prompt = _build_prompt(["dharma_swarm/dual_audit.py"])
    assert "security" in prompt
    assert "correctness" in prompt


def test_run_mocked():
    import asyncio

    mock_claude = {"findings": [{"category": "security", "location": "x:1", "title": "a"}], "summary": "c"}
    mock_codex = {"findings": [{"category": "security", "location": "x:1", "title": "a"}], "summary": "x"}

    async def _run():
        with patch("dharma_swarm.dual_audit._run_claude", new_callable=AsyncMock) as mc, \
             patch("dharma_swarm.dual_audit._run_codex", new_callable=AsyncMock) as mx:
            mc.return_value = (mock_claude, 1.0)
            mx.return_value = (mock_codex, 2.0)
            audit = DualAudit()
            report = await audit.run("dharma_swarm/dual_audit.py")
            assert len(report.agreements) == 1
            assert report.claude_duration_sec == 1.0
            assert report.codex_duration_sec == 2.0

    asyncio.run(_run())
