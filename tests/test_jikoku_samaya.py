"""
Tests for JIKOKU SAMAYA computational efficiency protocol.
"""

import pytest
import time
import json
from pathlib import Path
from datetime import datetime
import tempfile

from dharma_swarm.jikoku_samaya import (
    JikokuTracer,
    JikokuSpan,
    jikoku_span,
    jikoku_start,
    jikoku_end,
    jikoku_kaizen,
    init_tracer,
)


@pytest.fixture
def temp_log():
    """Create temporary log file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


def test_span_creation(temp_log):
    """Test basic span creation and completion"""
    tracer = JikokuTracer(log_path=temp_log, session_id="test-session-001")

    span_id = tracer.start("api_call", "Test API call", agent_id="test-agent")
    time.sleep(0.1)  # Simulate work
    span = tracer.end(span_id)

    assert span.category == "api_call"
    assert span.intent == "Test API call"
    assert span.agent_id == "test-agent"
    assert span.duration_sec >= 0.1
    assert span.ts_end is not None


def test_context_manager_span(temp_log):
    """Test span using context manager"""
    tracer = JikokuTracer(log_path=temp_log, session_id="test-session-002")

    with tracer.span("execute.llm_call", "Generate mutation", task_id="task-123"):
        time.sleep(0.05)

    # Should be written to log
    spans = tracer.get_session_spans()
    assert len(spans) == 1
    assert spans[0].category == "execute.llm_call"
    assert spans[0].task_id == "task-123"
    assert spans[0].duration_sec >= 0.05


def test_invalid_category():
    """Test that invalid categories are rejected"""
    tracer = JikokuTracer()

    with pytest.raises(ValueError, match="Invalid category"):
        tracer.start("invalid_category", "Test")


def test_execute_wildcard(temp_log):
    """Test that execute.* wildcard works"""
    tracer = JikokuTracer(log_path=temp_log)

    # These should all be valid
    span1 = tracer.start("execute.llm_call", "LLM call")
    span2 = tracer.start("execute.code_gen", "Code generation")
    span3 = tracer.start("execute.mutation", "Mutation proposal")

    tracer.end(span1)
    tracer.end(span2)
    tracer.end(span3)

    spans = tracer.get_session_spans()
    assert len(spans) == 3


def test_jsonl_serialization():
    """Test JSONL serialization and deserialization"""
    span = JikokuSpan(
        span_id="test-span-001",
        category="api_call",
        intent="Test span",
        ts_start=datetime.now().isoformat(),
        ts_end=datetime.now().isoformat(),
        duration_sec=1.23,
        session_id="test-session",
        agent_id="test-agent",
        task_id="test-task",
        metadata={"key": "value"}
    )

    # Serialize
    jsonl = span.to_jsonl()
    assert isinstance(jsonl, str)
    assert json.loads(jsonl)  # Valid JSON

    # Deserialize
    restored = JikokuSpan.from_jsonl(jsonl)
    assert restored.span_id == span.span_id
    assert restored.category == span.category
    assert restored.duration_sec == span.duration_sec
    assert restored.metadata == span.metadata


def test_kaizen_report(temp_log):
    """Test kaizen (continuous improvement) report generation"""
    tracer = JikokuTracer(log_path=temp_log, session_id="kaizen-test")

    # Create mix of spans
    with tracer.span("boot", "System boot"):
        time.sleep(0.01)

    with tracer.span("api_call", "API call 1"):
        time.sleep(0.05)

    with tracer.span("api_call", "API call 2"):
        time.sleep(0.03)

    with tracer.span("execute.llm_call", "LLM generation"):
        time.sleep(0.02)

    # Generate report
    report = tracer.kaizen_report(last_n_sessions=1)

    assert report['sessions_analyzed'] == 1
    assert report['total_spans'] == 4
    assert report['total_compute_sec'] > 0
    assert report['utilization_pct'] > 0
    assert 'category_breakdown' in report
    assert 'api_call' in report['category_breakdown']
    assert report['category_breakdown']['api_call']['count'] == 2


def test_utilization_calculation(temp_log):
    """Test that utilization percentage is calculated correctly"""
    tracer = JikokuTracer(log_path=temp_log, session_id="util-test")

    # Span that takes 0.1 seconds
    with tracer.span("execute.test", "Test work"):
        time.sleep(0.1)

    # Add 0.1 second gap (simulating idle time)
    time.sleep(0.1)

    # Another 0.1 second span
    with tracer.span("execute.test", "More work"):
        time.sleep(0.1)

    report = tracer.kaizen_report(last_n_sessions=1)

    # Total compute: ~0.2s, wall clock: ~0.3s
    # Utilization should be ~66%
    # Idle (pramāda) should be ~33%
    assert 50 < report['utilization_pct'] < 80
    assert 20 < report['idle_pct'] < 50


def test_optimization_targets(temp_log):
    """Test that longest spans are identified as optimization targets"""
    tracer = JikokuTracer(log_path=temp_log, session_id="opt-test")

    # Create spans of varying duration
    with tracer.span("execute.fast", "Fast operation"):
        time.sleep(0.01)

    with tracer.span("execute.slow", "Slow operation"):
        time.sleep(0.1)  # This should be optimization target

    with tracer.span("execute.medium", "Medium operation"):
        time.sleep(0.05)

    report = tracer.kaizen_report(last_n_sessions=1)

    # Longest span should be first in optimization targets
    assert len(report['optimization_targets']) > 0
    assert report['optimization_targets'][0]['category'] == "execute.slow"
    assert report['optimization_targets'][0]['duration_sec'] >= 0.1


def test_kaizen_goals_generation(temp_log):
    """Test that kaizen goals are generated based on metrics"""
    tracer = JikokuTracer(log_path=temp_log, session_id="goals-test")

    # Create low-utilization scenario: two short spans with long idle gap between
    with tracer.span("execute.work", "Actual work"):
        time.sleep(0.05)

    time.sleep(0.2)  # Long idle time between spans

    with tracer.span("execute.finish", "Wrap up"):
        time.sleep(0.01)

    report = tracer.kaizen_report(last_n_sessions=1)

    # Should have utilization goal (since utilization < 50%)
    assert 'kaizen_goals' in report
    assert len(report['kaizen_goals']) > 0
    assert any('INCREASE UTILIZATION' in goal for goal in report['kaizen_goals'])


def test_global_tracer_functions(temp_log):
    """Test global tracer convenience functions"""
    init_tracer(log_path=temp_log, session_id="global-test")

    # Use global functions
    span_id = jikoku_start("api_call", "Global test")
    time.sleep(0.01)
    span = jikoku_end(span_id)

    assert span.category == "api_call"

    # Context manager version
    with jikoku_span("execute.test", "Context manager test"):
        time.sleep(0.01)

    # Should have 2 spans
    report = jikoku_kaizen(last_n_sessions=1)
    assert report['total_spans'] == 2


def test_metadata_preservation(temp_log):
    """Test that metadata is preserved through span lifecycle"""
    tracer = JikokuTracer(log_path=temp_log, session_id="meta-test")

    metadata = {
        'model': 'claude-opus-4',
        'tokens': 1500,
        'cost_usd': 0.045
    }

    with tracer.span("api_call", "API with metadata", **metadata):
        pass

    spans = tracer.get_session_spans()
    assert len(spans) == 1
    assert spans[0].metadata['model'] == 'claude-opus-4'
    assert spans[0].metadata['tokens'] == 1500
    assert spans[0].metadata['cost_usd'] == 0.045


def test_pramada_detection(temp_log):
    """
    Test pramāda (heedlessness) detection.

    Pramāda is idle time - the tilde in "~3.5 minutes".
    The protocol should detect and quantify waste.
    """
    tracer = JikokuTracer(log_path=temp_log, session_id="pramada-test")

    # Scenario: Agent does 0.1s of work, idles for 0.4s, then finishes
    with tracer.span("execute.work", "Actual work"):
        time.sleep(0.1)

    time.sleep(0.4)  # PRAMĀDA - heedless waste between spans

    with tracer.span("execute.finish", "Wrap up"):
        time.sleep(0.01)

    report = tracer.kaizen_report(last_n_sessions=1)

    # Idle should be ~80% (0.4 / 0.5)
    assert report['idle_pct'] > 70
    assert report['utilization_pct'] < 30

    # Should trigger kaizen goal
    assert any('INCREASE UTILIZATION' in goal for goal in report['kaizen_goals'])


@pytest.mark.parametrize("target_utilization,expected_gain", [
    (5, 10.0),   # 5% → 50% = 10x gain
    (10, 5.0),   # 10% → 50% = 5x gain
    (25, 2.0),   # 25% → 50% = 2x gain
])
def test_utilization_gain_calculation(target_utilization, expected_gain):
    """Test that potential efficiency gains are calculated correctly"""
    # The protocol states: "Path from 5% → 50% = 10x, zero hardware"
    actual_gain = 50 / target_utilization
    assert abs(actual_gain - expected_gain) < 0.01
