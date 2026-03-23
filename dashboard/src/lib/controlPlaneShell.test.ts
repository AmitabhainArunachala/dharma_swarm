import assert from "node:assert/strict";
import test from "node:test";

import * as controlPlaneShell from "./controlPlaneShell.ts";
import {
  buildControlPlanePageSummary,
  buildControlPlaneSurfaceSections,
  buildControlPlanePosture,
  buildControlPlaneStripCells,
  buildControlPlaneSyncState,
  buildDashboardKeyboardRouteMap,
  controlPlaneOfflineMessage,
  controlPlaneRouteShortcut,
  controlPlaneRuntimeCommands,
  controlPlaneSurfaceToneLabel,
  controlPlanePrimaryRoute,
  controlPlaneStableRouteHrefs,
  splitControlPlaneSurfaces,
} from "./controlPlaneShell.ts";
import {
  CONTROL_PLANE_ROUTE_DECK,
  type ControlPlaneSurface,
} from "./controlPlaneSurfaces.ts";
import type { RuntimeControlPlaneSnapshot } from "./runtimeControlPlane.ts";

function makeSurface(
  overrides: Partial<ControlPlaneSurface> = {},
): ControlPlaneSurface {
  return {
    id: "command-post",
    href: "/dashboard/command-post",
    label: "Command Post",
    summary: "Dual-orchestrator relay.",
    accent: "aozora",
    metric: "3/4 lanes ready",
    detail: "Default lane anchors the operator path.",
    tone: "ok",
    current: false,
    ...overrides,
  };
}

function makeSnapshot(
  overrides: Partial<RuntimeControlPlaneSnapshot> = {},
): RuntimeControlPlaneSnapshot {
  return {
    chatReady: true,
    healthReady: true,
    statusKind: "warn",
    statusLabel: "degraded",
    detail:
      "Runtime health is degraded; keep the shell on canonical routes while providers recover.",
    healthStatusLabel: "2 anomalies · 0.84 fit",
    defaultProfile: {
      id: "claude_opus",
      label: "Claude Opus 4.6",
      provider: "openrouter",
      model: "anthropic/claude-opus-4-6",
      accent: "aozora",
      summary: "Strategic operator",
      available: true,
      availability_kind: "api_key",
      status_note: "Served by the dashboard backend via OpenRouter.",
    },
    totalProfileCount: 4,
    availableProfileCount: 3,
    unavailableProfileCount: 1,
    persistentSessions: true,
    contractVersion: "2026-03-20.chat.v1",
    sessionFeedReady: true,
    sessionFeedLabel: "/ws/chat/session/{session_id}",
    sessionFeedPathTemplate: "/ws/chat/session/{session_id}",
    agentCount: 9,
    anomalyCount: 2,
    tracesLastHour: 37,
    failureRateLabel: "2.8%",
    meanFitnessLabel: "0.84",
    ...overrides,
  };
}

function buildStripSupport(
  snapshot: RuntimeControlPlaneSnapshot,
  surfaces?: ControlPlaneSurface[],
) {
  const buildSupport = (
    controlPlaneShell as unknown as {
      buildControlPlaneStripSupport?: (
        snapshot: RuntimeControlPlaneSnapshot,
        surfaces?: ControlPlaneSurface[],
      ) => {
        title: string;
        detail: string;
        tone: string;
        commands: string[];
        href?: string;
        actionLabel?: string;
      } | null;
    }
  ).buildControlPlaneStripSupport;

  assert.equal(typeof buildSupport, "function");
  return buildSupport?.(snapshot, surfaces) ?? null;
}

test("controlPlaneStableRouteHrefs mirrors the canonical control-plane deck order", () => {
  assert.deepEqual(
    controlPlaneStableRouteHrefs(),
    CONTROL_PLANE_ROUTE_DECK.map((route) => route.href),
  );
});

test("controlPlanePrimaryRoute points shell actions at command post instead of legacy claude", () => {
  const primary = controlPlanePrimaryRoute();

  assert.equal(primary.href, "/dashboard/command-post");
  assert.equal(primary.label, "Command Post");
});

test("buildDashboardKeyboardRouteMap keeps c on the canonical control-plane route", () => {
  const routes = buildDashboardKeyboardRouteMap();

  assert.equal(routes.c, "/dashboard/command-post");
  assert.equal(routes.l, "/dashboard/log");
  assert.equal(routes.c === "/dashboard/claude", false);
});

