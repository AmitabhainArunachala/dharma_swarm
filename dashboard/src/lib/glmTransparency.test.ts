import assert from "node:assert/strict";
import test from "node:test";

import {
  buildGLMTransparencySummary,
  extractVisibleSynthesisCue,
  type GLMTransparencyToolEvent,
} from "./glmTransparency.ts";

test("extractVisibleSynthesisCue keeps the first visible synthesis sentence compact", () => {
  assert.equal(
    extractVisibleSynthesisCue(
      "  GLM mapped the anomaly cluster.\n\nIt found three silent agents after querying traces.  ",
    ),
    "GLM mapped the anomaly cluster.",
  );
  assert.equal(extractVisibleSynthesisCue("   "), null);
});

test("buildGLMTransparencySummary turns tool activity into a compact expandable trace model", () => {
  const events: GLMTransparencyToolEvent[] = [
    {
      type: "call",
      name: "grep_search",
      args: { pattern: "agent_silent" },
      timestamp: "2026-03-20T10:05:00.000Z",
    },
    {
      type: "result",
      name: "grep_search",
      summary: "3 anomalies matched in the monitor path.",
      timestamp: "2026-03-20T10:05:01.000Z",
    },
    {
      type: "call",
      name: "read_file",
      args: { path: "/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py" },
      timestamp: "2026-03-20T10:05:02.000Z",
    },
    {
      type: "result",
      name: "read_file",
      summary: "agent_silent is treated as medium severity once the trace goes quiet.",
      timestamp: "2026-03-20T10:05:03.000Z",
    },
  ];

  const summary = buildGLMTransparencySummary(
    "GLM mapped the anomaly cluster. It found three silent agents after querying traces.",
    events,
  );

  assert.equal(summary.cue, "GLM mapped the anomaly cluster.");
  assert.equal(summary.preview, "GLM mapped the anomaly cluster. | Search agent_silent | Read monitor.py");
  assert.equal(summary.stepCount, 4);
  assert.equal(summary.toolCallCount, 2);
  assert.equal(summary.toolResultCount, 2);
  assert.equal(summary.hasObservableTrace, true);
  assert.deepEqual(
    summary.steps.map((step) => ({
      kind: step.kind,
      label: step.label,
      detail: step.detail,
    })),
    [
      { kind: "call", label: "Search", detail: "agent_silent" },
      { kind: "result", label: "Search result", detail: "3 anomalies matched in the monitor path." },
      { kind: "call", label: "Read", detail: "monitor.py" },
      {
        kind: "result",
        label: "Read result",
        detail: "agent_silent is treated as medium severity once the trace goes quiet.",
      },
    ],
  );
});

test("buildGLMTransparencySummary falls back to the observable tool trace when there is no visible cue", () => {
  const summary = buildGLMTransparencySummary("", [
    {
      type: "call",
      name: "shell_exec",
      args: { command: "pytest -q tests/test_monitor.py --maxfail=1" },
      timestamp: "2026-03-20T10:06:00.000Z",
    },
  ]);

  assert.equal(summary.cue, null);
  assert.equal(summary.preview, "Run pytest -q tests/test_monitor.py --maxfail=1");
  assert.equal(summary.stepCount, 1);
  assert.equal(summary.toolCallCount, 1);
  assert.equal(summary.toolResultCount, 0);
});
