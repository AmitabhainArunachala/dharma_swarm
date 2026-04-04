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
    expect(summary?.verificationUpdatedAt).toBe("");
    expect(summary?.verificationChecks).toEqual([
      "tsc ok",
      "py_compile_bridge ok",
      "bridge_snapshots ok",
      "cycle_acceptance ok",
    ]);
  });

  test("loads explicit verification detail rows from durable state when check arrays are absent", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "verification.json"),
      JSON.stringify(
        {
          summary: "ok",
          continue_required: true,
          status: "1 failing, 2/3 passing",
          passing: "tsc, bridge_snapshots",
          failing: "cycle_acceptance",
          bundle: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        },
        null,
        2,
      ),
    );

    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    expect(summary?.verificationSummary).toBe("ok");
    expect(summary?.verificationChecks).toEqual([]);
    expect(summary?.verificationStatus).toBe("1 failing, 2/3 passing");
    expect(summary?.verificationPassing).toBe("tsc, bridge_snapshots");
    expect(summary?.verificationFailing).toBe("cycle_acceptance");
    expect(summary?.verificationBundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
  });

  test("hydrates runtime freshness and pulse previews from detailed verification bundle when checks are absent", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "verification.json"),
      JSON.stringify(
        {
          summary: "ok",
          continue_required: true,
          status: "1 failing, 2/3 passing",
          passing: "tsc, bridge_snapshots",
          failing: "cycle_acceptance",
          bundle: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toMatchObject({
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
  });

  test("hydrates a concrete verification bundle from passing and failing rows when the durable summary stays generic", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "verification.json"),
      JSON.stringify(
        {
          summary: "ok",
          continue_required: true,
          status: "1 failing, 2/3 passing",
          passing: "tsc, bridge_snapshots",
          failing: "cycle_acceptance",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toMatchObject({
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
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
    expect(payload.preview_Verification_receipt).toBe(path.join(stateDir, "verification.json"));
    expect(payload.preview_Verification_updated).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(payload.preview_Loop_state).toBe("cycle 3 running");
    expect(payload.preview_Task_progress).toBe("2 done, 1 pending of 3");
    expect(payload.preview_Active_task).toBe("terminal-control-surface");
    expect(payload.preview_Result_status).toBe("in_progress");
    expect(payload.preview_Acceptance).toBe("pass");
    expect(payload.preview_Last_result).toBe("in_progress / pass");
    expect(payload.preview_Loop_decision).toBe("ready to stop");
    expect(payload.preview_Next_task).toBe("Split /runtime and /dashboard control actions into dedicated pane routes.");
    expect(payload.preview_Durable_state).toBe(stateDir);
    expect(typeof payload.verification_updated_at).toBe("string");
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
    expect(verification.status).toBe("all 4 checks passing");
    expect(verification.passing).toBe("tsc, py_compile_bridge, bridge_snapshots, cycle_acceptance");
    expect(verification.failing).toBe("none");
    expect(verification.bundle).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok");
    expect(verification.checks).toEqual([
      {name: "tsc", ok: true},
      {name: "py_compile_bridge", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: true},
    ]);
    expect(verification.control_preview).toMatchObject({
      "Loop state": "cycle 3 running",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Verification status": "all 4 checks passing",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "stale | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Durable state": stateDir,
    });

    const run = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    expect(run.last_control_preview).toMatchObject({
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Active task": "terminal-control-surface",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Last result": "in_progress / pass",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification status": "all 4 checks passing",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification updated": expect.any(String),
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Durable state": stateDir,
    });
  });

  test("derives the verification receipt path from an overridden durable state when the preview omits it", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 3 running",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Verification summary": "tsc=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; cycle_acceptance ok",
      "Durable state": "/tmp/alt-durable",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Durable_state).toBe("/tmp/alt-durable");
    expect(payload.preview_Verification_receipt).toBe("/tmp/alt-durable/verification.json");

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect((verification.control_preview as Record<string, unknown>)["Durable state"]).toBe("/tmp/alt-durable");
    expect((verification.control_preview as Record<string, unknown>)["Verification receipt"]).toBe(
      "/tmp/alt-durable/verification.json",
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toMatchObject({
      "Durable state": "/tmp/alt-durable",
      "Verification receipt": "/tmp/alt-durable/verification.json",
    });
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
    expect(verification.status).toBe("1 failing, 3/4 passing");
    expect(verification.passing).toBe("tsc, py_compile_bridge, bridge_snapshots");
    expect(verification.failing).toBe("cycle_acceptance");
    expect(verification.bundle).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(verification.checks).toEqual([
      {name: "tsc", ok: true, rc: 0, preview: ""},
      {name: "py_compile_bridge", ok: true, rc: 0, preview: ""},
      {name: "bridge_snapshots", ok: true, rc: 0, preview: "ready"},
      {name: "cycle_acceptance", ok: false, rc: 0, preview: "old"},
    ]);

    const run = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    expect(run.last_continue_required).toBe(false);
    expect(run.last_verification).toEqual({
      ts: expect.any(String),
      updated_at: "2026-03-31T22:46:35.466340+00:00",
      summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      continue_required: false,
      status: "1 failing, 3/4 passing",
      passing: "tsc, py_compile_bridge, bridge_snapshots",
      failing: "cycle_acceptance",
      bundle: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      checks: [
        {name: "tsc", ok: true},
        {name: "py_compile_bridge", ok: true},
        {name: "bridge_snapshots", ok: true},
        {name: "cycle_acceptance", ok: false},
      ],
    });
  });

  test("loads loop and verification preview from run.json when summary files are missing after persistence", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Runtime activity": "Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state": "Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      "Recent operator actions": "reroute by operator (better frontier model)",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });

    rmSync(path.join(stateDir, "verification.json"), {force: true});
    rmSync(path.join(stateDir, "terminal-control-summary.json"), {force: true});

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toMatchObject({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Runtime activity": "Sessions=18  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0",
      "Artifact state": "Artifacts=7  PromotedFacts=2  ContextBundles=1  OperatorActions=3",
      "Recent operator actions": "reroute by operator (better frontier model)",
      "Loop state": "cycle 3 running",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      Updated: "2026-03-31T22:46:35.466340+00:00",
      "Control pulse preview":
        "stale | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
  });

  test("prefers the persisted verification updated_at from run.json over the write timestamp when verification.json is missing", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const run = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    run.last_verification = {
      ts: "2026-04-03T02:17:00Z",
      updated_at: "2026-04-03T02:00:00Z",
      summary: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      checks: [
        {name: "tsc", ok: true},
        {name: "bridge_snapshots", ok: true},
        {name: "cycle_acceptance", ok: false},
      ],
      status: "1 failing, 2/3 passing",
      passing: "tsc, bridge_snapshots",
      failing: "cycle_acceptance",
      bundle: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      continue_required: true,
    };
    writeFileSync(path.join(stateDir, "run.json"), JSON.stringify(run, null, 2));
    rmSync(path.join(stateDir, "verification.json"), {force: true});

    const summary = loadSupervisorControlState();
    const preview = loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-03T04:00:00Z"));

    expect(summary?.verificationUpdatedAt).toBe("2026-04-03T02:00:00Z");
    expect(preview?.["Verification updated"]).toBe("2026-04-03T02:00:00Z");
    expect(preview?.["Runtime freshness"]).toBe(
      "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(preview?.["Control pulse preview"]).toBe(
      "stale | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
  });

  test("hydrates control preview from verification receipt when run preview only has generic placeholders", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Loop decision": "continue required",
      "Next task": "Refresh pane-ready verification receipts.",
    });

    const run = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    delete run.last_control_preview;
    run.last_summary_fields = {
      status: "unknown",
      acceptance: "unknown",
      next_task: "none",
    };
    run.last_verification = {
      ts: "2026-04-03T02:17:00Z",
      summary: "ok",
      status: "passing",
      passing: "passing",
      failing: "none",
      bundle: "ok",
      checks: [],
      continue_required: false,
    };
    writeFileSync(path.join(stateDir, "run.json"), JSON.stringify(run, null, 2));
    rmSync(path.join(stateDir, "terminal-control-summary.json"), {force: true});

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toMatchObject({
      "Loop state": "cycle 3 running",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Control pulse preview":
        "stale | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Next task": "Refresh pane-ready verification receipts.",
      "Durable state": stateDir,
    });
  });

  test("prefers run loop-decision state over stale verification metadata when loading control state", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "run.json"),
      JSON.stringify(
        {
          repo_root: "/Users/dhyana/dharma_swarm",
          updated_at: "2026-04-02T12:00:00Z",
          cycle: 3,
          status: "running",
          tasks_total: 3,
          tasks_pending: 1,
          last_task_id: "terminal-control-surface",
          last_continue_required: true,
          last_summary_fields: {
            status: "in_progress",
            acceptance: "pass",
            next_task: "Keep the verification card aligned with cycle state.",
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

    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    expect(summary?.continueRequired).toBe(true);
    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm")?.["Loop decision"]).toBe("continue required");
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
      "Verification updated": "2026-03-31T22:46:35.466340+00:00",
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control truth preview":
        "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next Split /runtime and /dashboard control actions into dedicated pane routes.",
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
      "Verification receipt": path.join(stateDir, "verification.json"),
      "Verification updated": expect.any(String),
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control truth preview":
        "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next Split /runtime and /dashboard control actions into dedicated pane routes.",
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
    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))?.["Control truth preview"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next Split /runtime and /dashboard control actions into dedicated pane routes.",
    );
  });

  test("rebuilds stale control truth preview rows from normalized next-task state on load", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const run = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    run.last_control_preview = {
      "Loop state": "cycle 3 running",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control truth preview":
        "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next none",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
    };
    writeFileSync(path.join(stateDir, "run.json"), JSON.stringify(run, null, 2));

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))?.["Control truth preview"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next Split /runtime and /dashboard control actions into dedicated pane routes.",
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

  test("rewrites stale control truth preview text when persisting normalized control state", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 3 running",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance ok",
      "Control truth preview":
        "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next none",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Control_truth_preview).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next Split /runtime and /dashboard control actions into dedicated pane routes.",
    );
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

  test("promotes an explicit verification bundle into durable summary fields when checks are absent", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Verification summary": "ok",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.verification_checks).toEqual(["tsc ok", "bridge_snapshots ok", "cycle_acceptance fail"]);
    expect(payload.verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.verification_passing).toBe("tsc, bridge_snapshots");
    expect(payload.verification_failing).toBe("cycle_acceptance");
    expect(payload.preview_Verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.preview_Verification_bundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(verification.summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(verification.checks).toEqual([
      {name: "tsc", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: false},
    ]);
  });

  test("writes normalized control and verification receipts from a compact repo/control preview", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Repo/control preview":
        "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision continue required | cycle 7 waiting_for_verification | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next persist pane-ready verification receipts",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Active_task).toBe("terminal-control-surface");
    expect(payload.preview_Task_progress).toBe("2 done, 1 pending of 3");
    expect(payload.preview_Loop_state).toBe("cycle 7 waiting_for_verification");
    expect(payload.preview_Result_status).toBe("in_progress");
    expect(payload.preview_Acceptance).toBe("pass");
    expect(payload.preview_Verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.preview_Verification_checks).toBe("tsc ok; bridge_snapshots ok; cycle_acceptance fail");
    expect(payload.preview_Verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.preview_Verification_bundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.preview_Runtime_DB).toBe("/Users/dhyana/.dharma/state/runtime.db");
    expect(payload.verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.verification_passing).toBe("tsc, bridge_snapshots");
    expect(payload.verification_failing).toBe("cycle_acceptance");

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(verification.summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(verification.status).toBe("1 failing, 2/3 passing");
    expect(verification.bundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
  });

  test("derives loop and verification detail from compact pulse fields before writing durable state", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Control pulse preview":
        "fresh | complete / fail | cycle 8 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime freshness":
        "cycle 8 waiting_for_verification | updated 2026-04-02T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Durable state": "/tmp/compact-durable",
    });

    const payload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(payload.preview_Loop_state).toBe("cycle 8 waiting_for_verification");
    expect(payload.preview_Updated).toBe("2026-04-02T00:00:00Z");
    expect(payload.preview_Last_result).toBe("complete / fail");
    expect(payload.verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.verification_checks).toEqual(["tsc ok", "bridge_snapshots ok", "cycle_acceptance fail"]);
    expect(payload.verification_status).toBe("1 failing, 2/3 passing");
    expect(payload.verification_passing).toBe("tsc, bridge_snapshots");
    expect(payload.verification_failing).toBe("cycle_acceptance");
    expect(payload.verification_updated_at).toBe("2026-04-02T00:00:00Z");
    expect(payload.preview_Verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.preview_Verification_updated).toBe("2026-04-02T00:00:00Z");
    expect(payload.preview_Verification_bundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(payload.preview_Durable_state).toBe("/tmp/compact-durable");

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(verification.summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(verification.updated_at).toBe("2026-04-02T00:00:00Z");
    expect(verification.status).toBe("1 failing, 2/3 passing");
    expect(verification.passing).toBe("tsc, bridge_snapshots");
    expect(verification.failing).toBe("cycle_acceptance");
    expect(verification.bundle).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(verification.checks).toEqual([
      {name: "tsc", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: false},
    ]);

    const reloaded = loadSupervisorControlState();
    expect(reloaded?.verificationUpdatedAt).toBe("2026-04-02T00:00:00Z");
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

  test("hydrates control preview from explicit durable verification rows when summary fields stay generic", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "verification.json"),
      JSON.stringify(
        {
          summary: "ok",
          continue_required: true,
          status: "1 failing, 2/3 passing",
          passing: "tsc, bridge_snapshots",
          failing: "cycle_acceptance",
          bundle: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm")).toMatchObject({
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
  });

  test("hydrates pane-ready control rows from stored repo/control preview when run summaries are placeholders", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "run.json"),
      JSON.stringify(
        {
          repo_root: "/Users/dhyana/dharma_swarm",
          updated_at: "2026-04-03T02:16:08Z",
          cycle: 7,
          status: "running",
          tasks_total: 3,
          tasks_pending: 1,
          last_task_id: "terminal-control-surface",
          last_continue_required: true,
          last_summary_fields: {
            status: "unknown",
            acceptance: "unknown",
            next_task: "none",
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
          summary: "ok",
          status: "passing",
          passing: "passing",
          failing: "none",
          bundle: "ok",
          checks: [],
          continue_required: true,
        },
        null,
        2,
      ),
    );
    writeFileSync(
      path.join(stateDir, "terminal-control-summary.json"),
      JSON.stringify(
        {
          "preview_Repo/control_preview":
            "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision continue required | cycle 7 waiting_for_verification | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next persist pane-ready verification receipts",
        },
        null,
        2,
      ),
    );

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-03T04:00:00Z"))).toMatchObject({
      "Repo/control preview":
        "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision continue required | cycle 7 waiting_for_verification | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next persist pane-ready verification receipts",
      "Active task": "terminal-control-surface",
      "Task progress": "2 done, 1 pending of 3",
      "Loop state": "cycle 7 waiting_for_verification",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification receipt": path.join(stateDir, "verification.json"),
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=18 Runs=0 ActiveRuns=0",
      "Artifact state": "Artifacts=7 ContextBundles=1",
      "Next task": "persist pane-ready verification receipts",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 7 waiting_for_verification | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
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
      "Verification receipt": path.join(stateDir, "verification.json"),
      "Verification updated": "2026-03-31T22:46:35.466340+00:00",
      "Loop decision": "ready to stop",
      "Next task": "Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Runtime freshness":
        "cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control pulse preview":
        "fresh | in_progress / pass | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      "Control truth preview":
        "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | cycle 3 running | next Split /runtime and /dashboard control actions into dedicated pane routes.",
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
      "Topology warning severity": "high",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Branch divergence": "local +0/-0 | peer dharma_swarm track main...origin/main",
      "Detached peers": "none",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
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
      "Repo truth preview":
        "branch main@95210b1 | dirty staged 0 | unstaged 510 | untracked 42 | warn sab_canonical_repo_missing | hotspot change terminal (274); .dharma_psmv_hyperfile_branch (142)",
      "Repo/control preview":
        "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | db /Users/dhyana/.dharma/state/runtime.db | next Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
      Dirty: "0 staged, 510 unstaged, 42 untracked",
      "Dirty pressure": "high (552 local changes)",
      Staged: "0",
      Unstaged: "510",
      Untracked: "42",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Topology peer count": "2",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning severity": "high",
      "Topology risk": "sab_canonical_repo_missing",
      "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
      "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Branch divergence": "local +0/-0 | peer dharma_swarm track main...origin/main",
      "Detached peers": "none",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
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
      "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | db /Users/dhyana/.dharma/state/runtime.db | next Split /runtime and /dashboard control actions into dedicated pane routes.",
    );
    expect(payload.preview_Branch_divergence).toBe("local +0/-0 | peer dharma_swarm track main...origin/main");
    expect(payload.preview_Detached_peers).toBe("none");
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
      "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next Split /runtime and /dashboard control actions into dedicated pane routes.",
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

  test("propagates repo-derived compact control preview into durable control snapshots", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Session state": "18 sessions | 0 claims | 0 active claims | 0 acked claims",
      "Run state": "0 runs | 0 active runs",
      "Context state": "7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Runtime activity": "Sessions=18 Runs=0 ActiveRuns=0",
      "Artifact state": "Artifacts=7 ContextBundles=1",
      "Loop state": "cycle 3 running",
      "Task progress": "2 done, 1 pending of 3",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Loop decision": "ready to stop",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok",
      Updated: "2026-03-31T22:46:35.466340+00:00",
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
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Hotspot summary":
        "change terminal (274); .dharma_psmv_hyperfile_branch (142) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    });

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-01T04:00:00Z"))).toMatchObject({
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Active task": "terminal-repo-pane",
      "Task progress": "2 done, 1 pending of 3",
      "Loop state": "cycle 3 running",
      "Result status": "in_progress",
      Acceptance: "pass",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=18 Runs=0 ActiveRuns=0",
      "Artifact state": "Artifacts=7 ContextBundles=1",
    });

    const verification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect((verification.control_preview as Record<string, unknown>)["Repo/control preview"]).toBe(
      "stale | task terminal-repo-pane | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next Split /runtime and /dashboard control actions into dedicated pane routes.",
    );

    const run = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    expect((run.last_control_preview as Record<string, unknown>)["Repo/control preview"]).toBe(
      "stale | task terminal-repo-pane | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main | divergence peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next Split /runtime and /dashboard control actions into dedicated pane routes.",
    );
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
      "Topology warning severity": "high",
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
      "Topology warning severity": "high",
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
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Hotspot summary": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Branch divergence": "local +0/-0 | peer dharma_swarm track main...origin/main",
      "Detached peers": "none",
      "Topology peer count": "2",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Branch sync preview":
        "tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (552 local changes)",
      "Repo truth preview":
        "branch main@95210b1 | dirty n/a | warn sab_canonical_repo_missing | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dirty high (552 local changes) | warn sab_canonical_repo_missing | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159 | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next Split /runtime and /dashboard control actions into dedicated pane routes.",
    });
  });

  test("derives missing topology peer and drift rows from stored topology preview facts", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 6 running",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | cycle_acceptance=ok",
      Updated: "2026-04-03T01:15:00Z",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "tracking origin/main in sync",
      Ahead: "0",
      Behind: "0",
      "Dirty pressure": "high (599 local changes)",
      "Topology risk": "sab_canonical_repo_missing",
      "Topology status": "degraded (1 warning, 2 peers)",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology preview":
        "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ599 (528 modified, 71 untracked); dgc-core clean",
      "Topology pressure": "dharma_swarm Δ599 (528 modified, 71 untracked); dgc-core clean",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/components/RepoPane.tsx",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview).toMatchObject({
      "Primary warning": "sab_canonical_repo_missing",
      "Topology warning severity": "high",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Branch divergence": "local +0/-0 | peer dharma_swarm track main...origin/main",
      "Detached peers": "none",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology peer count": "2",
      "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo risk": "topology sab_canonical_repo_missing; high (599 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
    });
    expect(preview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(preview?.["Repo/control preview"]).toContain("progress 2 done, 1 pending of 3");
    expect(preview?.["Repo/control preview"]).toContain("outcome in_progress/pass");
    expect(preview?.["Repo/control preview"]).toContain("decision ready to stop");
    expect(preview?.["Repo/control preview"]).toContain("branch main@804d5d1");
    expect(preview?.["Repo/control preview"]).toContain("tracking origin/main in sync | sab_canonical_repo_missing");
    expect(preview?.["Repo/control preview"]).toContain("dirty high (599 local changes)");
    expect(preview?.["Repo/control preview"]).toContain("hotspot change terminal (274) | path terminal/src/components/RepoPane.tsx");
    expect(preview?.["Repo/control preview"]).toContain("updated 2026-04-03T01:15:00Z");
  });

  test("derives durable branch divergence and detached peers from stored topology facts", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 6 running",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | cycle_acceptance=ok",
      Updated: "2026-04-03T01:15:00Z",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "ahead of origin/main by 2",
      Ahead: "2",
      Behind: "0",
      "Primary warning": "peer_branch_diverged",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology peers":
        "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty False)",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview).toMatchObject({
      "Primary peer drift": "dharma_swarm drift main...origin/main",
      "Branch divergence": "local +2/-0 | peer dharma_swarm drift main...origin/main",
      "Detached peers": "dgc-core detached",
    });
    expect(preview?.["Repo/control preview"]).toContain(
      "divergence local +2/-0 | peer dharma_swarm drift main...origin/main",
    );
    expect(preview?.["Repo/control preview"]).toContain("detached dgc-core detached");
  });

  test("rehydrates branch divergence and detached peers from compact repo/control previews alone", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Repo/control preview":
        "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty high (656 local changes) | warn peer_branch_diverged | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | peer dharma_swarm drift main...origin/main | detached dgc-core detached | hotspot change terminal (281) | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
    });

    expect(loadSupervisorRepoPreview()).toMatchObject({
      Branch: "main",
      Head: "804d5d1",
      "Primary warning": "peer_branch_diverged",
      "Topology warnings": "1 (peer_branch_diverged)",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Branch divergence": "local +2/-1",
      "Primary peer drift": "dharma_swarm drift main...origin/main",
      "Peer drift markers": "dharma_swarm drift main...origin/main; dgc-core n/a",
      "Detached peers": "dgc-core detached",
      "Repo/control preview":
        "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main ahead 2 | dirty high (656 local changes) | warn peer_branch_diverged | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, detached, dirty True) | drift dharma_swarm drift main...origin/main | markers dharma_swarm drift main...origin/main; dgc-core n/a | divergence local +2/-1 | peer dharma_swarm drift main...origin/main | detached dgc-core detached | hotspot change terminal (281) | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
    });
  });

  test("derives durable git, warning, and hotspot facts from compact repo truth previews", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 8 running",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | cycle_acceptance=ok",
      Updated: "2026-04-03T02:16:08Z",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Branch status": "tracking origin/main in sync",
      Ahead: "2",
      Behind: "0",
      "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
      "Dirty pressure": "high (656 local changes)",
      "Repo truth preview":
        "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview).toMatchObject({
      Branch: "main",
      Head: "804d5d1",
      Dirty: "97 staged, 505 unstaged, 54 untracked",
      Staged: "97",
      Unstaged: "505",
      Untracked: "54",
      "Primary warning": "sab_canonical_repo_missing",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning severity": "high",
      "Primary changed hotspot": "terminal (281)",
      "Primary changed path": "terminal/src/components/RepoPane.tsx",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      "Hotspot summary":
        "change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
      "Lead hotspot preview":
        "change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
      "Hotspot pressure preview": "change terminal (281) | dep dharma_swarm.models | inbound 159",
    });
    expect(preview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(preview?.["Repo/control preview"]).toContain("progress 2 done, 1 pending of 3");
    expect(preview?.["Repo/control preview"]).toContain("outcome in_progress/pass");
    expect(preview?.["Repo/control preview"]).toContain("decision ready to stop");
    expect(preview?.["Repo/control preview"]).toContain("branch main@804d5d1");
    expect(preview?.["Repo/control preview"]).toContain("tracking origin/main in sync | sab_canonical_repo_missing");
    expect(preview?.["Repo/control preview"]).toContain("dirty high (656 local changes)");
    expect(preview?.["Repo/control preview"]).toContain(
      "hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(preview?.["Repo/control preview"]).toContain("cycle 8 running");
    expect(preview?.["Repo/control preview"]).toContain("updated 2026-04-03T02:16:08Z");
  });

  test("preserves semicolon-delimited topology warning members from compact repo truth previews", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 8 running",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | cycle_acceptance=fail",
      Updated: "2026-04-03T02:16:08Z",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Branch status": "tracking origin/main ahead 2",
      Ahead: "2",
      Behind: "1",
      "Dirty pressure": "high (656 local changes)",
      "Repo truth preview":
        "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn peer_branch_diverged; sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview).toMatchObject({
      "Primary warning": "peer_branch_diverged",
      "Topology warnings": "2 (peer_branch_diverged, sab_canonical_repo_missing)",
      "Repo truth preview":
        "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn peer_branch_diverged; sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx",
    });
    expect(preview?.["Repo/control preview"]).toContain("warn peer_branch_diverged; sab_canonical_repo_missing");
  });

  test("keeps branch and compact dirty facts in durable repo/control preview when dirty pressure is absent", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 9 running",
      "Active task": "terminal-repo-pane",
      "Task progress": "4 done, 0 pending of 4",
      "Result status": "complete",
      Acceptance: "pass",
      "Loop decision": "continue required",
      "Verification bundle": "tsc=ok | cycle_acceptance=ok",
      Updated: "2026-04-03T03:00:00Z",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Branch status": "tracking origin/main ahead 2",
      Ahead: "2",
      Behind: "0",
      "Repo risk preview":
        "tracking origin/main ahead 2 | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Repo truth preview":
        "branch main@804d5d1 | dirty staged 112 | unstaged 515 | untracked 75 | warn sab_canonical_repo_missing | hotspot change terminal (274) | path terminal/src/protocol.ts",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview?.["Repo/control preview"]).toContain("branch main@804d5d1");
    expect(preview?.["Repo/control preview"]).toContain("tracking origin/main ahead 2 | sab_canonical_repo_missing");
    expect(preview?.["Repo/control preview"]).toContain("dirty 112 staged, 515 unstaged, 75 untracked");
    expect(preview?.["Repo/control preview"]).toContain("hotspot change terminal (274) | path terminal/src/protocol.ts");
    expect(preview?.["Repo/control preview"]).toContain("cycle 9 running");
    expect(preview?.["Repo/control preview"]).toContain("updated 2026-04-03T03:00:00Z");
  });

  test("preserves multi-warning topology members from compact repo/control previews", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Repo/control preview":
        "stale | task terminal-repo-pane | branch main@804d5d1 | tracking origin/main [ahead 2, behind 1] | dirty high (656 local changes) | warn peer_branch_diverged; sab_canonical_repo_missing | peers 2 | divergence local +2/-1 | hotspot change terminal (281) | cycle 8 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | cycle_acceptance=fail",
    });

    expect(loadSupervisorRepoPreview()).toMatchObject({
      Branch: "main",
      Head: "804d5d1",
      "Primary warning": "peer_branch_diverged",
      "Topology warnings": "2 (peer_branch_diverged, sab_canonical_repo_missing)",
      "Topology peer count": "2",
    });
  });

  test("derives durable topology peer and pressure facts from sparse compact repo previews", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 8 running",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | cycle_acceptance=fail",
      Updated: "2026-04-03T02:16:08Z",
    });
    saveSupervisorRepoPreview(summary!, {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "tracking origin/main in sync",
      Ahead: "0",
      Behind: "0",
      "Dirty pressure": "high (563 local changes)",
      "Repo risk": "topology sab_canonical_repo_missing; high (563 local changes)",
      "Repo risk preview":
        "tracking origin/main in sync | sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology pressure preview": "1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)",
      "Primary changed hotspot": "terminal (274)",
    });

    const preview = loadSupervisorRepoPreview();
    expect(preview).toMatchObject({
      "Primary warning": "sab_canonical_repo_missing",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Topology warning severity": "high",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Primary peer drift": "dharma_swarm track main...origin/main",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
      "Topology peer count": "1",
      "Topology pressure": "dharma_swarm Δ563 (517 modified, 46 untracked)",
      "Branch divergence": "local +0/-0 | peer dharma_swarm track main...origin/main",
    });
    expect(preview?.["Repo/control preview"]).toContain("tracking origin/main in sync | sab_canonical_repo_missing");
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
      "Branch divergence": "n/a",
      "Detached peers": "none",
      "Risk preview": "sab_canonical_repo_missing",
      "Repo risk preview": "sab_canonical_repo_missing",
      "Topology preview": "sab_canonical_repo_missing",
      "Primary warning": "sab_canonical_repo_missing",
      "Repo truth preview":
        "branch main@95210b1 | dirty n/a | warn sab_canonical_repo_missing | hotspot change terminal (274) | paths terminal/src/protocol.ts",
      "Repo/control preview":
        "stale | task terminal-control-surface | progress 2 done, 1 pending of 3 | outcome in_progress/pass | decision ready to stop | branch main@95210b1 | sab_canonical_repo_missing | warn sab_canonical_repo_missing | hotspot change terminal (274) | path terminal/src/protocol.ts | cycle 3 running | updated 2026-03-31T22:46:35.466340+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=ok | next Split /runtime and /dashboard control actions into dedicated pane routes.",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Hotspot summary": "change terminal (274) | paths terminal/src/protocol.ts",
      "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts",
      "Hotspot pressure preview": "change terminal (274)",
      "Primary changed hotspot": "terminal (274)",
      "Primary changed path": "terminal/src/protocol.ts",
    });
    expect(loadSupervisorControlPreview()?.["Loop state"]).toBe("cycle 3 running");
  });

  test("prefers persisted runtime payload over stale durable control preview rows", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(
      summary!,
      {
        "Loop state": "cycle 3 running",
        "Active task": "stale-task",
        "Result status": "unknown",
        Acceptance: "unknown",
        "Verification summary": "ok",
        "Verification bundle": "ok",
        "Verification checks": "none",
        "Next task": "none",
        "Runtime DB": "/tmp/stale-runtime.db",
      },
      {
        runtimePayload: {
          version: "v1",
          domain: "runtime_snapshot",
          snapshot: {
            snapshot_id: "runtime-snap-1",
            created_at: "2026-04-03T02:16:08Z",
            repo_root: "/Users/dhyana/dharma_swarm",
            runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
            health: "degraded",
            bridge_status: "connected",
            active_session_count: 18,
            active_run_count: 0,
            artifact_count: 7,
            context_bundle_count: 1,
            anomaly_count: 1,
            verification_status: "1 failing, 2/3 passing",
            verification_summary: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            verification_bundle: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            verification_checks: "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
            verification_passing: "tsc, bridge_snapshots",
            verification_failing: "cycle_acceptance",
            loop_state: "cycle 19 running",
            loop_decision: "continue required",
            task_progress: "3 done, 1 pending of 4",
            result_status: "in_progress",
            acceptance: "fail",
            last_result: "in_progress / fail",
            updated_at: "2026-04-03T02:16:08Z",
            durable_state: stateDir,
            runtime_summary:
              "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
            runtime_freshness:
              "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            next_task: "Refresh live runtime state",
            active_task: "terminal-repo-pane",
            worktree_count: 1,
            summary: "runtime summary",
            warnings: ["heartbeat delayed"],
            metrics: {
              claims: "0",
              active_claims: "0",
              acknowledged_claims: "0",
              promoted_facts: "2",
              operator_actions: "3",
            },
            metadata: {},
          },
        },
      },
    );

    const preview = loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-03T04:00:00Z"));
    const summaryPayload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;

    expect((summaryPayload.runtime_payload as Record<string, unknown>).domain).toBe("runtime_snapshot");
    expect(preview).toMatchObject({
      "Loop state": "cycle 19 running",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Last result": "in_progress / fail",
      "Loop decision": "continue required",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Next task": "Refresh live runtime state",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime freshness":
        "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
  });

  test("prefers persisted workspace payload over stale durable repo preview rows", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(summary!, {
      "Loop state": "cycle 19 running",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Last result": "in_progress / fail",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Loop decision": "continue required",
      "Next task": "Refresh live repo topology state",
      Updated: "2026-04-03T02:16:08Z",
      "Runtime freshness":
        "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
    saveSupervisorRepoPreview(
      summary!,
      {
        "Repo root": "/Users/dhyana/dharma_swarm",
        Branch: "stale",
        Head: "deadbee",
        "Branch status": "tracking origin/main in sync",
        Ahead: "0",
        Behind: "0",
        "Dirty pressure": "high (1 local change)",
        "Repo risk": "topology stale_warning; high (1 local change)",
        "Primary changed hotspot": "stale (1)",
      },
      {
        workspacePayload: {
          version: "v1",
          domain: "workspace_snapshot",
          repo_root: "/Users/dhyana/dharma_swarm",
          git: {
            branch: "main",
            head: "804d5d1",
            staged: 112,
            unstaged: 562,
            untracked: 137,
            changed_hotspots: [
              {name: "terminal", count: 281},
              {name: ".dharma_psmv_hyperfile_branch", count: 142},
            ],
            changed_paths: ["terminal/src/components/RepoPane.tsx", "terminal/src/protocol.ts"],
            sync: {
              summary: "tracking origin/main ahead 2",
              status: "ahead",
              upstream: "origin/main",
              ahead: 2,
              behind: 0,
            },
          },
          topology: {
            warnings: ["sab_canonical_repo_missing"],
            repos: [
              {
                domain: "core",
                name: "dharma_swarm",
                role: "canonical_core",
                canonical: true,
                path: "/Users/dhyana/dharma_swarm",
                exists: true,
                is_git: true,
                branch: "main...origin/main",
                head: "804d5d1",
                dirty: true,
                modified_count: 562,
                untracked_count: 137,
              },
            ],
            preview: "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
            pressure_preview: "1 warning | dharma_swarm Δ699 (562 modified, 137 untracked)",
          },
          inventory: {
            python_modules: 420,
            python_tests: 87,
            scripts: 14,
            docs: 42,
            workflows: 5,
          },
          language_mix: [
            {suffix: ".py", count: 420},
            {suffix: ".ts", count: 80},
          ],
          largest_python_files: [
            {
              path: "/Users/dhyana/dharma_swarm/dharma_swarm/dgc_cli.py",
              lines: 6908,
              defs: 20,
              classes: 2,
              imports: 50,
            },
          ],
          most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
        },
      },
    );

    const preview = loadSupervisorRepoPreview();
    const summaryPayload = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;

    expect((summaryPayload.workspace_payload as Record<string, unknown>).domain).toBe("workspace_snapshot");
    expect(preview).toMatchObject({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "ahead of origin/main by 2",
      Ahead: "2",
      Behind: "0",
      Staged: "112",
      Unstaged: "562",
      Untracked: "137",
      "Dirty pressure": "high (811 local changes)",
      "Repo risk": "topology sab_canonical_repo_missing; ahead of upstream by 2; high (811 local changes)",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Primary warning": "sab_canonical_repo_missing",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty true)",
      "Primary changed hotspot": "terminal (281)",
      "Primary changed path": "terminal/src/components/RepoPane.tsx",
      "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
      "Primary file hotspot": "dgc_cli.py (6908 lines)",
    });
    expect(preview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(preview?.["Repo/control preview"]).toContain("branch main@804d5d1");
    expect(preview?.["Repo/control preview"]).toContain("ahead of origin/main by 2");

    const runPayload = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    expect((runPayload.workspace_payload as Record<string, unknown>).domain).toBe("workspace_snapshot");
  });

  test("hydrates control preview from run runtime payload when the durable summary is missing", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorControlSummary(
      summary!,
      {
        "Loop state": "cycle 19 running",
        "Task progress": "3 done, 1 pending of 4",
        "Active task": "terminal-repo-pane",
        "Result status": "in_progress",
        Acceptance: "fail",
        "Last result": "in_progress / fail",
        "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
        "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        "Loop decision": "continue required",
        "Next task": "Refresh live runtime state",
        Updated: "2026-04-03T02:16:08Z",
      },
      {
        runtimePayload: {
          version: "v1",
          domain: "runtime_snapshot",
          snapshot: {
            snapshot_id: "runtime-snap-run-fallback",
            created_at: "2026-04-03T02:16:08Z",
            repo_root: "/Users/dhyana/dharma_swarm",
            runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
            health: "degraded",
            bridge_status: "connected",
            active_session_count: 18,
            active_run_count: 0,
            artifact_count: 7,
            context_bundle_count: 1,
            anomaly_count: 1,
            verification_status: "1 failing, 2/3 passing",
            verification_summary: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            verification_bundle: "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            verification_checks: "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
            verification_passing: "tsc, bridge_snapshots",
            verification_failing: "cycle_acceptance",
            loop_state: "cycle 19 running",
            loop_decision: "continue required",
            task_progress: "3 done, 1 pending of 4",
            result_status: "in_progress",
            acceptance: "fail",
            last_result: "in_progress / fail",
            updated_at: "2026-04-03T02:16:08Z",
            durable_state: stateDir,
            runtime_summary:
              "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
            runtime_freshness:
              "cycle 19 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
            next_task: "Refresh live runtime state",
            active_task: "terminal-repo-pane",
            worktree_count: 1,
            summary: "runtime summary",
            warnings: ["heartbeat delayed"],
            metrics: {
              claims: "0",
              active_claims: "0",
              acknowledged_claims: "0",
              promoted_facts: "2",
              operator_actions: "3",
            },
            metadata: {},
          },
        },
      },
    );

    rmSync(path.join(stateDir, "terminal-control-summary.json"), {force: true});
    const runPayload = JSON.parse(readFileSync(path.join(stateDir, "run.json"), "utf8")) as Record<string, unknown>;
    runPayload.last_control_preview = {
      "Loop state": "cycle stale waiting",
      "Runtime DB": "/tmp/stale.db",
    };
    writeFileSync(path.join(stateDir, "run.json"), JSON.stringify(runPayload, null, 2));

    expect(loadSupervisorControlPreview("/Users/dhyana/dharma_swarm", new Date("2026-04-03T04:00:00Z"))).toMatchObject({
      "Loop state": "cycle 19 running",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Loop decision": "continue required",
      "Next task": "Refresh live runtime state",
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 claims | 0 active claims | 0 acked claims | 0 runs | 0 active runs | 7 artifacts | 2 promoted facts | 1 context bundles | 3 operator actions",
      "Verification status": "1 failing, 2/3 passing",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    });
  });

  test("hydrates repo preview from run workspace payload when the durable summary is missing", () => {
    const stateDir = makeStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    const summary = loadSupervisorControlState();

    expect(summary).not.toBeNull();
    saveSupervisorRepoPreview(
      summary!,
      {
        Branch: "stale",
        Head: "deadbee",
      },
      {
        workspacePayload: {
          version: "v1",
          domain: "workspace_snapshot",
          repo_root: "/Users/dhyana/dharma_swarm",
          git: {
            branch: "main",
            head: "804d5d1",
            staged: 112,
            unstaged: 562,
            untracked: 137,
            changed_hotspots: [{name: "terminal", count: 281}],
            changed_paths: ["terminal/src/components/RepoPane.tsx"],
            sync: {
              summary: "tracking origin/main ahead 2",
              status: "ahead",
              upstream: "origin/main",
              ahead: 2,
              behind: 0,
            },
          },
          topology: {
            warnings: ["sab_canonical_repo_missing"],
            repos: [
              {
                domain: "core",
                name: "dharma_swarm",
                role: "canonical_core",
                canonical: true,
                path: "/Users/dhyana/dharma_swarm",
                exists: true,
                is_git: true,
                branch: "main...origin/main",
                head: "804d5d1",
                dirty: true,
                modified_count: 562,
                untracked_count: 137,
              },
            ],
            preview: "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
            pressure_preview: "1 warning | dharma_swarm Δ699 (562 modified, 137 untracked)",
          },
          inventory: {
            python_modules: 420,
            python_tests: 87,
            scripts: 14,
            docs: 42,
            workflows: 5,
          },
          language_mix: [{suffix: ".py", count: 420}],
          largest_python_files: [
            {
              path: "/Users/dhyana/dharma_swarm/dharma_swarm/dgc_cli.py",
              lines: 6908,
              defs: 20,
              classes: 2,
              imports: 50,
            },
          ],
          most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
        },
      },
    );

    rmSync(path.join(stateDir, "terminal-control-summary.json"), {force: true});

    expect(loadSupervisorRepoPreview("/Users/dhyana/dharma_swarm")).toMatchObject({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "ahead of origin/main by 2",
      Ahead: "2",
      Behind: "0",
      "Dirty pressure": "high (811 local changes)",
      "Topology warnings": "1 (sab_canonical_repo_missing)",
      "Primary changed hotspot": "terminal (281)",
      "Primary changed path": "terminal/src/components/RepoPane.tsx",
    });
  });
});