test("controlPlaneOfflineMessage points operators at the canonical dashboard control script", () => {
  assert.deepEqual(controlPlaneRuntimeCommands(), [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh start",
    "bash scripts/dashboard_ctl.sh restart",
  ]);

  const message = controlPlaneOfflineMessage();

  assert.match(message, /dashboard_ctl\.sh status/);
  assert.match(message, /dashboard_ctl\.sh start/);
  assert.doesNotMatch(message, /python -m api\.main/);
});

test("controlPlaneRouteShortcut keeps g-prefixed shortcuts aligned with the canonical route deck", () => {
  assert.equal(controlPlaneRouteShortcut("command-post"), "g c");
  assert.equal(controlPlaneRouteShortcut("qwen35"), "g q");
  assert.equal(controlPlaneRouteShortcut("observatory"), "g v");
  assert.equal(controlPlaneRouteShortcut("runtime"), "g r");
});

test("controlPlaneSurfaceToneLabel exposes stable posture language for the shared route cards", () => {
  assert.equal(controlPlaneSurfaceToneLabel("ok"), "stable");
  assert.equal(controlPlaneSurfaceToneLabel("warn"), "degraded");
  assert.equal(controlPlaneSurfaceToneLabel("error"), "blocked");
  assert.equal(controlPlaneSurfaceToneLabel("muted"), "awaiting signal");
});

test("buildControlPlaneSyncState reports syncing during the first control-plane load", () => {
  assert.deepEqual(
    buildControlPlaneSyncState({
      isLoading: true,
      isFetching: true,
    }),
    {
      busy: true,
      label: "syncing",
      detail: "Waiting for the canonical runtime sources to answer.",
    },
  );
});

test("buildControlPlaneSyncState reports refreshing when a live control plane refetches", () => {
  assert.deepEqual(
    buildControlPlaneSyncState({
      isLoading: false,
      isFetching: true,
    }),
    {
      busy: true,
      label: "refreshing",
      detail: "Refreshing the canonical runtime state without leaving the current surface.",
    },
  );
});

test("buildControlPlaneSyncState reports live when the control plane is idle", () => {
  assert.deepEqual(
    buildControlPlaneSyncState({
      isLoading: false,
      isFetching: false,
    }),
    {
      busy: false,
      label: "live",
      detail: "Canonical runtime state is current on this surface.",
    },
  );
});

test("buildControlPlanePosture surfaces the highest-severity canonical route", () => {
  const posture = buildControlPlanePosture([
    makeSurface(),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      metric: "provider unreachable",
      tone: "warn",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      metric: "2 anomalies · 37 traces/h",
      tone: "error",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      metric: "ok",
      current: true,
    }),
  ]);

  assert.equal(posture.stableCount, 2);
  assert.equal(posture.degradedCount, 1);
  assert.equal(posture.blockedCount, 1);
  assert.equal(posture.waitingCount, 0);
  assert.equal(posture.postureLabel, "1 blocked · 1 degraded");
  assert.equal(posture.priorityLabel, "Attention route");
  assert.equal(posture.currentSurface?.label, "Runtime");
  assert.equal(posture.prioritySurface?.label, "Observatory");
});

test("buildControlPlanePosture distinguishes muted routes from degraded ones", () => {
  const posture = buildControlPlanePosture([
    makeSurface({ current: true }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      metric: "awaiting health",
      detail: "Health has not reported yet.",
      tone: "muted",
    }),
  ]);

  assert.equal(posture.postureLabel, "1 awaiting signal");
  assert.equal(posture.priorityLabel, "Waiting route");
  assert.equal(posture.prioritySurface?.label, "Runtime");
  assert.match(posture.postureDetail, /awaiting canonical route telemetry/i);
});

test("buildControlPlanePosture reports a stable canonical route deck", () => {
  const posture = buildControlPlanePosture([
    makeSurface({ current: true }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
    }),
  ]);

  assert.equal(posture.postureLabel, "4/4 stable");
  assert.equal(posture.priorityLabel, "Stable route");
  assert.equal(posture.prioritySurface?.label, "Command Post");
  assert.match(posture.postureDetail, /all canonical routes are stable/i);
});

