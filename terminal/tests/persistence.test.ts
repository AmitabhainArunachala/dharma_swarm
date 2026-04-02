import {afterEach, describe, expect, test} from "bun:test";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  loadSupervisorControlPreview,
  loadSupervisorControlState,
  loadSupervisorRepoPreview,
  saveSupervisorControlSummary,
  saveSupervisorRepoPreview,
} from "../src/persistence";

const TEMP_DIRS: string[] = [];

afterEach(() => {
  delete process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR;
  delete process.env.DHARMA_TERMINAL_STATE_DIR;
  while (TEMP_DIRS.length > 0) {
    rmSync(TEMP_DIRS.pop() ?? "", {force: true, recursive: true});
  }
});

function makeStateDir(): string {
  const root = mkdtempSync(path.join(os.tmpdir(), "dharma-terminal-"));
  TEMP_DIRS.push(root);
  const stateDir = path.join(root, "state");
  mkdirSync(stateDir, {recursive: true});
  writeFileSync(
    path.join(stateDir, "run.json"),
    JSON.stringify(
      {
        repo_root: "/Users/dhyana/dharma_swarm",
        updated_at: "2026-03-31T22:46:35.466340+00:00",
        cycle: 3,
        status: "running",
        tasks_total: 3,
        tasks_pending: 1,
        last_task_id: "terminal-control-surface",
        last_continue_required: false,
        last_summary_fields: {
          status: "in_progress",
          acceptance: "pass",
          next_task: "Split /runtime and /dashboard control actions into dedicated pane routes.",
        },
      },
      null,
      2,
    ),
  );
  writeFileSync(
    path.join(stateDir, "verification.json"),
    JSON.stringify(
      {
        summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
        continue_required: false,
        checks: [
          {name: "tsc", ok: true},
          {name: "py_compile_bridge", ok: true},
          {name: "bridge_snapshots", ok: true},
          {name: "cycle_acceptance", ok: true},
        ],
      },
      null,
      2,
    ),
  );
  return stateDir;
}

