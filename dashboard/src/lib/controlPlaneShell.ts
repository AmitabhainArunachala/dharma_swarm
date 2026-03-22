import { CONTROL_PLANE_ROUTE_DECK as rawControlPlaneRouteDeck } from "./controlPlaneRouteDeck.js";
import type {
  ControlPlaneRouteId,
  ControlPlaneRouteMeta,
  ControlPlaneSurface,
} from "./controlPlaneSurfaces";
import type {
  RuntimeControlPlaneSnapshot,
  RuntimeControlPlaneStatusKind,
} from "./runtimeControlPlane";

const CONTROL_PLANE_ROUTE_DECK =
  rawControlPlaneRouteDeck as readonly ControlPlaneRouteMeta[];

const CONTROL_PLANE_SHORTCUTS: Record<ControlPlaneRouteId, string> = {
  "command-post": "c",
  qwen35: "q",
  observatory: "v",
  runtime: "r",
};

const CONTROL_PLANE_RUNTIME_COMMANDS = [
  "bash scripts/dashboard_ctl.sh status",
  "bash scripts/dashboard_ctl.sh start",
  "bash scripts/dashboard_ctl.sh restart",
] as const;

export interface ControlPlaneSyncState {
  busy: boolean;
  label: "live" | "syncing" | "refreshing";
  detail: string;
}

export interface ControlPlanePosture {
  stableCount: number;
  degradedCount: number;
  blockedCount: number;
  waitingCount: number;
  currentSurface: ControlPlaneSurface | null;
  prioritySurface: ControlPlaneSurface | null;
  priorityLabel: "Attention route" | "Waiting route" | "Stable route";
  postureLabel: string;
  postureDetail: string;
}

export interface ControlPlaneSurfaceGroups {
  currentSurface: ControlPlaneSurface | null;
  peerSurfaces: ControlPlaneSurface[];
}

export interface ControlPlaneSurfaceSection {
  id: "current" | "peers" | "deck";
  title: string;
  detail: string;
  surfaces: ControlPlaneSurface[];
}

export interface ControlPlaneStripCell {
  label: string;
  value: string;
  tone: RuntimeControlPlaneStatusKind;
}

export interface ControlPlaneStripSupport {
  title: string;
  detail: string;
  tone: RuntimeControlPlaneStatusKind;
  commands: string[];
  href?: string;
  actionLabel?: string;
}

export interface ControlPlanePageSummaryItem {
  label: string;
  value: string;
  detail: string;
  tone: RuntimeControlPlaneStatusKind;
  commands?: string[];
  href?: string;
  actionLabel?: string;
}

export function controlPlaneStableRouteHrefs(): string[] {
  return CONTROL_PLANE_ROUTE_DECK.map((route) => route.href);
}

export function controlPlanePrimaryRoute(): ControlPlaneRouteMeta {
  return CONTROL_PLANE_ROUTE_DECK[0];
}

export function controlPlaneRuntimeCommands(): string[] {
  return [...CONTROL_PLANE_RUNTIME_COMMANDS];
}

export function controlPlaneOfflineMessage(): string {
  const [statusCommand, startCommand] = CONTROL_PLANE_RUNTIME_COMMANDS;
  return `Backend unreachable — dashboard data may be stale. Check the canonical shell with ${statusCommand} and recover with ${startCommand}.`;
}

function runtimeRecoveryLink(
  surfaces?: ControlPlaneSurface[],
): Pick<ControlPlaneStripSupport, "href" | "actionLabel"> {
  const runtimeSurface = surfaces?.find((surface) => surface.id === "runtime");
  const currentSurface = surfaces?.find((surface) => surface.current) ?? null;

  if (!runtimeSurface || currentSurface?.id === "runtime") {
    return {};
  }

  return {
    href: runtimeSurface.href,
    actionLabel: `Open ${runtimeSurface.label}`,
  };
}