test("buildControlPlanePosture keeps Command Post as the stable anchor even when another surface is active", () => {
  const posture = buildControlPlanePosture([
    makeSurface(),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      current: true,
    }),
  ]);

  assert.equal(posture.currentSurface?.label, "Runtime");
  assert.equal(posture.priorityLabel, "Stable route");
  assert.equal(posture.prioritySurface?.label, "Command Post");
});

test("buildControlPlaneStripCells exposes shell contract truth on the shared operator strip", () => {
  const cells = buildControlPlaneStripCells({
    snapshot: makeSnapshot(),
    surfaces: [
      makeSurface(),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
        metric: "provider unreachable",
        tone: "warn",
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
        metric: "2 anomalies · 37 traces/h",
        tone: "error",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "degraded",
        tone: "warn",
        current: true,
      }),
    ],
  });

  assert.deepEqual(
    cells.map((cell) => cell.label),
    [
      "Runtime",
      "Health",
      "Shell contract",
      "Session rail",
      "Operator path",
      "Attention route",
    ],
  );
  assert.equal(cells[0]?.value, "degraded");
  assert.equal(cells[1]?.value, "2 anomalies · 0.84 fit");
  assert.equal(cells[2]?.value, "2026-03-20.chat.v1 · persistent sessions");
  assert.equal(cells[3]?.value, "/ws/chat/session/{session_id}");
  assert.equal(cells[4]?.value, "1 blocked · 2 degraded");
  assert.equal(cells[5]?.value, "Observatory · 2 anomalies · 37 traces/h");
  assert.equal(cells[2]?.tone, "ok");
  assert.equal(cells[3]?.tone, "ok");
  assert.equal(cells[5]?.tone, "error");
});

test("buildControlPlaneStripCells falls back to lane and session summary without surface posture", () => {
  const cells = buildControlPlaneStripCells({
    snapshot: makeSnapshot({
      healthReady: false,
      statusKind: "warn",
      statusLabel: "health unavailable",
      healthStatusLabel: "health unavailable",
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      defaultProfile: null,
      persistentSessions: false,
      contractVersion: "unknown",
      sessionFeedReady: false,
      sessionFeedLabel: "not advertised",
      sessionFeedPathTemplate: null,
    }),
  });

  assert.deepEqual(
    cells.map((cell) => cell.label),
    ["Runtime", "Health", "Shell contract", "Session rail", "Default lane", "Profiles"],
  );
  assert.equal(cells[2]?.value, "unknown · ephemeral sessions");
  assert.equal(cells[3]?.value, "not advertised");
  assert.equal(cells[4]?.value, "No lane advertised");
  assert.equal(cells[5]?.value, "0 lanes");
  assert.equal(cells[2]?.tone, "warn");
  assert.equal(cells[3]?.tone, "warn");
});

test("buildControlPlaneStripCells keeps shell cells muted while the control plane is still cold-starting", () => {
  const cells = buildControlPlaneStripCells({
    snapshot: makeSnapshot({
      chatReady: false,
      healthReady: false,
      statusKind: "muted",
      statusLabel: "syncing",
      detail: "Waiting for the canonical runtime sources to report.",
      healthStatusLabel: "awaiting health",
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      defaultProfile: null,
      persistentSessions: false,
      contractVersion: "unknown",
      sessionFeedReady: false,
      sessionFeedLabel: "awaiting session rail",
      sessionFeedPathTemplate: null,
      agentCount: 0,
      anomalyCount: 0,
      tracesLastHour: 0,
      failureRateLabel: "unknown",
      meanFitnessLabel: "n/a",
    }),
  });

  assert.deepEqual(
    cells.map((cell) => cell.label),
    ["Runtime", "Health", "Shell contract", "Session rail", "Default lane", "Profiles"],
  );
  assert.equal(cells[0]?.value, "syncing");
  assert.equal(cells[1]?.value, "awaiting health");
  assert.equal(cells[2]?.value, "unknown · ephemeral sessions");
  assert.equal(cells[3]?.value, "awaiting session rail");
  assert.equal(cells[2]?.tone, "muted");
  assert.equal(cells[3]?.tone, "muted");
});

