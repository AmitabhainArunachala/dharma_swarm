import {afterEach, describe, expect, test} from "bun:test";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";
import {PassThrough} from "node:stream";
import {fileURLToPath} from "node:url";
import React from "react";
import {render} from "ink";

import {
  App,
  actionResultActionsForBridgeEvent,
  commandRunSnapshotActionsForBridgeEvent,
  commandResultActionsForBridgeEvent,
  createInitialAppState,
  createBridgeEventHandler,
  handshakeBackoffDelayMs,
  authoritativeResyncComplete,
  authoritativeResyncStatus,
  buildOperatorSummaryItems,
  commandRunEventFromPaneAction,
  controlPanePreview,
  markAuthoritativeSurface,
  missingAuthoritativeSurfaces,
  paneActionStartActions,
  persistControlPreview,
  persistRepoPreview,
  requestMissingAuthoritativeSurfaces,
  slashCommandStartActions,
  snapshotActionsForBridgeEvent,
  surfaceRefreshActionsForBridgeEvent,
  continuityStateFromSession,
} from "../src/app";
import {DharmaBridge} from "../src/bridge";
import {buildRepoPaneSections, RepoPane} from "../src/components/RepoPane";
import {buildContextSidebarLines, buildVisibleContextSidebarLines} from "../src/components/Sidebar";
import {
  commandTargetTab,
  eventToTabPatch,
  normalizeCommandName,
  resolveCommandTargetPane,
  resolveEventActionType,
  resolveEventCommand,
  runtimeSnapshotToPreview,
  runtimePayloadToPreview,
  runtimePreviewToLines,
  workspacePayloadToPreview,
  workspacePreviewToLines,
  workspaceSnapshotToPreview,
} from "../src/protocol";
import {initialState, reduceApp as baseReduceApp} from "../src/state";
import type {AppAction, AppState, TabPreview, TranscriptLine} from "../src/types";

const TESTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const TERMINAL_ROOT = path.resolve(TESTS_DIR, "..");
const TERMINAL_STATE_PATH = path.join(TERMINAL_ROOT, ".dharma-terminal-state.json");
const DEFAULT_ROUTE_LABEL = "codex:gpt-5.4 (ready)";

type LegacyActiveTabState = AppState & {activeTabId?: string};

function seedLegacyActiveTabState(state: LegacyActiveTabState): LegacyActiveTabState {
  const activeTabId =
    typeof state.activeTabId === "string" && state.activeTabId.trim().length > 0
      ? state.activeTabId
      : state.uiMode.activeTabId;
  return {
    ...state,
    uiMode: {
      ...state.uiMode,
      activeTabId,
    },
    activeTabId,
  };
}

function mirrorLegacyActiveTabState(state: AppState): LegacyActiveTabState {
  return {
    ...state,
    activeTabId: state.uiMode.activeTabId,
  };
}

function reduceApp(state: AppState, action: AppAction): AppState {
  return mirrorLegacyActiveTabState(baseReduceApp(seedLegacyActiveTabState(state as LegacyActiveTabState), action));
}

function applyActions(state: AppState, actions: AppAction[]): AppState {
  return actions.reduce((current, action) => reduceApp(current, action), state);
}

function replaceRepoLines(state: AppState, lines: TranscriptLine[]): AppState {
  return reduceApp(state, {type: "tab.replace", tabId: "repo", lines});
}

function applyBridgeEvent(state: AppState, event: Record<string, unknown>): AppState {
  const stateAfterCommandActions = applyActions(state, commandResultActionsForBridgeEvent(event));
  const stateAfterCommandSnapshots =
    String(event.type ?? "") === "command.result"
      ? applyActions(
          stateAfterCommandActions,
          commandRunSnapshotActionsForBridgeEvent(event, state.liveRepoPreview, state.liveControlPreview, null),
        )
      : stateAfterCommandActions;
  const stateAfterActionResults = applyActions(stateAfterCommandSnapshots, actionResultActionsForBridgeEvent(event));
  if (String(event.type ?? "") === "action.result") {
    const actionType = resolveEventActionType(event);
    const stateAfterActionCommandSnapshots = applyActions(
      stateAfterActionResults,
      commandRunSnapshotActionsForBridgeEvent(event, state.liveRepoPreview, state.liveControlPreview, null),
    );
    const stateAfterRefreshActions = applyActions(
      stateAfterActionCommandSnapshots,
      surfaceRefreshActionsForBridgeEvent(event, state.liveRepoPreview, state.liveControlPreview, state.sessionPane),
    );
    const targetPane =
      actionType === "command.run"
        ? resolveCommandTargetPane(event, "control")
        : String(event.target_pane ?? "control");
    const output = String(event.output ?? "").trim();
    const policy = typeof event.policy === "object" && event.policy !== null;
    const actionResultAppendActions =
      output &&
      actionType !== "surface.refresh" &&
      actionType !== "command.run" &&
      commandRunSnapshotActionsForBridgeEvent(event, state.liveRepoPreview, state.liveControlPreview, null).length === 0 &&
      !(targetPane === "models" && policy)
        ? ([{type: "tab.append", tabId: targetPane, lines: [{id: "action-1", kind: "system", text: output}]}] satisfies AppAction[])
        : [];
    return applyActions(
      stateAfterRefreshActions,
      [
        ...actionResultAppendActions,
        ...eventToTabPatch(event).map(
          (patch) => ({type: "tab.append", tabId: patch.tabId, lines: patch.lines}) satisfies AppAction,
        ),
      ],
    );
  }
  const stateAfterSnapshots = applyActions(
    stateAfterActionResults,
    snapshotActionsForBridgeEvent(event, state.liveRepoPreview, state.liveControlPreview),
  );
  const appendActions = eventToTabPatch(event).map((patch) => ({type: "tab.append", tabId: patch.tabId, lines: patch.lines}) satisfies AppAction);
  return applyActions(stateAfterSnapshots, appendActions);
}

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

test("handshakeBackoffDelayMs scales to a capped retry window", () => {
  expect(handshakeBackoffDelayMs(1)).toBe(5000);
  expect(handshakeBackoffDelayMs(2)).toBe(15000);
  expect(handshakeBackoffDelayMs(3)).toBe(30000);
  expect(handshakeBackoffDelayMs(4)).toBe(60000);
  expect(handshakeBackoffDelayMs(9)).toBe(60000);
});

test("authoritative recovery helpers identify missing surfaces and target only those requests", () => {
  expect(
    missingAuthoritativeSurfaces({
      repo: true,
      control: false,
      sessions: false,
      approvals: true,
      models: true,
      agents: false,
    }),
  ).toEqual(["control", "sessions", "agents"]);

  expect(
    authoritativeResyncComplete({
      repo: true,
      control: true,
      sessions: true,
      approvals: true,
      models: true,
      agents: true,
    }),
  ).toBe(true);

  expect(
    markAuthoritativeSurface(
      {
        repo: true,
        control: false,
        sessions: false,
        approvals: true,
        models: true,
        agents: false,
      },
      "control",
    ),
  ).toEqual({
    repo: true,
    control: true,
    sessions: false,
    approvals: true,
    models: true,
    agents: false,
  });

  expect(
    authoritativeResyncStatus({
      repo: true,
      control: true,
      sessions: false,
      approvals: true,
      models: false,
      agents: false,
    }),
  ).toBe("resyncing 3 surfaces");

  const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
  const bridge = {
    send(type: string, payload: Record<string, unknown> = {}) {
      sent.push({type, payload});
      return String(sent.length);
    },
  } as unknown as DharmaBridge;

  requestMissingAuthoritativeSurfaces(
    bridge,
    "codex",
    "gpt-5.4",
    "responsive",
    {
      repo: false,
      control: true,
      sessions: false,
      approvals: true,
      models: false,
      agents: false,
    },
  );

  expect(sent).toEqual([
    {type: "workspace.snapshot", payload: {}},
    {type: "session.catalog", payload: {limit: 12}},
    {type: "model.policy", payload: {provider: "codex", model: "gpt-5.4", strategy: "responsive"}},
    {type: "agent.routes", payload: {}},
  ]);
});

test("operator summary normalizes running_cycle loop labels", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    routePolicy: {
      ...initialState.routePolicy,
      provider: "codex",
      model: "gpt-5.4",
      routeId: "codex:gpt-5.4",
      routeState: "ready",
      availabilityReason: "configured",
      targets: [],
    },
    liveControlPreview: {
      "Loop state": "cycle 4 running_cycle",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual(
    expect.arrayContaining([{label: "loop", value: "cycle 4 running", tone: "live"}]),
  );
});

test("continuity only resumes with a provider-native session id for the active provider", () => {
  const state = reduceApp(initialState, {
    type: "route.policy.set",
    policy: {
      ...initialState.routePolicy,
      provider: "claude",
      model: "sonnet-4.5",
      routeId: "claude:sonnet-4.5",
    },
  });

  const resumable = continuityStateFromSession(state, {
    session: {
      session_id: "dgc-20260404-123000-abcd",
      provider_id: "claude",
      model_id: "sonnet-4.5",
      cwd: "/repo",
      created_at: "2026-04-04T00:00:00Z",
      updated_at: "2026-04-04T00:10:00Z",
      status: "completed",
      summary: "resumable claude turn",
      metadata: {
        provider_session_id: "550e8400-e29b-41d4-a716-446655440000",
      },
    },
    replay_ok: true,
    replay_issues: [],
    compaction_preview: {
      event_count: 4,
      by_type: {session_start: 1, text_complete: 1, session_end: 1},
      compactable_ratio: 0,
      protected_event_types: ["session_start", "session_end"],
      recent_event_types: ["session_start", "text_complete", "session_end"],
    },
    recent_events: [],
  });

  expect(resumable.continuityMode).toBe("resume");
  expect(resumable.resumeSessionId).toBe("550e8400-e29b-41d4-a716-446655440000");

  const routeSwitched = continuityStateFromSession(
    reduceApp(state, {
      type: "route.policy.set",
      policy: {
        ...state.routePolicy,
        provider: "ollama",
        model: "deepseek-v3.2",
        routeId: "ollama:deepseek-v3.2",
      },
    }),
    {
      session: {
        session_id: "dgc-20260404-123000-abcd",
        provider_id: "claude",
        model_id: "sonnet-4.5",
        cwd: "/repo",
        created_at: "2026-04-04T00:00:00Z",
        updated_at: "2026-04-04T00:10:00Z",
        status: "completed",
        summary: "resumable claude turn",
        metadata: {
          provider_session_id: "550e8400-e29b-41d4-a716-446655440000",
        },
      },
      replay_ok: true,
      replay_issues: [],
      compaction_preview: {
        event_count: 4,
        by_type: {session_start: 1, text_complete: 1, session_end: 1},
        compactable_ratio: 0,
        protected_event_types: ["session_start", "session_end"],
        recent_event_types: ["session_start", "text_complete", "session_end"],
      },
      recent_events: [],
    },
  );

  expect(routeSwitched.continuityMode).toBe("fresh");
  expect(routeSwitched.resumeSessionId).toBeUndefined();
  expect(routeSwitched.activeSessionId).toBe("dgc-20260404-123000-abcd");
});

test("bridge handler suppresses duplicate completed assistant text after streamed text", () => {
  let state: AppState = createInitialAppState(initialState);
  const bridge = {
    send() {
      return "1";
    },
  } as unknown as DharmaBridge;

  const handler = createBridgeEventHandler({
    dispatch: (action) => {
      state = reduceApp(state, action);
    },
    getState: () => state,
    bridge,
    pendingBootstraps: {current: {}},
  });

  handler({type: "text_delta", content: "Same assistant output"});
  handler({type: "text_complete", content: "Same assistant output"});

  const assistantLines = (state.tabs.find((tab) => tab.id === "chat")?.lines ?? []).filter((line) => line.kind === "assistant");
  expect(assistantLines.filter((line) => line.text === "Same assistant output")).toHaveLength(1);
});

const bootstrapWorkspacePreview: TabPreview = {
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
    "branch main@95210b1 | dirty staged 0 | unstaged 510 | untracked 42 | warn sab_canonical_repo_missing | hotspot change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35 | paths terminal/src/protocol.ts",
  "Repo risk": "topology sab_canonical_repo_missing; high (552 local changes)",
  Dirty: "0 staged, 510 unstaged, 42 untracked",
  "Dirty pressure": "high (552 local changes)",
  Staged: "0",
  Unstaged: "510",
  Untracked: "42",
  "Topology status": "degraded (1 warning, 2 peers)",
  "Topology peer count": "2",
  "Topology warnings": "1 (sab_canonical_repo_missing)",
  "Topology warning members": "sab_canonical_repo_missing",
  "Topology warning severity": "high",
  "Topology risk": "sab_canonical_repo_missing",
  "Risk preview": "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True)",
  "Topology preview":
    "sab_canonical_repo_missing | dharma_swarm (canonical_core, main...origin/main, dirty True) | dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
  "Topology pressure preview": "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
  "Primary warning": "sab_canonical_repo_missing",
  "Primary peer drift": "dharma_swarm track main...origin/main",
  "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty True)",
  "Peer drift markers": "dharma_swarm track main...origin/main; dgc-core n/a",
  "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None)",
  "Topology pressure": "dharma_swarm Δ552 (510 modified, 42 untracked); dgc-core clean",
  "Changed hotspots": "terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)",
  "Hotspot summary":
    "change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
  "Lead hotspot preview": "change terminal (274) | path terminal/src/protocol.ts | dep dharma_swarm.models | inbound 159",
  "Hotspot pressure preview": "change terminal (274) | dep dharma_swarm.models | inbound 159",
  "Changed paths":
    "terminal/src/protocol.ts; terminal/src/components/Sidebar.tsx; terminal/tests/protocol.test.ts",
  "Primary changed hotspot": "terminal (274)",
  "Primary changed path": "terminal/src/protocol.ts",
  "Primary file hotspot": "dgc_cli.py (6908 lines)",
  "Primary dependency hotspot": "dharma_swarm.models | inbound 159",
  Hotspots: "dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines)",
  "Inbound hotspots": "dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35",
  Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
  "Language mix": ".py: 1125; .md: 511; .json: 91; .sh: 68",
};

const bootstrapRuntimePreview: TabPreview = {
  "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
  "Runtime activity": "Sessions=18  Runs=0",
  "Artifact state": "Artifacts=7  ContextBundles=1",
  "Loop state": "cycle 4 running",
  "Loop decision": "continue required",
  "Active task": "terminal-repo-pane",
  "Task progress": "3 done, 1 pending of 4",
  "Result status": "complete",
  Acceptance: "fail",
  "Last result": "complete / fail",
  "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
  "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
  "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
  "Runtime freshness":
    "cycle 4 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
  "Control pulse preview":
    "complete / fail | cycle 4 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
  "Runtime summary":
    "/Users/dhyana/.dharma/state/runtime.db | none | none | none",
  "Next task": "Add an app-level bootstrap/refresh snapshot test.",
  Updated: "2026-04-01T00:00:00Z",
  "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
  Toolchain: "claude, python3, node",
  Alerts: "none",
};

const TEMP_DIRS: string[] = [];
let savedTerminalStateBackup: string | null | undefined;

class TestStdout extends PassThrough {
  columns = 220;
  rows = 60;
  isTTY = true;

  cursorTo(): boolean {
    return true;
  }

  moveCursor(): boolean {
    return true;
  }

  clearLine(): boolean {
    return true;
  }

  clearScreenDown(): boolean {
    return true;
  }

  getColorDepth(): number {
    return 8;
  }

  hasColors(): boolean {
    return true;
  }
}

class TestStdin extends PassThrough {
  isTTY = true;
  isRaw = false;

  setRawMode(value: boolean): this {
    this.isRaw = value;
    return this;
  }

  resume(): this {
    return this;
  }

  pause(): this {
    return this;
  }

  ref(): this {
    return this;
  }

  unref(): this {
    return this;
  }
}