export function buildControlPlaneStripSupport(
  snapshot: RuntimeControlPlaneSnapshot,
  surfaces?: ControlPlaneSurface[],
): ControlPlaneStripSupport | null {
  const [statusCommand, startCommand, restartCommand] = CONTROL_PLANE_RUNTIME_COMMANDS;
  const runtimeLink = runtimeRecoveryLink(surfaces);

  if (snapshot.statusLabel === "runtime unreachable") {
    return {
      title: "Runtime recovery",
      detail:
        "Canonical operator surfaces lost contact with the backend. Check the shell status first, then start or restart the launchd-backed runtime if the stack stays dark.",
      tone: "error",
      commands: [statusCommand, startCommand, restartCommand],
      ...runtimeLink,
    };
  }

  if (snapshot.chatReady && snapshot.totalProfileCount > 0 && snapshot.availableProfileCount === 0) {
    return {
      title: "Lane recovery",
      detail: `All advertised lanes are blocked on contract ${snapshot.contractVersion}. Check shell status, then restart the runtime if provider recovery does not repopulate /api/chat/status.`,
      tone: "error",
      commands: [statusCommand, restartCommand],
      ...runtimeLink,
    };
  }

  if (snapshot.chatReady && !snapshot.healthReady) {
    return {
      title: "Health recovery",
      detail:
        "Chat lanes are live, but /api/health is missing from the canonical runtime path. Check shell status, then restart if health stays dark.",
      tone: "warn",
      commands: [statusCommand, restartCommand],
      ...runtimeLink,
    };
  }

  if (snapshot.chatReady && !snapshot.sessionFeedReady) {
    return {
      title: "Session rail recovery",
      detail: `Contract ${snapshot.contractVersion} is live, but /api/chat/status is not advertising chat_ws_path_template for the shared session relay. Check shell status, then restart if the rail does not return.`,
      tone: "warn",
      commands: [statusCommand, restartCommand],
      ...runtimeLink,
    };
  }

  if (surfaces?.length) {
    const posture = buildControlPlanePosture(surfaces);
    const prioritySurface = posture.prioritySurface;
    const commandPostSurface =
      surfaces.find((surface) => surface.id === "command-post") ?? null;
    const commandPostRecoveryActive = Boolean(
      commandPostSurface &&
        (commandPostSurface.metric === "Codex not advertised" ||
          commandPostSurface.metric === "Codex unavailable"),
    );
    const commandPostPeerRecoveryActive = Boolean(
      commandPostSurface && commandPostSurface.metric === "Peer relay degraded",
    );

    if (commandPostSurface && commandPostRecoveryActive) {
      const commandPostIsCurrent = posture.currentSurface?.id === "command-post";
      const detail =
        commandPostSurface.metric === "Codex not advertised"
          ? "Command Post lost the canonical codex_operator lane from /api/chat/status. Check shell status, then restart the runtime if the contract does not re-advertise Codex."
          : "Command Post can still see codex_operator in /api/chat/status, but the lane cannot accept work. Check shell status, then restart the runtime if Codex stays blocked.";

      return {
        title: "Command Post recovery",
        detail,
        tone: "error",
        commands: [statusCommand, restartCommand],
        href: commandPostIsCurrent ? undefined : commandPostSurface.href,
        actionLabel: commandPostIsCurrent ? undefined : `Open ${commandPostSurface.label}`,
      };
    }

    if (commandPostSurface && commandPostPeerRecoveryActive) {
      const commandPostIsCurrent = posture.currentSurface?.id === "command-post";

      return {
        title: "Peer lane recovery",
        detail:
          "Command Post still has codex_operator, but no non-Codex peer lane is currently available from /api/chat/status. Check shell status, then restart the runtime if the peer lane does not return.",
        tone: "warn",
        commands: [statusCommand, restartCommand],
        href: commandPostIsCurrent ? undefined : commandPostSurface.href,
        actionLabel: commandPostIsCurrent ? undefined : `Open ${commandPostSurface.label}`,
      };
    }

    if (
      prioritySurface &&
      posture.currentSurface &&
      prioritySurface.id !== posture.currentSurface.id &&
      (prioritySurface.tone === "warn" || prioritySurface.tone === "error")
    ) {
      return {
        title: "Attention route handoff",
        detail: `${prioritySurface.label} is carrying the highest-pressure state on the canonical operator deck. Open it from ${posture.currentSurface.label} to work ${prioritySurface.metric} without leaving the shared shell.`,
        tone: prioritySurface.tone,
        commands: [],
        href: prioritySurface.href,
        actionLabel: `Open ${prioritySurface.label}`,
      };
    }
  }

  return null;
}

export function controlPlaneRouteShortcut(routeId: ControlPlaneRouteId): string {
  return `g ${CONTROL_PLANE_SHORTCUTS[routeId]}`;
}

export function controlPlaneSurfaceToneLabel(
  tone: RuntimeControlPlaneStatusKind,
): "stable" | "degraded" | "blocked" | "awaiting signal" {
  if (tone === "ok") return "stable";
  if (tone === "warn") return "degraded";
  if (tone === "error") return "blocked";
  return "awaiting signal";
}