test("buildControlPlaneStripSupport exposes canonical recovery commands when the runtime disappears", () => {
  const support = buildStripSupport(
    makeSnapshot({
      chatReady: false,
      healthReady: false,
      statusKind: "error",
      statusLabel: "runtime unreachable",
      detail: "Canonical runtime query failed: fetch failed",
      healthStatusLabel: "runtime unreachable",
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      defaultProfile: null,
      sessionFeedReady: false,
      sessionFeedLabel: "chat unavailable",
      sessionFeedPathTemplate: null,
      agentCount: 0,
      anomalyCount: 0,
      tracesLastHour: 0,
    }),
  );

  assert.ok(support);
  assert.equal(support?.title, "Runtime recovery");
  assert.equal(support?.tone, "error");
  assert.deepEqual(support?.commands, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh start",
    "bash scripts/dashboard_ctl.sh restart",
  ]);
  assert.match(support?.detail ?? "", /canonical operator surfaces/i);
});

test("buildControlPlaneStripSupport links runtime recovery back to the runtime surface from peer routes", () => {
  const support = buildStripSupport(
    makeSnapshot({
      chatReady: false,
      healthReady: false,
      statusKind: "error",
      statusLabel: "runtime unreachable",
      detail: "Canonical runtime query failed: fetch failed",
      healthStatusLabel: "runtime unreachable",
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      defaultProfile: null,
      sessionFeedReady: false,
      sessionFeedLabel: "chat unavailable",
      sessionFeedPathTemplate: null,
      agentCount: 0,
      anomalyCount: 0,
      tracesLastHour: 0,
    }),
    [
      makeSurface({
        id: "command-post",
        href: "/dashboard/command-post",
        label: "Command Post",
        current: true,
      }),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "runtime unreachable",
        detail: "Canonical runtime query failed: fetch failed",
        tone: "error",
      }),
    ],
  );

  assert.ok(support);
  assert.equal(support?.href, "/dashboard/runtime");
  assert.equal(support?.actionLabel, "Open Runtime");
});

test("buildControlPlaneStripSupport warns when the session rail drops off the shared contract", () => {
  const support = buildStripSupport(
    makeSnapshot({
      statusKind: "warn",
      statusLabel: "session feed unavailable",
      detail:
        "Chat status and backend health agree on the canonical runtime path. /api/chat/status is not advertising chat_ws_path_template for the session relay.",
      sessionFeedReady: false,
      sessionFeedLabel: "not advertised",
      sessionFeedPathTemplate: null,
    }),
  );

  assert.ok(support);
  assert.equal(support?.title, "Session rail recovery");
  assert.equal(support?.tone, "warn");
  assert.deepEqual(support?.commands, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh restart",
  ]);
  assert.match(support?.detail ?? "", /chat_ws_path_template/i);
  assert.match(support?.detail ?? "", /2026-03-20\.chat\.v1/);
});

test("buildControlPlaneStripSupport links session-rail recovery back to runtime from peer routes", () => {
  const support = buildStripSupport(
    makeSnapshot({
      statusKind: "warn",
      statusLabel: "session feed unavailable",
      detail:
        "Chat status and backend health agree on the canonical runtime path. /api/chat/status is not advertising chat_ws_path_template for the session relay.",
      sessionFeedReady: false,
      sessionFeedLabel: "not advertised",
      sessionFeedPathTemplate: null,
    }),
    [
      makeSurface({
        id: "command-post",
        href: "/dashboard/command-post",
        label: "Command Post",
        current: true,
      }),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "session feed unavailable",
        detail:
          "Chat status and backend health agree on the canonical runtime path. /api/chat/status is not advertising chat_ws_path_template for the session relay.",
        tone: "warn",
      }),
    ],
  );

  assert.ok(support);
  assert.equal(support?.href, "/dashboard/runtime");
  assert.equal(support?.actionLabel, "Open Runtime");
});

