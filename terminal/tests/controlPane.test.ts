import {describe, expect, test} from "bun:test";
import React from "react";

import {
  buildControlPaneSections,
  buildOperatorSignalRows,
  buildRuntimePaneSections,
  ControlPane,
  sectionCardPreviewRows,
} from "../src/components/ControlPane";
import type {TabPreview, TranscriptLine} from "../src/types";

function flattenElementText(node: React.ReactNode): string[] {
  if (node === null || node === undefined || typeof node === "boolean") {
    return [];
  }
  if (typeof node === "string" || typeof node === "number") {
    return [String(node)];
  }
  if (Array.isArray(node)) {
    return node.flatMap((child) => flattenElementText(child));
  }
  if (React.isValidElement(node)) {
    return flattenElementText(node.props.children);
  }
  return [];
}

describe("buildControlPaneSections", () => {
  test("renders loop, runtime, verification, and durable state rows from preview fields", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 6 running",
      "Active task": "terminal-control-surface",
      "Task progress": "0 done, 1 pending of 1",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Loop decision": "continue required",
      Updated: "2026-04-01T03:44:29Z",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Active runs detail": "agent-alpha (running) task terminal-control-",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Recent operator actions": "reroute by operator (better frontier model)",
      "Runtime activity": "Sessions=18  Runs=0",
      "Artifact state": "Artifacts=7  ContextBundles=1",
      Toolchain: "claude, python3, node",
      Alerts: "none",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Verification updated": "2026-04-01T03:45:00Z",
      "Last result": "in_progress / pass",
      "Runtime freshness": "cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Next task": "Promote runtime snapshot rows into a dedicated runtime pane.",
      "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running | 0 done, 1 pending of 1 | terminal-control-surface",
          "Outcome in_progress / pass",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Verification all 4 checks passing",
          "Runtime 18 sessions | 0 runs",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Decision continue required | Promote runtime snapshot rows into a dedicated runtime pane.",
          "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Task terminal-control-surface | 0 done, 1 pending of 1",
          "Outcome in_progress | accept pass",
          "Verify all 4 checks passing",
          "Decision continue required",
          "Updated 2026-04-01T03:44:29Z",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Runs 0 runs | 0 active runs",
          "Active agent-alpha (running) task terminal-control-",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Actions reroute by operator (better frontier model)",
          "Activity Sessions=18  Runs=0",
          "Artifacts Artifacts=7  ContextBundles=1",
          "Tools claude, python3, node",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification all 4 checks passing",
          "Updated 2026-04-01T03:45:00Z",
          "Receipt /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state/verification.json | updated 2026-04-01T03:45:00Z",
          "Status all 4 checks passing",
          "Passing tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
          "Checks tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
          "Summary tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
          "Receipt /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state/verification.json | updated 2026-04-01T03:45:00Z",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Next",
        rows: [
          "Decision continue required | Promote runtime snapshot rows into a dedicated runtime pane.",
          "Task Promote runtime snapshot rows into a dedicated runtime pane.",
        ],
      },
    ]);
  });

  test("renders the durable verification receipt inside the verification card when persisted state is available", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 6 running",
      "Verification summary": "tsc=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; cycle_acceptance fail",
      "Verification receipt": "/tmp/durable/verification.json",
      "Verification updated": "2026-04-01T03:45:00Z",
      "Last result": "in_progress / fail",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running",
          "Outcome in_progress / fail",
          "Pulse in_progress / fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 1/2 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Updated 2026-04-01T03:45:00Z",
          "Receipt /tmp/durable/verification.json | updated 2026-04-01T03:45:00Z",
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Checks tsc ok; cycle_acceptance fail",
          "Summary tsc=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
      {
        title: "Durability",
        rows: [
          "Receipt /tmp/durable/verification.json | updated 2026-04-01T03:45:00Z",
          "Pulse in_progress / fail",
        ],
      },
    ]);
  });

  test("derives the durable verification receipt from state when the preview only carries the durable directory", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 6 running",
      "Verification summary": "tsc=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; cycle_acceptance fail",
      "Verification updated": "2026-04-01T03:45:00Z",
      "Last result": "in_progress / fail",
      "Durable state": "/tmp/durable",
    };

    expect(buildControlPaneSections(preview).find((section) => section.title === "Verification")?.rows).toContain(
      "Receipt /tmp/durable/verification.json | updated 2026-04-01T03:45:00Z",
    );
    expect(buildRuntimePaneSections(preview).find((section) => section.title === "Verification")?.rows).toContain(
      "Receipt /tmp/durable/verification.json | updated 2026-04-01T03:45:00Z",
    );
  });

  test("does not let placeholder authority rows displace live control state in overview detail", () => {
    const preview: TabPreview = {
      Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      "Loop state": "cycle 6 running",
      "Active task": "terminal-control-surface",
      "Task progress": "0 done, 1 pending of 1",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Runtime activity": "Sessions=18  Runs=0",
      "Artifact state": "Artifacts=7  ContextBundles=1",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Loop decision": "continue required",
    };

    expect(buildControlPaneSections(preview)[0]?.rows[0]).toBe(
      "Loop cycle 6 running | 0 done, 1 pending of 1 | terminal-control-surface",
    );
    expect(buildControlPaneSections(preview)[0]?.rows).not.toContain(
      "Authority placeholder | bridge offline | awaiting authoritative control refresh",
    );
  });

  test("prioritizes loop and verification signal in overview section cards over placeholder authority rows", () => {
    const sections = buildControlPaneSections({
      Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      "Loop state": "cycle 6 running",
      "Active task": "terminal-control-surface",
      "Task progress": "0 done, 1 pending of 1",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Verification summary": "tsc=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; cycle_acceptance fail",
      "Last result": "in_progress / fail",
    });

    expect(sectionCardPreviewRows(sections[0]!)).toEqual([
      "Loop cycle 6 running | 0 done, 1 pending of 1 | terminal-control-surface",
      "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
    ]);
  });

  test("fills missing fields from transcript lines and falls back to transcript content before preview is ready", () => {
    const lines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Loop state: cycle 6 running"},
      {id: "2", kind: "system", text: "Active task: terminal-control-surface"},
      {id: "3", kind: "system", text: "Task progress: 0 done, 1 pending of 1"},
      {id: "4", kind: "system", text: "Result status: in_progress"},
      {id: "5", kind: "system", text: "Acceptance: pass"},
      {id: "6", kind: "system", text: "Loop decision: continue required"},
      {id: "7", kind: "system", text: "Runtime DB: /Users/dhyana/.dharma/state/runtime.db"},
      {id: "8", kind: "system", text: "Runtime activity: Sessions=18  Runs=0"},
      {id: "9", kind: "system", text: "Artifact state: Artifacts=7  ContextBundles=1"},
      {id: "10", kind: "system", text: "Verification summary: tsc=ok | cycle_acceptance=ok"},
      {id: "11", kind: "system", text: "Verification checks: tsc ok; cycle_acceptance ok"},
      {id: "11b", kind: "system", text: "Verification updated: 2026-04-01T03:45:00Z"},
      {id: "12", kind: "system", text: "Control pulse preview: in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=ok"},
      {id: "13", kind: "system", text: "Durable state: /tmp/state"},
    ];

    expect(buildControlPaneSections({"Loop state": "cycle 6 running"}, lines)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running | 0 done, 1 pending of 1 | terminal-control-surface",
          "Outcome in_progress / pass",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=ok",
          "Verification all 2 checks passing",
          "Runtime 18 sessions | 0 runs",
          "Context 7 artifacts | 1 context bundles",
          "Decision continue required",
          "State /tmp/state",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Task terminal-control-surface | 0 done, 1 pending of 1",
          "Outcome in_progress | accept pass",
          "Verify all 2 checks passing",
          "Decision continue required",
          "Updated 2026-04-01T03:44:29Z",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions",
          "Runs 0 runs",
          "Context 7 artifacts | 1 context bundles",
          "Activity Sessions=18  Runs=0",
          "Artifacts Artifacts=7  ContextBundles=1",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification all 2 checks passing",
          "Updated 2026-04-01T03:45:00Z",
          "Receipt /tmp/state/verification.json | updated 2026-04-01T03:45:00Z",
          "Status all 2 checks passing",
          "Passing tsc, cycle_acceptance",
          "Checks tsc ok; cycle_acceptance ok",
          "Summary tsc=ok | cycle_acceptance=ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /tmp/state",
          "Receipt /tmp/state/verification.json | updated 2026-04-01T03:45:00Z",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Next",
        rows: ["Decision continue required"],
      },
    ].filter((section) => section.rows.length > 0));

    expect(buildControlPaneSections(undefined, lines)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running | 0 done, 1 pending of 1 | terminal-control-surface",
          "Outcome in_progress / pass",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=ok",
          "Verification all 2 checks passing",
          "Runtime 18 sessions | 0 runs",
          "Context 7 artifacts | 1 context bundles",
          "Decision continue required",
          "State /tmp/state",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Task terminal-control-surface | 0 done, 1 pending of 1",
          "Outcome in_progress | accept pass",
          "Verify all 2 checks passing",
          "Decision continue required",
          "Updated 2026-04-01T03:44:29Z",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions",
          "Runs 0 runs",
          "Context 7 artifacts | 1 context bundles",
          "Activity Sessions=18  Runs=0",
          "Artifacts Artifacts=7  ContextBundles=1",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification all 2 checks passing",
          "Updated 2026-04-01T03:45:00Z",
          "Receipt /tmp/state/verification.json | updated 2026-04-01T03:45:00Z",
          "Status all 2 checks passing",
          "Passing tsc, cycle_acceptance",
          "Checks tsc ok; cycle_acceptance ok",
          "Summary tsc=ok | cycle_acceptance=ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /tmp/state",
          "Receipt /tmp/state/verification.json | updated 2026-04-01T03:45:00Z",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Next",
        rows: ["Decision continue required"],
      },
    ].filter((section) => section.rows.length > 0));
  });

  test("keeps raw snapshot fallback for unstructured placeholder lines", () => {
    const lines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Control-plane snapshot loading..."},
      {id: "2", kind: "assistant", text: "Awaiting first runtime refresh."},
    ];

    expect(buildControlPaneSections(undefined, lines)).toEqual([
      {
        title: "Control Snapshot",
        rows: lines.map((line) => line.text),
      },
    ]);
  });

  test("does not let authority-only placeholder previews suppress raw control transcript fallback", () => {
    const lines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Control-plane snapshot loading..."},
      {id: "2", kind: "assistant", text: "Awaiting first runtime refresh."},
    ];

    expect(
      buildControlPaneSections(
        {
          Authority: "placeholder | bridge booting | awaiting authoritative control refresh",
        },
        lines,
      ),
    ).toEqual([
      {
        title: "Control Snapshot",
        rows: lines.map((line) => line.text),
      },
    ]);
  });

  test("derives control and verification sections from compact repo/control preview when structured control rows are absent", () => {
    const preview: TabPreview = {
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next hydrate control preview from runtime state",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 13 ready | 3 done, 1 pending of 4 | terminal-repo-pane",
          "Outcome in_progress / fail",
          "Pulse stale | in_progress / fail | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness stale",
          "Runtime 18 sessions | 0 runs",
          "Context 7 artifacts | 1 context bundles",
          "Decision continue required | hydrate control preview from runtime state",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 13 ready",
          "Task terminal-repo-pane | 3 done, 1 pending of 4",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness stale",
          "Decision continue required",
          "Updated 2026-04-03T01:15:00Z",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions",
          "Runs 0 runs | 0 active runs",
          "Context 7 artifacts | 1 context bundles",
          "Activity Sessions=18 Runs=0 ActiveRuns=0",
          "Artifacts Artifacts=7 ContextBundles=1",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness stale",
          "Updated 2026-04-03T01:15:00Z",
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Checks tsc ok; cycle_acceptance fail",
          "Summary tsc=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
      {
        title: "Next",
        rows: [
          "Decision continue required | hydrate control preview from runtime state",
          "Task hydrate control preview from runtime state",
        ],
      },
    ]);
  });

  test("omits placeholder-only rows when the control preview is sparse", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 6 running",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=18  Runs=1  ActiveRuns=1",
      "Verification summary": "tsc=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; cycle_acceptance fail",
      "Last result": "in_progress / fail",
      "Runtime freshness": "cycle 6 running | updated unknown | verify tsc=ok | cycle_acceptance=fail",
      "Control pulse preview": "in_progress / fail | cycle 6 running | updated unknown | verify tsc=ok | cycle_acceptance=fail",
      "Durable state": "/tmp/state",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running",
          "Outcome in_progress / fail",
          "Pulse in_progress / fail | cycle 6 running | updated unknown | verify tsc=ok | cycle_acceptance=fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Runtime 18 sessions | 1 runs | 1 active runs",
          "State /tmp/state",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 1/2 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions",
          "Runs 1 runs | 1 active runs",
          "Activity Sessions=18  Runs=1  ActiveRuns=1",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Receipt /tmp/state/verification.json",
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Checks tsc ok; cycle_acceptance fail",
          "Summary tsc=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /tmp/state",
          "Receipt /tmp/state/verification.json",
          "Pulse in_progress / fail | cycle 6 running | updated unknown | verify tsc=ok | cycle_acceptance=fail",
        ],
      },
      {
        title: "Next",
        rows: [],
      },
    ].filter((section) => section.rows.length > 0));
  });

  test("renders a runtime-focused layout for the runtime pane", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 6 running",
      "Active task": "terminal-control-surface",
      "Task progress": "0 done, 1 pending of 1",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Loop decision": "continue required",
      Updated: "2026-04-01T03:44:29Z",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Active runs detail": "agent-alpha (running) task terminal-control-",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Recent operator actions": "reroute by operator (better frontier model)",
      "Runtime activity": "Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state": "Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      Toolchain: "claude, python3, node",
      Alerts: "none",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Last result": "in_progress / pass",
      "Runtime freshness": "cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Next task": "Promote runtime snapshot rows into a dedicated runtime pane.",
      "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
    };

    expect(buildRuntimePaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running | 0 done, 1 pending of 1 | terminal-control-surface",
          "Outcome in_progress / pass",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Verification all 4 checks passing",
          "Runtime 18 sessions | 0 runs",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Decision continue required | Promote runtime snapshot rows into a dedicated runtime pane.",
          "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Runs 0 runs | 0 active runs",
          "Active agent-alpha (running) task terminal-control-",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Actions reroute by operator (better frontier model)",
          "Activity Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
          "Artifacts Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
        ],
      },
      {
        title: "Tools",
        rows: ["Toolchain claude, python3, node"],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Task terminal-control-surface | 0 done, 1 pending of 1",
          "Outcome in_progress | accept pass",
          "Verify all 4 checks passing",
          "Decision continue required",
          "Updated 2026-04-01T03:44:29Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification all 4 checks passing",
          "Updated 2026-04-01T03:44:29Z",
          "Receipt /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state/verification.json | updated 2026-04-01T03:44:29Z",
          "Status all 4 checks passing",
          "Passing tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
          "Checks tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
          "Summary tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
          "Receipt /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state/verification.json | updated 2026-04-01T03:44:29Z",
          "Pulse in_progress / pass | cycle 6 running | updated 2026-04-01T03:44:29Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Next",
        rows: [
          "Decision continue required | Promote runtime snapshot rows into a dedicated runtime pane.",
          "Task Promote runtime snapshot rows into a dedicated runtime pane.",
        ],
      },
    ]);
  });

  test("keeps runtime section cards focused on verification state instead of generic detail rows", () => {
    const sections = buildRuntimePaneSections({
      "Loop state": "cycle 9 running",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
      "Artifact state": "Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Last result": "in_progress / fail",
    });

    expect(sectionCardPreviewRows(sections[3]!)).toEqual([
      "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
      "Status 1 failing, 2/3 passing",
    ]);
  });

  test("prioritizes the durable verification receipt in section cards when persisted state is available", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 9 waiting_for_verification",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification receipt": "/tmp/durable/verification.json",
      "Verification updated": "2026-04-03T02:16:08Z",
      "Last result": "in_progress / fail",
    };

    const controlVerification = buildControlPaneSections(preview).find((section) => section.title === "Verification");
    const runtimeVerification = buildRuntimePaneSections(preview).find((section) => section.title === "Verification");

    expect(sectionCardPreviewRows(controlVerification!)).toEqual([
      "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
      "Receipt /tmp/durable/verification.json | updated 2026-04-03T02:16:08Z",
    ]);
    expect(sectionCardPreviewRows(runtimeVerification!)).toEqual([
      "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
      "Receipt /tmp/durable/verification.json | updated 2026-04-03T02:16:08Z",
    ]);
  });

  test("suppresses placeholder authority rows in runtime overview when live runtime state is present", () => {
    const preview: TabPreview = {
      Authority: "placeholder | bridge offline | awaiting authoritative control refresh",
      "Loop state": "cycle 9 running",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
      "Artifact state": "Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Last result": "in_progress / fail",
    };

    const overviewRows = buildRuntimePaneSections(preview)[0]?.rows ?? [];
    expect(overviewRows[0]).toBe("Loop cycle 9 running");
    expect(overviewRows).not.toContain("Authority placeholder | bridge offline | awaiting authoritative control refresh");
  });

  test("derives runtime pane summaries from aggregate snapshot metrics when detail rows are absent", () => {
    const lines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Runtime DB: /Users/dhyana/.dharma/state/runtime.db"},
      {
        id: "2",
        kind: "system",
        text: "Runtime activity: Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=2  ActiveRuns=1",
      },
      {
        id: "3",
        kind: "system",
        text: "Artifact state: Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      },
      {id: "4", kind: "system", text: "Verification summary: tsc=ok | cycle_acceptance=fail"},
      {id: "5", kind: "system", text: "Verification checks: tsc ok; cycle_acceptance fail"},
      {id: "6", kind: "system", text: "Loop state: cycle 6 running"},
      {id: "7", kind: "system", text: "Result status: in_progress"},
      {id: "8", kind: "system", text: "Acceptance: fail"},
    ];

    expect(buildRuntimePaneSections(undefined, lines)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 6 running",
          "Outcome in_progress / fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Runtime 18 sessions | 2 runs | 1 active runs",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 18 sessions | 0 claims | 0 active claims | 0 acked claims",
          "Runs 2 runs | 1 active runs",
          "Context 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
          "Activity Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=2  ActiveRuns=1",
          "Artifacts Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 6 running",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 1/2 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Checks tsc ok; cycle_acceptance fail",
          "Summary tsc=ok | cycle_acceptance=fail",
        ],
      },
    ]);
  });

  test("does not let authority-only placeholder previews suppress raw runtime transcript fallback", () => {
    const lines: TranscriptLine[] = [
      {id: "1", kind: "system", text: "Runtime snapshot loading..."},
      {id: "2", kind: "assistant", text: "Awaiting first runtime refresh."},
    ];

    expect(
      buildRuntimePaneSections(
        {
          Authority: "placeholder | bridge booting | awaiting authoritative control refresh",
        },
        lines,
      ),
    ).toEqual([
      {
        title: "Runtime Snapshot",
        rows: lines.map((line) => line.text),
      },
    ]);
  });

  test("surfaces loop and verification state when typed runtime previews only carry supervisor fallback fields", () => {
    const preview: TabPreview = {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "3 sessions | 4 claims | 1 active claims | 1 acked claims",
      "Run state": "1 active run | 3 runs total",
      "Context state": "5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
      "Runtime activity": "Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
      "Artifact state": "Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
      "Loop state": "cycle 9 running",
      "Active task": "wire runtime payloads",
      "Task progress": "0 done, 1 pending of 1",
      "Loop decision": "continue required",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Last result": "in_progress / pass",
      "Verification status": "ok",
      "Verification summary": "ok",
      "Runtime freshness": "cycle 9 running | updated 2026-04-02T00:00:00Z | verify ok",
      "Control pulse preview": "fresh | in_progress / pass | cycle 9 running | updated 2026-04-02T00:00:00Z | verify ok",
      "Next task": "ship it",
      Updated: "2026-04-02T00:00:00Z",
      "Durable state": "/tmp/durable",
    };

    expect(buildRuntimePaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 running | 0 done, 1 pending of 1 | wire runtime payloads",
          "Outcome in_progress / pass",
          "Pulse fresh | in_progress / pass | cycle 9 running | updated 2026-04-02T00:00:00Z | verify ok",
          "Verification ok",
          "Freshness fresh",
          "Runtime 3 sessions | 1 runs | 1 active runs | 1 active claims",
          "Context 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
          "Decision continue required | ship it",
          "State /tmp/durable",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 3 sessions | 4 claims | 1 active claims | 1 acked claims",
          "Runs 1 active run | 3 runs total",
          "Context 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
          "Activity Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
          "Artifacts Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 9 running",
          "Task wire runtime payloads | 0 done, 1 pending of 1",
          "Outcome in_progress | accept pass",
          "Verify ok",
          "Freshness fresh",
          "Decision continue required",
          "Updated 2026-04-02T00:00:00Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification ok",
          "Freshness fresh",
          "Receipt /tmp/durable/verification.json",
          "Status ok",
          "Summary ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /tmp/durable",
          "Receipt /tmp/durable/verification.json",
          "Pulse fresh | in_progress / pass | cycle 9 running | updated 2026-04-02T00:00:00Z | verify ok",
        ],
      },
      {
        title: "Next",
        rows: ["Decision continue required | ship it", "Task ship it"],
      },
    ]);
  });

  test("prefers derived verification detail over generic placeholder labels when checks are available", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 9 running",
      "Verification status": "passing",
      "Verification summary": "ok",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification passing": "ok",
      "Verification failing": "fail",
      "Verification bundle": "ok",
      "Last result": "in_progress / fail",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 running",
          "Outcome in_progress / fail",
          "Pulse in_progress / fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 9 running",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
    ]);
  });

  test("derives verification detail from an explicit verification bundle when checks are absent", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 9 running",
      "Verification summary": "ok",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Last result": "in_progress / fail",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 running",
          "Outcome in_progress / fail",
          "Pulse in_progress / fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 9 running",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
    ]);
  });

  test("derives verification bundle detail from explicit passing and failing rows when summary stays generic", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 9 running",
      "Verification summary": "ok",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Last result": "in_progress / fail",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 running",
          "Outcome in_progress / fail",
          "Pulse in_progress / fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 9 running",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
    ]);
  });

  test("shows runtime summary fallback when the control preview lacks detailed runtime rows", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 9 running",
      "Verification summary": "tsc=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; cycle_acceptance ok",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 3 sessions | 1 claims | 1 active claims | 1 acked claims | 1 active run | 3 runs total | 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 running",
          "Verification all 2 checks passing",
          "Runtime /Users/dhyana/.dharma/state/runtime.db | 3 sessions | 1 claims | 1 active claims | 1 acked claims | 1 active run | 3 runs total | 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
        ],
      },
      {
        title: "Loop",
        rows: ["State cycle 9 running", "Verify all 2 checks passing"],
      },
      {
        title: "Runtime",
        rows: [
          "Summary /Users/dhyana/.dharma/state/runtime.db | 3 sessions | 1 claims | 1 active claims | 1 acked claims | 1 active run | 3 runs total | 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification all 2 checks passing",
          "Status all 2 checks passing",
          "Passing tsc, cycle_acceptance",
          "Checks tsc ok; cycle_acceptance ok",
          "Summary tsc=ok | cycle_acceptance=ok",
        ],
      },
    ]);
  });

  test("derives loop and verification rows from compact freshness fields when explicit control rows are missing", () => {
    const preview: TabPreview = {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
      "Artifact state": "Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
      "Control pulse preview":
        "fresh | in_progress / fail | cycle 9 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime freshness":
        "cycle 9 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Durable state": "/tmp/durable",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 waiting_for_verification",
          "Outcome in_progress / fail",
          "Pulse fresh | in_progress / fail | cycle 9 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Runtime 3 sessions | 1 runs | 1 active runs | 1 active claims",
          "Context 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
          "State /tmp/durable",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 9 waiting_for_verification",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-02T00:00:00Z",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 3 sessions | 4 claims | 1 active claims | 1 acked claims",
          "Runs 1 runs | 1 active runs",
          "Context 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
          "Activity Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
          "Artifacts Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-02T00:00:00Z",
          "Receipt /tmp/durable/verification.json | updated 2026-04-02T00:00:00Z",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /tmp/durable",
          "Receipt /tmp/durable/verification.json | updated 2026-04-02T00:00:00Z",
          "Pulse fresh | in_progress / fail | cycle 9 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        ],
      },
    ]);

    expect(buildRuntimePaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 9 waiting_for_verification",
          "Outcome in_progress / fail",
          "Pulse fresh | in_progress / fail | cycle 9 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Runtime 3 sessions | 1 runs | 1 active runs | 1 active claims",
          "Context 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
          "State /tmp/durable",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "DB /Users/dhyana/.dharma/state/runtime.db",
          "Sessions 3 sessions | 4 claims | 1 active claims | 1 acked claims",
          "Runs 1 runs | 1 active runs",
          "Context 5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
          "Activity Sessions=3 Runs=1 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
          "Artifacts Artifacts=5 PromotedFacts=2 ContextBundles=2 OperatorActions=6",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 9 waiting_for_verification",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-02T00:00:00Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-02T00:00:00Z",
          "Receipt /tmp/durable/verification.json | updated 2026-04-02T00:00:00Z",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
      {
        title: "Durability",
        rows: [
          "State /tmp/durable",
          "Receipt /tmp/durable/verification.json | updated 2026-04-02T00:00:00Z",
          "Pulse fresh | in_progress / fail | cycle 9 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        ],
      },
    ]);
  });

  test("treats compact supervisor pulse previews as structured control state before detailed rows arrive", () => {
    const preview: TabPreview = {
      "Control pulse preview":
        "fresh | in_progress / fail | cycle 11 waiting_for_verification | updated 2026-04-03T00:20:45Z | verify tsc=ok | cycle_acceptance=fail",
      "Runtime freshness": "cycle 11 waiting_for_verification | updated 2026-04-03T00:20:45Z | verify tsc=ok | cycle_acceptance=fail",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 11 waiting_for_verification",
          "Outcome in_progress / fail",
          "Pulse fresh | in_progress / fail | cycle 11 waiting_for_verification | updated 2026-04-03T00:20:45Z | verify tsc=ok | cycle_acceptance=fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness fresh",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 11 waiting_for_verification",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T00:20:45Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T00:20:45Z",
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Checks tsc ok; cycle_acceptance fail",
          "Summary tsc=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
    ]);

    expect(buildRuntimePaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 11 waiting_for_verification",
          "Outcome in_progress / fail",
          "Pulse fresh | in_progress / fail | cycle 11 waiting_for_verification | updated 2026-04-03T00:20:45Z | verify tsc=ok | cycle_acceptance=fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness fresh",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 11 waiting_for_verification",
          "Outcome in_progress | accept fail",
          "Verify 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T00:20:45Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T00:20:45Z",
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Checks tsc ok; cycle_acceptance fail",
          "Summary tsc=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
        ],
      },
    ]);
  });

  test("treats compact supervisor pulse transcript lines as structured control state before hydration finishes", () => {
    const lines: TranscriptLine[] = [
      {
        id: "1",
        kind: "system",
        text:
          "Control pulse preview: fresh | in_progress / pass | cycle 12 running | updated 2026-04-03T01:00:00Z | verify tsc=ok | bridge_snapshots=ok",
      },
      {
        id: "2",
        kind: "system",
        text: "Runtime freshness: cycle 12 running | updated 2026-04-03T01:00:00Z | verify tsc=ok | bridge_snapshots=ok",
      },
    ];

    expect(buildControlPaneSections(undefined, lines)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 12 running",
          "Outcome in_progress / pass",
          "Pulse fresh | in_progress / pass | cycle 12 running | updated 2026-04-03T01:00:00Z | verify tsc=ok | bridge_snapshots=ok",
          "Verification all 2 checks passing",
          "Freshness fresh",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 12 running",
          "Outcome in_progress | accept pass",
          "Verify all 2 checks passing",
          "Freshness fresh",
          "Updated 2026-04-03T01:00:00Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification all 2 checks passing",
          "Freshness fresh",
          "Updated 2026-04-03T01:00:00Z",
          "Status all 2 checks passing",
          "Passing tsc, bridge_snapshots",
          "Checks tsc ok; bridge_snapshots ok",
          "Summary tsc=ok | bridge_snapshots=ok",
          "Last in_progress / pass",
        ],
      },
    ]);
  });

  test("derives control and runtime sections from pulse and metrics when stored fields are only unknown placeholders", () => {
    const preview: TabPreview = {
      "Loop state": "unknown",
      "Result status": "unknown",
      Acceptance: "unknown",
      "Last result": "unknown",
      Updated: "unknown",
      "Runtime freshness": "unknown",
      "Verification summary": "unknown",
      "Verification bundle": "unknown",
      "Session state": "unknown",
      "Run state": "unknown",
      "Context state": "unknown",
      "Control pulse preview":
        "fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime activity": "Sessions=5 Runs=2 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
      "Artifact state": "Artifacts=8 PromotedFacts=3 ContextBundles=2 OperatorActions=4",
    };

    expect(buildControlPaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 13 waiting_for_verification",
          "Outcome complete / fail",
          "Pulse fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Runtime 5 sessions | 2 runs | 1 active runs | 1 active claims",
          "Context 8 artifacts | 3 promoted facts | 2 context bundles | 4 operator actions",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 13 waiting_for_verification",
          "Outcome complete | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T02:00:00Z",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "Sessions 5 sessions | 4 claims | 1 active claims | 1 acked claims",
          "Runs 2 runs | 1 active runs",
          "Context 8 artifacts | 3 promoted facts | 2 context bundles | 4 operator actions",
          "Activity Sessions=5 Runs=2 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
          "Artifacts Artifacts=8 PromotedFacts=3 ContextBundles=2 OperatorActions=4",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T02:00:00Z",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last complete / fail",
        ],
      },
    ]);

    expect(buildRuntimePaneSections(preview)).toEqual([
      {
        title: "Overview",
        rows: [
          "Loop cycle 13 waiting_for_verification",
          "Outcome complete / fail",
          "Pulse fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Runtime 5 sessions | 2 runs | 1 active runs | 1 active claims",
          "Context 8 artifacts | 3 promoted facts | 2 context bundles | 4 operator actions",
        ],
      },
      {
        title: "Runtime",
        rows: [
          "Sessions 5 sessions | 4 claims | 1 active claims | 1 acked claims",
          "Runs 2 runs | 1 active runs",
          "Context 8 artifacts | 3 promoted facts | 2 context bundles | 4 operator actions",
          "Activity Sessions=5 Runs=2 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
          "Artifacts Artifacts=8 PromotedFacts=3 ContextBundles=2 OperatorActions=4",
        ],
      },
      {
        title: "Loop",
        rows: [
          "State cycle 13 waiting_for_verification",
          "Outcome complete | accept fail",
          "Verify 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T02:00:00Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
          "Freshness fresh",
          "Updated 2026-04-03T02:00:00Z",
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Checks tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Last complete / fail",
        ],
      },
    ]);
  });

  test("builds operator signal rows for control and runtime modes from live verification and loop state", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 9 waiting_for_verification",
      "Active task": "terminal-control-surface",
      "Task progress": "2 done, 1 pending of 3",
      "Loop decision": "continue required",
      Updated: "2026-04-02T00:00:00Z",
      "Next task": "Refresh verification cards from durable state.",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification receipt": "/tmp/durable/verification.json",
      "Verification updated": "2026-04-02T00:05:00Z",
      "Runtime summary": "/Users/dhyana/.dharma/state/runtime.db | 3 sessions | 1 active run",
      "Durable state": "/tmp/durable",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 9 waiting_for_verification | continue required | 2026-04-02T00:00:00Z", tone: "strong"},
      {value: "Verification 1 failing, 2/3 passing | failing cycle_acceptance | updated 2026-04-02T00:05:00Z", tone: "warning"},
      {
        value: "Task terminal-control-surface | 2 done, 1 pending of 3 | Next Refresh verification cards from durable state.",
        tone: "muted",
      },
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
    ]);

    expect(buildOperatorSignalRows("runtime", preview)).toEqual([
      {value: "Loop cycle 9 waiting_for_verification | continue required | 2026-04-02T00:00:00Z", tone: "strong"},
      {value: "Verification 1 failing, 2/3 passing | failing cycle_acceptance | updated 2026-04-02T00:05:00Z", tone: "warning"},
      {value: "Runtime /Users/dhyana/.dharma/state/runtime.db | 3 sessions | 1 active run", tone: "muted"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
      {
        value: "Task terminal-control-surface | 2 done, 1 pending of 3 | Next Refresh verification cards from durable state.",
        tone: "muted",
      },
    ]);
  });

  test("renders runtime signal detail in the compact runtime pane without falling back to placeholder counts", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 12 waiting_for_verification",
      "Loop decision": "continue required",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
      "Runtime activity": "Sessions=22 Runs=3 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
      "Active task": "terminal-control-surface",
      "Task progress": "0 done, 1 pending of 1",
      "Next task": "Refresh verification cards from durable state.",
      "Durable state": "/tmp/durable",
      Updated: "2026-04-04T00:12:56Z",
    };

    const pane = ControlPane({
      title: "Runtime",
      mode: "runtime",
      preview,
      lines: [],
      windowSize: 24,
    });
    const visibleText = flattenElementText(pane).join("\n");

    expect(visibleText).toContain("Runtime Signal");
    expect(visibleText).toContain("Loop cycle 12 waiting_for_verification | continue required | 2026-04-04T00:12:56Z");
    expect(visibleText).toContain("Verification 1 failing, 3/4 passing | failing cycle_acceptance | updated 2026-04-04T00:12:56Z");
    expect(visibleText).toContain("Runtime 22 sessions | 3 runs | 1 active runs | 1 active claims");
    expect(visibleText).toContain("Receipt /tmp/durable/verification.json | State /tmp/durable");
    expect(visibleText).toContain("Task terminal-control-surface | 0 done, 1 pending of 1 | Next Refresh verification cards from durable state.");
  });

  test("threads the durable verification receipt into control and runtime signal context rows", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 12 waiting_for_verification",
      "Loop decision": "continue required",
      Updated: "2026-04-03T03:00:00Z",
      "Verification summary": "tsc=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; cycle_acceptance ok",
      "Verification receipt": "/tmp/durable/verification.json",
      "Next task": "Persist pane-ready verification receipts.",
      "Durable state": "/tmp/durable",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 12 waiting_for_verification | continue required | 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Next Persist pane-ready verification receipts.", tone: "muted"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
    ]);

    expect(buildOperatorSignalRows("runtime", preview)).toEqual([
      {value: "Loop cycle 12 waiting_for_verification | continue required | 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
      {value: "Task Persist pane-ready verification receipts.", tone: "muted"},
    ]);
  });

  test("derives verification updated signal rows from compact runtime freshness when explicit timestamps are absent", () => {
    const preview: TabPreview = {
      "Loop state": "unknown",
      Updated: "unknown",
      "Verification summary": "unknown",
      "Verification bundle": "unknown",
      "Control pulse preview":
        "fresh | complete / fail | cycle 13 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 13 waiting_for_verification | 2026-04-03T02:00:00Z", tone: "strong"},
      {value: "Verification 1 failing, 2/3 passing | failing cycle_acceptance | updated 2026-04-03T02:00:00Z", tone: "warning"},
      {value: "Freshness fresh", tone: "muted"},
    ]);
  });

  test("derives the verification receipt in signal rows from durable state when the receipt field is absent", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 12 waiting_for_verification",
      "Loop decision": "continue required",
      Updated: "2026-04-03T03:00:00Z",
      "Verification summary": "tsc=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; cycle_acceptance ok",
      "Next task": "Persist pane-ready verification receipts.",
      "Durable state": "/tmp/durable",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 12 waiting_for_verification | continue required | 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Next Persist pane-ready verification receipts.", tone: "muted"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
    ]);

    expect(buildOperatorSignalRows("runtime", preview)).toEqual([
      {value: "Loop cycle 12 waiting_for_verification | continue required | 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
      {value: "Task Persist pane-ready verification receipts.", tone: "muted"},
    ]);
  });

  test("derives compact runtime signal rows from detailed runtime state when aggregate summaries are absent", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 10 running",
      "Loop decision": "continue required",
      Updated: "2026-04-03T02:16:08Z",
      "Verification summary": "tsc=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; cycle_acceptance ok",
      "Session state": "3 sessions | 4 claims | 1 active claims | 1 acked claims",
      "Run state": "1 active run | 3 runs total",
      "Context state": "5 artifacts | 2 promoted facts | 2 context bundles | 6 operator actions",
      "Runtime activity": "unknown",
      "Runtime summary": "unknown",
      "Durable state": "/tmp/durable",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 10 running | continue required | 2026-04-03T02:16:08Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T02:16:08Z", tone: "strong"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
      {value: "Runtime 3 sessions | 1 active run | 5 artifacts", tone: "muted"},
    ]);
  });

  test("combines next task and durable state in signal rows so neither falls off the control surface", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 12 waiting_for_verification",
      "Loop decision": "continue required",
      Updated: "2026-04-03T03:00:00Z",
      "Verification summary": "tsc=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; cycle_acceptance ok",
      "Next task": "Persist pane-ready verification receipts.",
      "Durable state": "/tmp/durable",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 12 waiting_for_verification | continue required | 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Next Persist pane-ready verification receipts.", tone: "muted"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
    ]);

    expect(buildOperatorSignalRows("runtime", preview)).toEqual([
      {value: "Loop cycle 12 waiting_for_verification | continue required | 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Verification all 2 checks passing | updated 2026-04-03T03:00:00Z", tone: "strong"},
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
      {value: "Task Persist pane-ready verification receipts.", tone: "muted"},
    ]);
  });

  test("prioritizes the active task summary ahead of runtime context in the control signal band", () => {
    const preview: TabPreview = {
      "Loop state": "cycle 13 running_cycle",
      "Active task": "terminal-control-surface",
      "Task progress": "2 done, 1 pending of 3",
      "Loop decision": "continue required",
      Updated: "2026-04-03T17:04:59.195465+00:00",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Runtime summary": "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 active runs",
      "Next task":
        "Add a focused live-bridge regression for sparse pending runtime snapshots so metadata-light `/runtime` completions are verified through the same pending-command fallback path.",
      "Durable state": "/tmp/durable",
    };

    expect(buildOperatorSignalRows("control", preview)).toEqual([
      {value: "Loop cycle 13 running_cycle | continue required | 2026-04-03T17:04:59.195465+00:00", tone: "strong"},
      {value: "Verification all 4 checks passing | updated 2026-04-03T17:04:59.195465+00:00", tone: "strong"},
      {
        value:
          "Task terminal-control-surface | 2 done, 1 pending of 3 | Next Add a focused live-bridge regression for sparse pending runtime snapshots so metadata-light `/runtime` completions are verified through the same pending-command fallback path.",
        tone: "muted",
      },
      {value: "Receipt /tmp/durable/verification.json | State /tmp/durable", tone: "muted"},
    ]);
  });
});