export function buildControlPlaneSyncState(args?: {
  isLoading?: boolean;
  isFetching?: boolean;
}): ControlPlaneSyncState {
  if (args?.isLoading) {
    return {
      busy: true,
      label: "syncing",
      detail: "Waiting for the canonical runtime sources to answer.",
    };
  }

  if (args?.isFetching) {
    return {
      busy: true,
      label: "refreshing",
      detail: "Refreshing the canonical runtime state without leaving the current surface.",
    };
  }

  return {
    busy: false,
    label: "live",
    detail: "Canonical runtime state is current on this surface.",
  };
}

function firstSurfaceByTone(
  surfaces: ControlPlaneSurface[],
  tone: ControlPlaneSurface["tone"],
): ControlPlaneSurface | null {
  return surfaces.find((surface) => surface.tone === tone) ?? null;
}

function preferredSurfaceByTone(
  surfaces: ControlPlaneSurface[],
  currentSurface: ControlPlaneSurface | null,
  tone: ControlPlaneSurface["tone"],
): ControlPlaneSurface | null {
  if (currentSurface?.tone === tone) {
    return currentSurface;
  }

  return firstSurfaceByTone(surfaces, tone);
}

function stableAnchorSurface(
  surfaces: ControlPlaneSurface[],
  currentSurface: ControlPlaneSurface | null,
): ControlPlaneSurface | null {
  return (
    surfaces.find((surface) => surface.id === "command-post") ??
    currentSurface ??
    surfaces[0] ??
    null
  );
}

function compactCountLabel(count: number, noun: string): string {
  return `${count} ${noun}`;
}

function laneLabel(snapshot: RuntimeControlPlaneSnapshot): string {
  if (!snapshot.defaultProfile) return "No lane advertised";
  return `${snapshot.defaultProfile.label} · ${snapshot.defaultProfile.provider}`;
}

function profileLabel(snapshot: RuntimeControlPlaneSnapshot): string {
  if (snapshot.totalProfileCount === 0) return "0 lanes";
  return `${snapshot.availableProfileCount}/${snapshot.totalProfileCount} lanes ready`;
}

function sessionLabel(snapshot: RuntimeControlPlaneSnapshot): string {
  return snapshot.persistentSessions ? "persistent sessions" : "ephemeral sessions";
}

function shellContractLabel(snapshot: RuntimeControlPlaneSnapshot): string {
  return `${snapshot.contractVersion} · ${sessionLabel(snapshot)}`;
}

function sessionRailTone(
  snapshot: RuntimeControlPlaneSnapshot,
): RuntimeControlPlaneStatusKind {
  if (snapshot.statusKind === "muted" && !snapshot.chatReady) return "muted";
  if (!snapshot.chatReady) return "error";
  return snapshot.sessionFeedReady ? "ok" : "warn";
}

function highestTone(
  ...tones: RuntimeControlPlaneStatusKind[]
): RuntimeControlPlaneStatusKind {
  const orderedTones: RuntimeControlPlaneStatusKind[] = ["error", "warn", "ok", "muted"];
  return (
    orderedTones.find((tone) => tones.includes(tone)) ??
    "muted"
  );
}

function surfaceMetric(surface: ControlPlaneSurface | null): string {
  if (!surface) return "Unavailable";
  return `${surface.label} · ${surface.metric}`;
}

function healthTone(snapshot: RuntimeControlPlaneSnapshot): RuntimeControlPlaneStatusKind {
  if (!snapshot.healthReady) {
    return snapshot.chatReady ? "warn" : "muted";
  }
  if (snapshot.anomalyCount > 0) return "warn";
  return "ok";
}

function contractTone(snapshot: RuntimeControlPlaneSnapshot): RuntimeControlPlaneStatusKind {
  if (snapshot.contractVersion !== "unknown") {
    return snapshot.chatReady ? "ok" : "warn";
  }
  return snapshot.chatReady ? "warn" : "muted";
}

function profileTone(snapshot: RuntimeControlPlaneSnapshot): RuntimeControlPlaneStatusKind {
  if (!snapshot.defaultProfile) return "muted";
  return snapshot.defaultProfile.available === false ? "error" : "ok";
}

function profileDeckTone(snapshot: RuntimeControlPlaneSnapshot): RuntimeControlPlaneStatusKind {
  if (snapshot.totalProfileCount === 0) return "muted";
  if (snapshot.availableProfileCount === 0) return "error";
  if (snapshot.availableProfileCount < snapshot.totalProfileCount) return "warn";
  return "ok";
}