function stripAnsi(value: string): string {
  return value.replace(/\u001B\[[0-?]*[ -/]*[@-~]/g, "");
}

function normalizeTerminalText(value: string): string {
  return stripAnsi(value)
    .replace(/[┌┐└┘├┤┬┴┼│─]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function saveTerminalStateOverride(payload: Record<string, unknown>): void {
  if (savedTerminalStateBackup === undefined) {
    savedTerminalStateBackup = existsSync(TERMINAL_STATE_PATH) ? readFileSync(TERMINAL_STATE_PATH, "utf8") : null;
  }
  writeFileSync(TERMINAL_STATE_PATH, JSON.stringify(payload, null, 2));
}

async function flushRender(): Promise<void> {
  await Bun.sleep(50);
}

function makeSupervisorStateDir(): string {
  const root = mkdtempSync(path.join(os.tmpdir(), "dharma-terminal-app-"));
  TEMP_DIRS.push(root);
  const stateDir = path.join(root, "state");
  mkdirSync(stateDir, {recursive: true});
  writeFileSync(
    path.join(stateDir, "run.json"),
    JSON.stringify(
      {
        repo_root: "/Users/dhyana/dharma_swarm",
        updated_at: "2026-04-01T00:00:00Z",
        cycle: 4,
        status: "running",
        tasks_total: 4,
        tasks_pending: 1,
        last_task_id: "terminal-control-surface",
        last_continue_required: true,
        last_summary_fields: {
          status: "complete",
          acceptance: "fail",
          next_task: "Add an app-level bootstrap/refresh snapshot test.",
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
        summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        continue_required: true,
        checks: [
          {name: "tsc", ok: true},
          {name: "py_compile_bridge", ok: true},
          {name: "bridge_snapshots", ok: true},
          {name: "cycle_acceptance", ok: false},
        ],
      },
      null,
      2,
    ),
  );
  return stateDir;
}

function cleanupTempDirs(): void {
  delete process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR;
  delete process.env.DHARMA_TERMINAL_STATE_DIR;
  if (savedTerminalStateBackup !== undefined) {
    if (savedTerminalStateBackup === null) {
      rmSync(TERMINAL_STATE_PATH, {force: true});
    } else {
      writeFileSync(TERMINAL_STATE_PATH, savedTerminalStateBackup);
    }
    savedTerminalStateBackup = undefined;
  }
  while (TEMP_DIRS.length > 0) {
    rmSync(TEMP_DIRS.pop() ?? "", {force: true, recursive: true});
  }
}

afterEach(() => {
  cleanupTempDirs();
});

describe("snapshotActionsForBridgeEvent", () => {
  test("persists bootstrap runtime previews into the durable control summary", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview(bootstrapRuntimePreview);

    const outputPath = path.join(stateDir, "terminal-control-summary.json");
    expect(existsSync(outputPath)).toBe(true);

    const payload = JSON.parse(readFileSync(outputPath, "utf8")) as Record<string, unknown>;
    expect(payload.preview_Verification_summary).toBe(bootstrapRuntimePreview["Verification summary"]);
    expect(payload.preview_Verification_checks).toBe(bootstrapRuntimePreview["Verification checks"]);
    expect(payload.preview_Verification_status).toBe("1 failing, 3/4 passing");
    expect(payload.preview_Verification_passing).toBe("tsc, py_compile_bridge, bridge_snapshots");
    expect(payload.preview_Verification_failing).toBe("cycle_acceptance");
    expect(payload.preview_Loop_state).toBe(bootstrapRuntimePreview["Loop state"]);
    expect(payload.preview_Next_task).toBe(bootstrapRuntimePreview["Next task"]);

  });

  test("persists normalized repo previews into durable state for boot hydration", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistRepoPreview(bootstrapWorkspacePreview);

    const outputPath = path.join(stateDir, "terminal-control-summary.json");
    expect(existsSync(outputPath)).toBe(true);

    const payload = JSON.parse(readFileSync(outputPath, "utf8")) as Record<string, unknown>;
    expect(payload.preview_Repo_root).toBe(bootstrapWorkspacePreview["Repo root"]);
    expect(payload.preview_Branch).toBe(bootstrapWorkspacePreview.Branch);
    expect(payload.preview_Topology_warnings).toBe(bootstrapWorkspacePreview["Topology warnings"]);
    expect(payload.preview_Hotspot_summary).toBe(bootstrapWorkspacePreview["Hotspot summary"]);
    expect(payload.preview_Runtime_DB).toBeUndefined();
  });

  test("hydrates the initial app boot state from durable repo and control previews", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistRepoPreview(bootstrapWorkspacePreview);
    persistControlPreview(bootstrapRuntimePreview);

    const bootState = createInitialAppState(initialState);
    const repoTab = bootState.tabs.find((tab) => tab.id === "repo");
    const runtimeTab = bootState.tabs.find((tab) => tab.id === "runtime");
    const controlTab = bootState.tabs.find((tab) => tab.id === "control");

    expect(repoTab?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(bootState.liveRepoPreview ?? {}).map((line) => line.text),
    );
    expect(repoTab?.lines.map((line) => line.text)).not.toContain("Workspace snapshot loading...");
    expect(repoTab?.preview).toMatchObject(bootstrapWorkspacePreview);

    expect(runtimeTab?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(bootState.liveControlPreview ?? {}).map((line) => line.text),
    );
    expect(controlTab?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(bootState.liveControlPreview ?? {}).map((line) => line.text),
    );
    expect(controlTab?.preview).toMatchObject(bootstrapRuntimePreview);

    expect(bootState.liveRepoPreview).toMatchObject(bootstrapWorkspacePreview);
    expect(bootState.liveControlPreview).toMatchObject(bootstrapRuntimePreview);

    const sidebarLines = buildContextSidebarLines(
      bootState.tabs,
      "Chat",
      bootState.routePolicy.provider,
      bootState.routePolicy.model,
      bootState.bridgeStatus,
      bootState.liveRepoPreview,
      bootState.liveControlPreview,
    );
    expect(sidebarLines.some((line) => line.startsWith("Risk topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(sidebarLines.some((line) => line.startsWith("Paths terminal/src/protocol.ts; terminal/src/components/"))).toBe(true);
    expect(sidebarLines).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");
    expect(sidebarLines).toContain("Outcome complete | accept fail");
  });

  test("prefers richer restored runtime previews when hydrating shared control state on startup", () => {
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = path.join(os.tmpdir(), "dharma-terminal-missing-state");
    const sparseControlPreview: TabPreview = {
      "Loop state": "unknown",
      "Verification summary": "unknown",
      "Verification bundle": "unknown",
      "Next task": "unknown",
    };
    const richRuntimePreview: TabPreview = {
      "Loop state": "cycle 12 waiting_for_verification",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-control-surface",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Last result": "in_progress / fail",
      "Loop decision": "continue required",
      "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
      "Verification status": "1 failing, 2/3 passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      Updated: "2026-04-03T02:00:00Z",
      "Runtime freshness":
        "cycle 12 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Control pulse preview":
        "fresh | in_progress / fail | cycle 12 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Next task": "Promote runtime preview rows into the control signal band.",
      "Durable state": "/tmp/runtime-state",
    };

    const bootState = createInitialAppState({
      ...initialState,
      liveControlPreview: undefined,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control"
          ? {...tab, lines: [], preview: sparseControlPreview}
          : tab.id === "runtime"
            ? {...tab, lines: [], preview: richRuntimePreview}
            : tab,
      ),
    });

    expect(bootState.liveControlPreview).toMatchObject(richRuntimePreview);
    expect(bootState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(bootState.liveControlPreview ?? {}).map((line) => line.text),
    );
    expect(bootState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(bootState.liveControlPreview ?? {}).map((line) => line.text),
    );
    expect(bootState.liveControlPreview?.["Verification status"]).toBe("1 failing, 2/3 passing");
    expect(bootState.liveControlPreview?.["Next task"]).toBe(
      "Promote runtime preview rows into the control signal band.",
    );
  });

  test("normalizes sparse restored repo previews into startup-safe visible context rows", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    const sparseRepoPreview: TabPreview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      "Branch status": "tracking origin/main ahead 2",
      Sync: "origin/main | ahead 2 | behind 0",
      Ahead: "2",
      Behind: "0",
      "Repo risk": "topology sab_canonical_repo_missing; high (656 local changes)",
      "Dirty pressure": "high (656 local changes)",
      "Repo truth preview":
        "branch main@804d5d1 | dirty staged 97 | unstaged 505 | untracked 54 | warn sab_canonical_repo_missing | hotspot change terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159",
    };

    const bootState = createInitialAppState({
      ...initialState,
      liveRepoPreview: undefined,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {...tab, lines: [], preview: sparseRepoPreview}
          : tab.id === "control"
            ? {...tab, lines: [], preview: bootstrapRuntimePreview}
            : tab,
      ),
    });

    expect(bootState.liveRepoPreview?.["Repo/control preview"]).toContain("task terminal-control-surface");
    expect(bootState.liveRepoPreview?.["Repo/control preview"]).toContain("tracking origin/main ahead 2");
    expect(bootState.liveRepoPreview?.["Repo/control preview"]).not.toContain("undefined");

    const sidebarLines = buildContextSidebarLines(
      bootState.tabs,
      "Chat",
      bootState.provider,
      bootState.model,
      bootState.bridgeStatus,
      bootState.liveRepoPreview,
      bootState.liveControlPreview,
    );

    expect(sidebarLines.some((line) => line.includes("undefined"))).toBe(false);
    expect(sidebarLines.some((line) => line.startsWith("Git main@804d5d1 | high (656 local"))).toBe(true);
    expect(sidebarLines.some((line) => line.startsWith("Dirty staged 97 | unstaged 505 | unt"))).toBe(true);
    expect(sidebarLines.some((line) => line.startsWith("Snapshot truth branch main@804d5d1 | dirty staged 97 | unstaged 505 |"))).toBe(
      true,
    );
    expect(
      sidebarLines.some((line) => line.startsWith("Snapshot topology degraded") && line.includes("| warnings 1")),
    ).toBe(true);
    expect(sidebarLines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (281) | path terminal/src"))).toBe(
      true,
    );
  });

  test("renders hydrated repo and context previews on app startup", async () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistRepoPreview(bootstrapWorkspacePreview);
    persistControlPreview(bootstrapRuntimePreview);
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    const sentMessages: Array<{type: string; payload: Record<string, unknown>}> = [];
    const originalSend = DharmaBridge.prototype.send;
    const originalClose = DharmaBridge.prototype.close;
    DharmaBridge.prototype.send = function mockedSend(type: string, payload: Record<string, unknown> = {}): string {
      sentMessages.push({type, payload});
      return String(sentMessages.length);
    };
    DharmaBridge.prototype.close = function mockedClose(): void {};

    const stdout = new TestStdout();
    const stdin = new TestStdin();
    let rendered = "";
    stdout.on("data", (chunk) => {
      rendered += chunk.toString("utf8");
    });

    const instance = render(React.createElement(App), {
      stdout: stdout as unknown as NodeJS.WriteStream,
      stdin: stdin as unknown as NodeJS.ReadStream,
      stderr: new TestStdout() as unknown as NodeJS.WriteStream,
      debug: true,
      patchConsole: false,
      exitOnCtrlC: false,
    });

    try {
      await flushRender();
      stdin.write("\u0012");
      await flushRender();

      const bootState = createInitialAppState(initialState);
      const expectedRepoRows = [
        "Operator Snapshot",
        "Snapshot",
        "Git main@95210b1 | high (552 local changes) | sync tracking origin/main in sync",
        "Snapshot branch main@95210b1 | tracking origin/main in sync",
        "Snapshot dirty high (552 local changes) | staged 0 | unstaged 510 | untracked 42",
        "Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)",
        "Snapshot hotspots change terminal (274)",
        "Snapshot hotspot pressure change terminal (274)",
        "Task terminal-repo-pane | complete/fail | tsc=ok",
      ];
      const expectedSidebarLines = buildVisibleContextSidebarLines(
        bootState.tabs,
        "Repo",
        bootState.provider,
        bootState.model,
        bootState.bridgeStatus,
        {...bootstrapWorkspacePreview, Authority: "placeholder | bridge booting | awaiting authoritative repo refresh"},
        {...bootstrapRuntimePreview, Authority: "placeholder | bridge booting | awaiting authoritative control refresh"},
      ).filter((line) =>
        [
          "Repo Preview",
          "Control Preview",
          "Authority placeholder | bridge booting | awaiting authoritative repo refresh",
          "Authority placeholder | bridge booting | awaiting authoritative control refresh",
          "Branch main@95210b1",
          "Outcome complete | accept fail",
          "Runtime /Users/dhyana/.dharma/state/runtime.db",
          "Loop cycle 4 running | continue required",
        ].includes(line),
      );
      const normalized = normalizeTerminalText(rendered);

      expect(sentMessages.map((message) => message.type).filter((type) => type === "handshake").length).toBeLessThanOrEqual(1);
      for (const row of expectedRepoRows) {
        expect(normalized).toContain(normalizeTerminalText(row));
      }
      for (const line of expectedSidebarLines) {
        expect(normalized).toContain(normalizeTerminalText(line));
      }
    } finally {
      instance.unmount();
      instance.cleanup();
      DharmaBridge.prototype.send = originalSend;
      DharmaBridge.prototype.close = originalClose;
    }
  });

  test("renders hydrated control and runtime panes with loop and verification state on startup", async () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview(bootstrapRuntimePreview);
    saveTerminalStateOverride({version: 3, sidebarVisible: false, sidebarMode: "toc"});

    const originalSend = DharmaBridge.prototype.send;
    const originalClose = DharmaBridge.prototype.close;
    DharmaBridge.prototype.send = function mockedSend(): string {
      return "1";
    };
    DharmaBridge.prototype.close = function mockedClose(): void {};

    const stdout = new TestStdout();
    const stdin = new TestStdin();
    let rendered = "";
    stdout.on("data", (chunk) => {
      rendered += chunk.toString("utf8");
    });

    const instance = render(React.createElement(App), {
      stdout: stdout as unknown as NodeJS.WriteStream,
      stdin: stdin as unknown as NodeJS.ReadStream,
      stderr: new TestStdout() as unknown as NodeJS.WriteStream,
      debug: true,
      patchConsole: false,
      exitOnCtrlC: false,
    });

    try {
      await flushRender();
      stdin.write("\u0014");
      await flushRender();
      stdin.write("\u0019");
      await flushRender();
      stdin.write("j");
      await flushRender();

      const normalized = normalizeTerminalText(rendered);

      for (const row of [
        "Control",
        "Runtime",
        "Runtime Signal",
        "Loop cycle 4 running | continue required | 2026-04-01T00:00:00Z",
        "Verification 1 failing, 3/4 passing | failing cycle_acceptance",
        "Overview",
        "Loop cycle 4 running | 3 done, 1 pending of 4 | terminal-repo-pane",
        "Decision continue required | Add an app-level bootstrap/refresh snapshot test.",
        "selected runtime card",
        "State /Users/dhyana/.dharma/terminal_supervisor/terminal-20260401T034429Z/state",
        "Runtime 18 sessions | 0 runs",
      ]) {
        expect(normalized).toContain(normalizeTerminalText(row));
      }
    } finally {
      instance.unmount();
      instance.cleanup();
      DharmaBridge.prototype.send = originalSend;
      DharmaBridge.prototype.close = originalClose;
    }
  });

  test("hydrates pane previews from compact repo/control preview when explicit control rows are absent", () => {
    const repoPreview: TabPreview = {
      "Repo/control preview":
        "stale | task terminal-control-surface | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | cycle 13 ready | updated 2026-04-03T01:15:00Z | verify tsc=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 | artifacts Artifacts=7 ContextBundles=1 | next hydrate control preview from runtime state",
    };

    expect(controlPanePreview(undefined, repoPreview)).toEqual({
      "Repo/control preview": repoPreview["Repo/control preview"],
    });
    expect(
      controlPanePreview(
        {
          "Loop state": "cycle 4 running",
        },
        repoPreview,
      ),
    ).toEqual({
      "Loop state": "cycle 4 running",
      "Repo/control preview": repoPreview["Repo/control preview"],
    });
  });

  test("replaces stale repo transcript with live normalized snapshot during bootstrap and refresh", () => {
    const staleRepoLines: TranscriptLine[] = [
      {id: "stale-1", kind: "system", text: "# /git"},
      {id: "stale-2", kind: "system", text: "branch main"},
      {id: "stale-3", kind: "system", text: "raw diff summary that should be replaced"},
    ];
    const baseState: AppState = {
      ...initialState,
      activeTabId: "repo",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {...tab, lines: staleRepoLines, preview: {Branch: "stale", Head: "oldhead"}}
          : tab.id === "control"
            ? {...tab, lines: [], preview: undefined}
            : tab,
      ),
      liveRepoPreview: undefined,
      liveControlPreview: undefined,
    };

    const afterBootstrap = applyActions(
      baseState,
      snapshotActionsForBridgeEvent(
        {
          type: "session.bootstrap.result",
          workspace_preview: bootstrapWorkspacePreview,
          runtime_preview: bootstrapRuntimePreview,
        },
        baseState.liveRepoPreview,
        baseState.liveControlPreview,
      ),
    );

    expect(afterBootstrap.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(afterBootstrap.liveRepoPreview ?? bootstrapWorkspacePreview).map((line) => line.text),
    );
    expect(afterBootstrap.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain(
      "raw diff summary that should be replaced",
    );
    expect(afterBootstrap.liveRepoPreview).toMatchObject(bootstrapWorkspacePreview);
    expect(afterBootstrap.liveRepoPreview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(afterBootstrap.liveRepoPreview?.["Repo/control preview"]).toContain("branch main@95210b1");
    expect(afterBootstrap.liveControlPreview).toEqual(bootstrapRuntimePreview);
    expect(afterBootstrap.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(bootstrapRuntimePreview).map((line) => line.text),
    );

    const sidebarAfterBootstrap = buildContextSidebarLines(
      afterBootstrap.tabs,
      "Repo",
      afterBootstrap.provider,
      afterBootstrap.model,
      afterBootstrap.bridgeStatus,
      afterBootstrap.liveRepoPreview,
      afterBootstrap.liveControlPreview,
    );
    expect(sidebarAfterBootstrap.some((line) => line.startsWith("Risk topology sab_canonical_repo_missing; high"))).toBe(true);
    expect(sidebarAfterBootstrap).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");

    const staleRefreshState = replaceRepoLines(afterBootstrap, [
      {id: "refresh-stale-1", kind: "system", text: "# /git"},
      {id: "refresh-stale-2", kind: "system", text: "still stale after refresh trigger"},
    ]);
    const refreshContent = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511
- .json: 91
- .sh: 68

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208
- dharma_swarm/thinkodynamic_director.py | 5167 lines | defs 108 | imports 36

## Most imported local modules
- dharma_swarm.models | inbound 159
- dharma_swarm.stigmergy | inbound 35`;
    const refreshPayload = {
      version: "v1",
      domain: "workspace_snapshot",
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "95210b1",
        staged: 0,
        unstaged: 12,
        untracked: 1,
        changed_hotspots: [{name: "terminal", count: 8}],
        changed_paths: ["terminal/src/app.tsx"],
        sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
      },
      topology: {
        warnings: ["sab_canonical_repo_missing"],
        repos: [
          {
            domain: "dgc",
            name: "dharma_swarm",
            role: "canonical_core",
            canonical: true,
            path: "/Users/dhyana/dharma_swarm",
            exists: true,
            is_git: true,
            branch: "main...origin/main",
            dirty: true,
            modified_count: 12,
            untracked_count: 1,
          },
        ],
      },
      inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
      language_mix: [{suffix: ".py", count: 1125}, {suffix: ".md", count: 511}],
      largest_python_files: [{path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208}],
      most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
    } as const;
    const refreshPreview = workspacePayloadToPreview(refreshPayload);
    const afterRefresh = applyActions(
      staleRefreshState,
      snapshotActionsForBridgeEvent(
        {
          type: "workspace.snapshot.result",
          payload: refreshPayload,
        },
        staleRefreshState.liveRepoPreview,
        staleRefreshState.liveControlPreview,
      ),
    );

    expect(afterRefresh.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(afterRefresh.liveRepoPreview ?? refreshPreview).map((line) => line.text),
    );
    expect(afterRefresh.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain(
      "still stale after refresh trigger",
    );
    expect(afterRefresh.liveRepoPreview).toMatchObject(refreshPreview);
    expect(afterRefresh.liveRepoPreview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(afterRefresh.liveRepoPreview?.["Repo/control preview"]).toContain("branch main@95210b1");

  });

  test("replaces stale repo warning and hotspot fields when a clean /git snapshot arrives", () => {
    const staleState: AppState = {
      ...initialState,
      liveRepoPreview: bootstrapWorkspacePreview,
    };

    const cleanWorkspaceSnapshot = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 0 | untracked 0
Git hotspots: none
Git changed paths: none
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- dharma_swarm | role canonical_core | branch main...origin/main | dirty False | modified 0 | untracked 0

## Language mix
- .py: 1125

## Largest Python files

## Most imported local modules`;
    const cleanPreview = workspaceSnapshotToPreview(cleanWorkspaceSnapshot);
    const nextState = applyActions(
      staleState,
      commandRunSnapshotActionsForBridgeEvent(
        {
          type: "command.result",
          command: "/git status",
          output: cleanWorkspaceSnapshot,
        },
        staleState.liveRepoPreview,
        staleState.liveControlPreview,
        null,
      ),
    );

    expect(nextState.liveRepoPreview).toMatchObject(cleanPreview);
    expect(nextState.liveRepoPreview?.["Topology warnings"]).toBe("0");
    expect(nextState.liveRepoPreview?.["Primary warning"]).toBe("none");
    expect(nextState.liveRepoPreview?.["Changed hotspots"]).toBe("none");
    expect(nextState.liveRepoPreview?.["Primary changed path"]).toBe("none");
    expect(nextState.liveRepoPreview?.["Primary dependency hotspot"]).toBe("none");
    expect(nextState.liveRepoPreview?.["Hotspot summary"]).toBe("none");
  });

  test("replaces stale loop and verification fields when a clean /runtime snapshot arrives", () => {
    const supervisor = {
      stateDir: "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260403T000000Z/state",
      cycle: 8,
      runStatus: "ready",
      tasksTotal: 4,
      tasksPending: 0,
      activeTaskId: "terminal-repo-pane",
      lastResultStatus: "complete",
      acceptance: "pass",
      verificationSummary: "tsc=ok | bridge_snapshots=ok",
      verificationChecks: ["tsc ok", "bridge_snapshots ok"],
      continueRequired: false,
      nextTask: "none",
      updatedAt: "2026-04-03T00:00:00Z",
    };
    const staleState: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
    };
    const runtimeSnapshot = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=4  Claims=0  ActiveClaims=0  AckedClaims=0  Runs=0  ActiveRuns=0
Artifacts=1  PromotedFacts=0  ContextBundles=0  OperatorActions=1`;
    const expectedPreview = runtimeSnapshotToPreview(runtimeSnapshot, supervisor);
    const nextState = applyActions(
      staleState,
      commandRunSnapshotActionsForBridgeEvent(
        {
          type: "command.result",
          command: "/runtime",
          output: runtimeSnapshot,
        },
        staleState.liveRepoPreview,
        staleState.liveControlPreview,
        supervisor,
      ),
    );

    expect(nextState.liveControlPreview).toEqual(expectedPreview);
    expect(nextState.liveControlPreview?.["Verification status"]).toBe("all 2 checks passing");
    expect(nextState.liveControlPreview?.["Verification failing"]).toBe("none");
    expect(nextState.liveControlPreview?.["Next task"]).toBe("none");
    expect(nextState.liveControlPreview?.["Loop decision"]).toBe("ready to stop");
  });
});

describe("surfaceRefreshActionsForBridgeEvent", () => {
  test("builds the visible context sidebar from payload-first live repo and control refreshes", () => {
    const supervisor = {
      cycle: 9,
      runStatus: "refreshing",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-repo-pane",
      lastResultStatus: "in_progress",
      acceptance: "fail",
      verificationSummary: "tsc=ok | cycle_acceptance=fail",
      verificationChecks: ["tsc ok", "cycle_acceptance fail"],
      continueRequired: true,
      nextTask: "Add a full payload-first sidebar verification path.",
      updatedAt: "2026-04-03T02:16:08Z",
    };
    const repoEvent = {
      type: "action.result",
      action_type: "surface.refresh",
      surface: "repo",
      payload: {
        version: "v1",
        domain: "workspace_snapshot",
        repo_root: "/Users/dhyana/dharma_swarm",
        git: {
          branch: "main",
          head: "804d5d1",
          staged: 112,
          unstaged: 515,
          untracked: 73,
          changed_hotspots: [{name: "terminal", count: 274}],
          changed_paths: ["terminal/src/components/Sidebar.tsx"],
          sync: {
            summary: "origin/main | ahead 2 | behind 0",
            status: "ahead of origin/main by 2",
            upstream: "origin/main",
            ahead: 2,
            behind: 0,
          },
        },
        topology: {
          warnings: ["peer_branch_diverged"],
          repos: [
            {
              domain: "dgc",
              name: "dharma_swarm",
              role: "canonical_core",
              canonical: true,
              path: "/Users/dhyana/dharma_swarm",
              exists: true,
              is_git: true,
              branch: "main...origin/main",
              dirty: true,
              modified_count: 515,
              untracked_count: 73,
            },
          ],
        },
        inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
        language_mix: [{suffix: ".py", count: 1125}],
        largest_python_files: [{path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208}],
        most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
      },
      output: "stale repo output should not render",
    } as const;
    const controlEvent = {
      type: "action.result",
      action_type: "surface.refresh",
      surface: "control",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-sidebar-refresh-1",
          created_at: "2026-04-03T02:16:08Z",
          updated_at: "2026-04-03T02:16:08Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 18,
          active_run_count: 1,
          artifact_count: 7,
          context_bundle_count: 1,
          anomaly_count: 0,
          verification_status: "failing",
          verification_summary: "tsc=ok | cycle_acceptance=fail",
          verification_bundle: "tsc=ok | cycle_acceptance=fail",
          next_task: "Add a full payload-first sidebar verification path.",
          active_task: "terminal-repo-pane",
          task_progress: "3 done, 1 pending of 4",
          loop_state: "cycle 9 refreshing",
          loop_decision: "continue required",
          result_status: "in_progress",
          acceptance: "fail",
          last_result: "in_progress / fail",
          summary: "1 active run, 1 context bundle, 7 artifacts",
          warnings: [],
          metrics: {
            claims: "2",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "3",
            promoted_facts: "2",
          },
          metadata: {overview: {runs: 1}},
        },
      },
      output: "stale runtime output should not render",
    } as const;

    const stateAfterRepo = applyActions(
      initialState,
      surfaceRefreshActionsForBridgeEvent(repoEvent, undefined, undefined, initialState.sessionPane, supervisor),
    );
    const state = applyActions(
      stateAfterRepo,
      surfaceRefreshActionsForBridgeEvent(
        controlEvent,
        stateAfterRepo.liveRepoPreview,
        stateAfterRepo.liveControlPreview,
        stateAfterRepo.sessionPane,
        supervisor,
      ),
    );
    const lines = buildVisibleContextSidebarLines(
      state.tabs,
      "Repo",
      "codex",
      "gpt-5.4",
      "connected",
      state.liveRepoPreview,
      state.liveControlPreview,
      new Date("2026-04-03T02:20:00Z"),
    );

    const controlPulseIndex = lines.findIndex((line) =>
      line.startsWith("Control pulse fresh | in_progress / fail | cycle 9 refreshing | updated 2026-04-03T02:16:08Z"),
    );
    const runtimeStateIndex = lines.findIndex((line) =>
      line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=18 Runs=1 Claims=2"),
    );
    const repoRiskPreviewIndex = lines.findIndex((line) =>
      line.startsWith("Repo risk preview ahead of origin/main by 2 | peer_branch_diverged"),
    );

    expect(lines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 1"))).toBe(true);
    expect(lines).toContain("Snapshot warning members peer_branch_diverged");
    expect(lines.some((line) => line.startsWith("Snapshot branch divergence local +2/-0 | peer dharma_swarm drift"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot runtime /Users/dhyana/.dharma/s"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail"))).toBe(
      true,
    );
    expect(lines.some((line) => line.startsWith("Snapshot truth tsc=ok | cycle_acceptance=fail | cycle 9 refreshing | n"))).toBe(
      true,
    );
    expect(controlPulseIndex).toBeGreaterThan(-1);
    expect(runtimeStateIndex).toBeGreaterThan(controlPulseIndex);
    expect(repoRiskPreviewIndex).toBeGreaterThan(runtimeStateIndex);
    expect(lines.some((line) => line.includes("stale repo output should not render"))).toBe(false);
    expect(lines.some((line) => line.includes("stale runtime output should not render"))).toBe(false);
  });

  test("uses typed workspace payloads when the bridge emits a payload-first repo refresh", () => {
    const actions = surfaceRefreshActionsForBridgeEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "repo",
      payload: {
        version: "v1",
        domain: "workspace_snapshot",
        repo_root: "/Users/dhyana/dharma_swarm",
        git: {
          branch: "main",
          head: "95210b1",
          staged: 0,
          unstaged: 12,
          untracked: 1,
          changed_hotspots: [{name: "terminal", count: 8}],
          changed_paths: ["terminal/src/app.tsx"],
          sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
        },
        topology: {
          warnings: ["sab_canonical_repo_missing"],
          repos: [
            {
              domain: "dgc",
              name: "dharma_swarm",
              role: "canonical_core",
              canonical: true,
              path: "/Users/dhyana/dharma_swarm",
              exists: true,
              is_git: true,
              branch: "main...origin/main",
              dirty: true,
              modified_count: 12,
              untracked_count: 1,
            },
          ],
        },
        inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
        language_mix: [{suffix: ".py", count: 1125}],
        largest_python_files: [{path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208}],
        most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
      },
      output: "stale textual repo output that should not be authoritative",
    });

    const state = applyActions(initialState, actions);
    const repoTab = state.tabs.find((tab) => tab.id === "repo");

    expect(repoTab?.preview?.Branch).toBe("main");
    expect(repoTab?.preview?.["Primary changed path"]).toBe("terminal/src/app.tsx");
    expect(repoTab?.lines.some((line) => line.text.includes("stale textual repo output"))).toBe(false);
  });

  test("uses typed workspace payloads when the bridge nests the refresh snapshot beside the request envelope", () => {
    const actions = surfaceRefreshActionsForBridgeEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "repo",
      payload: {
        request: {
          action_type: "surface.refresh",
          surface: "repo",
        },
        payload: {
          version: "v1",
          domain: "workspace_snapshot",
          repo_root: "/Users/dhyana/dharma_swarm",
          git: {
            branch: "main",
            head: "95210b1",
            staged: 2,
            unstaged: 7,
            untracked: 1,
            changed_hotspots: [{name: "terminal", count: 9}],
            changed_paths: ["terminal/src/protocol.ts"],
            sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
          },
          topology: {
            warnings: [],
            repos: [],
          },
          inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
          language_mix: [{suffix: ".ts", count: 32}],
          largest_python_files: [],
          most_imported_modules: [],
        },
        output: "stale textual repo output that should not be authoritative",
      },
    });

    const state = applyActions(initialState, actions);
    const repoTab = state.tabs.find((tab) => tab.id === "repo");

    expect(repoTab?.preview?.Branch).toBe("main");
    expect(repoTab?.preview?.Dirty).toBe("2 staged, 7 unstaged, 1 untracked");
    expect(repoTab?.preview?.["Primary changed path"]).toBe("terminal/src/protocol.ts");
    expect(repoTab?.lines.some((line) => line.text.includes("stale textual repo output"))).toBe(false);
  });

  test("clears stale repo warning and hotspot fields on authoritative repo refresh", () => {
    const cleanPayload = {
      version: "v1",
      domain: "workspace_snapshot",
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "95210b1",
        staged: 0,
        unstaged: 0,
        untracked: 0,
        changed_hotspots: [],
        changed_paths: [],
        sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
      },
      topology: {
        warnings: [],
        repos: [
          {
            domain: "dgc",
            name: "dharma_swarm",
            role: "canonical_core",
            canonical: true,
            path: "/Users/dhyana/dharma_swarm",
            exists: true,
            is_git: true,
            branch: "main...origin/main",
            dirty: false,
            modified_count: 0,
            untracked_count: 0,
          },
        ],
      },
      inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
      language_mix: [{suffix: ".py", count: 1125}],
      largest_python_files: [],
      most_imported_modules: [],
    } as const;
    const cleanPreview = workspacePayloadToPreview(cleanPayload);
    const actions = surfaceRefreshActionsForBridgeEvent(
      {
        type: "action.result",
        action_type: "surface.refresh",
        surface: "repo",
        payload: cleanPayload,
      },
      bootstrapWorkspacePreview,
      bootstrapRuntimePreview,
    );

    const state = applyActions(
      {
        ...initialState,
        liveRepoPreview: bootstrapWorkspacePreview,
        liveControlPreview: bootstrapRuntimePreview,
      },
      actions,
    );
    const sidebarLines = buildContextSidebarLines(
      state.tabs,
      "Repo",
      state.provider,
      state.model,
      state.bridgeStatus,
      state.liveRepoPreview,
      state.liveControlPreview,
    );

    expect(state.liveRepoPreview).toMatchObject(cleanPreview);
    expect(state.liveRepoPreview?.["Topology warnings"]).toBe("0");
    expect(state.liveRepoPreview?.["Primary warning"]).toBe("none");
    expect(state.liveRepoPreview?.["Changed hotspots"]).toBe("none");
    expect(state.liveRepoPreview?.["Primary changed path"]).toBe("none");
    expect(state.liveRepoPreview?.["Primary dependency hotspot"]).toBe("none");
    expect(state.liveRepoPreview?.["Hotspot summary"]).toBe("none");
    expect(sidebarLines).toContain("Warnings 0");
    expect(sidebarLines).toContain("Changed none");
    expect(sidebarLines.some((line) => line.includes("terminal/src/protocol.ts"))).toBe(false);
  });

  test("clears stale loop and verification fields on authoritative runtime refresh", () => {
    const supervisor = {
      stateDir: "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260403T000000Z/state",
      cycle: 9,
      runStatus: "verifying",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-repo-pane",
      lastResultStatus: "in_progress",
      acceptance: "pass",
      verificationSummary: "tsc=ok | bridge_snapshots=ok",
      verificationChecks: ["tsc ok", "bridge_snapshots ok"],
      continueRequired: true,
      nextTask: "Ship the repo pane polish.",
      updatedAt: "2026-04-03T01:00:00Z",
    };
    const payload = {
      version: "v1",
      domain: "runtime_snapshot",
      snapshot: {
        snapshot_id: "runtime-clean-refresh-1",
        created_at: "2026-04-03T01:00:00Z",
        repo_root: "/Users/dhyana/dharma_swarm",
        runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
        health: "ok",
        bridge_status: "connected",
        active_session_count: 6,
        active_run_count: 1,
        artifact_count: 2,
        context_bundle_count: 1,
        anomaly_count: 0,
        verification_status: "passing",
        next_task: "Ship the repo pane polish.",
        active_task: "terminal-repo-pane",
        summary: "1 active run, 1 context bundle, 2 artifacts",
        warnings: [],
        metrics: {
          claims: "1",
          active_claims: "1",
          acknowledged_claims: "1",
          operator_actions: "2",
          promoted_facts: "1",
        },
        metadata: {},
      },
    } as const;
    const expectedPreview = runtimePayloadToPreview(payload, supervisor);
    const actions = surfaceRefreshActionsForBridgeEvent(
      {
        type: "action.result",
        action_type: "surface.refresh",
        surface: "control",
        payload,
      },
      bootstrapWorkspacePreview,
      bootstrapRuntimePreview,
      initialState.sessionPane,
      supervisor,
    );
    const state = applyActions(
      {
        ...initialState,
        liveRepoPreview: bootstrapWorkspacePreview,
        liveControlPreview: bootstrapRuntimePreview,
      },
      actions,
    );

    expect(state.liveControlPreview).toEqual(expectedPreview);
    expect(state.liveControlPreview?.["Verification status"]).toBe("all 2 checks passing");
    expect(state.liveControlPreview?.["Verification failing"]).toBe("none");
    expect(state.liveControlPreview?.["Next task"]).toBe("Ship the repo pane polish.");
    expect(state.liveControlPreview?.["Loop state"]).toBe("cycle 9 verifying");
    expect(state.liveRepoPreview).toMatchObject(bootstrapWorkspacePreview);
    expect(state.liveRepoPreview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(state.liveRepoPreview?.["Repo/control preview"]).toContain("branch main@95210b1");
    expect(state.liveRepoPreview?.["Repo/control preview"]).toContain("cycle 9 verifying");
    expect(state.liveRepoPreview?.["Repo/control preview"]).toContain("verify tsc=ok | bridge_snapshots=ok");
  });

  test("uses typed session payloads when the bridge emits a payload-first sessions refresh", () => {
    const actions = surfaceRefreshActionsForBridgeEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "sessions",
      payload: {
        version: "v1",
        domain: "session_catalog",
        count: 1,
        sessions: [
          {
            session: {
              session_id: "sess_456",
              provider_id: "claude",
              model_id: "claude-opus-4-6",
              status: "running",
              branch_label: "feature/session-pane",
              summary: "inspect replay health",
            },
            replay_ok: false,
            replay_issues: ["truncated transcript"],
            total_turns: 3,
            total_cost_usd: 0.12,
          },
        ],
      },
    }, undefined, undefined, initialState.sessionPane);

    const state = applyActions(initialState, actions);
    const sessionsTab = state.tabs.find((tab) => tab.id === "sessions");

    expect(actions.some((action) => action.type === "session.catalog.set")).toBe(true);
    expect(sessionsTab?.preview?.["Latest session"]).toBe("sess_456");
    expect(sessionsTab?.lines.some((line) => line.text.includes("claude:claude-opus-4-6"))).toBe(true);
  });
});

describe("commandResultActionsForBridgeEvent", () => {
  test("uses pending command fallbacks for sparse slash command results", () => {
    expect(commandResultActionsForBridgeEvent(
      {
        type: "command.result",
        summary: "executed command.run",
      },
      "/runtime status",
      "runtime",
    )).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "/runtime -> runtime"},
    ]);
  });

  test("session bootstrap prefers typed workspace payload over sparse bootstrap repo preview", () => {
    const sparseBootstrapWorkspacePreview: TabPreview = {
      "Repo root": bootstrapWorkspacePreview["Repo root"],
      Branch: bootstrapWorkspacePreview.Branch,
      "Repo risk": bootstrapWorkspacePreview["Repo risk"],
    };
    const bootstrapWorkspacePayload = {
      version: "v1",
      domain: "workspace_snapshot",
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "95210b1",
        staged: 0,
        unstaged: 510,
        untracked: 42,
        changed_hotspots: [{name: "terminal", count: 274}],
        changed_paths: ["terminal/src/protocol.ts"],
        sync: {
          summary: "origin/main | ahead 0 | behind 0",
          status: "tracking",
          upstream: "origin/main",
          ahead: 0,
          behind: 0,
        },
      },
      topology: {
        warnings: ["sab_canonical_repo_missing"],
        repos: [
          {
            domain: "dgc",
            name: "dharma_swarm",
            role: "canonical_core",
            canonical: true,
            path: "/Users/dhyana/dharma_swarm",
            exists: true,
            is_git: true,
            branch: "main...origin/main",
            head: "95210b1",
            dirty: true,
            modified_count: 510,
            untracked_count: 42,
          },
          {
            domain: "sab",
            name: "dgc-core",
            role: "operator_shell",
            canonical: false,
            path: "/Users/dhyana/dgc-core",
            exists: false,
            is_git: false,
            branch: undefined,
            head: undefined,
            dirty: null,
            modified_count: 0,
            untracked_count: 0,
          },
        ],
        preview: "2 repos | warn sab_canonical_repo_missing | dharma_swarm dirty | dgc-core missing",
        pressure_preview: "1 warning | dharma_swarm Δ552 (510 modified, 42 untracked)",
      },
      inventory: {
        python_modules: 501,
        python_tests: 494,
        scripts: 124,
        docs: 239,
        workflows: 1,
      },
      language_mix: [{suffix: ".py", count: 1125}],
      largest_python_files: [{path: "terminal/src/protocol.ts", lines: 4044, defs: 0, classes: 0, imports: 0}],
      most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
    } as const;

    const state = applyActions(
      {
        ...initialState,
        liveRepoPreview: undefined,
        liveControlPreview: bootstrapRuntimePreview,
        tabs: initialState.tabs.map((tab) =>
          tab.id === "repo"
            ? {
                ...tab,
                lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}],
                preview: sparseBootstrapWorkspacePreview,
              }
            : tab,
        ),
      },
      snapshotActionsForBridgeEvent(
        {
          type: "session.bootstrap.result",
          workspace_preview: sparseBootstrapWorkspacePreview,
          workspace_payload: bootstrapWorkspacePayload,
          runtime_preview: bootstrapRuntimePreview,
        },
        undefined,
        bootstrapRuntimePreview,
      ),
    );

    expect(state.liveRepoPreview?.Branch).toBe("main");
    expect(state.liveRepoPreview?.Head).toBe("95210b1");
    expect(state.liveRepoPreview?.["Topology warnings"]).toBe("1 (sab_canonical_repo_missing)");
    expect(state.liveRepoPreview?.["Topology preview"]).toBe(
      "2 repos | warn sab_canonical_repo_missing | dharma_swarm dirty | dgc-core missing",
    );
    expect(state.liveRepoPreview?.["Hotspot summary"]).toBe(
      "change terminal (274) | files protocol.ts (4044 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    );
    expect(state.liveRepoPreview?.["Repo/control preview"]).toContain("task terminal-repo-pane");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("stale repo output");
  });

  test("session bootstrap prefers typed runtime payload over sparse bootstrap control preview", () => {
    const sparseBootstrapRuntimePreview: TabPreview = {
      "Runtime activity": "Sessions=18  Runs=0",
      "Artifact state": "Artifacts=7  ContextBundles=1",
      "Loop decision": "unknown",
    };
    const bootstrapRuntimePayload = {
      version: "v1" as const,
      domain: "runtime_snapshot" as const,
      snapshot: {
        snapshot_id: "runtime-bootstrap-1",
        created_at: "2026-04-03T02:16:08Z",
        repo_root: "/Users/dhyana/dharma_swarm",
        runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
        health: "ok",
        bridge_status: "connected",
        active_session_count: 18,
        active_run_count: 0,
        artifact_count: 7,
        context_bundle_count: 1,
        anomaly_count: 0,
        verification_status: "1 failing, 3/4 passing",
        verification_summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        verification_bundle: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        verification_checks: "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
        verification_passing: "tsc, py_compile_bridge, bridge_snapshots",
        verification_failing: "cycle_acceptance",
        loop_state: "cycle 5 running",
        loop_decision: "continue required",
        task_progress: "4 done, 1 pending of 5",
        result_status: "in_progress",
        acceptance: "fail",
        last_result: "in_progress / fail",
        updated_at: "2026-04-03T02:16:08Z",
        durable_state: "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260404T011956Z/state",
        runtime_summary: "/Users/dhyana/.dharma/state/runtime.db | 18 sessions | 0 active runs",
        runtime_freshness:
          "cycle 5 running | updated 2026-04-03T02:16:08Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
        next_task: "Thread typed runtime snapshot through session bootstrap.",
        active_task: "terminal-repo-pane",
        summary: "0 active runs, 1 context bundle, 7 artifacts",
        warnings: [],
        metrics: {
          claims: "0",
          active_claims: "0",
          acknowledged_claims: "0",
          operator_actions: "3",
          promoted_facts: "2",
        },
        metadata: {overview: {runs: 0}},
      },
    };
    const expectedPreview = runtimePayloadToPreview(bootstrapRuntimePayload);

    const state = applyActions(
      {
        ...initialState,
        liveRepoPreview: undefined,
        liveControlPreview: bootstrapRuntimePreview,
        tabs: initialState.tabs.map((tab) =>
          tab.id === "control" || tab.id === "runtime"
            ? {
                ...tab,
                lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
                preview: sparseBootstrapRuntimePreview,
              }
            : tab,
        ),
      },
      snapshotActionsForBridgeEvent(
        {
          type: "session.bootstrap.result",
          workspace_preview: bootstrapWorkspacePreview,
          runtime_preview: sparseBootstrapRuntimePreview,
          runtime_payload: bootstrapRuntimePayload,
        },
        undefined,
        bootstrapRuntimePreview,
      ),
    );

    expect(state.liveControlPreview).toMatchObject(expectedPreview);
    expect(state.liveControlPreview?.["Loop state"]).toBe("cycle 5 running");
    expect(state.liveControlPreview?.["Task progress"]).toBe("4 done, 1 pending of 5");
    expect(state.liveControlPreview?.["Next task"]).toBe("Thread typed runtime snapshot through session bootstrap.");
    expect(state.liveControlPreview?.["Verification status"]).toBe("1 failing, 3/4 passing");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "stale runtime output",
    );
  });

  test("prefers pending operator pane fallbacks over stale chat targets for sparse slash command results", () => {
    expect(commandResultActionsForBridgeEvent(
      {
        type: "command.result",
        target_pane: "chat",
        summary: "executed command.run",
      },
      "/git status",
      "repo",
    )).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "/git -> repo"},
    ]);
  });

  test("quarantines launcher-pane fallbacks for sparse slash command results", () => {
    expect(commandResultActionsForBridgeEvent(
      {
        type: "command.result",
        summary: "executed command.run",
      },
      undefined,
      "commands",
    )).toEqual([
      {type: "tab.activate", tabId: "control"},
      {type: "status.set", value: "executed command.run"},
    ]);
  });

  test("activates the command target pane and keeps repo output out of chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes model commands with trailing arguments into the model pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: false,
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/model set codex gpt-5.4",
      output: "Active route: codex:gpt-5.4",
    });

    expect(nextState.activeTabId).toBe("models");
    expect(nextState.modelPickerVisible).toBe(false);
    expect(nextState.tabs.find((tab) => tab.id === "models")?.lines.map((line) => line.text)).toContain(
      "Active route: codex:gpt-5.4",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines).toEqual(
      baseState.tabs.find((tab) => tab.id === "chat")?.lines,
  );
});

test("operator summary surfaces live loop, verification, and runtime state from the control preview", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    approvalPane: {
      entriesByActionId: {
        "approval-1": {
          decision: {
            version: "v1",
            domain: "permission_decision",
            action_id: "approval-1",
            tool_name: "shell",
            risk: "medium",
            decision: "require_approval",
            rationale: "needs review",
            policy_source: "test",
            requires_confirmation: true,
            metadata: {},
          },
          status: "pending",
          firstSeenAt: "2026-04-03T00:00:00Z",
          lastSeenAt: "2026-04-03T00:00:00Z",
          lastSourceEventType: "permission.decision",
          seenCount: 1,
          pending: true,
        },
      },
      order: ["approval-1"],
      historyBacked: true,
    },
    sessionPane: {
      catalog: {count: 22, sessions: []},
      detailsBySessionId: {},
    },
    liveControlPreview: {
      "Loop state": "cycle 7 waiting_for_verification",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
      "Runtime activity": "Sessions=22 Runs=3 ActiveRuns=1 Claims=4 ActiveClaims=1 AckedClaims=1",
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "connected", tone: "live"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 7 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "1 failing, 3/4 passing", tone: "critical"},
    {label: "runtime", value: "22 sessions | 3 runs | 1 active", tone: "live"},
    {label: "approvals", value: "1 pending", tone: "warn"},
    {label: "sessions", value: "22", tone: "live"},
  ]);
});

test("operator summary falls back to neutral loop and runtime state when control preview is not ready", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "booting",
    liveControlPreview: undefined,
    sessionPane: {
      catalog: {count: 0, sessions: []},
      detailsBySessionId: {},
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "booting", tone: "critical"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "unknown", tone: "neutral"},
    {label: "verify", value: "unknown", tone: "neutral"},
    {label: "runtime", value: "idle", tone: "neutral"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "0", tone: "neutral"},
  ]);
});

test("operator summary preserves generic verification fallback before detailed checks arrive", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    sessionPane: {
      catalog: {count: 3, sessions: []},
      detailsBySessionId: {},
    },
    liveControlPreview: {
      "Loop state": "cycle 8 waiting_for_verification",
      "Verification status": "ok",
      "Verification summary": "ok",
      "Runtime activity": "Sessions=3 Runs=1 ActiveRuns=1",
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "connected", tone: "live"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 8 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "ok", tone: "live"},
    {label: "runtime", value: "3 sessions | 1 runs | 1 active", tone: "live"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "3", tone: "live"},
  ]);
});

test("operator summary derives verification state from an explicit durable bundle when summary stays generic", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    sessionPane: {
      catalog: {count: 3, sessions: []},
      detailsBySessionId: {},
    },
    liveControlPreview: {
      "Loop state": "cycle 8 waiting_for_verification",
      "Verification summary": "ok",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime activity": "Sessions=3 Runs=1 ActiveRuns=1",
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "connected", tone: "live"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 8 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "1 failing, 2/3 passing", tone: "critical"},
    {label: "runtime", value: "3 sessions | 1 runs | 1 active", tone: "live"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "3", tone: "live"},
  ]);
});

test("operator summary derives verification state from passing and failing detail rows when summary is generic", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    sessionPane: {
      catalog: {count: 4, sessions: []},
      detailsBySessionId: {},
    },
    liveControlPreview: {
      "Loop state": "cycle 10 waiting_for_verification",
      "Verification status": "passing",
      "Verification summary": "ok",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "cycle_acceptance",
      "Runtime activity": "Sessions=4 Runs=2 ActiveRuns=1",
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "connected", tone: "live"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 10 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "1 failing, 2/3 passing", tone: "critical"},
    {label: "runtime", value: "4 sessions | 2 runs | 1 active", tone: "live"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "4", tone: "live"},
  ]);
});

test("operator summary derives loop and verification state from compact runtime freshness when explicit fields stay generic", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    sessionPane: {
      catalog: {count: 2, sessions: []},
      detailsBySessionId: {},
    },
    liveControlPreview: {
      "Loop state": "unknown",
      "Verification summary": "unknown",
      "Verification status": "unknown",
      "Runtime freshness": "cycle 11 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Control pulse preview":
        "fresh | complete / fail | cycle 11 waiting_for_verification | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Runtime activity": "Sessions=2 Runs=1 ActiveRuns=1",
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "connected", tone: "live"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 11 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "1 failing, 2/3 passing", tone: "critical"},
    {label: "runtime", value: "2 sessions | 1 runs | 1 active", tone: "live"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "2", tone: "live"},
  ]);
});

test("operator summary falls back to the persisted control preview when live control state is absent", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "degraded",
    liveControlPreview: undefined,
    tabs: initialState.tabs.map((tab) =>
      tab.id === "control"
        ? {
            ...tab,
            preview: {
              "Loop state": "cycle 9 waiting_for_verification",
              "Verification summary": "tsc=ok | py_compile_bridge=ok | cycle_acceptance=fail",
              "Verification checks": "tsc ok; py_compile_bridge ok; cycle_acceptance fail",
              "Runtime activity": "Sessions=5 Runs=1 ActiveRuns=1",
            },
          }
        : tab,
    ),
    sessionPane: {
      catalog: {count: 5, sessions: []},
      detailsBySessionId: {},
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "degraded", tone: "warn"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 9 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "1 failing, 2/3 passing", tone: "critical"},
    {label: "runtime", value: "5 sessions | 1 runs | 1 active", tone: "live"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "5", tone: "live"},
  ]);
});

test("operator summary prefers non-placeholder control tab preview values over generic live control placeholders", () => {
  const state: AppState = {
    ...initialState,
    bridgeStatus: "connected",
    liveControlPreview: {
      "Loop state": "unknown",
      "Verification summary": "unknown",
      "Verification status": "unknown",
      "Runtime summary": "unknown",
    },
    tabs: initialState.tabs.map((tab) =>
      tab.id === "control"
        ? {
            ...tab,
            preview: {
              "Loop state": "cycle 12 waiting_for_verification",
              "Verification summary": "tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
              "Verification checks": "tsc ok; bridge_snapshots ok; cycle_acceptance fail",
              "Runtime activity": "Sessions=4 Runs=2 ActiveRuns=1",
            },
          }
        : tab,
    ),
    sessionPane: {
      catalog: {count: 4, sessions: []},
      detailsBySessionId: {},
    },
  };

  expect(buildOperatorSummaryItems(state)).toEqual([
    {label: "bridge", value: "connected", tone: "live"},
    {label: "route", value: DEFAULT_ROUTE_LABEL, tone: "neutral"},
    {label: "strategy", value: "responsive", tone: "neutral"},
    {label: "loop", value: "cycle 12 waiting_for_verification", tone: "warn"},
    {label: "verify", value: "1 failing, 2/3 passing", tone: "critical"},
    {label: "runtime", value: "4 sessions | 2 runs | 1 active", tone: "live"},
    {label: "approvals", value: "clear", tone: "live"},
    {label: "sessions", value: "4", tone: "live"},
  ]);
});

  test("routes the /models alias into the model pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: false,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "models"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/models",
      output: "Available routes: codex:gpt-5.4",
    });

    expect(nextState.activeTabId).toBe("models");
    expect(nextState.tabs.find((tab) => tab.id === "models")?.lines.map((line) => line.text)).toContain(
      "Available routes: codex:gpt-5.4",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/models -> models");
  });

  test("opens the model picker for bare /models command results without duplicating policy refreshes", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: false,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "models"
            ? {...tab, lines: []}
            : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    onEvent({
      type: "command.result",
      command: "/models",
      output: "Available routes: codex:gpt-5.4",
    });

    expect(state.activeTabId).toBe("models");
    expect(state.uiMode.activeOverlay).toEqual({
      kind: "modelPicker",
      selectedIndex: 0,
      returnTabId: "chat",
    });
    expect(state.tabs.find((tab) => tab.id === "models")?.lines.map((line) => line.text)).toContain(
      "Available routes: codex:gpt-5.4",
    );
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("opens the model picker for bare /models command.run action results without polluting chat", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: false,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "models"
            ? {...tab, lines: []}
            : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    onEvent({
      type: "action.result",
      payload: {
        action_type: "command.run",
        request: {
          command: "/models",
        },
        output: "Available routes: codex:gpt-5.4",
      },
    });

    expect(state.activeTabId).toBe("models");
    expect(state.uiMode.activeOverlay).toEqual({
      kind: "modelPicker",
      selectedIndex: 0,
      returnTabId: "chat",
    });
    expect(state.tabs.find((tab) => tab.id === "models")?.lines.map((line) => line.text)).toContain(
      "Available routes: codex:gpt-5.4",
    );
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("keeps /model set command results out of the picker refresh path", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: false,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "models"
            ? {...tab, lines: []}
            : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    onEvent({
      type: "command.result",
      command: "/model set codex gpt-5.4",
      output: "Active route: codex:gpt-5.4",
    });

    expect(state.activeTabId).toBe("models");
    expect(state.modelPickerVisible).toBe(false);
    expect(state.tabs.find((tab) => tab.id === "models")?.lines.map((line) => line.text)).toContain(
      "Active route: codex:gpt-5.4",
    );
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("routes runtime commands into the runtime pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "control"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("routes dashboard commands into the control pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/dashboard",
      output: "Verification summary: tsc=ok | cycle_acceptance=ok",
    });

    expect(nextState.activeTabId).toBe("control");
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Verification summary: tsc=ok | cycle_acceptance=ok",
    );
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).not.toContain(
      "Verification summary: tsc=ok | cycle_acceptance=ok",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/dashboard -> control");
  });

  test("routes trishula command results into the agents pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "agents"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/trishula inbox",
      output: "Unread trishula notes: 3",
    });

    expect(nextState.activeTabId).toBe("agents");
    expect(nextState.tabs.find((tab) => tab.id === "agents")?.lines.map((line) => line.text)).toContain(
      "Unread trishula notes: 3",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/trishula -> agents");
  });

  test("routes hum command results into the agents pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "agents" || tab.id === "sessions"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/hum",
      target_pane: "agents",
      output: "Hum lane: 2 pending dispatches",
    });

    expect(nextState.activeTabId).toBe("agents");
    expect(nextState.tabs.find((tab) => tab.id === "agents")?.lines.map((line) => line.text)).toContain(
      "Hum lane: 2 pending dispatches",
    );
    expect(nextState.tabs.find((tab) => tab.id === "sessions")?.lines.map((line) => line.text)).not.toContain(
      "Hum lane: 2 pending dispatches",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/hum -> agents");
  });

  test("prefers an explicit target pane on command results over local command inference", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "control"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      target_pane: "control",
      output: "Command override landed in control",
    });

    expect(nextState.activeTabId).toBe("control");
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Command override landed in control",
    );
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain(
      "Command override landed in control",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> control");
  });

  test("ignores an explicit chat target pane for operational command results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      target_pane: "chat",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("keeps chat control command results out of the chat transcript", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/reset",
      target_pane: "repo",
      output: "Conversation memory reset.",
    });

    expect(nextState.activeTabId).toBe("chat");
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines).toEqual([]);
    expect(nextState.statusLine).toBe("/reset -> chat");
  });

  test("normalizes workspace target pane aliases onto the repo pane", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      target_pane: "workspace",
      output: "Command override landed in repo",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Command override landed in repo",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("normalizes legacy notes targets onto the sessions pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "sessions"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/memory",
      target_pane: "notes",
      output: "Session memory lane",
    });

    expect(nextState.activeTabId).toBe("sessions");
    expect(nextState.tabs.find((tab) => tab.id === "sessions")?.lines.map((line) => line.text)).toContain(
      "Session memory lane",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/memory -> sessions");
  });

  test("routes explicit approvals pane targets without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "approvals"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      target_pane: "approvals",
      output: "Approval review: repo write pending",
    });

    expect(nextState.activeTabId).toBe("approvals");
    expect(nextState.tabs.find((tab) => tab.id === "approvals")?.lines.map((line) => line.text)).toContain(
      "Approval review: repo write pending",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> approvals");
  });

  test("ignores launcher-pane targets on command results and activates the inferred operator pane", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "commands"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      target_pane: "commands",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "commands")?.lines.map((line) => line.text)).not.toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("quarantines sparse launcher-pane command results into control instead of reopening the launcher", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "commands"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      target_pane: "commands",
      output: "Operator summary refreshed",
    });

    expect(nextState.activeTabId).toBe("control");
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Operator summary refreshed",
    );
    expect(nextState.tabs.find((tab) => tab.id === "commands")?.lines.map((line) => line.text)).not.toContain(
      "Operator summary refreshed",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("action applied");
  });

  test("ignores invalid explicit target panes and falls back to slash-command routing", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "control"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/runtime",
      target_pane: "not-a-real-pane",
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("honors the bridge runtime target pane without leaking output into chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "control"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/runtime",
      target_pane: "runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("derives command-result status from the summary when command is omitted", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      summary: "executed /git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("activates the inferred operator pane for summary-only command results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      summary: "executed /git status",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines).toEqual([]);
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("ignores filesystem paths when deriving command-result routing from the summary", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      summary: "wrote snapshot to /Users/dhyana/dharma_swarm/state and then executed /git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("promotes /git workspace snapshots from command results into normalized repo rows immediately", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      liveRepoPreview: {
        ...bootstrapWorkspacePreview,
        "Primary warning": "sab_canonical_repo_missing",
        "Primary changed hotspot": "terminal (274)",
      },
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {
                ...tab,
                lines: [
                  {id: "repo-stale-1", kind: "system", text: "# /git"},
                  {id: "repo-stale-2", kind: "system", text: "old repo transcript"},
                ],
              }
            : tab,
      ),
    };

    const gitOutput = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48
Git hotspots: dharma_swarm (301); terminal (284); .dharma_psmv_hyperfile_branch (147)
Git changed paths: dharma_swarm/terminal_bridge.py; terminal/src/app.tsx; terminal/tests/app.test.ts
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: peer_branch_diverged
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 518 | untracked 48
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511

## Largest Python files
- dharma_swarm/terminal_bridge.py | 7012 lines | defs 193 | imports 208

## Most imported local modules
- dharma_swarm.models | inbound 159`;

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git",
      output: gitOutput,
    });

    const repoTab = nextState.tabs.find((tab) => tab.id === "repo");
    expect(nextState.activeTabId).toBe("repo");
    expect(repoTab?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(workspaceSnapshotToPreview(gitOutput)).map((line) => line.text),
    );
    expect(repoTab?.lines.map((line) => line.text)).not.toContain("# Workspace X-Ray");
    expect(repoTab?.lines.map((line) => line.text)).not.toContain("old repo transcript");
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });
});