describe("supervisor control persistence", () => {
  test("loads loop and verification state from the explicit durable state dir", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    expect(summary?.stateDir).toBe(stateDir);
    expect(summary?.cycle).toBe(3);
    expect(summary?.runStatus).toBe("running");
    expect(summary?.activeTaskId).toBe("terminal-control-surface");
    expect(summary?.verificationSummary).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(summary?.verificationChecks).toEqual([
      "tsc ok",
      "py_compile_bridge ok",
      "bridge_snapshots ok",
      "cycle_acceptance ok",
    ]);
  });

  test("writes a compact operator control summary back into durable state", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!);

    const outputPath = path.join(stateDir, "terminal-control-summary.json");
    expect(existsSync(outputPath)).toBe(true);

    const payload = JSON.parse(readFileSync(outputPath, "utf8")) as Record<string, unknown>;
    expect(payload.verification_summary).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(payload.verification_bundle).toEqual([
      {name: "tsc", ok: true},
      {name: "py_compile_bridge", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: true},
    ]);
    expect(payload.verification_status).toBe("all 4 checks passing");
    expect(payload.verification_passing).toBe("tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance");
    expect(payload.verification_failing).toBe("none");
    expect(payload.preview_Verification_status).toBe("all 4 checks passing");
    expect(payload.preview_Verification_passing).toBe("tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance");
    expect(payload.preview_Verification_failing).toBe("none");
    expect(payload.preview_Runtime_freshness).toBe(
      "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(payload.preview_Control_pulse_preview).toBe(
      "stale | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(payload.active_task_id).toBe("terminal-control-surface");
    expect(payload.run_status).toBe("running");

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(verification.summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok");
    expect(verification.continue_required).toBe(false);
    expect(verification.checks).toEqual([
      {name: "tsc", ok: true},
      {name: "py_compile_bridge", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: true},
    ]);
  });

  test("mirrors normalized verification detail back into verification.json without dropping existing check metadata", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "verification.json"),
      JSON.stringify(
        {
          summary: "passing",
          continue_required: false,
          checks: [
            {name: "tsc", ok: true, rc: 0, preview: ""},
            {name: "py_compile_bridge", ok: true, rc: 0, preview: ""},
            {name: "bridge_snapshots", ok: true, rc: 0, preview: "ready"},
            {name: "cycle_acceptance", ok: true, rc: 0, preview: "old"},
          ],
        },
        null,
        2,
      ),
    );
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Verification summary": "ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "passing",
      "Verification passing": "passing",
      "Verification failing": "none",
      "Verification bundle": "ok",
    });

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(verification.summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(verification.continue_required).toBe(false);
    expect(verification.checks).toEqual([
      {name: "tsc", ok: true, rc: 0, preview: ""},
      {name: "py_compile_bridge", ok: true, rc: 0, preview: ""},
      {name: "bridge_snapshots", ok: true, rc: 0, preview: "ready"},
      {name: "cycle_acceptance", ok: false, rc: 0, preview: "old"},
    ]);
  });

  test("round-trips the richer control preview through durable state", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
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
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Active task": "terminal-control-surface",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Last result": "in_progress / pass",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Verification status": "all 4 checks passing",
      "Verification passing": "tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
      "Verification failing": "none",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Durable state": stateDir,
    });

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toEqual({
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
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Active task": "terminal-control-surface",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Last result": "in_progress / pass",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Verification status": "all 4 checks passing",
      "Verification passing": "tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
      "Verification failing": "none",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Durable state": stateDir,
    });
  });

  test("derives the runtime summary fallback for older stored control previews", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "terminal-control-summary.json"),
      JSON.stringify(
        {
          preview_Runtime_DB: "/Users/dhyana/.dharma/state/runtime.db",
          preview_Session_state: "18 sessions | 0 claims | 0 active claims | 0 acked claims",
          preview_Run_state: "0 runs | 0 active runs",
          preview_Context_state: "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))?.["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
    );
    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))?.["Control pulse preview"]).toBe(
      "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
  });

  test("promotes live preview verification fields into the durable summary payload", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.verification_checks).toEqual(["tsc ok", "bridge_snapshots ok", "cycle_acceptance fail"]);
    expect(payload.verification_bundle).toEqual([
      {name: "tsc", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: false},
    ]);
    expect(payload.verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.verification_passing).toBe("tsc, bridge_snapshots");
    expect(payload.verification_failing).toBe("cycle_acceptance");
    expect(payload.preview_Verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
  });

  test("normalizes generic verification placeholders into the detailed durable summary when checks exist", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Verification summary": "ok",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "passing",
      "Verification passing": "ok",
      "Verification failing": "fail",
      "Verification bundle": "ok",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.verification_passing).toBe("tsc, bridge_snapshots");
    expect(payload.verification_failing).toBe("cycle_acceptance");
    expect(payload.preview_Verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.preview_Verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.preview_Verification_passing).toBe("tsc, bridge_snapshots");
    expect(payload.preview_Verification_failing).toBe("cycle_acceptance");
    expect(payload.preview_Verification_bundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
  });

  test("normalizes stored generic verification preview fields when loading the control pane boot preview", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "terminal-control-summary.json"),
      JSON.stringify(
        {
          preview_Verification_summary: "ok",
          preview_Verification_checks: "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
          preview_Verification_status: "passing",
          preview_Verification_passing: "ok",
          preview_Verification_failing: "fail",
          preview_Verification_bundle: "ok",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm")).toMatchObject({
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
  });

  test("writes a derived runtime summary into durable state when only component fields are provided", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Runtime_summary).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
    );
  });

  test("replaces a stored placeholder runtime summary when richer runtime rows arrive", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime summary": "/Users/dhyana/.dharma/state/runtime.db | none | none | none",
    });

    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "20 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 active runs | 0 runs total",
      "Context state": "0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Runtime_summary).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );
    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm")?.["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );
  });

  test("preserves stored runtime component rows when a later control refresh only updates loop and verification state", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Last result": "in_progress / pass",
      Updated: "2026-03-31T22:46:35.466340+00:00",
    });

    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 4 running",
      "Task progress": "3 done, 0 pending of 3",
      "Last result": "complete / pass",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Verification status": "all 4 checks passing",
      "Verification passing": "tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
      "Verification failing": "none",
      Updated: "2026-04-01T00:00:00Z",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Runtime_DB).toBe("/Users/dhyana/.dharma/state/runtime.db");
    expect(payload.preview_Session_state).toBe("18 sessions | 0 claims | 0 active claims | 0 acked claims");
    expect(payload.preview_Run_state).toBe("0 runs | 0 active runs");
    expect(payload.preview_Context_state).toBe("7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions");
    expect(payload.preview_Runtime_summary).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
    );
    expect(payload.preview_Control_pulse_preview).toBe(
      "stale | complete / pass | cycle 4 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))?.["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
    );
  });

  test("merges stored preview overrides with supervisor fallback fields", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    writeFileSync(
      path.join(stateDir, "terminal-control-summary.json"),
      JSON.stringify(
        {
          preview_Runtime_DB: "/Users/dhyana/.dharma/state/runtime.db",
          preview_Runtime_activity: "Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
          preview_Artifact_state: "Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
          preview_Recent_operator_actions: "reroute by operator (better frontier model)",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toEqual({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state": "Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      "Recent operator actions": "reroute by operator (better frontier model)",
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Active task": "terminal-control-surface",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Last result": "in_progress / pass",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Verification status": "all 4 checks passing",
      "Verification passing": "tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance",
      "Verification failing": "none",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | none | none | none",
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Durable state": stateDir,
    });
  });

  test("round-trips repo preview fields through durable state without leaking control keys", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Loop state": "cycle 3 running",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      Upstream: "origin/main",
      Ahead: "0",
      Behind: "0",
      "Branch status": "tracking origin/main in sync",
      Sync: "origin/main | ahead 0 | behind 0",
      "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
      Dirty: "0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure": "high (552 local changes)",
      Staged: "0",
      Unstaged: "510",
      Untracked: "42",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Topology peer count": "2",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Changed hotspots": "terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
      "Hotspot summary": "change terminal (274); .dharma_psmv_hyperfile_branch (142)",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
      "Changed paths": "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
      "Primary file hotspot": "dgc_cli.py (6908 lines)",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      Hotspots: "dgc_cli.py (6908 lines)",
      "Inbound hotspots": "dharma_swarm.models | inbound 159",
      Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
      "Language mix": ".py: 1125; .md: 511",
    });

    expect(loadSupervisorRepoPreview()).toEqual({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      Upstream: "origin/main",
      Ahead: "0",
      Behind: "0",
      "Branch status": "tracking origin/main in sync",
      Sync: "origin/main | ahead 0 | behind 0",
      "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo/control preview":
        "stale | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
      Dirty: "0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure": "high (552 local changes)",
      Staged: "0",
      Unstaged: "510",
      Untracked: "42",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Topology peer count": "2",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
      "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Changed hotspots": "terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
      "Hotspot summary": "change terminal (274); .dharma_psmv_hyperfile_branch (142)",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
      "Changed paths": "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
      "Primary file hotspot": "dgc_cli.py (6908 lines)",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      Hotspots: "dgc_cli.py (6908 lines)",
      "Inbound hotspots": "dharma_swarm.models | inbound 159",
      Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
      "Language mix": ".py: 1125; .md: 511",
    });
    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload["preview_Repo/control_preview"]).toBe(
      "stale | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(loadSupervisorControlPreview()?.["Runtime DB"]).toBe("/Users/dhyana/.dharma/state/runtime.db");
  });

  test("persists repo alert and hotspot preview facts needed by repo and context surfaces", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      "Branch status": "tracking origin/main in sync",
      "Repo risk":
        "topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Dirty pressure": "high (552 local changes)",
      Staged: "0",
      Unstaged: "510",
      Untracked: "42",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning severity": "high",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Hotspot summary":
        "change terminal (274); .dharma_psmv_hyperfile_branch (142) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview?.["Repo/control preview"]).toBe(
      "stale | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    );
    expect(preview?.["Topology warning severity"]).toBe("high");
    expect(preview?.["Primary peer drift"]).toBe("dharma_swarm track main...origin/main");
    expect(preview?.["Hotspot summary"]).toBe(
      "change terminal (274); .dharma_psmv_hyperfile_branch (142) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    );

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Topology_warning_severity).toBe("high");
    expect(payload.preview_Primary_peer_drift).toBe("dharma_swarm track main...origin/main");
    expect(payload.preview_Hotspot_summary).toBe(
      "change terminal (274); .dharma_psmv_hyperfile_branch (142) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    );
    expect(preview?.Alerts).toBeUndefined();
  });

  test("derives missing repo preview rows from partial durable repo facts", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 3 running",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      Updated: "2026-03-31T22:46:35.466340+00:00",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      "Branch status": "tracking origin/main in sync",
      Ahead: "0",
      Behind: "0",
      "Dirty pressure": "high (552 local changes)",
      "Topology risk": "sab_canonical_repo_missing",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
    });

    expect(loadSupervisorRepoPreview()).toEqual({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      "Branch status": "tracking origin/main in sync",
      Ahead: "0",
      Behind: "0",
      "Dirty pressure": "high (552 local changes)",
      "Topology risk": "sab_canonical_repo_missing",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 (sab_canonical_repo_missing) | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Branch sync preview":
        "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo/control preview":
        "stale | task terminal-repo-pane | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
    });
  });

  test("preserves stored repo preview fields when the durable control summary refreshes later", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Hotspot summary": "change terminal (274) | paths terminal/src/protocol.ts",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts",
      "Hotspot pressure preview": "change terminal (274)",
    });
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
    });

    expect(loadSupervisorRepoPreview()).toEqual({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      "Repo/control preview":
        "stale | task terminal-control-surface | unknown | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Hotspot summary": "change terminal (274) | paths terminal/src/protocol.ts",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts",
      "Hotspot pressure preview": "change terminal (274)",
    });
    expect(loadSupervisorControlPreview()?.["Loop state"]).toBe("cycle 3 running");
  });
});