export function buildControlPlanePosture(
  surfaces: ControlPlaneSurface[],
): ControlPlanePosture {
  const stableCount = surfaces.filter((surface) => surface.tone === "ok").length;
  const degradedCount = surfaces.filter((surface) => surface.tone === "warn").length;
  const blockedCount = surfaces.filter((surface) => surface.tone === "error").length;
  const waitingCount = surfaces.filter((surface) => surface.tone === "muted").length;
  const currentSurface = surfaces.find((surface) => surface.current) ?? null;

  if (blockedCount > 0) {
    const prioritySurface = preferredSurfaceByTone(surfaces, currentSurface, "error");
    const degradedLabel =
      degradedCount > 0 ? ` · ${compactCountLabel(degradedCount, "degraded")}` : "";

    return {
      stableCount,
      degradedCount,
      blockedCount,
      waitingCount,
      currentSurface,
      prioritySurface,
      priorityLabel: "Attention route",
      postureLabel: `${compactCountLabel(blockedCount, "blocked")}${degradedLabel}`,
      postureDetail: `${
        prioritySurface?.label ?? "A canonical route"
      } is carrying the highest-pressure failure state across the control plane.`,
    };
  }

  if (degradedCount > 0) {
    const prioritySurface = preferredSurfaceByTone(surfaces, currentSurface, "warn");

    return {
      stableCount,
      degradedCount,
      blockedCount,
      waitingCount,
      currentSurface,
      prioritySurface,
      priorityLabel: "Attention route",
      postureLabel: compactCountLabel(degradedCount, "degraded"),
      postureDetail: `${
        prioritySurface?.label ?? "A canonical route"
      } is degraded while the rest of the control plane stays live.`,
    };
  }

  if (waitingCount > 0) {
    const prioritySurface = preferredSurfaceByTone(surfaces, currentSurface, "muted");

    return {
      stableCount,
      degradedCount,
      blockedCount,
      waitingCount,
      currentSurface,
      prioritySurface,
      priorityLabel: "Waiting route",
      postureLabel: compactCountLabel(waitingCount, "awaiting signal"),
      postureDetail: `${
        prioritySurface?.label ?? "A canonical route"
      } is still awaiting canonical route telemetry.`,
    };
  }

  return {
    stableCount,
    degradedCount,
    blockedCount,
    waitingCount,
    currentSurface,
    prioritySurface: stableAnchorSurface(surfaces, currentSurface),
    priorityLabel: "Stable route",
    postureLabel: `${stableCount}/${surfaces.length} stable`,
    postureDetail: "All canonical routes are stable on the shared operator deck.",
  };
}

export function buildControlPlaneStripCells(args: {
  snapshot: RuntimeControlPlaneSnapshot;
  surfaces?: ControlPlaneSurface[];
}): ControlPlaneStripCell[] {
  const { snapshot, surfaces } = args;
  const posture = surfaces?.length ? buildControlPlanePosture(surfaces) : null;
  const cells: ControlPlaneStripCell[] = [
    {
      label: "Runtime",
      value: snapshot.statusLabel,
      tone: snapshot.statusKind,
    },
    {
      label: "Health",
      value: snapshot.healthStatusLabel,
      tone: healthTone(snapshot),
    },
    {
      label: "Shell contract",
      value: shellContractLabel(snapshot),
      tone: contractTone(snapshot),
    },
  ];

  if (posture) {
    cells.push(
      {
        label: "Session rail",
        value: snapshot.sessionFeedLabel,
        tone: sessionRailTone(snapshot),
      },
      {
        label: "Operator path",
        value: posture.postureLabel,
        tone: posture.prioritySurface?.tone ?? "muted",
      },
      {
        label: posture.priorityLabel,
        value: surfaceMetric(posture.prioritySurface),
        tone: posture.prioritySurface?.tone ?? "muted",
      },
    );
    return cells;
  }

  cells.push(
    {
      label: "Session rail",
      value: snapshot.sessionFeedLabel,
      tone: sessionRailTone(snapshot),
    },
    {
      label: "Default lane",
      value: laneLabel(snapshot),
      tone: profileTone(snapshot),
    },
    {
      label: "Profiles",
      value: profileLabel(snapshot),
      tone: profileDeckTone(snapshot),
    },
  );

  return cells;
}