describe("actionResultActionsForBridgeEvent", () => {
  test("returns pane activation and status updates for wrapped slash command action results", () => {
    expect(actionResultActionsForBridgeEvent({
      type: "action.result",
      result: {
        payload: {
          action_type: "command.run",
          request: {
            command: "/git status",
            target_pane: "workspace",
          },
        },
      },
    })).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "/git -> repo"},
    ]);
  });

  test("uses pending command fallbacks for sparse slash command action results", () => {
    expect(actionResultActionsForBridgeEvent(
      {
        type: "action.result",
        action_type: "command.run",
        summary: "executed command.run",
      },
      "/runtime status",
      "runtime",
    )).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "/runtime -> runtime"},
    ]);
  });

  test("prefers pending operator pane fallbacks over stale chat targets for sparse slash command action results", () => {
    expect(actionResultActionsForBridgeEvent(
      {
        type: "action.result",
        action_type: "command.run",
        target_pane: "chat",
        summary: "executed command.run",
      },
      "/git status",
      "repo",
    )).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "/git -> repo"},
    ]);
  });

  test("quarantines launcher-pane fallbacks for sparse slash command action results", () => {
    expect(actionResultActionsForBridgeEvent(
      {
        type: "action.result",
        action_type: "command.run",
        summary: "executed command.run",
      },
      undefined,
      "commands",
    )).toEqual([
      {type: "tab.activate", tabId: "control"},
      {type: "status.set", value: "executed command.run"},
    ]);
  });

  test("keeps chat control command action results out of chat even when the bridge reports a non-chat target", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/reset",
      target_pane: "repo",
      summary: "executed /reset",
      output: "Conversation memory reset.",
    });

    expect(nextState.activeTabId).toBe("chat");
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines).toEqual([]);
    expect(nextState.statusLine).toBe("/reset -> chat");
  });

  test("activates the target pane for slash commands triggered through pane actions", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      target_pane: "repo",
      summary: "executed /git",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("derives the target pane from the command when pane action results omit target_pane", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/git status",
      summary: "executed /git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("normalizes workspace pane aliases for slash command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/git status",
      target_pane: "workspace",
      summary: "executed /git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes explicit approvals aliases for slash command action results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "approvals"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      target_pane: "permissions",
      summary: "executed /runtime",
      output: "Approval review: runtime restart pending",
    });

    expect(nextState.activeTabId).toBe("approvals");
    expect(nextState.tabs.find((tab) => tab.id === "approvals")?.lines.map((line) => line.text)).toContain(
      "Approval review: runtime restart pending",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> approvals");
  });

  test("ignores launcher-pane targets for slash command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "commands"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      target_pane: "registry",
      summary: "executed /runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "commands")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("ignores an explicit chat target for operational slash command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      target_pane: "chat",
      summary: "executed /runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("prefers nested operator pane targets over wrapper chat targets for slash command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "approvals"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      target_pane: "chat",
      request: {
        command: "/runtime",
        target_pane: "permissions",
      },
      output: "Approval review: runtime restart pending",
    });

    expect(nextState.activeTabId).toBe("approvals");
    expect(nextState.tabs.find((tab) => tab.id === "approvals")?.lines.map((line) => line.text)).toContain(
      "Approval review: runtime restart pending",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> approvals");
  });

  test("prefers the deepest nested operational pane target over conflicting wrapper panes", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab.id === "repo"
              ? {...tab, lines: []}
              : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      target_pane: "workspace",
      payload: {
        action_type: "command.run",
        request: {
          command: "/runtime status",
          target_pane: "runtime",
        },
        output: "Loop state: cycle 6 running",
      },
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines).toEqual([]);
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("derives the runtime pane from runtime command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "control"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      summary: "executed /runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("derives the control pane from dashboard command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/dashboard",
      summary: "executed /dashboard",
      output: "Loop state: cycle 3 running",
    });

    expect(nextState.activeTabId).toBe("control");
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 3 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 3 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes trishula command action results into the agents pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "agents" || tab.id === "ontology"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/trishula inbox",
      target_pane: "agents",
      summary: "executed /trishula inbox",
      output: "Unread trishula notes: 3",
    });

    expect(nextState.activeTabId).toBe("agents");
    expect(nextState.tabs.find((tab) => tab.id === "agents")?.lines.map((line) => line.text)).toContain(
      "Unread trishula notes: 3",
    );
    expect(nextState.tabs.find((tab) => tab.id === "ontology")?.lines.map((line) => line.text)).not.toContain(
      "Unread trishula notes: 3",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("normalizes direct runtime command results into the runtime and control panes", () => {
    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}], preview: bootstrapRuntimePreview}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/runtime",
      summary: "executed /runtime",
      output: runtimeContent,
    });

    const expectedPreview = runtimeSnapshotToPreview(runtimeContent, null);
    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.liveControlPreview).toEqual(expectedPreview);
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual(["existing conversation"]);
  });

  test("derives the repo pane from the slash command embedded in an action summary", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      summary: "executed /git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("promotes typed runtime snapshot payloads from command.run results without appending raw runtime fallback text", () => {
    const payload = {
      version: "v1" as const,
      domain: "runtime_snapshot" as const,
      snapshot: {
        snapshot_id: "snap-1",
        created_at: "2026-04-04T00:00:00Z",
        repo_root: "/Users/dhyana/dharma_swarm",
        runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
        health: "ok",
        bridge_status: "connected",
        active_session_count: 2,
        active_run_count: 1,
        artifact_count: 3,
        context_bundle_count: 1,
        anomaly_count: 0,
        verification_status: "ok",
        verification_summary: "tsc=ok | cycle_acceptance=ok",
        verification_bundle: "tsc=ok | cycle_acceptance=ok",
        loop_state: "cycle 3 running",
        loop_decision: "continue required",
        task_progress: "3 done, 1 pending of 4",
        result_status: "complete",
        acceptance: "ok",
        last_result: "complete / ok",
        updated_at: "2026-04-04T00:00:00Z",
        durable_state: "/Users/dhyana/.dharma/terminal_supervisor/state",
        next_task: "none",
        active_task: "terminal-command-routing",
        warnings: [],
        metrics: {
          claims: "1",
          active_claims: "1",
          acknowledged_claims: "0",
          promoted_facts: "2",
          operator_actions: "3",
          runs: "1",
        },
        metadata: {},
      },
    };
    const expectedPreview = runtimePayloadToPreview(payload);
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "control"
            ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}]}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      request: {command: "/runtime", target_pane: "runtime"},
      output: "raw runtime fallback should stay out of the transcript",
      payload,
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).not.toContain(
      "raw runtime fallback should stay out of the transcript",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("routes nested slash command action payloads into the inferred pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "commands"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      request: {
        command: "/runtime status",
        target_pane: "registry",
      },
      output: "Loop state: cycle 6 running",
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "commands")?.lines.map((line) => line.text)).not.toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("derives the repo pane from an inline-code slash command embedded in an action summary", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "control"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      summary: "executed `/git status`",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes payload-wrapped slash command action results into the inferred pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          target_pane: "workspace",
        },
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes request-payload-wrapped slash command action results into the inferred pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          payload: {
            command: "/git status",
            target_pane: "workspace",
          },
        },
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("promotes typed workspace snapshot payloads from command results without appending raw repo fallback text", () => {
    const payload = {
      version: "v1" as const,
      domain: "workspace_snapshot" as const,
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "804d5d1",
        staged: 1,
        unstaged: 2,
        untracked: 3,
        changed_hotspots: [{name: "terminal", count: 4}],
        changed_paths: ["terminal/src/app.tsx"],
        sync: {summary: "origin/main ahead 2", status: "ahead", upstream: "origin/main", ahead: 2, behind: 0},
      },
      topology: {warnings: [], repos: []},
      inventory: {python_modules: 10, python_tests: 20, scripts: 3, docs: 4, workflows: 1},
      language_mix: [{suffix: ".ts", count: 12}],
      largest_python_files: [],
      most_imported_modules: [],
    };
    const expectedPreview = workspacePayloadToPreview(payload);
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}]}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      target_pane: "repo",
      output: "raw repo fallback should stay out of the transcript",
      payload,
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain(
      "raw repo fallback should stay out of the transcript",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes payload-wrapped slash command output into the inferred pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/runtime status",
          target_pane: "registry",
        },
        output: "Loop state: cycle 6 running",
      },
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("routes object-wrapped command envelopes into the inferred pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: {
        arguments: {
          command: "/git status",
        },
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("honors explicit target panes nested inside object-wrapped command arguments without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: {
        arguments: {
          command: "/git status",
          target_pane: "dashboard",
        },
      },
      output: "Command override landed in control",
    });

    expect(nextState.activeTabId).toBe("control");
    expect(nextState.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Command override landed in control",
    );
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain(
      "Command override landed in control",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> control");
  });

  test("routes payload-wrapped camelCase target panes and content aliases without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          targetPane: "workspace",
        },
        content: "Repo dirty: 517 unstaged, 47 untracked",
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes payload-wrapped target-surface-id aliases without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          targetSurfaceId: "workspace",
        },
        output: "Repo dirty: 517 unstaged, 47 untracked",
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes payload-wrapped surface aliases without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          targetSurface: "workspace",
        },
        content: "Repo dirty: 517 unstaged, 47 untracked",
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes session command action results into the sessions pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "sessions"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/session recent",
      target_pane: "sessions",
      summary: "executed /session recent",
      output: "Recent sessions: sess_123, sess_122",
    });

    expect(nextState.activeTabId).toBe("sessions");
    expect(nextState.tabs.find((tab) => tab.id === "sessions")?.lines.map((line) => line.text)).toContain(
      "Recent sessions: sess_123, sess_122",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes stderr-only slash command results into the inferred pane without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/runtime status",
          target_pane: "registry",
        },
        stderr: "Runtime probe failed: supervisor socket unavailable",
      },
    });

    expect(nextState.activeTabId).toBe("runtime");
    expect(nextState.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Runtime probe failed: supervisor socket unavailable",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/runtime -> runtime");
  });

  test("activates the inferred pane for payload-only command.run action results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      payload: {
        action_type: "command.run",
        request: {
          command: "/git status",
          target_pane: "workspace",
        },
        output: "Repo dirty: 517 unstaged, 47 untracked",
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toContain(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes pane and tab aliases for slash command action results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const paneState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/memory recent",
          pane: "notes",
        },
        output: "Recent memory lane",
      },
    });

    expect(paneState.activeTabId).toBe("sessions");
    expect(paneState.tabs.find((tab) => tab.id === "sessions")?.lines.at(-1)?.text).toBe("Recent memory lane");
    expect(paneState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);

    const tabState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          tabId: "workspace",
        },
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(tabState.activeTabId).toBe("repo");
    expect(tabState.tabs.find((tab) => tab.id === "repo")?.lines.at(-1)?.text).toBe(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(tabState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes target-tab aliases for slash command action results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const targetTabState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/memory recent",
          target_tab: "notes",
        },
        output: "Recent memory lane",
      },
    });

    expect(targetTabState.activeTabId).toBe("sessions");
    expect(targetTabState.tabs.find((tab) => tab.id === "sessions")?.lines.at(-1)?.text).toBe("Recent memory lane");
    expect(targetTabState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);

    const targetTabIdState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/git status",
          targetTabId: "workspace",
        },
      },
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(targetTabIdState.activeTabId).toBe("repo");
    expect(targetTabIdState.tabs.find((tab) => tab.id === "repo")?.lines.at(-1)?.text).toBe(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(targetTabIdState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes target-pane-id aliases for slash command results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const camelCaseState = applyBridgeEvent(baseState, {
      type: "command.result",
      command: "/git status",
      targetPaneId: "approval",
      output: "Review pending: repo write requires approval",
    });

    expect(camelCaseState.activeTabId).toBe("approvals");
    expect(camelCaseState.tabs.find((tab) => tab.id === "approvals")?.lines.at(-1)?.text).toBe(
      "Review pending: repo write requires approval",
    );
    expect(camelCaseState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);

    const snakeCaseState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      payload: {
        request: {
          command: "/memory recent",
          target_pane_id: "notes",
        },
        output: "Recent memory lane",
      },
    });

    expect(snakeCaseState.activeTabId).toBe("sessions");
    expect(snakeCaseState.tabs.find((tab) => tab.id === "sessions")?.lines.at(-1)?.text).toBe("Recent memory lane");
    expect(snakeCaseState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
  });

  test("routes result-wrapped slash command action results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      result: {
        request: {
          command: "/git status",
          target_pane: "workspace",
        },
        output: "Repo dirty: 517 unstaged, 47 untracked",
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.at(-1)?.text).toBe(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes result-payload-wrapped slash command action results without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      result: {
        payload: {
          action_type: "command.run",
          request: {
            command: "/git status",
            target_pane: "workspace",
          },
          output: "Repo dirty: 517 unstaged, 47 untracked",
        },
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.at(-1)?.text).toBe(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("routes doubly wrapped request-result payloads without mutating chat", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      result: {
        request: {
          result: {
            payload: {
              action_type: "command.run",
              command: "/git status",
              target_pane: "workspace",
            },
          },
        },
        output: "Repo dirty: 517 unstaged, 47 untracked",
      },
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.at(-1)?.text).toBe(
      "Repo dirty: 517 unstaged, 47 untracked",
    );
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("keeps summary-only slash command action results out of chat while still activating the inferred pane", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      summary: "executed /git status",
    });

    expect(nextState.activeTabId).toBe("repo");
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines).toEqual([]);
    expect(nextState.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(nextState.statusLine).toBe("/git -> repo");
  });

  test("promotes /git workspace snapshots into normalized repo rows immediately", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      liveRepoPreview: {
        ...bootstrapWorkspacePreview,
        "Primary warning": "sab_canonical_repo_missing",
        "Primary changed hotspot": "terminal (274)",
      },
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: workspacePreviewToLines({
                ...bootstrapWorkspacePreview,
                "Primary warning": "sab_canonical_repo_missing",
                "Primary changed hotspot": "terminal (274)",
              }),
              preview: {
                ...bootstrapWorkspacePreview,
                "Primary warning": "sab_canonical_repo_missing",
                "Primary changed hotspot": "terminal (274)",
              },
            }
          : tab,
      ),
    };

    const gitOutput = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48