test("buildControlPlaneStripSupport exposes Command Post recovery when Codex drops off the canonical contract", () => {
  const support = buildStripSupport(makeSnapshot(), [
    makeSurface({
      id: "command-post",
      href: "/dashboard/command-post",
      label: "Command Post",
      metric: "Codex not advertised",
      detail:
        "Codex lane is not currently advertised by the canonical chat contract. Command Post cannot keep the dual-orchestrator relay live without Codex.",
      tone: "error",
    }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      metric: "available",
      tone: "ok",
      current: true,
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      metric: "0 anomalies · 12 traces/h",
      tone: "ok",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      metric: "ok",
      tone: "ok",
    }),
  ]);

  assert.ok(support);
  assert.equal(support?.title, "Command Post recovery");
  assert.equal(support?.tone, "error");
  assert.deepEqual(support?.commands, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh restart",
  ]);
  assert.equal(support?.href, "/dashboard/command-post");
  assert.equal(support?.actionLabel, "Open Command Post");
  assert.match(support?.detail ?? "", /codex_operator/i);
  assert.match(support?.detail ?? "", /\/api\/chat\/status/i);
});

test("buildControlPlaneStripSupport exposes peer-lane recovery when Command Post loses its non-Codex relay", () => {
  const support = buildStripSupport(makeSnapshot(), [
    makeSurface({
      id: "command-post",
      href: "/dashboard/command-post",
      label: "Command Post",
      metric: "Peer relay degraded",
      detail:
        "No peer lane is currently available to pair with Codex on the dual-orchestrator relay.",
      tone: "warn",
    }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      metric: "provider unreachable",
      tone: "error",
      current: true,
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      metric: "0 anomalies · 12 traces/h",
      tone: "ok",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      metric: "ok",
      tone: "ok",
    }),
  ]);

  assert.ok(support);
  assert.equal(support?.title, "Peer lane recovery");
  assert.equal(support?.tone, "warn");
  assert.deepEqual(support?.commands, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh restart",
  ]);
  assert.equal(support?.href, "/dashboard/command-post");
  assert.equal(support?.actionLabel, "Open Command Post");
  assert.match(support?.detail ?? "", /peer lane/i);
  assert.match(support?.detail ?? "", /\/api\/chat\/status/i);
});

test("buildControlPlaneStripSupport offers a handoff when another canonical route is carrying the highest-pressure state", () => {
  const support = buildStripSupport(makeSnapshot(), [
    makeSurface({
      current: true,
    }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      metric: "quota blocked",
      detail: "Qwen cannot take surgical work until provider quota recovers.",
      tone: "warn",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      metric: "2 anomalies · 37 traces/h",
      detail: "Observatory is carrying the highest-pressure telemetry seam.",
      tone: "error",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      metric: "ok",
      tone: "ok",
    }),
  ]);

  assert.ok(support);
  assert.equal(support?.title, "Attention route handoff");
  assert.equal(support?.tone, "error");
  assert.equal(support?.commands.length, 0);
  assert.equal(support?.href, "/dashboard/observatory");
  assert.equal(support?.actionLabel, "Open Observatory");
  assert.match(support?.detail ?? "", /highest-pressure state/i);
  assert.match(support?.detail ?? "", /Observatory/);
});

test("buildControlPlaneStripSupport stays quiet when the current route already holds the highest-pressure state", () => {
  const support = buildStripSupport(makeSnapshot(), [
    makeSurface({
      current: true,
      tone: "error",
      metric: "relay degraded",
      detail: "Command Post is already carrying the highest-pressure route state.",
    }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      tone: "warn",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      tone: "ok",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      tone: "ok",
    }),
  ]);

  assert.equal(support, null);
});

test("buildControlPlaneStripSupport stays quiet when the current route shares the highest-pressure failure tier", () => {
  const support = buildStripSupport(makeSnapshot(), [
    makeSurface({
      tone: "error",
      metric: "relay degraded",
      detail: "Command Post is blocked on the same shared failure seam.",
    }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      tone: "warn",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      tone: "ok",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
      current: true,
      tone: "error",
      metric: "transport degraded",
      detail: "Runtime is already carrying the same top-tier failure state.",
    }),
  ]);

  assert.equal(support, null);
});