export function buildControlPlanePageSummary(args: {
  routeId: ControlPlaneRouteId;
  snapshot: RuntimeControlPlaneSnapshot;
  surfaces: ControlPlaneSurface[];
}): ControlPlanePageSummaryItem[] {
  const { routeId, snapshot, surfaces } = args;
  const route = CONTROL_PLANE_ROUTE_DECK.find((entry) => entry.id === routeId);
  if (!route) {
    throw new Error(`Unknown control-plane route: ${routeId}`);
  }

  const currentRoute = surfaces.find((surface) => surface.id === routeId) ?? null;
  const posture = surfaces.length ? buildControlPlanePosture(surfaces) : null;
  const prioritySurface = posture?.prioritySurface ?? null;
  const stripSupport = buildControlPlaneStripSupport(snapshot, surfaces);
  const recoverySupportActive = Boolean(stripSupport && stripSupport.commands.length > 0);
  const shouldOfferPriorityHandoff = Boolean(
    !recoverySupportActive && prioritySurface && prioritySurface.id !== routeId,
  );
  const shellTone = highestTone(contractTone(snapshot), sessionRailTone(snapshot));
  const recoverySummaryItem = recoverySupportActive
    ? {
        label: "Recovery",
        value: stripSupport?.title ?? "Recovery",
        detail: stripSupport?.detail ?? "Canonical shell recovery is available.",
        tone: stripSupport?.tone ?? "warn",
        commands: stripSupport?.commands ?? [],
        href: stripSupport?.href,
        actionLabel: stripSupport?.actionLabel,
      }
    : {
        label: "Shortcut",
        value: controlPlaneRouteShortcut(routeId),
        detail: `${route.label} stays addressable from anywhere on the canonical operator deck.`,
        tone: "muted" as const,
      };

  return [
    {
      label: "Current route",
      value: currentRoute?.metric ?? route.label,
      detail:
        currentRoute?.detail ??
        `${route.label} is waiting for canonical route telemetry on the operator deck.`,
      tone: currentRoute?.tone ?? "muted",
    },
    {
      label: posture?.priorityLabel ?? "Route deck",
      value: prioritySurface
        ? surfaceMetric(prioritySurface)
        : posture?.postureLabel ?? "Awaiting route posture",
      detail:
        posture?.postureDetail ??
        `${route.label} is waiting for the shared control-plane posture to report.`,
      tone: prioritySurface?.tone ?? "muted",
      href: shouldOfferPriorityHandoff ? prioritySurface?.href : undefined,
      actionLabel: shouldOfferPriorityHandoff
        ? `Open ${prioritySurface?.label}`
        : undefined,
    },
    recoverySummaryItem,
    {
      label: "Shell contract",
      value: shellContractLabel(snapshot),
      detail: `Session rail ${snapshot.sessionFeedLabel}.`,
      tone: shellTone,
    },
  ];
}

export function splitControlPlaneSurfaces(
  surfaces: ControlPlaneSurface[],
): ControlPlaneSurfaceGroups {
  const currentSurface = surfaces.find((surface) => surface.current) ?? null;
  return {
    currentSurface,
    peerSurfaces: currentSurface ? surfaces.filter((surface) => !surface.current) : surfaces,
  };
}

export function buildControlPlaneSurfaceSections(
  surfaces: ControlPlaneSurface[],
): ControlPlaneSurfaceSection[] {
  const groups = splitControlPlaneSurfaces(surfaces);

  if (!groups.currentSurface) {
    return [
      {
        id: "deck",
        title: "Canonical route deck",
        detail: "All canonical control-plane routes stay visible from this surface.",
        surfaces,
      },
    ];
  }

  return [
    {
      id: "current",
      title: "Current surface",
      detail: `${groups.currentSurface.label} is the active route on the shared operator deck.`,
      surfaces: [groups.currentSurface],
    },
    {
      id: "peers",
      title: groups.peerSurfaces.length === 1 ? "Peer route" : "Peer routes",
      detail:
        groups.peerSurfaces.length > 0
          ? `${groups.peerSurfaces.length} sibling routes stay one hop away without leaving the canonical shell.`
          : "No peer routes are currently advertised on the canonical deck.",
      surfaces: groups.peerSurfaces,
    },
  ];
}

export function buildDashboardKeyboardRouteMap(): Record<string, string> {
  const routes: Record<string, string> = {
    a: "/dashboard/agents",
    t: "/dashboard/tasks",
    e: "/dashboard/evolution",
    g: "/dashboard/gates",
    s: "/dashboard/stigmergy",
    o: "/dashboard",
    m: "/dashboard/modules",
    u: "/dashboard/audit",
    l: "/dashboard/log",
  };

  for (const route of CONTROL_PLANE_ROUTE_DECK) {
    routes[CONTROL_PLANE_SHORTCUTS[route.id]] = route.href;
  }

  return routes;
}