Git hotspots: dharma_swarm (301); terminal (284); .dharma_psmv_hyperfile_branch (147)
Git changed paths: dharma_swarm/terminal_bridge.py; terminal/src/app.tsx; terminal/tests/app.test.ts
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: peer_branch_diverged
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 518 | untracked 48
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511

## Largest Python files
- dharma_swarm/terminal_bridge.py | 7012 lines | defs 193 | imports 208

## Most imported local modules
- dharma_swarm.models | inbound 159`;

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/git",
      summary: "executed /git",
      output: gitOutput,
    });

    const repoTab = nextState.tabs.find((tab) => tab.id === "repo");
    expect(nextState.activeTabId).toBe("repo");
    expect(repoTab?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(workspaceSnapshotToPreview(gitOutput)).map((line) => line.text),
    );
    expect(repoTab?.lines.map((line) => line.text)).not.toContain(gitOutput);

    const sections = buildRepoPaneSections(repoTab?.preview, repoTab?.lines ?? []);
    expect(sections[0]?.rows).toContain(
      "Dirty staged 0 | unstaged 518 | untracked 48 | topo 1 (peer_branch_diverged) | lead dharma_swarm (301)",
    );
    expect(sections[2]?.title).toBe("Repo Risk");
    expect(sections[2]?.rows).toContain("Lead warning peer_branch_diverged");
    expect(sections[1]?.rows).toContain("Lead change dharma_swarm (301) | path dharma_swarm/terminal_bridge.py");
  });

  test("keeps the repo preview normalized from /git command output through workspace refresh", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: [
                {id: "repo-stale-1", kind: "system", text: "# /git"},
                {id: "repo-stale-2", kind: "system", text: "old repo transcript"},
              ],
            }
          : tab,
      ),
    };

    const gitOutput = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48
Git hotspots: dharma_swarm (301); terminal (284); .dharma_psmv_hyperfile_branch (147)
Git changed paths: dharma_swarm/terminal_bridge.py; terminal/src/app.tsx; terminal/tests/app.test.ts
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: peer_branch_diverged
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 518 | untracked 48
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511

## Largest Python files
- dharma_swarm/terminal_bridge.py | 7012 lines | defs 193 | imports 208

## Most imported local modules
- dharma_swarm.models | inbound 159`;
    const gitPreview = workspaceSnapshotToPreview(gitOutput);

    const afterGit = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "command.run",
      command: "/git",
      summary: "executed /git",
      output: gitOutput,
    });

    expect(afterGit.activeTabId).toBe("repo");
    expect(afterGit.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(gitPreview).map((line) => line.text),
    );
    expect(afterGit.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("# Workspace X-Ray");
    expect(afterGit.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("old repo transcript");
    expect(afterGit.liveRepoPreview).toMatchObject(gitPreview);

    const sidebarAfterGit = buildContextSidebarLines(
      afterGit.tabs,
      "Repo",
      afterGit.provider,
      afterGit.model,
      afterGit.bridgeStatus,
      afterGit.liveRepoPreview,
      afterGit.liveControlPreview,
    );
    expect(sidebarAfterGit).toContain("Lead warn peer_branch_diverged");
    expect(sidebarAfterGit).toContain("Lead path dharma_swarm/terminal_bridge.py");

    const refreshContent = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208

## Most imported local modules
- dharma_swarm.models | inbound 159`;
    const refreshPreview = workspaceSnapshotToPreview(refreshContent);

    const afterRefresh = applyBridgeEvent(afterGit, {
      type: "workspace.snapshot.result",
      content: refreshContent,
    });

    expect(afterRefresh.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(refreshPreview).map((line) => line.text),
    );
    expect(afterRefresh.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("# Workspace X-Ray");
    expect(afterRefresh.liveRepoPreview).toMatchObject(refreshPreview);

    const sidebarAfterRefresh = buildContextSidebarLines(
      afterRefresh.tabs,
      "Repo",
      afterRefresh.provider,
      afterRefresh.model,
      afterRefresh.bridgeStatus,
      afterRefresh.liveRepoPreview,
      afterRefresh.liveControlPreview,
    );
    expect(sidebarAfterRefresh).toContain("Lead warn sab_canonical_repo_missing");
    expect(sidebarAfterRefresh).toContain("Lead path terminal/src/app.tsx");
    expect(sidebarAfterRefresh.some((line) => line.startsWith("Dirty high (563 local changes) | staged 0 | unstaged 517"))).toBe(true);
  });

  test("handles /git through the live bridge listener and keeps the sidebar repo preview stable after refresh", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      sidebarMode: "context",
      liveRepoPreview: {
        ...bootstrapWorkspacePreview,
        "Primary warning": "sab_canonical_repo_missing",
        "Primary changed path": "terminal/src/protocol.ts",
      },
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: [
                {id: "repo-stale-1", kind: "system", text: "# /git"},
                {id: "repo-stale-2", kind: "system", text: "stale transcript that should disappear"},
              ],
              preview: {
                ...bootstrapWorkspacePreview,
                "Primary warning": "sab_canonical_repo_missing",
                "Primary changed path": "terminal/src/protocol.ts",
              },
            }
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, preview: bootstrapRuntimePreview}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const gitOutput = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48
Git hotspots: dharma_swarm (301); terminal (284); .dharma_psmv_hyperfile_branch (147)
Git changed paths: dharma_swarm/terminal_bridge.py; terminal/src/app.tsx; terminal/tests/app.test.ts
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: peer_branch_diverged
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 518 | untracked 48
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511

## Largest Python files
- dharma_swarm/terminal_bridge.py | 7012 lines | defs 193 | imports 208

## Most imported local modules
- dharma_swarm.models | inbound 159`;

    onEvent({
      type: "action.result",
      action_type: "command.run",
      command: "/git",
      summary: "executed /git",
      output: gitOutput,
    });

    const repoAfterGit = state.tabs.find((tab) => tab.id === "repo");
    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(repoAfterGit?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(state.liveRepoPreview ?? workspaceSnapshotToPreview(gitOutput)).map((line) => line.text),
    );
    expect(repoAfterGit?.lines.map((line) => line.text)).not.toContain("stale transcript that should disappear");
      expect(sent.map((entry) => entry.type)).toEqual([
        "workspace.snapshot",
        "runtime.snapshot",
        "model.policy",
        "agent.routes",
        "evolution.surface",
    ]);

    const sidebarAfterGit = buildContextSidebarLines(
      state.tabs,
      "Repo",
      state.provider,
      state.model,
      state.bridgeStatus,
      state.liveRepoPreview,
      state.liveControlPreview,
    );
    expect(sidebarAfterGit).toContain("Lead warn peer_branch_diverged");
    expect(sidebarAfterGit).toContain("Lead path dharma_swarm/terminal_bridge.py");
    expect(sidebarAfterGit).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");

    const refreshContent = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511
- .json: 91
- .sh: 68

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208
- dharma_swarm/thinkodynamic_director.py | 5167 lines | defs 108 | imports 36

## Most imported local modules
- dharma_swarm.models | inbound 159
- dharma_swarm.stigmergy | inbound 35`;

    onEvent({
      type: "workspace.snapshot.result",
      content: refreshContent,
    });

    const repoAfterRefresh = state.tabs.find((tab) => tab.id === "repo");
    expect(repoAfterRefresh?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(state.liveRepoPreview ?? workspaceSnapshotToPreview(refreshContent)).map((line) => line.text),
    );

    const sidebarAfterRefresh = buildContextSidebarLines(
      state.tabs,
      "Repo",
      state.provider,
      state.model,
      state.bridgeStatus,
      state.liveRepoPreview,
      state.liveControlPreview,
    );
    expect(sidebarAfterRefresh).toContain("Lead warn sab_canonical_repo_missing");
    expect(sidebarAfterRefresh).toContain("Lead path terminal/src/app.tsx");
    expect(sidebarAfterRefresh).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");
    expect(sidebarAfterRefresh.some((line) => line.includes("stale transcript that should disappear"))).toBe(false);

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Repo_root).toBe("/Users/dhyana/dharma_swarm");
    expect(persisted.preview_Branch).toBe("main");
    expect(persisted.preview_Topology_warnings).toBe("1 (sab_canonical_repo_missing)");
    expect(persisted.preview_Hotspot_summary).toBe(state.liveRepoPreview?.["Hotspot summary"]);
  });

  test("handles runtime snapshot refresh through the live bridge listener and keeps the control preview stable", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "run.json"),
      JSON.stringify(
        {
          repo_root: "/Users/dhyana/dharma_swarm",
          updated_at: "2026-04-01T00:00:00Z",
          cycle: 6,
          status: "running",
          tasks_total: 4,
          tasks_pending: 1,
          last_task_id: "terminal-repo-pane",
          last_continue_required: true,
          last_summary_fields: {
            status: "complete",
            acceptance: "fail",
            next_task: "Add an app-level bootstrap/refresh snapshot test.",
          },
        },
        null,
        2,
      ),
    );

    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      sidebarMode: "context",
      liveRepoPreview: bootstrapWorkspacePreview,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [
                {id: `${tab.id}-stale-1`, kind: "system", text: "# /dashboard"},
                {id: `${tab.id}-stale-2`, kind: "system", text: "stale runtime transcript that should disappear"},
              ],
              preview: bootstrapRuntimePreview,
            }
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      command: "/dashboard",
      summary: "executed /dashboard",
      output: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("control");
    expect(state.statusLine).toBe("/dashboard -> control");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain("Loop state: cycle 6 running");
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;
    const supervisor = {
      stateDir,
      cycle: 6,
      runStatus: "running",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-repo-pane",
      lastResultStatus: "complete",
      acceptance: "fail",
      verificationSummary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      verificationChecks: ["tsc ok", "py_compile_bridge ok", "bridge_snapshots ok", "cycle_acceptance fail"],
      continueRequired: true,
      nextTask: "Add an app-level bootstrap/refresh snapshot test.",
      updatedAt: "2026-04-01T00:00:00Z",
    };
    const expectedPreview = runtimeSnapshotToPreview(runtimeContent, supervisor);

    onEvent({
      type: "runtime.snapshot.result",
      content: runtimeContent,
    });

    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "stale runtime transcript that should disappear",
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain("Result status: complete");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain("Acceptance: fail");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain("Updated: 2026-04-01T00:00:00Z");
    expect(state.liveControlPreview).toEqual(expectedPreview);

    const sidebarAfterRuntimeRefresh = buildContextSidebarLines(
      state.tabs,
      "Control",
      state.provider,
      state.model,
      state.bridgeStatus,
      state.liveRepoPreview,
      state.liveControlPreview,
    );
    expect(sidebarAfterRuntimeRefresh).toContain("Task terminal-repo-pane | 3 done, 1 pending of 4");
    expect(sidebarAfterRuntimeRefresh).toContain("Outcome complete | accept fail");
    expect(
      sidebarAfterRuntimeRefresh.some((line) =>
        line.startsWith("Sessions 23 sessions | 2 claims | 1 active claims | 1 acked"),
      ),
    ).toBe(true);
    expect(sidebarAfterRuntimeRefresh).toContain("Runs 3 runs | 1 active runs");
    expect(
      sidebarAfterRuntimeRefresh.some((line) =>
        line.startsWith("Context 9 artifacts | 3 promoted facts | 2 context bundles"),
      ),
    ).toBe(true);
    expect(sidebarAfterRuntimeRefresh.some((line) => line.startsWith("Activity Sessions=23 Claims=2 Ac"))).toBe(true);
    expect(sidebarAfterRuntimeRefresh.some((line) => line.includes("stale runtime transcript that should disappear"))).toBe(false);

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Runtime_activity).toBe("Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1");
    expect(persisted.preview_Artifact_state).toBe("Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4");
    expect(persisted.preview_Active_task).toBe("terminal-repo-pane");
  });

  test("projects live repo and runtime refreshes into repo pane and context sidebar pulse rows", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "run.json"),
      JSON.stringify(
        {
          repo_root: "/Users/dhyana/dharma_swarm",
          updated_at: "2026-04-01T00:00:00Z",
          cycle: 6,
          status: "running",
          tasks_total: 4,
          tasks_pending: 1,
          last_task_id: "terminal-repo-pane",
          last_continue_required: true,
          last_summary_fields: {
            status: "complete",
            acceptance: "fail",
            next_task: "Add an app-level bootstrap/refresh snapshot test.",
          },
        },
        null,
        2,
      ),
    );

    let state: AppState = {
      ...initialState,
      activeTabId: "repo",
      sidebarMode: "context",
      liveRepoPreview: {
        ...bootstrapWorkspacePreview,
        "Primary warning": "sab_canonical_repo_missing",
        "Primary changed path": "terminal/src/protocol.ts",
      },
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: [{id: "repo-stale", kind: "system", text: "stale repo transcript"}],
              preview: {
                ...bootstrapWorkspacePreview,
                "Primary warning": "sab_canonical_repo_missing",
                "Primary changed path": "terminal/src/protocol.ts",
              },
            }
          : tab.id === "control" || tab.id === "runtime"
            ? {
                ...tab,
                lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime transcript"}],
                preview: bootstrapRuntimePreview,
              }
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const refreshContent = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511
- .json: 91
- .sh: 68

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208
- dharma_swarm/thinkodynamic_director.py | 5167 lines | defs 108 | imports 36

## Most imported local modules
- dharma_swarm.models | inbound 159
- dharma_swarm.stigmergy | inbound 35`;
    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;

    onEvent({
      type: "workspace.snapshot.result",
      content: refreshContent,
    });
    onEvent({
      type: "runtime.snapshot.result",
      content: runtimeContent,
    });

    const repoTab = state.tabs.find((tab) => tab.id === "repo");
    const controlTab = state.tabs.find((tab) => tab.id === "control");
    const repoSections = buildRepoPaneSections(repoTab?.preview, repoTab?.lines ?? [], controlTab?.preview, controlTab?.lines ?? []);
    const visibleSidebarLines = buildVisibleContextSidebarLines(
      state.tabs,
      "Repo",
      state.routePolicy.provider,
      state.routePolicy.model,
      state.bridgeStatus,
      state.liveRepoPreview,
      state.liveControlPreview,
    );

    expect(repoSections[0]?.title).toBe("Operator Snapshot");
    expect(repoSections[0]?.rows).toContain("Git main@95210b1 | high (563 local changes) | sync tracking origin/main in sync");
    expect(repoSections[0]?.rows).toContain("Snapshot branch main@95210b1 | tracking origin/main in sync");
    expect(repoSections[0]?.rows).toContain(
      "Snapshot branch sync tracking origin/main in sync | +0/-0 | topology sab_canonical_repo_missing; high (563 local changes)",
    );
    expect(repoSections[0]?.rows).toContain("Dirty staged 0 | unstaged 517 | untracked 46 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)");
    expect(repoSections[0]?.rows).toContain("Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)");
    expect(repoSections[0]?.rows).toContain("Snapshot warnings sab_canonical_repo_missing | severity high");
    expect(repoSections[0]?.rows).toContain(
      "Snapshot alert high | warning sab_canonical_repo_missing | drift dharma_swarm track main...origin/main",
    );
    expect(repoSections[0]?.rows).toContain(
      "Snapshot hotspots change terminal (281) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159",
    );
    expect(repoSections[0]?.rows).toContain(
      "Snapshot hotspot summary change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | deps dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35 | paths terminal/src/app.tsx",
    );
    expect(repoSections[0]?.rows).toContain(
      "Snapshot truth branch main@95210b1 | dirty staged 0 | unstaged 517 | untracked 46 | warn sab_canonical_repo_missing | hotspot change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | deps dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35 | paths terminal/src/app.tsx",
    );
    expect(repoSections[0]?.rows).toContain(
      "Snapshot repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 517 | untracked 46 | warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty True) | peers dharma_swarm (canonical_core, main...origin/main, dirty True); dgc-core (operator_shell, n/a, dirty None) | drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main; dgc-core n/a | divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281) | summary change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93) | files dgc_cli.py (6908 lines); thinkodynamic_director.py (5167 lines) | deps dharma_swarm.models | inbound 159; dharma_swarm.stigmergy | inbound 35 | paths terminal/src/app.tsx | cycle 6 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(repoSections[0]?.rows).toContain(
      "Task terminal-repo-pane | complete/fail | tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(repoSections[0]?.rows).toContain(
      "Control pulse stale | complete / fail | cycle 6 running | updated 2026-04-01T00:00:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(repoSections[0]?.rows).toContain(
      "Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1 | Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4",
    );
    expect(repoSections[0]?.rows).toContain(
      "Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/fail",
    );
    expect(repoSections[0]?.rows).toContain(
      "Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail | next Add an app-level bootstrap/refresh snapshot test.",
    );
    expect(repoSections.flatMap((section) => section.rows).some((row) => row.includes("stale repo transcript"))).toBe(false);
    expect(repoSections.flatMap((section) => section.rows).some((row) => row.includes("stale runtime transcript"))).toBe(false);

    expect(visibleSidebarLines).toContain("Repo Preview");
    expect(visibleSidebarLines).toContain("Hotspot Focus");
    expect(visibleSidebarLines).toContain("Repo Risk");
    expect(visibleSidebarLines).toContain("Control Preview");
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot branch main@95210b1 | tracking origin/main"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot dirty high (563 local changes) | staged 0"))).toBe(true);
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Snapshot topology signal high | dharma_swarm track main...origin/main"),
      ),
    ).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot repo/control stale | task terminal-repo-pane"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot control preview stale | complete / fail | c…"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Pressure preview 1 warning | dharma_swarm Δ563"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot hotspot pressure change terminal (281) | dep dharma_swarm.models |"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Dirty staged 0 | unstaged 517 | un"))).toBe(true);
    const repoRiskPreviewIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Repo risk preview tracking origin/main in sync | sab_canonical_repo_missing"),
    );
    const snapshotRepoControlIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Snapshot repo/control stale | task terminal-repo-pane"),
    );
    const snapshotControlPreviewIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Snapshot control preview stale | complete / fail | c…"),
    );
    const pressurePreviewIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Pressure preview 1 warning | dharma_swarm Δ563"),
    );
    const hotspotPressureIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Snapshot hotspot pressure change terminal (281) | dep dharma_swarm.models |"),
    );
    const repoControlIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@95210b1 | tracking origin/main in sync | sab_canonical_repo_missing"),
    );
    const controlPulseIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Control pulse stale | complete / fail | cycle 6 running | updated 2026-04-01T00:00:00Z"),
    );
    const runtimeStateIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Runtime state /Users/dhyana/.dharma/state/runtime.db | Sessions=23 Claims=2"),
    );
    const controlTaskIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Control task terminal-repo-pane | 3 done, 1 pending of 4 | complete/fail"),
    );
    const controlVerifyIndex = visibleSidebarLines.findIndex((line) =>
      line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail"),
    );
    const hotspotFocusIndex = visibleSidebarLines.findIndex((line) => line === "Hotspot Focus");
    const repoRiskSectionIndex = visibleSidebarLines.findIndex((line) => line === "Repo Risk");
    const controlPreviewIndex = visibleSidebarLines.findIndex((line) => line === "Control Preview");
    expect(repoRiskPreviewIndex).toBeGreaterThan(-1);
    expect(snapshotRepoControlIndex).toBeGreaterThan(-1);
    expect(snapshotControlPreviewIndex).toBeGreaterThan(-1);
    expect(pressurePreviewIndex).toBeGreaterThan(-1);
    expect(hotspotPressureIndex).toBeGreaterThan(-1);
    expect(repoRiskPreviewIndex).toBeGreaterThan(snapshotRepoControlIndex);
    expect(controlPulseIndex).toBeGreaterThan(repoRiskPreviewIndex);
    expect(runtimeStateIndex).toBeGreaterThan(controlPulseIndex);
    expect(controlTaskIndex).toBeGreaterThan(runtimeStateIndex);
    expect(controlVerifyIndex).toBeGreaterThan(controlTaskIndex);
    expect(snapshotControlPreviewIndex).toBe(controlPulseIndex + 4);
    expect(pressurePreviewIndex).toBe(controlVerifyIndex + 1);
    expect(hotspotPressureIndex).toBe(pressurePreviewIndex + 1);
    expect(hotspotFocusIndex).toBe(hotspotPressureIndex + 1);
    expect(hotspotFocusIndex).toBeGreaterThan(controlVerifyIndex);
    expect(repoRiskSectionIndex).toBeGreaterThan(hotspotFocusIndex);
    expect(controlPreviewIndex).toBeGreaterThan(repoRiskSectionIndex);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, 2"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot branch sync tracking origin/main in sync | +0/-0"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot hotspots change terminal (281) | path terminal/src/app.tsx"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot hotspot summary change terminal (281); .dharma"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot truth branch main@95210b1 | dirty staged 0 | unstaged 517"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot focus Root /Users/dhyana/dharma_sw"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Snapshot focus ") && line.endsWith("| lead terminal/src/app.tsx"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Lead peer dharma_swarm (canonical_core, main...origin/main"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Pressure dharma_swarm Δ563"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.startsWith("Loop cycle 6 running | continue"))).toBe(true);
    expect(visibleSidebarLines.some((line) => line.includes("stale repo transcript"))).toBe(false);
    expect(visibleSidebarLines.some((line) => line.includes("stale runtime transcript"))).toBe(false);
  });

  test("normalizes direct dashboard command results through the live bridge listener and persists verification summary", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}], preview: bootstrapRuntimePreview}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;
    const expectedPreview = runtimeSnapshotToPreview(runtimeContent, {
      stateDir,
      cycle: 4,
      runStatus: "running",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-control-surface",
      lastResultStatus: "complete",
      acceptance: "fail",
      verificationSummary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      verificationChecks: ["tsc ok", "py_compile_bridge ok", "bridge_snapshots ok", "cycle_acceptance fail"],
      continueRequired: true,
      nextTask: "Add an app-level bootstrap/refresh snapshot test.",
      updatedAt: "2026-04-01T00:00:00Z",
    });

    onEvent({
      type: "command.result",
      command: "/dashboard",
      summary: "executed /dashboard",
      output: runtimeContent,
    });

    expect(state.activeTabId).toBe("control");
    expect(state.statusLine).toBe("/dashboard -> control");
    expect(state.liveControlPreview).toEqual(expectedPreview);
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual(["existing conversation"]);
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Verification_summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_bundle).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");
    expect(persisted.preview_Verification_failing).toBe("cycle_acceptance");
    expect(persisted.preview_Runtime_DB).toBe("/Users/dhyana/.dharma/state/runtime.db");
  });

  test("persists pane-triggered runtime command snapshots after optimistic activation resolves to the runtime pane", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = applyActions(
      {
        ...initialState,
        activeTabId: "control",
        liveControlPreview: bootstrapRuntimePreview,
        tabs: initialState.tabs.map((tab) =>
          tab.id === "chat"
            ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
            : tab.id === "control" || tab.id === "runtime"
              ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}], preview: bootstrapRuntimePreview}
              : tab,
        ),
      },
      paneActionStartActions({
        summary: "run /runtime",
        payload: {action_type: "command.run", command: "/runtime", target_pane: "chat"},
      }),
    );

    expect(state.activeTabId).toBe("runtime");
    expect(state.statusLine).toBe("command /runtime -> runtime");

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;
    const expectedPreview = runtimeSnapshotToPreview(runtimeContent, {
      stateDir,
      cycle: 4,
      runStatus: "running",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-control-surface",
      lastResultStatus: "complete",
      acceptance: "fail",
      verificationSummary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      verificationChecks: ["tsc ok", "py_compile_bridge ok", "bridge_snapshots ok", "cycle_acceptance fail"],
      continueRequired: true,
      nextTask: "Add an app-level bootstrap/refresh snapshot test.",
      updatedAt: "2026-04-01T00:00:00Z",
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      target_pane: "chat",
      summary: "executed /runtime",
      output: runtimeContent,
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.statusLine).toBe("/runtime -> runtime");
    expect(state.liveControlPreview).toEqual(expectedPreview);
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(expectedPreview).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual(["existing conversation"]);
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Verification_summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_bundle).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");
    expect(persisted.preview_Verification_failing).toBe("cycle_acceptance");
    expect(persisted.preview_Runtime_DB).toBe("/Users/dhyana/.dharma/state/runtime.db");
  });

  test("unwraps alias-envelope command-result runtime snapshots through the live bridge listener without appending raw snapshot text", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}], preview: bootstrapRuntimePreview}
            : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=23  Claims=2  ActiveClaims=1  AckedClaims=1  Runs=3  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;
    const expectedPreview = runtimeSnapshotToPreview(runtimeContent, {
      stateDir,
      cycle: 4,
      runStatus: "running",
      tasksTotal: 4,
      tasksPending: 1,
      activeTaskId: "terminal-control-surface",
      lastResultStatus: "complete",
      acceptance: "fail",
      verificationSummary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      verificationChecks: ["tsc ok", "py_compile_bridge ok", "bridge_snapshots ok", "cycle_acceptance fail"],
      continueRequired: true,
      nextTask: "Add an app-level bootstrap/refresh snapshot test.",
      updatedAt: "2026-04-01T00:00:00Z",
    });

    onEvent({
      type: "command.result",
      payload: {
        request: {
          command: "/runtime status",
          targetPane: "registry",
        },
        content: runtimeContent,
      },
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.statusLine).toBe("/runtime -> runtime");
    expect(state.liveControlPreview).toEqual(expectedPreview);

    const controlLines = state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text) ?? [];
    const runtimeLines = state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text) ?? [];
    expect(controlLines).toEqual(runtimePreviewToLines(expectedPreview).map((line) => line.text));
    expect(runtimeLines).toEqual(runtimePreviewToLines(expectedPreview).map((line) => line.text));
    expect(controlLines).not.toContain("stale runtime output");
    expect(runtimeLines).not.toContain("stale runtime output");
    expect(controlLines).not.toContain(runtimeContent);
    expect(runtimeLines).not.toContain(runtimeContent);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual(["existing conversation"]);
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Verification_summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_bundle).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");
    expect(persisted.preview_Runtime_DB).toBe("/Users/dhyana/.dharma/state/runtime.db");
  });

  test("routes bootstrap auto-executed operational commands to their resolved pane instead of chat", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-1",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "runtime",
        target_pane: "chat",
      },
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.statusLine).toBe("intent /runtime -> runtime");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/runtime", target_pane: "chat"},
      },
    ]);
  });

  test("keeps streamed slash command text out of chat while routing completions to the pending pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "repo",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      content: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);

    onEvent({
      type: "command.result",
      command: "/git status",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("keeps streamed chat-scoped slash command text out of the chat transcript", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/reset", tabId: "chat"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      content: "Conversation memory reset.",
    });

    expect(state.activeTabId).toBe("chat");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({
      command: "/reset",
      tabId: "chat",
      lastCompletedText: "Conversation memory reset.",
    });

    onEvent({
      type: "command.result",
      command: "/reset",
      output: "Conversation memory reset.",
    });

    expect(state.activeTabId).toBe("chat");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("activates the pending pane on slash-command text deltas without appending partial output", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/runtime", tabId: "runtime"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_delta",
      content: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({command: "/runtime", tabId: "runtime"});
  });

  test("routes streamed slash command completions into the pending target pane instead of chat", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      content: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({
      command: "/git status",
      tabId: "repo",
      lastCompletedText: "Repo dirty: 517 unstaged, 47 untracked",
    });
  });

  test("retargets streamed slash command deltas to an explicit operator pane before the final result arrives", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "control",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/dashboard", tabId: "control"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_delta",
      command: "/dashboard",
      target_pane: "runtime",
      content: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({command: "/dashboard", tabId: "runtime"});
  });

  test("retargets streamed slash command completions to an explicit operator pane without leaking into chat", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "control",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/dashboard", tabId: "control"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      command: "/dashboard",
      target_pane: "runtime",
      content: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual([
      "Loop state: cycle 6 running",
    ]);
    expect(state.tabs.find((tab) => tab.id === "control")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({
      command: "/dashboard",
      tabId: "runtime",
      lastCompletedText: "Loop state: cycle 6 running",
    });
  });

  test("projects streamed git snapshot completions into the repo pane without appending raw snapshot text or polluting chat", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}]}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    const gitOutput = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48
