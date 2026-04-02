import {describe, expect, test} from "bun:test";

import {buildControlPaneSections, buildRuntimePaneSections} from "../src/components/ControlPane";
import type {TabPreview, TranscriptLine} from "../src/types";

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
          "Status all 4 checks passing",
          "Passing tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
          "Summary tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Bundle tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Next",
        rows: ["Task Promote runtime snapshot rows into a dedicated runtime pane."],
      },
    ]);
  });

  test("shows authority state when control preview is still a placeholder", () => {
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
      "Authority placeholder | bridge offline | awaiting authoritative control refresh",
    );
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
          "Decision continue required",
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
          "Status all 2 checks passing",
          "Passing tsc, cycle_acceptance",
          "Summary tsc=ok | cycle_acceptance=ok",
          "Bundle tsc=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Next",
        rows: [],
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
          "Decision continue required",
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
          "Status all 2 checks passing",
          "Passing tsc, cycle_acceptance",
          "Summary tsc=ok | cycle_acceptance=ok",
          "Bundle tsc=ok | cycle_acceptance=ok",
        ],
      },
      {
        title: "Next",
        rows: [],
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
          "Pulse in_progress / fail | cycle 6 running | updated unknown | verify tsc=ok | cycle_acceptance=fail",
          "Verification 1 failing, 1/2 passing | failing cycle_acceptance",
          "Runtime 18 sessions | 1 runs | 1 active runs",
          "State /tmp/state",
        ],
      },
      {
        title: "Loop",
        rows: ["State cycle 6 running"],
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
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Summary tsc=ok | cycle_acceptance=fail",
          "Bundle tsc=ok | cycle_acceptance=fail",
          "Last in_progress / fail",
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
          "Decision continue required",
          "Updated 2026-04-01T03:44:29Z",
        ],
      },
      {
        title: "Verification",
        rows: [
          "Status all 4 checks passing",
          "Passing tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
          "Bundle tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Summary tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
          "Last in_progress / pass",
        ],
      },
      {
        title: "Next",
        rows: [
          "Task Promote runtime snapshot rows into a dedicated runtime pane.",
          "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
        ],
      },
    ]);
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
        rows: ["State cycle 6 running", "Outcome in_progress | accept fail"],
      },
      {
        title: "Verification",
        rows: [
          "Status 1 failing, 1/2 passing",
          "Passing tsc",
          "Failing cycle_acceptance",
          "Bundle tsc=ok | cycle_acceptance=fail",
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
          "Decision continue required",
          "Updated 2026-04-02T00:00:00Z",
        ],
      },
      {
        title: "Verification",
        rows: ["Status ok", "Summary ok", "Last in_progress / pass"],
      },
      {
        title: "Next",
        rows: ["Task ship it", "State /tmp/durable"],
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
          "Pulse in_progress / fail",
          "Verification 1 failing, 2/3 passing | failing cycle_acceptance",
        ],
      },
      {
        title: "Loop",
        rows: ["State cycle 9 running"],
      },
      {
        title: "Verification",
        rows: [
          "Status 1 failing, 2/3 passing",
          "Passing tsc, bridge_snapshots",
          "Failing cycle_acceptance",
          "Summary tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          "Bundle tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
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
        rows: ["State cycle 9 running"],
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
          "Status all 2 checks passing",
          "Passing tsc, cycle_acceptance",
          "Summary tsc=ok | cycle_acceptance=ok",
          "Bundle tsc=ok | cycle_acceptance=ok",
        ],
      },
    ]);
  });
});