test("buildControlPlanePageSummary keeps the current route tied to deck posture and shell contract", () => {
  const summary = buildControlPlanePageSummary({
    routeId: "qwen35",
    snapshot: makeSnapshot(),
    surfaces: [
      makeSurface({
        current: false,
      }),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
        metric: "provider unreachable",
        detail: "Qwen provider is restarting and cannot take work.",
        tone: "warn",
        current: true,
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
        metric: "2 anomalies · 37 traces/h",
        tone: "error",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "degraded",
        tone: "warn",
      }),
    ],
  });

  assert.deepEqual(
    summary.map((item) => item.label),
    ["Current route", "Attention route", "Shortcut", "Shell contract"],
  );
  assert.equal(summary[0]?.value, "provider unreachable");
  assert.equal(summary[0]?.tone, "warn");
  assert.equal(summary[1]?.value, "Observatory · 2 anomalies · 37 traces/h");
  assert.equal(summary[1]?.tone, "error");
  assert.equal(summary[1]?.href, "/dashboard/observatory");
  assert.equal(summary[1]?.actionLabel, "Open Observatory");
  assert.equal(summary[2]?.value, "g q");
  assert.equal(summary[2]?.tone, "muted");
  assert.equal(summary[3]?.value, "2026-03-20.chat.v1 · persistent sessions");
  assert.equal(summary[3]?.tone, "ok");
  assert.match(summary[3]?.detail ?? "", /\/ws\/chat\/session\/\{session_id\}/);
});

test("buildControlPlanePageSummary keeps shell status visible when the current route is carrying the failure", () => {
  const summary = buildControlPlanePageSummary({
    routeId: "command-post",
    snapshot: makeSnapshot({
      statusKind: "error",
      statusLabel: "lanes unavailable",
      detail: "Chat status is live, but no advertised lanes are currently available.",
      availableProfileCount: 0,
      unavailableProfileCount: 4,
      sessionFeedReady: false,
      sessionFeedLabel: "not advertised",
      sessionFeedPathTemplate: null,
    }),
    surfaces: [
      makeSurface({
        metric: "0/4 lanes ready",
        detail: "All advertised lanes are unavailable.",
        tone: "error",
        current: true,
      }),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
        metric: "not advertised",
        tone: "muted",
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
        metric: "health unavailable",
        tone: "warn",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "lanes unavailable",
        tone: "error",
      }),
    ],
  });

  assert.equal(summary[0]?.value, "0/4 lanes ready");
  assert.equal(summary[0]?.tone, "error");
  assert.equal(summary[1]?.label, "Attention route");
  assert.equal(summary[1]?.value, "Command Post · 0/4 lanes ready");
  assert.equal(summary[1]?.href, undefined);
  assert.equal(summary[1]?.actionLabel, undefined);
  assert.match(summary[1]?.detail ?? "", /highest-pressure failure state/i);
  assert.equal(summary[3]?.value, "2026-03-20.chat.v1 · persistent sessions");
  assert.equal(summary[3]?.tone, "warn");
  assert.match(summary[3]?.detail ?? "", /not advertised/i);
});

test("buildControlPlanePageSummary defers cross-route handoffs while strip recovery is active", () => {
  const summary = buildControlPlanePageSummary({
    routeId: "qwen35",
    snapshot: makeSnapshot({
      statusKind: "warn",
      statusLabel: "session feed unavailable",
      detail:
        "Chat status and backend health agree on the canonical runtime path. /api/chat/status is not advertising chat_ws_path_template for the session relay.",
      sessionFeedReady: false,
      sessionFeedLabel: "not advertised",
      sessionFeedPathTemplate: null,
    }),
    surfaces: [
      makeSurface({
        current: false,
      }),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
        metric: "session rail unavailable",
        detail: "Qwen cannot mirror shared session telemetry until the rail returns.",
        tone: "warn",
        current: true,
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
        metric: "2 anomalies · 37 traces/h",
        detail: "Observatory is carrying the highest-pressure telemetry seam.",
        tone: "error",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "session feed unavailable",
        tone: "warn",
      }),
    ],
  });

  assert.equal(summary[1]?.label, "Attention route");
  assert.equal(summary[1]?.value, "Observatory · 2 anomalies · 37 traces/h");
  assert.equal(summary[1]?.href, undefined);
  assert.equal(summary[1]?.actionLabel, undefined);
  assert.equal(summary[2]?.label, "Recovery");
  assert.equal(summary[2]?.value, "Session rail recovery");
  assert.equal(summary[2]?.tone, "warn");
  assert.deepEqual(summary[2]?.commands, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh restart",
  ]);
  assert.equal(summary[2]?.href, "/dashboard/runtime");
  assert.equal(summary[2]?.actionLabel, "Open Runtime");
});