Git hotspots: dharma_swarm (301); terminal (284)
Git changed paths: dharma_swarm/terminal_bridge.py; terminal/src/app.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1`;

    onEvent({
      type: "text_complete",
      content: gitOutput,
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(workspaceSnapshotToPreview(gitOutput)).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain(gitOutput);
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("stale repo output");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({
      command: "/git status",
      tabId: "repo",
      lastCompletedText: gitOutput,
    });
  });

  test("projects streamed runtime snapshot completions into runtime/control without appending raw snapshot text or polluting chat", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime" || tab.id === "control"
            ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: `stale ${tab.id} output`}]}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/runtime", tabId: "runtime"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    const runtimeOutput = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=18  Runs=1  ActiveRuns=1
Artifacts=7  ContextBundles=1
Durable state: /Users/dhyana/.dharma/terminal_supervisor/terminal-20260403T220715Z/state`;

    onEvent({
      type: "text_complete",
      content: runtimeOutput,
    });

    const runtimeLines = state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text) ?? [];
    const controlLines = state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text) ?? [];
    expect(state.activeTabId).toBe("runtime");
    expect(runtimeLines).toEqual(controlLines);
    expect(runtimeLines).toContain("# Control Preview");
    expect(runtimeLines).toContain("Runtime DB: /Users/dhyana/.dharma/state/runtime.db");
    expect(runtimeLines).toContain("Session state: 18 sessions");
    expect(runtimeLines).toContain("Run state: 1 runs | 1 active runs");
    expect(runtimeLines).toContain("Context state: 7 artifacts | 1 context bundles");
    expect(runtimeLines).not.toContain(runtimeOutput);
    expect(runtimeLines).not.toContain("stale runtime output");
    expect(controlLines).not.toContain("stale control output");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toEqual({
      command: "/runtime",
      tabId: "runtime",
      lastCompletedText: runtimeOutput,
    });
  });

  test("deduplicates final slash command results after the streamed completion already populated the pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "runtime",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/runtime", tabId: "runtime"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      content: "Loop state: cycle 6 running",
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual([
      "Loop state: cycle 6 running",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("replays the final command result into an explicit override pane when streamed completion landed in a fallback pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "control",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/dashboard", tabId: "control"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      content: "Loop state: cycle 6 running",
    });

    onEvent({
      type: "command.result",
      command: "/dashboard",
      target_pane: "runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual([
      "Loop state: cycle 6 running",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("replays the final command.run action result into an explicit override pane when streamed completion landed in a fallback pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "control",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "control" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/dashboard", tabId: "control"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "text_complete",
      content: "Loop state: cycle 6 running",
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      command: "/dashboard",
      target_pane: "runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual([
      "Loop state: cycle 6 running",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("keeps focus on the pending pane when a streamed command result arrives without command metadata", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo", lastCompletedText: "Repo dirty: 517 unstaged, 47 untracked"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "command.result",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("ignores stale wrapper chat targets when a sparse streamed command result falls back to the pending pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "command.result",
      target_pane: "chat",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("ignores stale launcher targets when a sparse streamed command result falls back to the pending pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "commands"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "command.result",
      target_pane: "commands",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "commands")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("ignores stale operational pane aliases when a sparse streamed command result falls back to the pending pane", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "command.result",
      target_pane: "runtime",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("projects sparse pending repo snapshots into the repo pane instead of the control transcript", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}]}
            : tab.id === "control"
              ? {...tab, lines: [{id: "control-stale", kind: "system", text: "stale control output"}]}
              : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    const gitOutput = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 518 | untracked 48
Git hotspots: dharma_swarm (301); terminal (284)
Git changed paths: dharma_swarm/terminal_bridge.py; terminal/src/app.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1`;

    onEvent({
      type: "command.result",
      output: gitOutput,
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(workspaceSnapshotToPreview(gitOutput)).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("stale repo output");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(["stale control output"]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual(["existing conversation"]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("keeps focus on the pending pane when a sparse command.run action result arrives after streamed completion", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/runtime", tabId: "runtime", lastCompletedText: "Loop state: cycle 6 running"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      output: "Loop state: cycle 6 running",
    });

    expect(state.activeTabId).toBe("runtime");
    expect(state.statusLine).toBe("/runtime -> runtime");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("ignores stale wrapper chat targets for sparse command.run action results after streamed completion", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: []}
            : tab.id === "control"
              ? {...tab, lines: [{id: "control-1", kind: "system", text: "existing control summary"}]}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      target_pane: "chat",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual([
      "existing control summary",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("ignores stale launcher targets for sparse command.run action results after streamed completion", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "commands"
            ? {...tab, lines: []}
            : tab.id === "control"
              ? {...tab, lines: [{id: "control-1", kind: "system", text: "existing control summary"}]}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      target_pane: "commands",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "commands")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual([
      "existing control summary",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("ignores stale operational pane targets for sparse command.run action results after streamed completion", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "commands",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo" || tab.id === "runtime"
            ? {...tab, lines: []}
            : tab.id === "control"
              ? {...tab, lines: [{id: "control-1", kind: "system", text: "existing control summary"}]}
              : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: {command: "/git status", tabId: "repo"},
    } as {current: {command: string; tabId: string; lastCompletedText?: string} | null};
    const bridge = {
      send() {
        return "1";
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "action.result",
      action_type: "command.run",
      target_pane: "runtime",
      output: "Repo dirty: 517 unstaged, 47 untracked",
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("/git -> repo");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual([
      "Repo dirty: 517 unstaged, 47 untracked",
    ]);
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines).toEqual([]);
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual([
      "existing control summary",
    ]);
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(pendingCommandStream.current).toBeNull();
  });

  test("clears the command-stream chat guard once slash command routing completes", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "runtime",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "runtime"
            ? {...tab, lines: []}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const pendingCommandStream = {
      current: null,
    } as {current: {command: string; tabId: string} | null};
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
      pendingCommandStream,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-command-1",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "runtime",
      },
    });

    expect(pendingCommandStream.current).toEqual({command: "/runtime", tabId: "runtime"});

    onEvent({
      type: "text_delta",
      content: "Loop state: cycle 6 running",
    });

    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);

    onEvent({
      type: "action.result",
      action_type: "command.run",
      command: "/runtime",
      output: "Loop state: cycle 6 running",
    });

    expect(pendingCommandStream.current).toBeNull();
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Loop state: cycle 6 running",
    );

    onEvent({
      type: "text_complete",
      content: "Normal assistant reply resumes in chat",
    });

    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
      "Normal assistant reply resumes in chat",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/runtime"},
      },
      {type: "workspace.snapshot", payload: undefined},
      {type: "runtime.snapshot", payload: undefined},
      {
        type: "model.policy",
        payload: {provider: "codex", model: "gpt-5.4", strategy: "responsive"},
      },
      {type: "agent.routes", payload: undefined},
      {type: "evolution.surface", payload: undefined},
    ]);
  });

  test("routes bootstrap auto-executed command intents that use pane aliases", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-1b",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "memory recent",
        pane: "notes",
      },
    });

    expect(state.activeTabId).toBe("sessions");
    expect(state.statusLine).toBe("intent /memory recent -> sessions");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/memory recent", pane: "notes"},
      },
    ]);
  });

  test("routes bootstrap auto-executed command intents that use tab aliases", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-1c",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "git status",
        tabId: "workspace",
      },
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("intent /git status -> repo");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/git status", tabId: "workspace"},
      },
    ]);
  });

  test("routes bootstrap auto-executed command intents that use target-pane-id aliases", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-target-pane-id-1",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "memory recent",
        targetPaneId: "notes",
      },
    });

    expect(state.activeTabId).toBe("sessions");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/memory recent", targetPaneId: "notes"},
      },
    ]);
  });

  test("routes bootstrap auto-executed command intents that use target-surface aliases", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-target-surface-1",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "git status",
        targetSurface: "dashboard",
      },
    });

    expect(state.activeTabId).toBe("control");
    expect(state.statusLine).toBe("intent /git status -> control");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/git status", targetSurface: "dashboard"},
      },
    ]);
  });

  test("routes bootstrap auto-executed command intents that use surface-id aliases", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-surface-id-1",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "memory recent",
        surfaceId: "session",
      },
    });

    expect(state.activeTabId).toBe("sessions");
    expect(state.statusLine).toBe("intent /memory recent -> sessions");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/memory recent", surfaceId: "session"},
      },
    ]);
  });

  test("routes bootstrap auto-executed command intents that use target-surface-id aliases", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "chat",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-target-surface-id-1",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "git status",
        targetSurfaceId: "workspace",
      },
    });

    expect(state.activeTabId).toBe("repo");
    expect(state.statusLine).toBe("intent /git status -> repo");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/git status", targetSurfaceId: "workspace"},
      },
    ]);
  });

  test("keeps bootstrap auto-executed chat-control commands on chat despite explicit non-chat targets", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "repo",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "chat"
          ? {...tab, lines: [{id: "chat-1", kind: "assistant", text: "existing conversation"}]}
          : tab.id === "repo"
            ? {...tab, lines: [{id: "repo-1", kind: "system", text: "repo snapshot"}]}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "session.bootstrap.result",
      request_id: "bootstrap-2",
      selected_provider: "codex",
      selected_model: "gpt-5.4",
      routing_strategy: "responsive",
      intent: {
        kind: "command",
        auto_execute: true,
        command: "reset",
        target_pane: "repo",
      },
    });

    expect(state.activeTabId).toBe("chat");
    expect(state.statusLine).toBe("intent /reset -> chat");
    expect(state.tabs.find((tab) => tab.id === "chat")?.lines.map((line) => line.text)).toEqual([
      "existing conversation",
    ]);
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(["repo snapshot"]);
    expect(sent).toEqual([
      {
        type: "command.run",
        payload: {command: "/reset", target_pane: "repo"},
      },
    ]);
  });

  test("ignores operator snapshot results as a non-authoritative compatibility lane", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = {
      ...initialState,
      activeTabId: "agents",
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {...tab, lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale control output"}], preview: bootstrapRuntimePreview}
          : tab.id === "agents"
            ? {...tab, lines: [{id: "agents-stale", kind: "system", text: "stale agent output"}]}
            : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const payload = {
      type: "operator.snapshot.result",
      snapshot: {
        runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
        overview: {
          sessions: 23,
          claims: 2,
          active_claims: 1,
          acknowledged_claims: 1,
          runs: 3,
          active_runs: 1,
          artifacts: 9,
          promoted_facts: 3,
          context_bundles: 2,
          operator_actions: 4,
        },
        runs: [{assigned_to: "agent-alpha", status: "running", task_id: "terminal-control-surface", run_id: "run-1234567890"}],
        actions: [{action_name: "reroute", actor: "operator", task_id: "terminal-control-surface", reason: "better frontier model"}],
      },
    };

    onEvent(payload);
    expect(state.tabs.find((tab) => tab.id === "agents")?.lines.map((line) => line.text)).toContain("stale agent output");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain("stale control output");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain("stale control output");
    expect(state.liveControlPreview).toEqual(bootstrapRuntimePreview);
    expect(state.tabs.find((tab) => tab.id === "agents")?.preview).toBeUndefined();
    expect(sent).toEqual([]);
  });

  test("replaces stale agents state from typed agent routes payloads", () => {
    let state: AppState = {
      ...initialState,
      activeTabId: "agents",
      tabs: initialState.tabs.map((tab) =>
        tab.id === "agents"
          ? {
              ...tab,
              lines: [{id: "agents-stale", kind: "system", text: "stale agent output"}],
              preview: {Legacy: "stale"},
            }
          : tab,
      ),
    };

    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge: {send() { return "1"; }} as DharmaBridge,
      pendingBootstraps: {current: {}} as {current: Record<string, {prompt: string; provider: string; model: string}>},
    });

    onEvent({
      type: "agent.routes.result",
      payload: {
        version: "v1",
        domain: "agent_routes",
        routes: [{intent: "deep_code_work", provider: "codex", model_alias: "codex-5.4", reasoning: "high", role: "builder"}],
        openclaw: {present: true, readable: true, agents_count: 3, providers: ["codex", "claude"]},
        subagent_capabilities: ["route by task type"],
      },
    });

    const agentsTab = state.tabs.find((tab) => tab.id === "agents");
    expect(agentsTab?.lines.some((line) => line.text.includes("deep_code_work -> codex:codex-5.4"))).toBe(true);
    expect(agentsTab?.lines.map((line) => line.text)).not.toContain("stale agent output");
    expect(agentsTab?.preview?.Routes).toBe("1");
    expect(agentsTab?.preview?.Legacy).toBeUndefined();
  });

  test("does not steal focus for non-command action results", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
    };

    const nextState = applyBridgeEvent(baseState, {
      type: "action.result",
      action_type: "model.set",
      target_pane: "models",
      summary: "model policy set to codex:gpt-5.4 (responsive)",
      output: "Active route: codex:gpt-5.4",
    });

    expect(nextState.activeTabId).toBe("chat");
  });

  test("refreshes snapshots against the newly selected model route after model.set", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "action.result",
      action_type: "model.set",
      target_pane: "models",
      summary: "model policy set to claude:claude-opus-4-6 (genius)",
      payload: {
        version: "v1",
        domain: "routing_decision",
        decision: {
          route_id: "claude:claude-opus-4-6",
          provider_id: "claude",
          model_id: "claude-opus-4-6",
          strategy: "genius",
          reason: "selected by operator",
          fallback_chain: ["codex:gpt-5.4"],
          degraded: false,
          metadata: {active_label: "Claude Opus 4.6"},
        },
        strategies: ["responsive", "cost", "genius"],
        targets: [
          {alias: "opus-4.6", label: "Claude Opus 4.6", provider: "claude", model: "claude-opus-4-6"},
          {alias: "codex-5.4", label: "Codex 5.4", provider: "codex", model: "gpt-5.4"},
        ],
        fallback_targets: [{label: "Codex 5.4", provider: "codex", model: "gpt-5.4"}],
      },
    });

    expect(state.routePolicy.provider).toBe("claude");
    expect(state.routePolicy.model).toBe("claude-opus-4-6");
    expect(state.routePolicy.strategy).toBe("genius");
    expect(sent).toEqual([
      {type: "workspace.snapshot", payload: {}},
      {type: "runtime.snapshot", payload: {}},
      {
        type: "model.policy",
        payload: {provider: "claude", model: "claude-opus-4-6", strategy: "genius"},
      },
      {type: "agent.routes", payload: {}},
      {type: "evolution.surface", payload: {}},
    ]);
  });
});

describe("surfaceRefreshActionsForBridgeEvent", () => {
  test("replaces stale repo transcript with normalized live repo preview on repo refresh", () => {
    const staleState: AppState = {
      ...initialState,
      liveRepoPreview: bootstrapWorkspacePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: [
                {id: "stale-1", kind: "system", text: "# /git"},
                {id: "stale-2", kind: "system", text: "stale repo output"},
              ],
            }
          : tab,
      ),
    };

    const refreshContent = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 494
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208

## Most imported local modules
- dharma_swarm.models | inbound 159`;
    const refreshPayload = {
      version: "v1",
      domain: "workspace_snapshot",
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "95210b1",
        staged: 0,
        unstaged: 517,
        untracked: 46,
        changed_hotspots: [
          {name: "terminal", count: 281},
          {name: ".dharma_psmv_hyperfile_branch", count: 147},
          {name: "dharma_swarm", count: 93},
        ],
        changed_paths: [
          "terminal/src/app.tsx",
          "terminal/tests/app.test.ts",
          "terminal/src/components/RepoPane.tsx",
        ],
        sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
      },
      topology: {
        warnings: ["sab_canonical_repo_missing"],
        repos: [
          {
            domain: "dgc",
            name: "dharma_swarm",
            role: "canonical_core",
            canonical: true,
            path: "/Users/dhyana/dharma_swarm",
            exists: true,
            is_git: true,
            branch: "main...origin/main",
            dirty: true,
            modified_count: 517,
            untracked_count: 46,
          },
          {
            domain: "dgc",
            name: "dgc-core",
            role: "operator_shell",
            canonical: false,
            path: "/Users/dhyana/dgc-core",
            exists: false,
            is_git: false,
            branch: "n/a",
            dirty: null,
            modified_count: 0,
            untracked_count: 0,
          },
        ],
      },
      inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
      language_mix: [
        {suffix: ".py", count: 1125},
        {suffix: ".md", count: 511},
      ],
      largest_python_files: [{path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208}],
      most_imported_modules: [{module: "dharma_swarm.models", count: 159}],
    } as const;
    const refreshPreview = workspacePayloadToPreview(refreshPayload);

    const nextState = applyBridgeEvent(staleState, {
      type: "action.result",
      action_type: "surface.refresh",
      surface: "repo",
      target_pane: "repo",
      summary: "refreshed repo",
      payload: refreshPayload,
    });

    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(refreshPreview).map((line) => line.text),
    );
    expect(nextState.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("stale repo output");
    expect(nextState.liveRepoPreview).toMatchObject(refreshPreview);
  });

  test("replaces control and runtime panes with normalized live runtime preview on control refresh", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    let state: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const sent: {type: string; payload?: Record<string, unknown>}[] = [];
    const bridge = {
      send(type: string, payload?: Record<string, unknown>) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const runtimeContent = `# Runtime
Runtime DB: /Users/dhyana/.dharma/state/runtime.db
Sessions=22  Claims=1  ActiveClaims=1  AckedClaims=1  Runs=2  ActiveRuns=1
Artifacts=9  PromotedFacts=3  ContextBundles=2  OperatorActions=4
Toolchain
  claude: /usr/local/bin/claude
  python3: /opt/homebrew/bin/python3
  node: /usr/local/bin/node`;

    onEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "control",
      target_pane: "control",
      summary: "refreshed control",
      output: runtimeContent,
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-1",
          created_at: "2026-04-01T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 22,
          active_run_count: 1,
          artifact_count: 9,
          context_bundle_count: 2,
          anomaly_count: 0,
          verification_status: "unknown",
          next_task: "Add an app-level bootstrap/refresh snapshot test.",
          active_task: "terminal-repo-pane",
          summary: "1 active runs, 2 context bundles, 9 artifacts",
          warnings: [],
          metrics: {
            claims: "1",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "4",
            promoted_facts: "3",
          },
          metadata: {overview: {runs: 2}},
        },
      },
    });

    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(state.liveControlPreview ?? {}).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toEqual(
      runtimePreviewToLines(state.liveControlPreview ?? {}).map((line) => line.text),
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(state.liveControlPreview?.["Runtime activity"]).toContain("Sessions=22");

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Verification_summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");
    expect(persisted.preview_Verification_bundle).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.preview_Runtime_activity).toContain("Sessions=22");
    expect(sent.map((entry) => entry.type)).toEqual([
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("renders live branch, dirty, topology, and hotspot facts in the repo pane after payload-first refreshes", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = {
      ...initialState,
      activeTabId: "repo",
      liveRepoPreview: bootstrapWorkspacePreview,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}],
              preview: bootstrapWorkspacePreview,
            }
          : tab.id === "control"
            ? {
                ...tab,
                lines: [{id: "control-stale", kind: "system", text: "stale runtime output"}],
                preview: bootstrapRuntimePreview,
              }
            : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const repoRefreshPayload = {
      version: "v1" as const,
      domain: "workspace_snapshot" as const,
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "95210b1",
        staged: 0,
        unstaged: 517,
        untracked: 46,
        changed_hotspots: [
          {name: "terminal", count: 281},
          {name: ".dharma_psmv_hyperfile_branch", count: 147},
          {name: "dharma_swarm", count: 93},
        ],
        changed_paths: [
          "terminal/src/app.tsx",
          "terminal/tests/app.test.ts",
          "terminal/src/components/RepoPane.tsx",
        ],
        sync: {
          summary: "origin/main | ahead 0 | behind 0",
          status: "tracking",
          upstream: "origin/main",
          ahead: 0,
          behind: 0,
        },
      },
      topology: {
        warnings: ["sab_canonical_repo_missing"],
        repos: [
          {
            domain: "dgc",
            name: "dharma_swarm",
            role: "canonical_core",
            canonical: true,
            path: "/Users/dhyana/dharma_swarm",
            exists: true,
            is_git: true,
            branch: "main...origin/main",
            head: "95210b1",
            dirty: true,
            modified_count: 517,
            untracked_count: 46,
          },
          {
            domain: "dgc",
            name: "dgc-core",
            role: "operator_shell",
            canonical: false,
            path: "/Users/dhyana/dgc-core",
            exists: true,
            is_git: false,
            branch: "n/a",
            head: "",
            dirty: null,
            modified_count: 0,
            untracked_count: 0,
          },
        ],
      },
      inventory: {
        python_modules: 501,
        python_tests: 495,
        scripts: 124,
        docs: 239,
        workflows: 1,
      },
      language_mix: [
        {suffix: ".py", count: 1125},
        {suffix: ".md", count: 511},
        {suffix: ".json", count: 91},
        {suffix: ".sh", count: 68},
      ],
      largest_python_files: [
        {path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208},
        {path: "dharma_swarm/thinkodynamic_director.py", lines: 5167, defs: 108, classes: 0, imports: 36},
      ],
      most_imported_modules: [
        {module: "dharma_swarm.models", count: 159},
        {module: "dharma_swarm.stigmergy", count: 35},
      ],
    };

    onEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "control",
      target_pane: "control",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-1",
          created_at: "2026-04-01T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 22,
          active_run_count: 1,
          artifact_count: 9,
          context_bundle_count: 2,
          anomaly_count: 0,
          verification_status: "unknown",
          next_task: "Add an app-level bootstrap/refresh snapshot test.",
          active_task: "terminal-repo-pane",
          summary: "1 active runs, 2 context bundles, 9 artifacts",
          warnings: [],
          metrics: {
            claims: "1",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "4",
            promoted_facts: "3",
          },
          metadata: {overview: {runs: 2}},
        },
      },
    });
    onEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "repo",
      target_pane: "repo",
      payload: repoRefreshPayload,
    });

    const repoTab = state.tabs.find((tab) => tab.id === "repo");
    const controlTab = state.tabs.find((tab) => tab.id === "control");
    const pane = RepoPane({
      title: repoTab?.title ?? "Repo",
      preview: state.liveRepoPreview ?? repoTab?.preview,
      controlPreview: state.liveControlPreview ?? controlTab?.preview,
      controlLines: controlTab?.lines ?? [],
      lines: repoTab?.lines ?? [],
      windowSize: 64,
      selectedSectionIndex: 0,
    });
    const visibleText = flattenElementText(pane).join("\n");

    expect(repoTab?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(state.liveRepoPreview ?? workspacePayloadToPreview(repoRefreshPayload)).map((line) => line.text),
    );
    expect(visibleText).toContain("Snapshot branch main@95210b1 | tracking origin/main in sync");
    expect(visibleText).toContain("Dirty staged 0 | unstaged 517 | untracked 46 | topo 1 (sab_canonical_repo_missing) | lead terminal (281)");
    expect(visibleText).toContain("Snapshot topology degraded (1 warning, 2 peers) | warnings 1 (sab_canonical_repo_missing)");
    expect(visibleText).toContain(
      "Snapshot hotspot summary change terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)",
    );
    expect(visibleText).toContain("Snapshot repo/control stale |");
    expect(visibleText).toContain("branch main@95210b1 | tracking origin/main in sync | dirty staged 0 | unstaged 517 | untracked 46");
    expect(visibleText).toContain(
      "warn 1 (sab_canonical_repo_missing) | peer dharma_swarm (canonical_core, main...origin/main, dirty true) | peers dharma_swarm (canonical_core, main...origin/main, dirty true)",
    );
    expect(visibleText).toContain("drift dharma_swarm track main...origin/main | markers dharma_swarm track main...origin/main");
    expect(visibleText).toContain("divergence local +0/-0 | peer dharma_swarm track main...origin/main | hotspot terminal (281)");
    expect(visibleText).toContain("path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159");
    expect(visibleText).not.toContain("stale repo output");
    expect(visibleText).not.toContain("stale runtime output");
  });

  test("unwraps nested control refresh runtime snapshots and persists the derived verification bundle", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    let state: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "action.result",
      action_type: "surface.refresh",
      surface: "control",
      payload: {
        request: {
          action_type: "surface.refresh",
          surface: "control",
        },
        payload: {
          version: "v1",
          domain: "runtime_snapshot",
          snapshot: {
            snapshot_id: "runtime-nested-refresh-1",
            created_at: "2026-04-03T00:00:00Z",
            repo_root: "/Users/dhyana/dharma_swarm",
            runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
            health: "ok",
            bridge_status: "connected",
            active_session_count: 22,
            active_run_count: 1,
            artifact_count: 9,
            context_bundle_count: 2,
            anomaly_count: 0,
            verification_status: "passing",
            next_task: "Add an app-level bootstrap/refresh snapshot test.",
            active_task: "terminal-control-surface",
            summary: "1 active run, 2 context bundles, 9 artifacts",
            warnings: [],
            metrics: {
              claims: "1",
              active_claims: "1",
              acknowledged_claims: "1",
              operator_actions: "4",
              promoted_facts: "3",
            },
            metadata: {
              overview: {runs: 2},
              supervisor_preview: {
                "Loop state": "cycle 7 waiting_for_verification",
                "Verification summary": "passing",
                "Verification status": "passing",
                "Verification passing": "passing",
                "Verification failing": "none",
              },
            },
          },
        },
      },
    });

    expect(state.liveControlPreview?.["Loop state"]).toBe("cycle 7 waiting_for_verification");
    expect(state.liveControlPreview?.["Verification summary"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(state.liveControlPreview?.["Verification status"]).toBe("1 failing, 3/4 passing");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Verification failing: cycle_acceptance",
    );

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Loop_state).toBe("cycle 7 waiting_for_verification");
    expect(persisted.preview_Verification_summary).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");

    const persistedVerification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(persistedVerification.summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persistedVerification.continue_required).toBe(true);
  });

  test("normalizes generic runtime snapshot verification payloads into live previews and durable summary", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    let state: AppState = {
      ...initialState,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-generic-verify-1",
          created_at: "2026-04-01T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 22,
          active_run_count: 1,
          artifact_count: 9,
          context_bundle_count: 2,
          anomaly_count: 0,
          verification_status: "passing",
          next_task: "Add an app-level bootstrap/refresh snapshot test.",
          active_task: "terminal-control-surface",
          summary: "1 active run, 2 context bundles, 9 artifacts",
          warnings: [],
          metrics: {
            claims: "1",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "4",
            promoted_facts: "3",
          },
          metadata: {
            overview: {runs: 2},
            supervisor_preview: {
              "Verification status": "passing",
              "Verification summary": "passing",
              "Verification passing": "passing",
              "Verification failing": "none",
            },
          },
        },
      },
    });

    expect(state.liveControlPreview?.["Verification status"]).toBe("1 failing, 3/4 passing");
    expect(state.liveControlPreview?.["Verification summary"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(state.liveControlPreview?.["Verification bundle"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(state.liveControlPreview?.["Verification failing"]).toBe("cycle_acceptance");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Verification status: 1 failing, 3/4 passing",
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).toContain(
      "Verification summary: tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).toContain(
      "Verification failing: cycle_acceptance",
    );
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain("stale runtime output");

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.verification_status).toBe("1 failing, 3/4 passing");
    expect(persisted.verification_summary).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");
    expect(persisted.preview_Verification_summary).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(persisted.preview_Verification_failing).toBe("cycle_acceptance");

    const persistedVerification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(persistedVerification.summary).toBe("tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persistedVerification.continue_required).toBe(true);
    expect(persistedVerification.checks).toEqual([
      {name: "tsc", ok: true},
      {name: "py_compile_bridge", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: false},
    ]);
  });

  test("uses typed runtime snapshot control fields directly when supervisor preview metadata is sparse", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    let state: AppState = {
      ...initialState,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-typed-control-1",
          created_at: "2026-04-04T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 20,
          active_run_count: 0,
          artifact_count: 0,
          context_bundle_count: 0,
          anomaly_count: 0,
          verification_status: "1 failing, 3/4 passing",
          verification_summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          verification_checks: "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
          verification_bundle: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          verification_passing: "tsc, py_compile_bridge, bridge_snapshots",
          verification_failing: "cycle_acceptance",
          verification_receipt: `${stateDir}/verification.json`,
          verification_updated_at: "2026-04-04T00:05:25.355844+00:00",
          loop_state: "cycle 4 running_cycle",
          loop_decision: "continue required",
          task_progress: "2 done, 1 pending of 3",
          result_status: "complete",
          acceptance: "pass",
          last_result: "complete / pass",
          updated_at: "2026-04-04T00:05:25.355844+00:00",
          durable_state: stateDir,
          runtime_summary:
            "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
          runtime_freshness:
            "cycle 4 running_cycle | updated 2026-04-04T00:05:25.355844+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          next_task: "Refresh verification cards from durable state.",
          active_task: "terminal-control-surface",
          summary: "20 sessions, 0 runs",
          warnings: [],
          metrics: {
            claims: "0",
            active_claims: "0",
            acknowledged_claims: "0",
            operator_actions: "0",
            promoted_facts: "0",
          },
          metadata: {
            overview: {runs: 0},
            supervisor_preview: {},
          },
        },
      },
    });

    expect(state.liveControlPreview?.["Verification receipt"]).toBe(`${stateDir}/verification.json`);
    expect(state.liveControlPreview?.["Verification failing"]).toBe("cycle_acceptance");
    expect(state.liveControlPreview?.["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );
    expect(state.liveControlPreview?.["Runtime freshness"]).toBe(
      "cycle 4 running_cycle | updated 2026-04-04T00:05:25.355844+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );

    const controlLines = state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text) ?? [];
    expect(controlLines).toContain(`Verification receipt: ${stateDir}/verification.json`);
    expect(controlLines).toContain("Verification failing: cycle_acceptance");
    expect(controlLines).toContain(
      "Runtime summary: /Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );
    expect(controlLines).not.toContain("stale runtime output");

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Verification_receipt).toBe(`${stateDir}/verification.json`);
    expect(persisted.preview_Verification_failing).toBe("cycle_acceptance");
    expect(persisted.preview_Runtime_summary).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );
    expect(persisted.preview_Runtime_freshness).toBe(
      "cycle 4 running_cycle | updated 2026-04-04T00:05:25.355844+00:00 | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
  });

  test("promotes compact supervisor pulse fields from runtime snapshots into live loop and verification state", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
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

    let state: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
              preview: bootstrapRuntimePreview,
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-compact-supervisor-1",
          created_at: "2026-04-03T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 5,
          active_run_count: 1,
          artifact_count: 4,
          context_bundle_count: 1,
          anomaly_count: 0,
          verification_status: "unknown",
          next_task: "Add a compact pulse regression.",
          active_task: "terminal-control-surface",
          summary: "1 active run, 1 context bundle, 4 artifacts",
          warnings: [],
          metrics: {
            claims: "2",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "3",
            promoted_facts: "1",
          },
          metadata: {
            overview: {runs: 1},
            supervisor_preview: {
              "Control pulse preview":
                "fresh | complete / fail | cycle 7 waiting_for_verification | updated 2026-04-03T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
              "Runtime freshness":
                "cycle 7 waiting_for_verification | updated 2026-04-03T00:00:00Z | verify tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail",
              "Durable state": stateDir,
            },
          },
        },
      },
    });

    expect(state.liveControlPreview?.["Loop state"]).toBe("cycle 7 waiting_for_verification");
    expect(state.liveControlPreview?.["Last result"]).toBe("complete / fail");
    expect(state.liveControlPreview?.["Verification summary"]).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(state.liveControlPreview?.["Verification checks"]).toBe("tsc ok; bridge_snapshots ok; cycle_acceptance fail");
    expect(state.liveControlPreview?.["Verification status"]).toBe("1 failing, 2/3 passing");
    expect(state.liveControlPreview?.["Verification failing"]).toBe("cycle_acceptance");

    const controlLines = state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text) ?? [];
    expect(controlLines).toContain("Loop state: cycle 7 waiting_for_verification");
    expect(controlLines).toContain("Last result: complete / fail");
    expect(controlLines).toContain("Verification status: 1 failing, 2/3 passing");
    expect(controlLines).not.toContain("stale runtime output");

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Loop_state).toBe("cycle 7 waiting_for_verification");
    expect(persisted.preview_Last_result).toBe("complete / fail");
    expect(persisted.preview_Verification_summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persisted.verification_status).toBe("1 failing, 2/3 passing");

    const persistedVerification = JSON.parse(readFileSync(path.join(stateDir, "verification.json"), "utf8")) as Record<string, unknown>;
    expect(persistedVerification.summary).toBe("tsc=ok | bridge_snapshots=ok | cycle_acceptance=fail");
    expect(persistedVerification.checks).toEqual([
      {name: "tsc", ok: true},
      {name: "bridge_snapshots", ok: true},
      {name: "cycle_acceptance", ok: false},
    ]);
  });

  test("drops stale loop and verification fields on direct runtime snapshot events", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    writeFileSync(
      path.join(stateDir, "run.json"),
      JSON.stringify(
        {
          repo_root: "/Users/dhyana/dharma_swarm",
          updated_at: "2026-04-03T02:00:00Z",
          cycle: 10,
          status: "ready",
          tasks_total: 4,
          tasks_pending: 0,
          last_task_id: "terminal-repo-pane",
          last_continue_required: false,
          last_summary_fields: {
            status: "complete",
            acceptance: "pass",
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
          summary: "tsc=ok | bridge_snapshots=ok",
          continue_required: false,
          checks: [
            {name: "tsc", ok: true},
            {name: "bridge_snapshots", ok: true},
          ],
        },
        null,
        2,
      ),
    );

    let state: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
              preview: bootstrapRuntimePreview,
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {send() { return "1"; }} as unknown as DharmaBridge;
    const pendingBootstraps = {current: {}} as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    const payload = {
      version: "v1",
      domain: "runtime_snapshot",
      snapshot: {
        snapshot_id: "runtime-direct-clean-1",
        created_at: "2026-04-03T02:00:00Z",
        repo_root: "/Users/dhyana/dharma_swarm",
        runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
        health: "ok",
        bridge_status: "connected",
        active_session_count: 3,
        active_run_count: 0,
        artifact_count: 1,
        context_bundle_count: 0,
        anomaly_count: 0,
        verification_status: "passing",
        next_task: "none",
        active_task: "terminal-repo-pane",
        summary: "0 active runs, 0 context bundles, 1 artifact",
        warnings: [],
        metrics: {
          claims: "0",
          active_claims: "0",
          acknowledged_claims: "0",
          operator_actions: "1",
          promoted_facts: "0",
        },
        metadata: {},
      },
    } as const;
    const supervisor = {
      stateDir,
      cycle: 10,
      runStatus: "ready",
      tasksTotal: 4,
      tasksPending: 0,
      activeTaskId: "terminal-repo-pane",
      lastResultStatus: "complete",
      acceptance: "pass",
      verificationSummary: "tsc=ok | bridge_snapshots=ok",
      verificationChecks: ["tsc ok", "bridge_snapshots ok"],
      continueRequired: false,
      nextTask: "none",
      updatedAt: "2026-04-03T02:00:00Z",
    };
    const expectedPreview = runtimePayloadToPreview(payload, supervisor);

    onEvent({
      type: "runtime.snapshot.result",
      payload,
    });

    expect(state.liveControlPreview).toEqual(expectedPreview);
    expect(state.liveControlPreview?.["Verification status"]).toBe("all 2 checks passing");
    expect(state.liveControlPreview?.["Verification failing"]).toBe("none");
    expect(state.liveControlPreview?.["Next task"]).toBe("none");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "stale runtime output",
    );
  });

  test("drops stale loop and verification fields on bootstrap runtime previews", () => {
    const cleanBootstrapRuntimePreview: TabPreview = {
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=3 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0",
      "Artifact state": "Artifacts=1 PromotedFacts=0 ContextBundles=0 OperatorActions=1",
      "Loop state": "cycle 10 ready",
      "Loop decision": "ready to stop",
      "Active task": "terminal-repo-pane",
      "Task progress": "4 done, 0 pending of 4",
      "Result status": "complete",
      Acceptance: "pass",
      "Last result": "complete / pass",
      "Verification summary": "tsc=ok | bridge_snapshots=ok",
      "Verification checks": "tsc ok; bridge_snapshots ok",
      "Verification bundle": "tsc=ok | bridge_snapshots=ok",
      "Verification status": "all 2 checks passing",
      "Verification passing": "tsc, bridge_snapshots",
      "Verification failing": "none",
      "Runtime freshness": "cycle 10 ready | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok",
      "Control pulse preview": "complete / pass | cycle 10 ready | updated 2026-04-03T02:00:00Z | verify tsc=ok | bridge_snapshots=ok",
      "Runtime summary":
        "/Users/dhyana/.dharma/state/runtime.db | 3 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 1 artifact | 0 promoted facts | 0 context bundles | 1 operator action",
      "Next task": "none",
      Updated: "2026-04-03T02:00:00Z",
      "Durable state": "/Users/dhyana/.dharma/terminal_supervisor/terminal-20260403T020000Z/state",
      Toolchain: "claude, python3, node",
      Alerts: "none",
    };

    const state = applyActions(
      {
        ...initialState,
        liveRepoPreview: bootstrapWorkspacePreview,
        liveControlPreview: bootstrapRuntimePreview,
        tabs: initialState.tabs.map((tab) =>
          tab.id === "control" || tab.id === "runtime"
            ? {
                ...tab,
                lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
                preview: bootstrapRuntimePreview,
              }
            : tab,
        ),
      },
      snapshotActionsForBridgeEvent(
        {
          type: "session.bootstrap.result",
          workspace_preview: bootstrapWorkspacePreview,
          runtime_preview: cleanBootstrapRuntimePreview,
        },
        bootstrapWorkspacePreview,
        bootstrapRuntimePreview,
      ),
    );

    expect(state.liveControlPreview).toEqual(cleanBootstrapRuntimePreview);
    expect(state.liveControlPreview?.["Verification status"]).toBe("all 2 checks passing");
    expect(state.liveControlPreview?.["Verification failing"]).toBe("none");
    expect(state.liveControlPreview?.["Next task"]).toBe("none");
    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain(
      "stale runtime output",
    );
    expect(state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text)).not.toContain(
      "stale runtime output",
    );
  });

  test("drops stale repo warning and hotspot fields on bootstrap workspace previews", () => {
    const cleanBootstrapWorkspacePreview: TabPreview = {
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "95210b1",
      Upstream: "origin/main",
      Ahead: "0",
      Behind: "0",
      "Branch status": "tracking origin/main in sync",
      Sync: "origin/main | ahead 0 | behind 0",
      "Branch sync preview": "tracking origin/main in sync | +0/-0 | topology stable; low (0 local changes)",
      "Repo risk preview": "tracking origin/main in sync | stable | dharma_swarm (canonical_core, main...origin/main, dirty False)",
      "Repo risk": "stable; low (0 local changes)",
      Dirty: "0 staged, 0 unstaged, 0 untracked",
      "Dirty pressure": "low (0 local changes)",
      Staged: "0",
      Unstaged: "0",
      Untracked: "0",
      "Topology status": "stable (0 warnings, 1 peer)",
      "Topology peer count": "1",
      "Topology warnings": "0",
      "Topology risk": "stable",
      "Risk preview": "stable | dharma_swarm (canonical_core, main...origin/main, dirty False)",
      "Topology preview": "dharma_swarm (canonical_core, main...origin/main, dirty False)",
      "Topology pressure preview": "0 warnings | dharma_swarm clean",
      "Primary warning": "none",
      "Primary topology peer": "dharma_swarm (canonical_core, main...origin/main, dirty False)",
      "Topology peers": "dharma_swarm (canonical_core, main...origin/main, dirty False)",
      "Topology pressure": "dharma_swarm clean",
      "Changed hotspots": "none",
      "Hotspot summary": "none",
      "Lead hotspot preview": "none",
      "Hotspot pressure preview": "none",
      "Changed paths": "none",
      "Primary changed hotspot": "none",
      "Primary changed path": "none",
      "Primary file hotspot": "none",
      "Primary dependency hotspot": "none",
      Hotspots: "none",
      "Inbound hotspots": "none",
      Inventory: "501 modules | 494 tests | 124 scripts | 239 docs | 1 workflows",
      "Language mix": ".py: 1125; .md: 511; .json: 91; .sh: 68",
    };

    const staleRepoPreview: TabPreview = {
      ...bootstrapWorkspacePreview,
      "Primary warning": "stale_warning_that_should_clear",
      "Primary changed path": "stale/path.ts",
      "Primary dependency hotspot": "stale.module | inbound 9",
      "Hotspot summary": "stale hotspot summary",
    };

    const state = applyActions(
      {
        ...initialState,
        liveRepoPreview: staleRepoPreview,
        liveControlPreview: bootstrapRuntimePreview,
        tabs: initialState.tabs.map((tab) =>
          tab.id === "repo"
            ? {
                ...tab,
                lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}],
                preview: staleRepoPreview,
              }
            : tab,
        ),
      },
      snapshotActionsForBridgeEvent(
        {
          type: "session.bootstrap.result",
          workspace_preview: cleanBootstrapWorkspacePreview,
          runtime_preview: bootstrapRuntimePreview,
        },
        staleRepoPreview,
        bootstrapRuntimePreview,
      ),
    );

    expect(state.liveRepoPreview).toMatchObject(cleanBootstrapWorkspacePreview);
    expect(state.liveRepoPreview?.["Topology warnings"]).toBe("0");
    expect(state.liveRepoPreview?.["Primary warning"]).toBe("none");
    expect(state.liveRepoPreview?.["Primary changed path"]).toBe("none");
    expect(state.liveRepoPreview?.["Primary dependency hotspot"]).toBe("none");
    expect(state.liveRepoPreview?.["Hotspot summary"]).toBe("none");
    expect(state.tabs.find((tab) => tab.id === "repo")?.lines.map((line) => line.text)).not.toContain("stale repo output");
  });

  test("replaces a bootstrap placeholder runtime summary when a live runtime snapshot carries detailed rows", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;
    let state: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
              preview: bootstrapRuntimePreview,
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-summary-refresh-1",
          created_at: "2026-04-02T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 20,
          active_run_count: 0,
          artifact_count: 0,
          context_bundle_count: 0,
          anomaly_count: 0,
          verification_status: "passing",
          next_task: "Promote runtime loop metadata into the operator summary.",
          active_task: "terminal-control-surface",
          summary: "20 sessions, 0 runs",
          warnings: [],
          metrics: {
            claims: "0",
            active_claims: "0",
            acknowledged_claims: "0",
            operator_actions: "0",
            promoted_facts: "0",
          },
          metadata: {
            overview: {runs: 0},
            supervisor_preview: {
              "Loop state": "cycle 7 waiting_for_verification",
              "Task progress": "4 done, 0 pending of 4",
              "Active task": "terminal-control-surface",
              "Result status": "in_progress",
              Acceptance: "pass",
              "Last result": "in_progress / pass",
              "Loop decision": "continue required",
              Updated: "2026-04-02T00:00:00Z",
            },
          },
        },
      },
    });

    expect(state.liveControlPreview?.["Runtime summary"]).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Runtime_summary).toBe(
      "/Users/dhyana/.dharma/state/runtime.db | 20 sessions | 0 claims | 0 active claims | 0 acked claims | 0 active runs | 0 runs total | 0 artifacts | 0 promoted facts | 0 context bundles | 0 operator actions",
    );
  });

  test("keeps loop rows synchronized when runtime snapshot metadata overrides supervisor preview state", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    let state: AppState = {
      ...initialState,
      liveControlPreview: bootstrapRuntimePreview,
      tabs: initialState.tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
              preview: bootstrapRuntimePreview,
            }
          : tab,
      ),
    };
    const dispatch = (action: AppAction): void => {
      state = reduceApp(state, action);
    };
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;
    const pendingBootstraps = {
      current: {},
    } as {current: Record<string, {prompt: string; provider: string; model: string}>};
    const onEvent = createBridgeEventHandler({
      dispatch,
      getState: () => state,
      bridge,
      pendingBootstraps,
    });

    onEvent({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-loop-sync-1",
          created_at: "2026-04-02T00:30:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 24,
          active_run_count: 1,
          artifact_count: 11,
          context_bundle_count: 3,
          anomaly_count: 0,
          verification_status: "passing",
          next_task: "obsolete payload next task",
          active_task: "obsolete-active-task",
          summary: "1 active run, 3 context bundles, 11 artifacts",
          warnings: [],
          metrics: {
            claims: "2",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "5",
            promoted_facts: "4",
          },
          metadata: {
            overview: {runs: 3},
            supervisor_preview: {
              "Loop state": "cycle 7 waiting_for_verification",
              "Task progress": "4 done, 0 pending of 4",
              "Active task": "terminal-control-surface",
              "Result status": "in_progress",
              Acceptance: "fail",
              "Last result": "in_progress / fail",
              "Loop decision": "ready to stop",
              "Next task": "Promote runtime loop metadata into the operator summary.",
              "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
              "Verification checks": "tsc ok; py_compile_bridge ok; bridge_snapshots ok; cycle_acceptance fail",
              "Verification status": "1 failing, 3/4 passing",
              "Verification passing": "tsc, py_compile_bridge, bridge_snapshots",
              "Verification failing": "cycle_acceptance",
              Updated: "2026-04-02T00:30:00Z",
            },
          },
        },
      },
    });

    expect(state.liveControlPreview?.["Loop state"]).toBe("cycle 7 waiting_for_verification");
    expect(state.liveControlPreview?.["Task progress"]).toBe("4 done, 0 pending of 4");
    expect(state.liveControlPreview?.["Active task"]).toBe("terminal-control-surface");
    expect(state.liveControlPreview?.["Loop decision"]).toBe("ready to stop");
    expect(state.liveControlPreview?.["Next task"]).toBe("Promote runtime loop metadata into the operator summary.");
    expect(state.liveControlPreview?.["Verification summary"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(state.liveControlPreview?.["Verification bundle"]).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(state.liveControlPreview?.["Verification status"]).toBe("1 failing, 3/4 passing");

    const controlLines = state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text) ?? [];
    const runtimeLines = state.tabs.find((tab) => tab.id === "runtime")?.lines.map((line) => line.text) ?? [];
    expect(controlLines).toContain("Loop state: cycle 7 waiting_for_verification");
    expect(controlLines).toContain("Task progress: 4 done, 0 pending of 4");
    expect(controlLines).toContain("Loop decision: ready to stop");
    expect(controlLines).toContain("Next task: Promote runtime loop metadata into the operator summary.");
    expect(controlLines).toContain("Verification status: 1 failing, 3/4 passing");
    expect(controlLines).not.toContain("Loop state: cycle 4 running");
    expect(runtimeLines).toEqual(controlLines);

    const persisted = JSON.parse(readFileSync(path.join(stateDir, "terminal-control-summary.json"), "utf8")) as Record<string, unknown>;
    expect(persisted.preview_Loop_state).toBe("cycle 7 waiting_for_verification");
    expect(persisted.preview_Task_progress).toBe("4 done, 0 pending of 4");
    expect(persisted.preview_Active_task).toBe("terminal-control-surface");
    expect(persisted.preview_Loop_decision).toBe("ready to stop");
    expect(persisted.preview_Next_task).toBe("Promote runtime loop metadata into the operator summary.");
    expect(persisted.preview_Verification_summary).toBe(
      "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
    );
    expect(persisted.preview_Verification_status).toBe("1 failing, 3/4 passing");
  });
});

describe("slashCommandStartActions", () => {
  test("routes typed /models commands to the models pane without appending chat transcript actions", () => {
    const actions = slashCommandStartActions({command: "/models"});

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "models"},
      {type: "status.set", value: "command /models -> models"},
    ]);
    expect(actions.some((action) => action.type === "tab.append")).toBe(false);
  });

  test("routes typed git commands to the repo pane without appending chat transcript actions", () => {
    const actions = slashCommandStartActions({command: "/git status"});

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "command /git status -> repo"},
    ]);
    expect(actions.some((action) => action.type === "tab.append")).toBe(false);
  });

  test("ignores explicit chat targets for operational typed slash commands", () => {
    const actions = slashCommandStartActions({
      command: "/runtime",
      target_pane: "chat",
    });

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /runtime -> runtime"},
    ]);
  });

  test("keeps chat control slash commands on chat even when an explicit non-chat target is provided", () => {
    const actions = slashCommandStartActions({
      command: "/reset",
      target_pane: "repo",
    });

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "chat"},
      {type: "status.set", value: "command /reset -> chat"},
    ]);
  });

  test("routes typed notes commands to the sessions pane without appending chat transcript actions", () => {
    const actions = slashCommandStartActions({command: "/notes"});

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "sessions"},
      {type: "status.set", value: "command /notes -> sessions"},
    ]);
    expect(actions.some((action) => action.type === "tab.append")).toBe(false);
  });

  test("routes typed logs commands to the sessions pane without appending chat transcript actions", () => {
    const actions = slashCommandStartActions({command: "/logs --tail 50"});

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "sessions"},
      {type: "status.set", value: "command /logs --tail 50 -> sessions"},
    ]);
    expect(actions.some((action) => action.type === "tab.append")).toBe(false);
  });

  test("routes typed hum commands to the agents pane without appending chat transcript actions", () => {
    const actions = slashCommandStartActions({command: "/hum"});

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "agents"},
      {type: "status.set", value: "command /hum -> agents"},
    ]);
    expect(actions.some((action) => action.type === "tab.append")).toBe(false);
  });

  test("routes typed approval commands to the approvals pane without appending chat transcript actions", () => {
    const actions = slashCommandStartActions({command: "/permissions pending"});

    expect(actions).toEqual([
      {type: "tab.activate", tabId: "approvals"},
      {type: "status.set", value: "command /permissions pending -> approvals"},
    ]);
    expect(actions.some((action) => action.type === "tab.append")).toBe(false);
  });
});

describe("paneActionStartActions", () => {
  test("builds a command envelope from pane-action summaries so pending streamed output can target the inferred pane", () => {
    const event = commandRunEventFromPaneAction({
      summary: "run /runtime status",
      payload: {action_type: "command.run"},
    });

    expect(event).toEqual({
      action_type: "command.run",
      summary: "run /runtime status",
    });
    expect(resolveEventCommand(event!)).toBe("/runtime");
    expect(resolveCommandTargetPane(event!, "control")).toBe("runtime");
  });

  test("optimistically activates the runtime pane for pane-triggered runtime commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /runtime",
        payload: {action_type: "command.run", command: "/runtime"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /runtime -> runtime"},
    ]);
  });

  test("optimistically activates the repo pane for pane-triggered git commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /git",
        payload: {action_type: "command.run", command: "/git"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "command /git -> repo"},
    ]);
  });

  test("derives the target pane from the slash command embedded in the pane action summary", () => {
    expect(
      paneActionStartActions({
        summary: "run /runtime status",
        payload: {action_type: "command.run"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /runtime -> runtime"},
    ]);
  });

  test("derives the target pane from nested pane action command payloads", () => {
    expect(
      paneActionStartActions({
        summary: "refresh runtime lane",
        payload: {
          action_type: "command.run",
          request: {command: "/runtime status", target_pane: "registry"},
        },
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /runtime status -> runtime"},
    ]);
  });

  test("ignores filesystem paths when deriving pane action command routing from the summary", () => {
    expect(
      paneActionStartActions({
        summary: "wrote trace to /tmp/runtime.log and then run /git status",
        payload: {action_type: "command.run"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "command /git -> repo"},
    ]);
  });

  test("ignores leading filesystem paths when deriving pane action command routing from the summary", () => {
    expect(
      paneActionStartActions({
        summary: "/tmp/runtime.log captured before executed /runtime status",
        payload: {action_type: "command.run"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /runtime -> runtime"},
    ]);
  });

  test("honors an explicit non-chat target pane for pane-triggered slash commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /dashboard",
        payload: {action_type: "command.run", command: "/dashboard", target_pane: "runtime"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /dashboard -> runtime"},
    ]);
  });

  test("honors pane aliases for pane-triggered slash commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /memory recent",
        payload: {action_type: "command.run", command: "/memory recent", pane: "notes"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "sessions"},
      {type: "status.set", value: "command /memory recent -> sessions"},
    ]);
  });

  test("ignores an explicit chat target for operational pane-triggered slash commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /runtime",
        payload: {action_type: "command.run", command: "/runtime", target_pane: "chat"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "runtime"},
      {type: "status.set", value: "command /runtime -> runtime"},
    ]);
  });

  test("ignores launcher-pane targets for operational pane-triggered slash commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /git",
        payload: {action_type: "command.run", command: "/git", target_pane: "commands"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "repo"},
      {type: "status.set", value: "command /git -> repo"},
    ]);
  });

  test("keeps pane-triggered chat control slash commands on chat despite explicit non-chat targets", () => {
    expect(
      paneActionStartActions({
        summary: "run /reset",
        payload: {action_type: "command.run", command: "/reset", target_pane: "repo"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "chat"},
      {type: "status.set", value: "command /reset -> chat"},
    ]);
  });

  test("optimistically activates the sessions pane for pane-triggered notes commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /notes",
        payload: {action_type: "command.run", command: "/notes"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "sessions"},
      {type: "status.set", value: "command /notes -> sessions"},
    ]);
  });

  test("optimistically activates the agents pane for pane-triggered hum commands", () => {
    expect(
      paneActionStartActions({
        summary: "run /hum",
        payload: {action_type: "command.run", command: "/hum"},
      }),
    ).toEqual([
      {type: "tab.activate", tabId: "agents"},
      {type: "status.set", value: "command /hum -> agents"},
    ]);
  });

  test("keeps non-command pane actions on the current tab while updating status", () => {
    expect(
      paneActionStartActions({
        summary: "refresh model policy",
        payload: {action_type: "surface.refresh", surface: "models"},
      }),
    ).toEqual([{type: "status.set", value: "refresh model policy"}]);
  });
});

describe("model picker state", () => {
  test("opens the picker as an overlay without changing the active tab", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: false,
      modelPickerReturnTabId: "chat",
    };

    const opened = reduceApp(baseState, {type: "modelPicker.open", returnTabId: "chat"});
    expect(opened.activeTabId).toBe("chat");
    expect(opened.uiMode.activeOverlay).toEqual({
      kind: "modelPicker",
      selectedIndex: 0,
      returnTabId: "chat",
    });

    const closed = reduceApp(opened, {type: "modelPicker.close"});
    expect(closed.activeTabId).toBe("chat");
    expect(closed.uiMode.activeOverlay).toEqual({kind: "none"});
  });

  test("switching tabs closes the picker while preserving explicit models navigation", () => {
    const baseState: AppState = {
      ...initialState,
      activeTabId: "chat",
      modelPickerVisible: true,
    };

    const moved = reduceApp(baseState, {type: "tab.activate", tabId: "repo"});
    expect(moved.activeTabId).toBe("repo");
    expect(moved.uiMode.activeOverlay).toEqual({kind: "none"});

    const modelsTab = reduceApp(baseState, {type: "tab.activate", tabId: "models"});
    expect(modelsTab.activeTabId).toBe("models");
    expect(modelsTab.uiMode.activeOverlay).toEqual({kind: "none"});
  });

  test("scrolls panes within bounded offsets", () => {
    const baseState: AppState = {
      ...initialState,
      paneScrollOffsets: {repo: 2},
    };

    const scrolled = reduceApp(baseState, {type: "pane.scroll", tabId: "repo", delta: 10, maxOffset: 6});
    expect(scrolled.paneScrollOffsets.repo).toBe(6);

    const rewound = reduceApp(scrolled, {type: "pane.scroll", tabId: "repo", delta: -20, maxOffset: 6});
    expect(rewound.paneScrollOffsets.repo).toBe(0);
  });
});