test("buildControlPlanePageSummary defers cross-route handoffs while Command Post recovery is active", () => {
  const summary = buildControlPlanePageSummary({
    routeId: "runtime",
    snapshot: makeSnapshot(),
    surfaces: [
      makeSurface({
        id: "command-post",
        href: "/dashboard/command-post",
        label: "Command Post",
        metric: "Codex unavailable",
        detail:
          "Codex Operator is quota blocked: Quota exhausted on the canonical operator lane. Command Post cannot keep the dual-orchestrator relay live without Codex.",
        tone: "error",
      }),
      makeSurface({
        id: "qwen35",
        href: "/dashboard/qwen35",
        label: "Qwen Surgeon",
        accent: "rokusho",
        metric: "available",
        tone: "ok",
      }),
      makeSurface({
        id: "observatory",
        href: "/dashboard/observatory",
        label: "Observatory",
        accent: "botan",
        metric: "0 anomalies · 12 traces/h",
        tone: "ok",
      }),
      makeSurface({
        id: "runtime",
        href: "/dashboard/runtime",
        label: "Runtime",
        accent: "kinpaku",
        metric: "ok",
        tone: "ok",
        current: true,
      }),
    ],
  });

  assert.equal(summary[1]?.label, "Attention route");
  assert.equal(summary[1]?.value, "Command Post · Codex unavailable");
  assert.equal(summary[1]?.href, undefined);
  assert.equal(summary[1]?.actionLabel, undefined);
  assert.equal(summary[2]?.label, "Recovery");
  assert.equal(summary[2]?.value, "Command Post recovery");
  assert.equal(summary[2]?.tone, "error");
  assert.deepEqual(summary[2]?.commands, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh restart",
  ]);
  assert.equal(summary[2]?.href, "/dashboard/command-post");
  assert.equal(summary[2]?.actionLabel, "Open Command Post");
});

test("splitControlPlaneSurfaces keeps the current surface while exposing peer routes in deck order", () => {
  const groups = splitControlPlaneSurfaces([
    makeSurface(),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
      current: true,
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
    }),
  ]);

  assert.equal(groups.currentSurface?.id, "qwen35");
  assert.deepEqual(
    groups.peerSurfaces.map((surface) => surface.id),
    ["command-post", "observatory", "runtime"],
  );
});

test("splitControlPlaneSurfaces returns the full deck as peers when no current surface is marked", () => {
  const surfaces = [
    makeSurface(),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
    }),
  ];

  const groups = splitControlPlaneSurfaces(surfaces);

  assert.equal(groups.currentSurface, null);
  assert.deepEqual(groups.peerSurfaces, surfaces);
});

test("buildControlPlaneSurfaceSections spotlights the current route and keeps peers in deck order", () => {
  const sections = buildControlPlaneSurfaceSections([
    makeSurface({
      current: true,
    }),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
    }),
    makeSurface({
      id: "observatory",
      href: "/dashboard/observatory",
      label: "Observatory",
      accent: "botan",
      tone: "warn",
    }),
    makeSurface({
      id: "runtime",
      href: "/dashboard/runtime",
      label: "Runtime",
      accent: "kinpaku",
    }),
  ]);

  assert.deepEqual(sections.map((section) => section.id), ["current", "peers"]);
  assert.equal(sections[0]?.title, "Current surface");
  assert.deepEqual(
    sections[0]?.surfaces.map((surface) => surface.id),
    ["command-post"],
  );
  assert.equal(sections[1]?.title, "Peer routes");
  assert.deepEqual(
    sections[1]?.surfaces.map((surface) => surface.id),
    ["qwen35", "observatory", "runtime"],
  );
});

test("buildControlPlaneSurfaceSections falls back to a single canonical deck when no route is active", () => {
  const surfaces = [
    makeSurface(),
    makeSurface({
      id: "qwen35",
      href: "/dashboard/qwen35",
      label: "Qwen Surgeon",
      accent: "rokusho",
    }),
  ];

  const sections = buildControlPlaneSurfaceSections(surfaces);

  assert.deepEqual(sections.map((section) => section.id), ["deck"]);
  assert.equal(sections[0]?.title, "Canonical route deck");
  assert.deepEqual(sections[0]?.surfaces, surfaces);
});