describe("typed session bridge handling", () => {
  test("requests authoritative resync after handshake and reconnects after bridge exit", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    expect(state.bridgeStatus).toBe("connected");
    expect(state.statusLine).toBe("resyncing 6 surfaces");
    expect(state.authoritativeSurfaces).toEqual({
      repo: false,
      control: false,
      sessions: false,
      approvals: false,
      models: false,
      agents: false,
    });
    expect(sent.map((entry) => entry.type)).toEqual([
      "status",
      "command.graph",
      "command.registry",
      "ontology.snapshot",
      "session.catalog",
      "permission.history",
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    sent.length = 0;
    handler({
      type: "bridge.error",
      code: "bridge_exit",
      message: "bridge exited (1)",
    });

    expect(state.bridgeStatus).toBe("degraded");
    expect(state.statusLine).toBe("bridge exited, reconnecting");
    expect(state.authoritativeSurfaces).toEqual({
      repo: false,
      control: false,
      sessions: false,
      approvals: false,
      models: false,
      agents: false,
    });
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    expect(state.bridgeStatus).toBe("connected");
    expect(state.statusLine).toBe("resyncing 6 surfaces");
    expect(sent.map((entry) => entry.type)).toEqual([
      "status",
      "command.graph",
      "command.registry",
      "ontology.snapshot",
      "session.catalog",
      "permission.history",
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("deduplicates reconnect attempts across repeated transport failures before recovery", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "bridge.error",
      code: "bridge_send_failed",
      message: "send failed",
    });
    handler({
      type: "bridge.error",
      code: "bridge_stdin_unavailable",
      message: "stdin unavailable",
    });
    handler({
      type: "bridge.error",
      code: "bridge_spawn_error",
      message: "spawn failed",
    });

    expect(state.bridgeStatus).toBe("offline");
    expect(state.statusLine).toBe("backend offline, retrying");
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    expect(state.bridgeStatus).toBe("connected");
    expect(state.statusLine).toBe("resyncing 6 surfaces");
    expect(sent.map((entry) => entry.type)).toEqual([
      "status",
      "command.graph",
      "command.registry",
      "ontology.snapshot",
      "session.catalog",
      "permission.history",
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("recovers deterministically across multiple reconnect cycles", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });
    sent.length = 0;

    handler({
      type: "bridge.error",
      code: "bridge_exit",
      message: "bridge exited (1)",
    });
    handler({
      type: "bridge.error",
      code: "bridge_exit",
      message: "bridge exited (1)",
    });
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);
    expect(state.bridgeStatus).toBe("degraded");

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });
    expect(state.bridgeStatus).toBe("connected");
    expect(state.statusLine).toBe("resyncing 6 surfaces");
    expect(sent.map((entry) => entry.type)).toEqual([
      "status",
      "command.graph",
      "command.registry",
      "ontology.snapshot",
      "session.catalog",
      "permission.history",
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    sent.length = 0;
    handler({
      type: "bridge.error",
      code: "bridge_send_failed",
      message: "send failed",
    });
    handler({
      type: "bridge.error",
      code: "bridge_send_failed",
      message: "send failed",
    });
    expect(state.bridgeStatus).toBe("offline");
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });
    expect(state.bridgeStatus).toBe("connected");
    expect(state.statusLine).toBe("resyncing 6 surfaces");
    expect(sent.map((entry) => entry.type)).toEqual([
      "status",
      "command.graph",
      "command.registry",
      "ontology.snapshot",
      "session.catalog",
      "permission.history",
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);
  });

  test("ignores duplicate handshake success while already connected and not awaiting recovery", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    expect(state.bridgeStatus).toBe("connected");
    expect(sent.map((entry) => entry.type)).toEqual([
      "status",
      "command.graph",
      "command.registry",
      "ontology.snapshot",
      "session.catalog",
      "permission.history",
      "workspace.snapshot",
      "runtime.snapshot",
      "model.policy",
      "agent.routes",
      "evolution.surface",
    ]);

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    expect(state.bridgeStatus).toBe("connected");
    expect(state.statusLine).toBe("backend connected");
    expect(sent).toEqual([]);
  });

  test("reconnects after repeated malformed bridge output", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({type: "bridge.error", code: "invalid_bridge_json", message: "{bad"});
    expect(state.bridgeStatus).toBe("degraded");
    expect(state.statusLine).toBe("bridge output invalid (1/3)");
    expect(sent).toEqual([]);

    handler({type: "bridge.error", code: "invalid_bridge_json", message: "{bad"});
    expect(state.statusLine).toBe("bridge output invalid (2/3)");
    expect(sent).toEqual([]);

    handler({type: "bridge.error", code: "invalid_bridge_json", message: "{bad"});
    expect(state.bridgeStatus).toBe("degraded");
    expect(state.statusLine).toBe("bridge unhealthy, reconnecting");
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);
  });

  test("resets malformed bridge output threshold after a valid event", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({type: "bridge.error", code: "invalid_bridge_json", message: "{bad"});
    handler({type: "bridge.error", code: "invalid_bridge_json", message: "{bad"});
    expect(state.statusLine).toBe("bridge output invalid (2/3)");

    handler({
      type: "workspace.snapshot.result",
      content: `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281)
Git changed paths: terminal/src/app.tsx
Git sync: origin/main | ahead 0 | behind 0`,
    });

    handler({type: "bridge.error", code: "invalid_bridge_json", message: "{bad"});
    expect(state.statusLine).toBe("bridge output invalid (1/3)");
    expect(sent).toEqual([]);
  });

  test("typed resync results override stale hydrated state after reconnect", () => {
    let state: AppState = {
      ...createInitialAppState(initialState),
      bridgeStatus: "degraded",
      liveControlPreview: {...bootstrapRuntimePreview, "Runtime activity": "Sessions=99 Runs=9 | Artifacts=99 ContextBundles=99"},
      tabs: createInitialAppState(initialState).tabs.map((tab) =>
        tab.id === "control" || tab.id === "runtime"
          ? {
              ...tab,
              lines: [{id: `${tab.id}-stale`, kind: "system", text: "stale runtime output"}],
              preview: {...bootstrapRuntimePreview, "Runtime activity": "Sessions=99 Runs=9 | Artifacts=99 ContextBundles=99"},
            }
          : tab.id === "agents"
            ? {
                ...tab,
                lines: [{id: "agents-stale", kind: "system", text: "stale agent output"}],
                preview: {Routes: "99"},
              }
            : tab.id === "models"
              ? {
                  ...tab,
                  lines: [{id: "models-stale", kind: "system", text: "stale model output"}],
                  preview: {Route: "stale:route"},
                }
              : tab.id === "sessions"
                ? {
                    ...tab,
                    lines: [{id: "sessions-stale", kind: "system", text: "stale session output"}],
                    preview: {"Latest session": "stale-session"},
                  }
                : tab.id === "approvals"
                  ? {
                      ...tab,
                      lines: [{id: "approvals-stale", kind: "system", text: "stale approval output"}],
                      preview: {Pending: "99"},
                    }
                  : tab,
      ),
    };
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });
    expect(state.statusLine).toBe("resyncing 6 surfaces");

    handler({
      type: "workspace.snapshot.result",
      payload: {
        version: "v1",
        domain: "workspace_snapshot",
        repo_root: "/Users/dhyana/dharma_swarm",
        git: {
          branch: "main",
          head: "95210b1",
          staged: 0,
          unstaged: 517,
          untracked: 46,
          changed_hotspots: [{name: "terminal", count: 281}],
          changed_paths: ["terminal/src/app.tsx"],
          sync: {summary: "origin/main | ahead 0 | behind 0", status: "tracking", upstream: "origin/main", ahead: 0, behind: 0},
        },
        topology: {
          warnings: ["sab_canonical_repo_missing"],
          repos: [
            {
              domain: "dgc",
              name: "dharma_swarm",
              role: "canonical_core",
              canonical: true,
              path: "/Users/dhyana/dharma_swarm",
              exists: true,
              is_git: true,
              branch: "main...origin/main",
              head: "95210b1",
              dirty: true,
              modified_count: 517,
              untracked_count: 46,
            },
          ],
        },
        inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
        language_mix: [{suffix: ".py", count: 1125}],
        largest_python_files: [],
        most_imported_modules: [],
      },
    });
    expect(state.statusLine).toBe("resyncing 5 surfaces");

    handler({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-resync-1",
          created_at: "2026-04-02T00:00:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 2,
          active_run_count: 1,
          artifact_count: 7,
          context_bundle_count: 3,
          anomaly_count: 0,
          verification_status: "passing",
          next_task: "finish reconnect tests",
          active_task: "terminal-lifecycle-hardening",
          summary: "1 active run, 3 context bundles, 7 artifacts",
          warnings: [],
          metrics: {
            claims: "1",
            active_claims: "1",
            acknowledged_claims: "1",
            operator_actions: "2",
            promoted_facts: "4",
          },
          metadata: {},
        },
      },
    });
    expect(state.statusLine).toBe("resyncing 4 surfaces");
    handler({
      type: "model.policy.result",
      payload: {
        version: "v1",
        domain: "routing_decision",
        decision: {
          route_id: "codex:gpt-5.4",
          provider_id: "codex",
          model_id: "gpt-5.4",
          strategy: "responsive",
          reason: "selected by current routing policy",
          fallback_chain: ["claude:claude-sonnet-4-6"],
          degraded: false,
          metadata: {active_label: "Codex 5.4"},
        },
        strategies: ["responsive", "cost"],
        targets: [{alias: "codex-5.4", label: "Codex 5.4", provider: "codex", model: "gpt-5.4"}],
        fallback_targets: [{label: "Claude Sonnet 4.6", provider: "claude", model: "claude-sonnet-4-6"}],
      },
    });
    expect(state.statusLine).toBe("resyncing 3 surfaces");
    handler({
      type: "agent.routes.result",
      payload: {
        version: "v1",
        domain: "agent_routes",
        routes: [{intent: "deep_code_work", provider: "codex", model_alias: "codex-5.4", reasoning: "high", role: "builder"}],
        openclaw: {present: true, readable: true, agents_count: 3, providers: ["codex", "claude"]},
        subagent_capabilities: ["route by task type"],
      },
    });
    expect(state.statusLine).toBe("resyncing 2 surfaces");
    handler({
      type: "permission.history.result",
      payload: {
        version: "v1",
        domain: "permission_history",
        count: 1,
        entries: [
          {
            action_id: "perm-recover-1",
            decision: {
              version: "v1",
              domain: "permission_decision",
              action_id: "perm-recover-1",
              tool_name: "Bash",
              risk: "shell_or_network",
              decision: "require_approval",
              rationale: "operator gated",
              policy_source: "legacy-governance",
              requires_confirmation: true,
              metadata: {session_id: "sess-recover-1"},
            },
            first_seen_at: "2026-04-02T00:00:00Z",
            last_seen_at: "2026-04-02T00:00:00Z",
            seen_count: 1,
            pending: true,
            status: "pending",
          },
        ],
      },
    });
    expect(state.statusLine).toBe("resyncing 1 surface");
    handler({
      type: "session.catalog.result",
      payload: {
        version: "v1",
        domain: "session_catalog",
        count: 1,
        sessions: [
          {
            session: {
              session_id: "sess-recover-1",
              provider_id: "codex",
              model_id: "gpt-5.4",
              cwd: "/repo",
              created_at: "2026-04-02T00:00:00Z",
              updated_at: "2026-04-02T00:10:00Z",
              status: "running",
              summary: "recover operator state",
              metadata: {},
            },
            replay_ok: true,
            replay_issues: [],
            total_turns: 4,
            total_cost_usd: 0.42,
          },
        ],
      },
    });
    expect(state.statusLine).toBe("operator state live");

    expect(state.tabs.find((tab) => tab.id === "control")?.lines.map((line) => line.text)).not.toContain("stale runtime output");
    expect(state.liveControlPreview?.["Runtime activity"]).toContain("Sessions=2");
    expect(state.authoritativeSurfaces).toMatchObject({
      control: true,
      models: true,
      agents: true,
      approvals: true,
      sessions: true,
    });
    expect(state.tabs.find((tab) => tab.id === "models")?.lines.map((line) => line.text)).not.toContain("stale model output");
    expect(state.tabs.find((tab) => tab.id === "models")?.preview?.Route).toBe("codex:gpt-5.4");
    expect(state.tabs.find((tab) => tab.id === "agents")?.lines.map((line) => line.text)).not.toContain("stale agent output");
    expect(state.tabs.find((tab) => tab.id === "agents")?.preview?.Routes).toBe("1");
    expect(state.tabs.find((tab) => tab.id === "approvals")?.lines.map((line) => line.text)).not.toContain("stale approval output");
    expect(state.tabs.find((tab) => tab.id === "approvals")?.preview?.Pending).toBe("1");
    expect(state.tabs.find((tab) => tab.id === "sessions")?.lines.map((line) => line.text)).not.toContain("stale session output");
    expect(state.tabs.find((tab) => tab.id === "sessions")?.preview?.["Latest session"]).toBe("sess-recover-1");
    expect(sent).toContainEqual({
      type: "session.detail",
      payload: {session_id: "sess-recover-1", transcript_limit: 40},
    });
  });

  test("workspace resync replaces stale hydrated repo preview after reconnect", () => {
    let state: AppState = {
      ...createInitialAppState(initialState),
      bridgeStatus: "degraded",
      liveRepoPreview: {
        ...bootstrapWorkspacePreview,
        "Primary warning": "stale_warning_that_should_clear",
        "Primary changed path": "stale/path.ts",
        "Hotspot summary": "stale hotspot summary",
      },
      tabs: createInitialAppState(initialState).tabs.map((tab) =>
        tab.id === "repo"
          ? {
              ...tab,
              lines: [{id: "repo-stale", kind: "system", text: "stale repo output"}],
              preview: {
                ...bootstrapWorkspacePreview,
                "Primary warning": "stale_warning_that_should_clear",
                "Primary changed path": "stale/path.ts",
                "Hotspot summary": "stale hotspot summary",
              },
            }
          : tab,
      ),
    };
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "bridge.error",
      code: "bridge_exit",
      message: "bridge exited (1)",
    });
    expect(state.bridgeStatus).toBe("degraded");
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });
    expect(sent.map((entry) => entry.type)).toContain("workspace.snapshot");

    const refreshContent = `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@95210b1 | staged 0 | unstaged 517 | untracked 46
Git hotspots: terminal (281); .dharma_psmv_hyperfile_branch (147); dharma_swarm (93)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 0 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 517 | untracked 46
- dgc-core | role operator_shell | branch n/a | dirty None | modified 0 | untracked 0

## Language mix
- .py: 1125
- .md: 511
- .json: 91
- .sh: 68

## Largest Python files
- dharma_swarm/dgc_cli.py | 6908 lines | defs 192 | imports 208
- dharma_swarm/thinkodynamic_director.py | 5167 lines | defs 108 | imports 36

## Most imported local modules
- dharma_swarm.models | inbound 159
- dharma_swarm.stigmergy | inbound 35`;
    const refreshPayload = {
      version: "v1" as const,
      domain: "workspace_snapshot" as const,
      repo_root: "/Users/dhyana/dharma_swarm",
      git: {
        branch: "main",
        head: "95210b1",
        staged: 0,
        unstaged: 517,
        untracked: 46,
        changed_hotspots: [
          {name: "terminal", count: 281},
          {name: ".dharma_psmv_hyperfile_branch", count: 147},
          {name: "dharma_swarm", count: 93},
        ],
        changed_paths: [
          "terminal/src/app.tsx",
          "terminal/tests/app.test.ts",
          "terminal/src/components/RepoPane.tsx",
        ],
        sync: {
          summary: "origin/main | ahead 0 | behind 0",
          status: "tracking",
          upstream: "origin/main",
          ahead: 0,
          behind: 0,
        },
      },
      topology: {
        warnings: ["sab_canonical_repo_missing"],
        repos: [
          {
            domain: "dgc",
            name: "dharma_swarm",
            role: "canonical_core",
            canonical: true,
            path: "/Users/dhyana/dharma_swarm",
            exists: true,
            is_git: true,
            branch: "main...origin/main",
            head: "95210b1",
            dirty: true,
            modified_count: 517,
            untracked_count: 46,
          },
          {
            domain: "dgc",
            name: "dgc-core",
            role: "operator_shell",
            canonical: false,
            path: "/Users/dhyana/dgc-core",
            exists: true,
            is_git: false,
            branch: "n/a",
            head: "",
            dirty: null,
            modified_count: 0,
            untracked_count: 0,
          },
        ],
      },
      inventory: {
        python_modules: 501,
        python_tests: 495,
        scripts: 124,
        docs: 239,
        workflows: 1,
      },
      language_mix: [
        {suffix: ".py", count: 1125},
        {suffix: ".md", count: 511},
        {suffix: ".json", count: 91},
        {suffix: ".sh", count: 68},
      ],
      largest_python_files: [
        {path: "dharma_swarm/dgc_cli.py", lines: 6908, defs: 192, classes: 0, imports: 208},
        {path: "dharma_swarm/thinkodynamic_director.py", lines: 5167, defs: 108, classes: 0, imports: 36},
      ],
      most_imported_modules: [
        {module: "dharma_swarm.models", count: 159},
        {module: "dharma_swarm.stigmergy", count: 35},
      ],
    };
    const refreshPreview = workspacePayloadToPreview(refreshPayload);

    handler({
      type: "workspace.snapshot.result",
      content: refreshContent,
      payload: refreshPayload,
    });

    const repoTab = state.tabs.find((tab) => tab.id === "repo");
    expect(state.bridgeStatus).toBe("connected");
    expect(repoTab?.lines.map((line) => line.text)).toEqual(
      workspacePreviewToLines(state.liveRepoPreview ?? refreshPreview).map((line) => line.text),
    );
    expect(repoTab?.lines.map((line) => line.text)).not.toContain("stale repo output");
    expect(state.liveRepoPreview).toMatchObject(refreshPreview);
    expect(state.liveRepoPreview?.["Primary warning"]).toBe("sab_canonical_repo_missing");
    expect(state.liveRepoPreview?.["Primary changed path"]).toBe("terminal/src/app.tsx");
    expect(state.liveRepoPreview?.["Hotspot summary"]).not.toBe("stale hotspot summary");
    expect(state.authoritativeSurfaces.repo).toBe(true);
  });

  test("initial bootstrap restores persisted branch divergence and detached peers into repo previews", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Loop state": "cycle 6 running",
      "Verification bundle": "tsc=ok | cycle_acceptance=ok",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview({
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

    const state = createInitialAppState(initialState);
    const repoTab = state.tabs.find((tab) => tab.id === "repo");

    expect(state.liveRepoPreview).toMatchObject({
      "Branch divergence": "local +2/-0 | peer dharma_swarm drift main...origin/main",
      "Detached peers": "dgc-core detached",
    });
    expect(repoTab?.preview?.["Branch divergence"]).toBe("local +2/-0 | peer dharma_swarm drift main...origin/main");
    expect(repoTab?.preview?.["Detached peers"]).toBe("dgc-core detached");
    expect(repoTab?.lines.map((line) => line.text)).toContain(
      "Branch divergence: local +2/-0 | peer dharma_swarm drift main...origin/main",
    );
    expect(repoTab?.lines.map((line) => line.text)).toContain("Detached peers: dgc-core detached");
  });

  test("cold boot surfaces restored repo and control previews in visible context before the first live refresh", async () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Loop state": "cycle 6 running",
      "Loop decision": "continue required",
      "Verification bundle": "tsc=ok | cycle_acceptance=fail",
      "Next task": "Hydrate control preview from runtime state.",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview({
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
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    const sentMessages: Array<{type: string; payload: Record<string, unknown>}> = [];
    const originalSend = DharmaBridge.prototype.send;
    const originalClose = DharmaBridge.prototype.close;
    DharmaBridge.prototype.send = function mockedSend(type: string, payload: Record<string, unknown> = {}): string {
      sentMessages.push({type, payload});
      return String(sentMessages.length);
    };
    DharmaBridge.prototype.close = function mockedClose(): void {};

    const stdout = new TestStdout();
    const stdin = new TestStdin();
    let rendered = "";
    stdout.on("data", (chunk) => {
      rendered += chunk.toString("utf8");
    });

    const instance = render(React.createElement(App), {
      stdout: stdout as unknown as NodeJS.WriteStream,
      stdin: stdin as unknown as NodeJS.ReadStream,
      stderr: new TestStdout() as unknown as NodeJS.WriteStream,
      debug: true,
      patchConsole: false,
      exitOnCtrlC: false,
    });

    try {
      await flushRender();
      stdin.write("\u0012");
      await flushRender();

      const normalized = normalizeTerminalText(rendered);

      expect(sentMessages.every((message) => message.type === "handshake")).toBe(true);
      for (const line of [
        "Repo Preview",
        "Control Preview",
        "Authority placeholder | bridge booting | awaiting authoritative repo refresh",
        "Authority placeholder | bridge booting | awaiting authoritative control refresh",
        "Branch divergence local +2/-0 | peer dharma_swarm drift main...origin/main",
        "Detached peers dgc-core detached",
        "Loop cycle 6 running | continue required",
        "Verify tsc=ok",
        "Next Hydrate control preview from runtime state.",
      ]) {
        expect(normalized).toContain(normalizeTerminalText(line));
      }
    } finally {
      instance.unmount();
      instance.cleanup();
      DharmaBridge.prototype.send = originalSend;
      DharmaBridge.prototype.close = originalClose;
    }
  });

  test("cold boot derives persisted repo snapshot rows in visible context from compact repo/control preview before the first live refresh", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Loop state": "cycle 4 running",
      "Loop decision": "continue required",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Next task": "Hydrate control preview from runtime state.",
      Updated: "2026-04-03T01:15:00Z",
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@804d5d1 | tracking origin/main ahead 2 | warn sab_canonical_repo_missing | dirty staged 112 | unstaged 545 | untracked 112 | hotspot terminal (281) | path terminal/src/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | cycle 4 running | updated 2026-04-03T01:15:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | activity Sessions=18 Runs=0 ActiveRuns=0 Claims=0 ActiveClaims=0 AckedClaims=0 | artifacts Artifacts=7 PromotedFacts=2 ContextBundles=1 OperatorActions=3 | next Hydrate control preview from runtime state.",
    });
    persistRepoPreview({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "tracking origin/main ahead 2",
      Sync: "origin/main | ahead 2 | behind 0",
      Ahead: "2",
      Behind: "0",
    });
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    const bootState = createInitialAppState(initialState);
    const visibleSidebarLines = buildVisibleContextSidebarLines(
      bootState.tabs,
      "Repo",
      bootState.provider,
      bootState.model,
      bootState.bridgeStatus,
      {
        ...bootState.liveRepoPreview,
        Authority: "placeholder | bridge booting | awaiting authoritative repo refresh",
      },
      {
        ...bootState.liveControlPreview,
        Authority: "placeholder | bridge booting | awaiting authoritative control refresh",
      },
      new Date("2026-04-03T12:00:00Z"),
    );

    expect(visibleSidebarLines).toContain("Authority placeholder | bridge booting | awaiting authoritative repo refresh");
    expect(visibleSidebarLines).toContain("Authority placeholder | bridge booting | awaiting authoritative control refresh");
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"),
      ),
    ).toBe(true);
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Snapshot dirty n/a | staged 112 | unstaged 545 | un"),
      ),
    ).toBe(true);
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Snapshot topology degraded (1 warning, no"),
      ),
    ).toBe(true);
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Snapshot hotspot summary change terminal (281) | path terminal/src/RepoPane.tsx"),
      ),
    ).toBe(true);
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Repo/control stale | task terminal-repo-pane | branch main@804d5d1"),
      ),
    ).toBe(true);
    expect(visibleSidebarLines).toContain("Control task terminal-repo-pane | 3 done, 1 pending of 4 | in_progress/fail");
    expect(
      visibleSidebarLines.some((line) =>
        line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail"),
      ),
    ).toBe(true);
  });

  test("reconnect keeps persisted repo and control snapshot rows visible until the first authoritative workspace refresh", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Loop state": "cycle 5 running",
      "Loop decision": "continue required",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Next task": "Keep persisted snapshots visible through reconnect.",
      Updated: "2026-04-03T21:15:00Z",
      "Repo/control preview":
        "stale | task terminal-repo-pane | progress 3 done, 1 pending of 4 | outcome in_progress/fail | decision continue required | branch main@804d5d1 | tracking origin/main ahead 2 | warn sab_canonical_repo_missing | dirty staged 112 | unstaged 545 | untracked 112 | hotspot terminal (281) | path terminal/src/components/RepoPane.tsx | dep dharma_swarm.models | inbound 159 | cycle 5 running | updated 2026-04-03T21:15:00Z | verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail | db /Users/dhyana/.dharma/state/runtime.db | next Keep persisted snapshots visible through reconnect.",
    });
    persistRepoPreview({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "tracking origin/main ahead 2",
      Sync: "origin/main | ahead 2 | behind 0",
      Ahead: "2",
      Behind: "0",
    });
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    let state = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const visibleLines = (appState: AppState): string[] =>
      buildVisibleContextSidebarLines(
        appState.tabs,
        "Repo",
        appState.provider,
        appState.model,
        appState.bridgeStatus,
        appState.liveRepoPreview
          ? {
              ...appState.liveRepoPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.repo
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative repo refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative repo refresh`,
            }
          : undefined,
        appState.liveControlPreview
          ? {
              ...appState.liveControlPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.control
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative control refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative control refresh`,
            }
          : undefined,
      );

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    const bootLines = visibleLines(state);
    expect(bootLines).toContain("Authority placeholder | bridge booting | awaiting authoritative repo refresh");
    expect(bootLines).toContain("Authority placeholder | bridge booting | awaiting authoritative control refresh");
    expect(bootLines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"))).toBe(true);
    expect(bootLines.some((line) => line.startsWith("Snapshot dirty n/a | staged 112 | unstaged 545 | un"))).toBe(true);
    expect(bootLines).toContain("Loop cycle 5 running | continue required");
    expect(bootLines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail"))).toBe(
      true,
    );

    handler({
      type: "bridge.error",
      code: "bridge_exit",
      message: "bridge exited (1)",
    });

    const degradedLines = visibleLines(state);
    expect(state.bridgeStatus).toBe("degraded");
    expect(degradedLines).toContain("Authority placeholder | bridge degraded | awaiting authoritative repo refresh");
    expect(degradedLines).toContain("Authority placeholder | bridge degraded | awaiting authoritative control refresh");
    expect(degradedLines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"))).toBe(true);
    expect(degradedLines.some((line) => line.startsWith("Snapshot dirty n/a | staged 112 | unstaged 545 | un"))).toBe(true);
    expect(degradedLines.some((line) => line.includes("task terminal-repo-pane") && line.includes("branch main@804d5d1"))).toBe(true);
    expect(degradedLines).toContain("Loop cycle 5 running | continue required");
    expect(degradedLines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail"))).toBe(
      true,
    );
    expect(sent.map((entry) => entry.type)).toEqual(["handshake"]);

    sent.length = 0;
    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    const reconnectLines = visibleLines(state);
    expect(state.bridgeStatus).toBe("connected");
    expect(reconnectLines).toContain("Authority resyncing | awaiting authoritative repo refresh");
    expect(reconnectLines).toContain("Authority resyncing | awaiting authoritative control refresh");
    expect(reconnectLines.some((line) => line.startsWith("Snapshot branch main@804d5d1 | tracking origin/main ah"))).toBe(true);
    expect(reconnectLines.some((line) => line.startsWith("Snapshot dirty n/a | staged 112 | unstaged 545 | un"))).toBe(true);
    expect(reconnectLines.some((line) => line.startsWith("Snapshot topology degraded (1 warning, no"))).toBe(true);
    expect(reconnectLines.some((line) => line.includes("task terminal-repo-pane") && line.includes("branch main@804d5d1"))).toBe(true);
    expect(reconnectLines).toContain("Loop cycle 5 running | continue required");
    expect(reconnectLines.some((line) => line.startsWith("Control verify tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail"))).toBe(
      true,
    );
    expect(sent.map((entry) => entry.type)).toEqual(
      expect.arrayContaining([
        "status",
        "command.graph",
        "command.registry",
        "ontology.snapshot",
        "session.catalog",
        "permission.history",
        "workspace.snapshot",
        "runtime.snapshot",
        "model.policy",
        "agent.routes",
        "evolution.surface",
      ]),
    );
  });

  test("cold boot derives topology peer and pressure rows from sparse restored repo previews", async () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Loop state": "cycle 6 running",
      "Loop decision": "continue required",
      "Verification bundle": "tsc=ok | cycle_acceptance=fail",
      "Next task": "Hydrate control preview from runtime state.",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview({
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
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    const sentMessages: Array<{type: string; payload: Record<string, unknown>}> = [];
    const originalSend = DharmaBridge.prototype.send;
    const originalClose = DharmaBridge.prototype.close;
    DharmaBridge.prototype.send = function mockedSend(type: string, payload: Record<string, unknown> = {}): string {
      sentMessages.push({type, payload});
      return String(sentMessages.length);
    };
    DharmaBridge.prototype.close = function mockedClose(): void {};

    const stdout = new TestStdout();
    const stdin = new TestStdin();
    let rendered = "";
    stdout.on("data", (chunk) => {
      rendered += chunk.toString("utf8");
    });

    const instance = render(React.createElement(App), {
      stdout: stdout as unknown as NodeJS.WriteStream,
      stdin: stdin as unknown as NodeJS.ReadStream,
      stderr: new TestStdout() as unknown as NodeJS.WriteStream,
      debug: true,
      patchConsole: false,
      exitOnCtrlC: false,
    });

    try {
      await flushRender();
      stdin.write("\u0012");
      await flushRender();

      const normalized = normalizeTerminalText(rendered);

      expect(sentMessages.every((message) => message.type === "handshake")).toBe(true);
      for (const line of [
        "Repo Preview",
        "Lead peer dharma_swarm (canonical_core, main...origin/main, dirty True)",
        "Pressure dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Pressure preview 1 warning | dharma_swarm Δ563 (517 modified, 46 untracked)",
        "Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main",
      ]) {
        expect(normalized).toContain(normalizeTerminalText(line));
      }
    } finally {
      instance.unmount();
      instance.cleanup();
      DharmaBridge.prototype.send = originalSend;
      DharmaBridge.prototype.close = originalClose;
    }
  });

  test("first authoritative workspace and runtime refresh replace placeholder authority in visible context while keeping preview rows", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Runtime activity": "Sessions=18  Runs=0",
      "Artifact state": "Artifacts=7  ContextBundles=1",
      "Loop state": "cycle 6 running",
      "Loop decision": "continue required",
      "Verification bundle": "tsc=ok | cycle_acceptance=fail",
      "Next task": "Hydrate control preview from runtime state.",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "ahead of origin/main by 2",
      Ahead: "2",
      Behind: "0",
      "Dirty pressure": "high (700 local changes)",
      "Topology warnings": "3 (peer_branch_diverged, detached_peer, sab_canonical_repo_missing)",
      "Hotspot summary": "change terminal (274) | path terminal/src/app.tsx | dep dharma_swarm.models | inbound 159",
      "Branch divergence": "local +2/-0 | peer dgc-core detached",
      "Detached peers": "dgc-core detached",
    });
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    let state = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const visibleLines = (appState: AppState): string[] =>
      buildVisibleContextSidebarLines(
        appState.tabs,
        "Repo",
        appState.provider,
        appState.model,
        appState.bridgeStatus,
        appState.liveRepoPreview
          ? {
              ...appState.liveRepoPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.repo
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative repo refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative repo refresh`,
            }
          : undefined,
        appState.liveControlPreview
          ? {
              ...appState.liveControlPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.control
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative control refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative control refresh`,
            }
          : undefined,
      );

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    const bootLines = visibleLines(state);
    expect(bootLines).toContain("Authority placeholder | bridge booting | awaiting authoritative repo refresh");
    expect(bootLines).toContain("Authority placeholder | bridge booting | awaiting authoritative control refresh");
    expect(bootLines).toContain("Branch divergence local +2/-0 | peer dgc-core detached");
    expect(bootLines).toContain("Detached peers dgc-core detached");
    expect(bootLines).toContain("Loop cycle 6 running | continue required");
    expect(bootLines.some((line) => line.startsWith("Verify tsc=ok"))).toBe(true);

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    expect(sent.map((message) => message.type)).toEqual(
      expect.arrayContaining([
        "status",
        "command.graph",
        "command.registry",
        "ontology.snapshot",
        "session.catalog",
        "permission.history",
        "workspace.snapshot",
        "runtime.snapshot",
        "model.policy",
        "agent.routes",
        "evolution.surface",
      ]),
    );

    handler({
      type: "workspace.snapshot.result",
      content: `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@804d5d19675ddcd904153fa9642de47ce345d95d | staged 112 | unstaged 515 | untracked 73
Git hotspots: terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 2 | behind 0

## Topology
- warning: peer_branch_diverged
- warning: detached_peer
- warning: sab_canonical_repo_missing
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 627 | untracked 73
- dgc-core | role operator_shell | branch detached | dirty False | modified 0 | untracked 0`,
    });

    const afterWorkspaceLines = visibleLines(state);
    expect(state.authoritativeSurfaces.repo).toBe(false);
    expect(afterWorkspaceLines).toContain("Authority resyncing | awaiting authoritative repo refresh");
    expect(afterWorkspaceLines).toContain("Authority resyncing | awaiting authoritative control refresh");
    expect(afterWorkspaceLines.some((line) => line.startsWith("Snapshot branch main@804d5d1"))).toBe(true);
    expect(afterWorkspaceLines).toContain("Branch divergence local +2/-0 | peer dgc-core detached");
    expect(afterWorkspaceLines).toContain("Detached peers dgc-core detached");
    expect(afterWorkspaceLines.some((line) => line.startsWith("Snapshot dirty high (700 local changes) | staged 112 | unstaged 515"))).toBe(true);
    expect(afterWorkspaceLines.some((line) => line.startsWith("Summary change terminal (274) | path terminal/src/app.tsx"))).toBe(true);

    handler({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-refresh-1",
          created_at: "2026-04-03T06:17:11Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 18,
          active_run_count: 0,
          artifact_count: 7,
          context_bundle_count: 1,
          anomaly_count: 0,
          verification_status: "failing",
          verification_summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          verification_bundle: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          loop_state: "cycle 4 running",
          loop_decision: "continue required",
          task_progress: "3 done, 1 pending of 4",
          result_status: "in_progress",
          acceptance: "fail",
          last_result: "in_progress / fail",
          updated_at: "2026-04-03T06:17:11Z",
          durable_state: stateDir,
          next_task: "Hydrate control preview from runtime state.",
          active_task: "terminal-repo-pane",
          warnings: [],
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
    });

    const refreshedLines = visibleLines(state);
    expect(refreshedLines).toContain("Authority live | authoritative");
    expect(refreshedLines).toContain("Authority resyncing | awaiting authoritative repo refresh");
    expect(refreshedLines.some((line) => line.includes("awaiting authoritative control refresh"))).toBe(false);
    expect(refreshedLines.some((line) => line.startsWith("Snapshot branch main@804d5d1"))).toBe(true);
    expect(refreshedLines).toContain("Branch divergence local +2/-0 | peer dgc-core detached");
    expect(refreshedLines).toContain("Detached peers dgc-core detached");
    expect(refreshedLines).toContain("Loop cycle 4 running | continue required");
    expect(refreshedLines.some((line) => line.startsWith("Verify tsc=ok"))).toBe(true);
    expect(refreshedLines.some((line) => line.startsWith("Next "))).toBe(true);
  });

  test("markdown workspace snapshots with hotspot detail sections clear repo resync without typed payloads", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Loop state": "cycle 6 running",
      "Loop decision": "continue required",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview(bootstrapWorkspacePreview);
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    let state = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const visibleLines = (appState: AppState): string[] =>
      buildVisibleContextSidebarLines(
        appState.tabs,
        "Repo",
        appState.provider,
        appState.model,
        appState.bridgeStatus,
        appState.liveRepoPreview
          ? {
              ...appState.liveRepoPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.repo
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative repo refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative repo refresh`,
            }
          : undefined,
        appState.liveControlPreview
          ? {
              ...appState.liveControlPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.control
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative control refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative control refresh`,
            }
          : undefined,
      );

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    handler({
      type: "workspace.snapshot.result",
      content: `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@804d5d19675ddcd904153fa9642de47ce345d95d | staged 112 | unstaged 515 | untracked 73
Git hotspots: terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91)
Git changed paths: terminal/src/app.tsx; terminal/tests/app.test.ts; terminal/src/components/RepoPane.tsx
Git sync: origin/main | ahead 2 | behind 0
Python modules: 501
Python tests: 495
Scripts: 124
Docs: 239
Workflows: 1

## Topology
- warning: peer_branch_diverged
- dharma_swarm | role canonical_core | branch main...origin/main | dirty True | modified 627 | untracked 73
- dgc-core | role operator_shell | branch detached | dirty False | modified 0 | untracked 0

## Largest Python files
- terminal/src/app.tsx | 2853 lines | defs 10 | imports 20

## Most imported local modules
- terminal.src.app | inbound 44`,
    });

    const markdownAuthoritativeLines = visibleLines(state);
    expect(state.authoritativeSurfaces.repo).toBe(true);
    expect(markdownAuthoritativeLines).toContain("Authority live | authoritative");
    expect(markdownAuthoritativeLines).toContain("Authority resyncing | awaiting authoritative control refresh");
    expect(markdownAuthoritativeLines).toContain("Warnings 1 (peer_branch_diverged)");
    expect(markdownAuthoritativeLines).toContain("Members peer_branch_diverged");
    expect(markdownAuthoritativeLines.some((line) => line.startsWith("Branch divergence local +2/-0"))).toBe(true);
    expect(markdownAuthoritativeLines.some((line) => line.startsWith("Summary change terminal (274) | path terminal/src/app.tsx"))).toBe(true);
  });

  test("sparse reconnect runtime snapshots keep persisted control preview rows visible until authoritative control fields arrive", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Runtime DB": "/Users/dhyana/.dharma/state/runtime.db",
      "Loop state": "cycle 6 running",
      "Loop decision": "continue required",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-repo-pane",
      "Result status": "in_progress",
      Acceptance: "fail",
      "Last result": "in_progress / fail",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification summary": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      "Verification status": "1 failing, 3/4 passing",
      "Next task": "Hydrate control preview from runtime state.",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview({
      "Repo root": "/Users/dhyana/dharma_swarm",
      Branch: "main",
      Head: "804d5d1",
      "Branch status": "ahead of origin/main by 2",
      Ahead: "2",
      Behind: "0",
    });
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    let state = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const visibleLines = (appState: AppState): string[] =>
      buildVisibleContextSidebarLines(
        appState.tabs,
        "Repo",
        appState.provider,
        appState.model,
        appState.bridgeStatus,
        appState.liveRepoPreview
          ? {
              ...appState.liveRepoPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.repo
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative repo refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative repo refresh`,
            }
          : undefined,
        appState.liveControlPreview
          ? {
              ...appState.liveControlPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.control
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative control refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative control refresh`,
            }
          : undefined,
      );

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    handler({
      type: "workspace.snapshot.result",
      content: `# Workspace X-Ray
Repo root: /Users/dhyana/dharma_swarm
Git: main@804d5d19675ddcd904153fa9642de47ce345d95d | staged 112 | unstaged 515 | untracked 73
Git hotspots: terminal (274)
Git changed paths: terminal/src/app.tsx
Git sync: origin/main | ahead 2 | behind 0`,
    });

    const afterWorkspaceLines = visibleLines(state);
    expect(afterWorkspaceLines).toContain("Authority resyncing | awaiting authoritative control refresh");
    const persistedLoopLine = afterWorkspaceLines.find((line) => line.startsWith("Loop "));
    const persistedTaskLine = afterWorkspaceLines.find((line) => line.startsWith("Control task "));
    const persistedVerifyLine = afterWorkspaceLines.find((line) => line.startsWith("Control verify "));
    expect(persistedLoopLine).toBeDefined();
    expect(persistedTaskLine).toBeDefined();
    expect(persistedVerifyLine).toBeDefined();

    handler({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-sparse-refresh-1",
          created_at: "2026-04-03T06:17:11Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 18,
          active_run_count: 0,
          artifact_count: 7,
          context_bundle_count: 1,
          anomaly_count: 0,
          verification_status: "unknown",
          summary: "18 sessions, 7 artifacts, 1 context bundle",
          warnings: [],
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
    });

    const sparseLines = visibleLines(state);
    expect(sparseLines).toContain("Authority resyncing | awaiting authoritative control refresh");
    expect(sparseLines).toContain(persistedLoopLine!);
    expect(sparseLines).toContain(persistedTaskLine!);
    expect(sparseLines).toContain(persistedVerifyLine!);

    handler({
      type: "runtime.snapshot.result",
      payload: {
        version: "v1",
        domain: "runtime_snapshot",
        snapshot: {
          snapshot_id: "runtime-authoritative-refresh-1",
          created_at: "2026-04-03T06:20:00Z",
          repo_root: "/Users/dhyana/dharma_swarm",
          runtime_db: "/Users/dhyana/.dharma/state/runtime.db",
          health: "ok",
          bridge_status: "connected",
          active_session_count: 18,
          active_run_count: 0,
          artifact_count: 7,
          context_bundle_count: 1,
          anomaly_count: 0,
          verification_status: "failing",
          verification_summary: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          verification_bundle: "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
          loop_state: "cycle 6 verifying",
          loop_decision: "continue required",
          task_progress: "4 done, 0 pending of 4",
          result_status: "in_progress",
          acceptance: "fail",
          last_result: "in_progress / fail",
          updated_at: "2026-04-03T06:20:00Z",
          durable_state: stateDir,
          next_task: "Promote repo topology warnings into control preview.",
          active_task: "terminal-repo-pane",
          warnings: [],
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
    });

    const authoritativeLines = visibleLines(state);
    expect(authoritativeLines).toContain("Authority live | authoritative");
    expect(authoritativeLines).toContain("Loop cycle 6 verifying | continue required");
    expect(authoritativeLines.some((line) => line.startsWith("Next Promote repo topology warnings into control preview."))).toBe(true);
  });

  test("sparse reconnect workspace payloads keep persisted topology and hotspot rows visible until authoritative repo fields arrive", () => {
    const stateDir = makeSupervisorStateDir();
    process.env.DHARMA_TERMINAL_SUPERVISOR_STATE_DIR = stateDir;

    persistControlPreview({
      "Loop state": "cycle 6 running",
      "Loop decision": "continue required",
      "Task progress": "3 done, 1 pending of 4",
      "Active task": "terminal-repo-pane",
      "Verification bundle": "tsc=ok | py_compile_bridge=ok | bridge_snapshots=ok | cycle_acceptance=fail",
      Updated: "2026-04-03T01:15:00Z",
    });
    persistRepoPreview(bootstrapWorkspacePreview);
    saveTerminalStateOverride({version: 3, sidebarVisible: true, sidebarMode: "context"});

    let state = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const visibleLines = (appState: AppState): string[] =>
      buildVisibleContextSidebarLines(
        appState.tabs,
        "Repo",
        appState.provider,
        appState.model,
        appState.bridgeStatus,
        appState.liveRepoPreview
          ? {
              ...appState.liveRepoPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.repo
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative repo refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative repo refresh`,
            }
          : undefined,
        appState.liveControlPreview
          ? {
              ...appState.liveControlPreview,
              Authority:
                appState.bridgeStatus === "connected"
                  ? appState.authoritativeSurfaces.control
                    ? "live | authoritative"
                    : "resyncing | awaiting authoritative control refresh"
                  : `placeholder | bridge ${appState.bridgeStatus} | awaiting authoritative control refresh`,
            }
          : undefined,
      );

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "handshake.result",
      default_provider: "codex",
      providers: [{provider_id: "codex", default_model: "gpt-5.4"}],
    });

    handler({
      type: "workspace.snapshot.result",
      payload: {
        version: "v1",
        domain: "workspace_snapshot",
        repo_root: "/Users/dhyana/dharma_swarm",
        git: {
          branch: "main",
          head: "804d5d19675ddcd904153fa9642de47ce345d95d",
          staged: 112,
          unstaged: 515,
          untracked: 73,
          changed_hotspots: [{name: "terminal", count: 274}],
          changed_paths: ["terminal/src/app.tsx"],
          sync: {summary: "origin/main | ahead 2 | behind 0", status: "tracking", upstream: "origin/main", ahead: 2, behind: 0},
        },
        inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
        language_mix: [{suffix: ".py", count: 1125}],
      } as Record<string, unknown>,
    });

    const sparseLines = visibleLines(state);
    expect(state.liveRepoPreview?.["Topology warnings"]).toBe("1 (sab_canonical_repo_missing)");
    expect(state.liveRepoPreview?.["Topology warning members"]).toBe("sab_canonical_repo_missing");
    expect(state.liveRepoPreview?.["Branch divergence"]).toBe("local +0/-0 | peer dharma_swarm track main...origin/main");
    expect(state.liveRepoPreview?.["Hotspot summary"]).toBe(
      "change terminal (274); .dharma_psmv_hyperfile_branch (142); dharma_swarm (91) | files dgc_cli.py (6908 lines) | deps dharma_swarm.models | inbound 159 | paths terminal/src/protocol.ts",
    );
    expect(state.authoritativeSurfaces.repo).toBe(false);
    expect(sparseLines).toContain("Authority resyncing | awaiting authoritative repo refresh");
    expect(sparseLines).toContain("Warnings 1 (sab_canonical_repo_missing)");
    expect(sparseLines).toContain("Members sab_canonical_repo_missing");
    expect(sparseLines).toContain("Branch divergence local +0/-0 | peer dharma_swarm track main...origin/main");
    expect(sparseLines.some((line) => line.startsWith("Summary change terminal (274) | path terminal/src/protocol.ts"))).toBe(true);

    handler({
      type: "workspace.snapshot.result",
      payload: {
        version: "v1",
        domain: "workspace_snapshot",
        repo_root: "/Users/dhyana/dharma_swarm",
        git: {
          branch: "main",
          head: "804d5d19675ddcd904153fa9642de47ce345d95d",
          staged: 112,
          unstaged: 515,
          untracked: 73,
          changed_hotspots: [{name: "terminal", count: 274}],
          changed_paths: ["terminal/src/app.tsx"],
          sync: {summary: "origin/main | ahead 2 | behind 0", status: "tracking", upstream: "origin/main", ahead: 2, behind: 0},
        },
        topology: {
          warnings: ["peer_branch_diverged"],
          repos: [
            {
              domain: "dgc",
              name: "dharma_swarm",
              role: "canonical_core",
              canonical: true,
              path: "/Users/dhyana/dharma_swarm",
              exists: true,
              is_git: true,
              branch: "main...origin/main",
              head: "804d5d1",
              dirty: true,
              modified_count: 627,
              untracked_count: 73,
            },
            {
              domain: "operator",
              name: "dgc-core",
              role: "operator_shell",
              canonical: false,
              path: "/Users/dhyana/dgc-core",
              exists: true,
              is_git: true,
              branch: "detached",
              head: "c0ffee1",
              dirty: false,
              modified_count: 0,
              untracked_count: 0,
            },
          ],
        },
        inventory: {python_modules: 501, python_tests: 495, scripts: 124, docs: 239, workflows: 1},
        language_mix: [{suffix: ".py", count: 1125}],
        largest_python_files: [{path: "terminal/src/app.tsx", lines: 2749, defs: 10, classes: 0, imports: 20}],
        most_imported_modules: [{module: "terminal.src.app", count: 44}],
      },
    });

    const authoritativeLines = visibleLines(state);
    expect(state.authoritativeSurfaces.repo).toBe(true);
    expect(authoritativeLines).toContain("Authority live | authoritative");
    expect(state.liveRepoPreview?.["Topology warnings"]).toBe("1 (peer_branch_diverged)");
    expect(state.liveRepoPreview?.["Topology warning members"]).toBe("peer_branch_diverged");
    expect(state.liveRepoPreview?.["Branch divergence"]).toContain("local +2/-0");
    expect(state.liveRepoPreview?.["Branch divergence"]).not.toBe("local +0/-0 | peer dharma_swarm track main...origin/main");
    expect(state.liveRepoPreview?.["Hotspot summary"]).toBe(
      "change terminal (274) | files app.tsx (2749 lines) | deps terminal.src.app | inbound 44 | paths terminal/src/app.tsx",
    );
    expect(authoritativeLines).toContain("Warnings 1 (peer_branch_diverged)");
    expect(authoritativeLines).toContain("Members peer_branch_diverged");
    expect(authoritativeLines.some((line) => line.startsWith("Branch divergence local +2/-0"))).toBe(true);
    expect(authoritativeLines.some((line) => line.startsWith("Summary change terminal (274) | path terminal/src/app.tsx"))).toBe(true);
  });

  test("replaces the sessions tab from typed catalog/detail payloads and requests drilldown", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return String(sent.length);
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "session.catalog.result",
      content: "legacy catalog prose should be ignored",
      payload: {
        count: 1,
        sessions: [
          {
            session: {
              session_id: "sess-1",
              provider_id: "codex",
              model_id: "gpt-5.4",
              cwd: "/repo",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T01:00:00Z",
              status: "completed",
              summary: "overnight build",
              metadata: {},
            },
            replay_ok: true,
            replay_issues: [],
            total_turns: 1,
            total_cost_usd: 1.5,
          },
        ],
      },
    });

    expect(state.sessionPane.catalog?.count).toBe(1);
    expect(state.sessionPane.selectedSessionId).toBe("sess-1");
    expect(state.tabs.find((tab) => tab.id === "sessions")?.lines.some((line) => line.text.includes("legacy catalog prose"))).toBe(false);
    expect(sent).toContainEqual({
      type: "session.detail",
      payload: {session_id: "sess-1", transcript_limit: 40},
    });

    handler({
      type: "session.detail.result",
      content: "legacy detail prose should be ignored",
      payload: {
        session: {
          session_id: "sess-1",
          provider_id: "codex",
          model_id: "gpt-5.4",
          cwd: "/repo",
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T01:00:00Z",
          status: "completed",
          summary: "overnight build",
          metadata: {},
        },
        replay_ok: true,
        replay_issues: [],
        compaction_preview: {
          event_count: 6,
          by_type: {text_delta: 2},
          compactable_ratio: 0.333,
          protected_event_types: ["session_start", "session_end"],
          recent_event_types: ["session_start", "text_delta", "session_end"],
        },
        recent_events: [
          {
            event_id: "evt-1",
            event_type: "tool_result",
            source: "provider",
            audience: "all",
            transport: "local",
            session_id: "sess-1",
            created_at: "2026-04-01T00:30:00Z",
            payload: {tool_name: "Read", content: "ok"},
          },
        ],
        approval_history: {
          version: "v1",
          domain: "permission_history",
          count: 1,
          entries: [
            {
              action_id: "perm-detail-1",
              decision: {
                version: "v1",
                domain: "permission_decision",
                action_id: "perm-detail-1",
                tool_name: "Bash",
                risk: "shell_or_network",
                decision: "require_approval",
                rationale: "Bash is not classified as safe and remains operator-gated",
                policy_source: "legacy-governance",
                requires_confirmation: true,
                command_prefix: "git status",
                metadata: {session_id: "sess-1"},
              },
              resolution: {
                version: "v1",
                domain: "permission_resolution",
                action_id: "perm-detail-1",
                resolution: "approved",
                resolved_at: "2026-04-02T00:10:00Z",
                actor: "operator",
                summary: "approved perm-detail-1",
                enforcement_state: "runtime_recorded",
                metadata: {session_id: "sess-1"},
              },
              outcome: {
                version: "v1",
                domain: "permission_outcome",
                action_id: "perm-detail-1",
                outcome: "runtime_applied",
                outcome_at: "2026-04-02T00:10:01Z",
                source: "runtime",
                summary: "runtime applied perm-detail-1",
                metadata: {runtime_action_id: "runtime_detail_1", runtime_event_id: "evt_runtime_detail_1"},
              },
              first_seen_at: "2026-04-02T00:00:00Z",
              last_seen_at: "2026-04-02T00:10:00Z",
              seen_count: 2,
              pending: false,
              status: "runtime_applied",
            },
          ],
        },
      },
    });

    const sessionsTab = state.tabs.find((tab) => tab.id === "sessions");
    expect(state.sessionPane.detailsBySessionId["sess-1"]?.compaction_preview.event_count).toBe(6);
    expect(state.sessionPane.detailsBySessionId["sess-1"]?.approval_history?.count).toBe(1);
    expect(sessionsTab?.lines.some((line) => line.text.includes("legacy detail prose"))).toBe(false);
    expect(sessionsTab?.lines.some((line) => line.text.includes("# Session Detail"))).toBe(true);
    expect(sessionsTab?.lines.some((line) => line.text.includes("tool_result"))).toBe(true);
    expect(sessionsTab?.lines.some((line) => line.text.includes("## Approval history"))).toBe(true);
    expect(sessionsTab?.lines.some((line) => line.text.includes("runtime_applied"))).toBe(true);
    expect(sessionsTab?.lines.some((line) => line.text.includes("runtime_detail_1 | evt_runtime_detail_1"))).toBe(true);
  });
});

describe("typed approval bridge handling", () => {
  test("tracks pending approvals from typed permission payloads and renders the approvals pane", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.decision",
      payload: {
        version: "v1",
        domain: "permission_decision",
        action_id: "perm_1",
        tool_name: "Bash",
        risk: "shell_or_network",
        decision: "require_approval",
        rationale: "Bash is not classified as safe and remains operator-gated",
        policy_source: "legacy-governance",
        requires_confirmation: true,
        command_prefix: "git status",
        metadata: {
          tool_call_id: "tool_1",
          provider_id: "codex",
          session_id: "sess_1",
        },
      },
    });

    const approvalsTab = state.tabs.find((tab) => tab.id === "approvals");
    expect(state.activeTabId).toBe("chat");
    expect(state.approvalPane.historyBacked).toBe(false);
    expect(state.approvalPane.selectedActionId).toBe("perm_1");
    expect(state.approvalPane.entriesByActionId.perm_1?.pending).toBe(true);
    expect(approvalsTab?.preview?.Authority).toBe("provisional_live");
    expect(approvalsTab?.preview?.Pending).toBe("1");
    expect(approvalsTab?.lines.some((line) => line.text.includes("Action: perm_1"))).toBe(true);
    expect(approvalsTab?.lines.some((line) => line.text.includes("Session: sess_1"))).toBe(true);
    expect(state.statusLine).toBe("approval required Bash (shell_or_network)");
    expect(sent).toContainEqual({type: "permission.history", payload: {limit: 50}});
  });

  test("hydrates approval pane from typed permission history payloads", () => {
    let state: AppState = createInitialAppState(initialState);
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.history.result",
      payload: {
        version: "v1",
        domain: "permission_history",
        count: 1,
        entries: [
          {
            action_id: "perm_hist_1",
            decision: {
              version: "v1",
              domain: "permission_decision",
              action_id: "perm_hist_1",
              tool_name: "Bash",
              risk: "shell_or_network",
              decision: "require_approval",
              rationale: "Bash is not classified as safe and remains operator-gated",
              policy_source: "legacy-governance",
              requires_confirmation: true,
              command_prefix: "git status",
              metadata: {
                tool_call_id: "tool_h1",
                provider_id: "codex",
                session_id: "sess_h1",
              },
            },
            resolution: {
              version: "v1",
              domain: "permission_resolution",
              action_id: "perm_hist_1",
              resolution: "approved",
              resolved_at: "2026-04-02T00:10:00Z",
              actor: "operator",
              summary: "approved perm_hist_1",
              enforcement_state: "recorded_only",
              metadata: {
                session_id: "sess_h1",
              },
            },
            first_seen_at: "2026-04-02T00:00:00Z",
            last_seen_at: "2026-04-02T00:10:00Z",
            seen_count: 2,
            pending: false,
            status: "approved",
          },
        ],
      },
    });

    const approvalsTab = state.tabs.find((tab) => tab.id === "approvals");
    expect(state.approvalPane.historyBacked).toBe(true);
    expect(state.approvalPane.lastHistorySyncAt).toBeDefined();
    expect(state.approvalPane.selectedActionId).toBe("perm_hist_1");
    expect(state.approvalPane.entriesByActionId.perm_hist_1?.status).toBe("approved");
    expect(state.approvalPane.entriesByActionId.perm_hist_1?.resolution?.enforcement_state).toBe("recorded_only");
    expect(approvalsTab?.preview?.Authority).toBe("history");
    expect(approvalsTab?.preview?.Resolved).toBe("1");
    expect(approvalsTab?.lines.some((line) => line.text.includes("Resolution: approved"))).toBe(true);
  });

  test("tracks operator approval resolution from typed payloads without claiming runtime enforcement", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.decision",
      payload: {
        version: "v1",
        domain: "permission_decision",
        action_id: "perm_2",
        tool_name: "Bash",
        risk: "shell_or_network",
        decision: "require_approval",
        rationale: "Bash is not classified as safe and remains operator-gated",
        policy_source: "legacy-governance",
        requires_confirmation: true,
        command_prefix: "git status",
        metadata: {
          tool_call_id: "tool_2",
          provider_id: "codex",
          session_id: "sess_2",
        },
      },
    });
    handler({
      type: "permission.resolution",
      payload: {
        version: "v1",
        domain: "permission_resolution",
        action_id: "perm_2",
        resolution: "approved",
        resolved_at: "2026-04-02T00:10:00Z",
        actor: "operator",
        summary: "approved perm_2",
        note: "safe after inspection",
        enforcement_state: "recorded_only",
        metadata: {
          session_id: "sess_2",
        },
      },
    });

    const approvalsTab = state.tabs.find((tab) => tab.id === "approvals");
    expect(state.approvalPane.historyBacked).toBe(false);
    expect(state.approvalPane.entriesByActionId.perm_2?.pending).toBe(false);
    expect(state.approvalPane.entriesByActionId.perm_2?.status).toBe("approved");
    expect(state.approvalPane.entriesByActionId.perm_2?.resolution?.enforcement_state).toBe("recorded_only");
    expect(approvalsTab?.preview?.Authority).toBe("provisional_live");
    expect(approvalsTab?.preview?.Resolved).toBe("1");
    expect(approvalsTab?.preview?.Status).toBe("approved");
    expect(approvalsTab?.lines.some((line) => line.text.includes("Resolution: approved"))).toBe(true);
    expect(state.statusLine).toBe("approved perm_2 (recorded_only)");
    expect(sent).toContainEqual({type: "permission.history", payload: {limit: 50}});
  });

  test("tracks runtime approval outcome from typed payloads and reconciles back to history", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.decision",
      payload: {
        version: "v1",
        domain: "permission_decision",
        action_id: "perm_3",
        tool_name: "Bash",
        risk: "shell_or_network",
        decision: "require_approval",
        rationale: "Bash is not classified as safe and remains operator-gated",
        policy_source: "legacy-governance",
        requires_confirmation: true,
        command_prefix: "git status",
        metadata: {
          tool_call_id: "tool_3",
          provider_id: "codex",
          session_id: "sess_3",
        },
      },
    });
    handler({
      type: "permission.resolution",
      payload: {
        version: "v1",
        domain: "permission_resolution",
        action_id: "perm_3",
        resolution: "approved",
        resolved_at: "2026-04-02T00:10:00Z",
        actor: "operator",
        summary: "approved perm_3",
        enforcement_state: "runtime_recorded",
        metadata: {
          session_id: "sess_3",
          runtime_action_id: "runtime_3",
        },
      },
    });
    handler({
      type: "permission.outcome",
      payload: {
        version: "v1",
        domain: "permission_outcome",
        action_id: "perm_3",
        outcome: "runtime_applied",
        outcome_at: "2026-04-02T00:10:01Z",
        source: "runtime",
        summary: "runtime applied perm_3",
        metadata: {
          session_id: "sess_3",
          runtime_action_id: "runtime_3",
        },
      },
    });

    const approvalsTab = state.tabs.find((tab) => tab.id === "approvals");
    expect(state.approvalPane.historyBacked).toBe(false);
    expect(state.approvalPane.entriesByActionId.perm_3?.status).toBe("runtime_applied");
    expect(state.approvalPane.entriesByActionId.perm_3?.outcome?.outcome).toBe("runtime_applied");
    expect(approvalsTab?.preview?.Authority).toBe("provisional_live");
    expect(approvalsTab?.preview?.Outcome).toBe("runtime_applied");
    expect(approvalsTab?.lines.some((line) => line.text.includes("Runtime outcome: runtime_applied"))).toBe(true);
    expect(state.statusLine).toBe("runtime_applied perm_3");
    expect(sent.filter((message) => message.type === "permission.history")).toHaveLength(3);
  });

  test("tracks rejected runtime approval outcome from typed payloads", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.decision",
      payload: {
        version: "v1",
        domain: "permission_decision",
        action_id: "perm_4",
        tool_name: "Bash",
        risk: "shell_or_network",
        decision: "require_approval",
        rationale: "Bash is not classified as safe and remains operator-gated",
        policy_source: "legacy-governance",
        requires_confirmation: true,
        command_prefix: "git status",
        metadata: {
          tool_call_id: "tool_4",
          provider_id: "codex",
          session_id: "sess_4",
        },
      },
    });
    handler({
      type: "permission.resolution",
      payload: {
        version: "v1",
        domain: "permission_resolution",
        action_id: "perm_4",
        resolution: "denied",
        resolved_at: "2026-04-02T00:10:00Z",
        actor: "operator",
        summary: "denied perm_4",
        enforcement_state: "runtime_recorded",
        metadata: {
          session_id: "sess_4",
          runtime_action_id: "runtime_4",
        },
      },
    });
    handler({
      type: "permission.outcome",
      payload: {
        version: "v1",
        domain: "permission_outcome",
        action_id: "perm_4",
        outcome: "runtime_rejected",
        outcome_at: "2026-04-02T00:10:01Z",
        source: "runtime",
        summary: "runtime rejected perm_4",
        metadata: {
          session_id: "sess_4",
          runtime_action_id: "runtime_4",
          runtime_event_id: "evt_runtime_4",
        },
      },
    });

    const approvalsTab = state.tabs.find((tab) => tab.id === "approvals");
    expect(state.approvalPane.entriesByActionId.perm_4?.status).toBe("runtime_rejected");
    expect(state.approvalPane.entriesByActionId.perm_4?.outcome?.outcome).toBe("runtime_rejected");
    expect(approvalsTab?.preview?.Outcome).toBe("runtime_rejected");
    expect(approvalsTab?.lines.some((line) => line.text.includes("Runtime outcome: runtime_rejected"))).toBe(true);
    expect(approvalsTab?.lines.some((line) => line.text.includes("Runtime event id: evt_runtime_4"))).toBe(true);
    expect(state.statusLine).toBe("runtime_rejected perm_4");
    expect(sent.filter((message) => message.type === "permission.history")).toHaveLength(3);
  });

  test("requests canonical approval history when a resolution arrives before local decision state", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.resolution",
      payload: {
        version: "v1",
        domain: "permission_resolution",
        action_id: "perm_unknown",
        resolution: "approved",
        resolved_at: "2026-04-02T00:10:00Z",
        actor: "operator",
        summary: "approved perm_unknown",
        enforcement_state: "recorded_only",
        metadata: {
          session_id: "sess_missing",
        },
      },
    });

    expect(state.approvalPane.entriesByActionId.perm_unknown).toBeUndefined();
    expect(sent).toContainEqual({type: "permission.history", payload: {limit: 50}});
  });

  test("requests canonical approval history when an outcome arrives before local approval state", () => {
    let state: AppState = createInitialAppState(initialState);
    const sent: Array<{type: string; payload: Record<string, unknown>}> = [];
    const bridge = {
      send(type: string, payload: Record<string, unknown> = {}) {
        sent.push({type, payload});
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "permission.outcome",
      payload: {
        version: "v1",
        domain: "permission_outcome",
        action_id: "perm_unknown",
        outcome: "runtime_applied",
        outcome_at: "2026-04-02T00:10:01Z",
        source: "runtime",
        summary: "runtime applied perm_unknown",
        metadata: {
          session_id: "sess_missing",
        },
      },
    });

    expect(state.approvalPane.entriesByActionId.perm_unknown).toBeUndefined();
    expect(sent).toContainEqual({type: "permission.history", payload: {limit: 50}});
  });

  test("ingests structured activity entries for thinking and tool events", () => {
    let state: AppState = createInitialAppState(initialState);
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({type: "thinking_delta", content: "Inspecting the operator bridge flow"});
    handler({
      type: "tool_call_complete",
      tool_name: "exec_command",
      tool_call_id: "tool-99",
      arguments: JSON.stringify({command: "git status", description: "Check worktree"}),
    });

    expect(state.activityFeed.entries).toHaveLength(2);
    expect(state.activityFeed.entries[0]?.kind).toBe("thinking");
    expect(state.activityFeed.entries[1]?.kind).toBe("tool");
    expect(state.activityFeed.entries[1]?.correlationId).toBe("tool-99");
  });

  test("merges correlated tool activity into one evolving entry", () => {
    let state: AppState = createInitialAppState(initialState);
    const bridge = {
      send() {
        return "1";
      },
    } as unknown as DharmaBridge;

    const handler = createBridgeEventHandler({
      dispatch: (action) => {
        state = reduceApp(state, action);
      },
      getState: () => state,
      bridge,
      pendingBootstraps: {current: {}},
    });

    handler({
      type: "tool_call_complete",
      tool_name: "exec_command",
      tool_call_id: "tool-merge",
      arguments: JSON.stringify({command: "git status", description: "Check worktree"}),
    });
    handler({
      type: "tool_result",
      tool_name: "exec_command",
      tool_call_id: "tool-merge",
      content: "working tree clean",
    });

    const toolEntries = state.activityFeed.entries.filter((entry) => entry.kind === "tool");
    expect(toolEntries).toHaveLength(2);
    expect(toolEntries.every((entry) => entry.correlationId === "tool-merge")).toBe(true);
    expect(toolEntries[0]?.phase).toBe("running");
    expect(toolEntries[0]?.detail?.some((line) => line.includes("git status"))).toBe(true);
    expect(toolEntries[1]?.phase).toBe("complete");
    expect(toolEntries[1]?.summary).toContain("working tree clean");
  });
});
