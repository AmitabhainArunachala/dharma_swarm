import type {
  RuntimeControlPlaneSnapshot,
  RuntimeControlPlaneStatusKind,
} from "./runtimeControlPlane";
import { CONTROL_PLANE_ROUTE_DECK as rawControlPlaneRouteDeck } from "./controlPlaneRouteDeck.js";
import { isDashboardPathActive } from "./dashboardPath.js";
import type { ChatProfileOut, ChatStatusOut } from "./types";

export type ControlPlaneRouteId = "command-post" | "qwen35" | "observatory" | "runtime";
export type ControlPlaneSurfaceAccent = "aozora" | "rokusho" | "botan" | "kinpaku";
export type ControlPlaneSurfaceIcon = "BrainCircuit" | "Bot" | "HeartPulse" | "Settings2";

export interface ControlPlaneRouteMeta {
  id: ControlPlaneRouteId;
  href: string;
  label: string;
  summary: string;
  accent: ControlPlaneSurfaceAccent;
  navIcon: ControlPlaneSurfaceIcon;
}

export const CONTROL_PLANE_ROUTE_DECK =
  rawControlPlaneRouteDeck as readonly ControlPlaneRouteMeta[];

export interface ControlPlaneSurface {
  id: ControlPlaneRouteId;
  href: string;
  label: string;
  summary: string;
  accent: ControlPlaneSurfaceAccent;
  metric: string;
  detail: string;
  tone: RuntimeControlPlaneStatusKind;
  current: boolean;
}

const CODEX_OPERATOR_PROFILE_ID = "codex_operator";
const COMMAND_POST_PREFERRED_PEER_ID = "claude_opus";

function cleanAvailabilityLabel(profile: ChatProfileOut | null): string {
  if (!profile) return "not advertised";
  if (profile.available === true) return "available";
  return profile.availability_kind?.replace(/_/g, " ") ?? "unavailable";
}

function findProfile(
  chatStatus: ChatStatusOut | null,
  profileId: string,
): ChatProfileOut | null {
  return chatStatus?.profiles?.find((profile) => profile.id === profileId) ?? null;
}

function qwenProfile(chatStatus: ChatStatusOut | null): ChatProfileOut | null {
  return chatStatus?.profiles?.find((profile) => profile.id === "qwen35_surgeon") ?? null;
}

function commandPostCodexProfile(chatStatus: ChatStatusOut | null): ChatProfileOut | null {
  return findProfile(chatStatus, CODEX_OPERATOR_PROFILE_ID);
}

function commandPostUsableProfiles(chatStatus: ChatStatusOut | null): ChatProfileOut[] {
  const profiles = chatStatus?.profiles ?? [];
  const available = profiles.filter((profile) => profile.available !== false);
  return available.length > 0 ? available : profiles;
}

function commandPostPeerProfile(chatStatus: ChatStatusOut | null): ChatProfileOut | null {
  const peerProfiles = commandPostUsableProfiles(chatStatus).filter(
    (profile) => profile.id !== CODEX_OPERATOR_PROFILE_ID,
  );
  return (
    peerProfiles.find((profile) => profile.id === COMMAND_POST_PREFERRED_PEER_ID) ??
    peerProfiles[0] ??
    null
  );
}

function unavailableProfileDetail(profile: ChatProfileOut): string {
  const availability = cleanAvailabilityLabel(profile);
  const statusNote = profile.status_note?.trim();
  if (statusNote) {
    return `${profile.label} is ${availability}: ${statusNote}`;
  }
  return `${profile.label} is ${availability}.`;
}

function qwenTone(profile: ChatProfileOut | null): RuntimeControlPlaneStatusKind {
  if (!profile) return "muted";
  if (profile.available === true) return "ok";
  return "error";
}

function awaitingRouteSignal(
  snapshot: RuntimeControlPlaneSnapshot,
  chatStatus: ChatStatusOut | null,
): boolean {
  return (
    snapshot.statusKind === "muted" &&
    !snapshot.chatReady &&
    snapshot.totalProfileCount === 0 &&
    snapshot.contractVersion === "unknown" &&
    chatStatus === null
  );
}

function blockedLaneDeck(snapshot: RuntimeControlPlaneSnapshot): boolean {
  return snapshot.totalProfileCount > 0 && snapshot.availableProfileCount === 0;
}

function commandPostMissingCodex(
  snapshot: RuntimeControlPlaneSnapshot,
  chatStatus: ChatStatusOut | null,
): boolean {
  return snapshot.totalProfileCount > 0 && !commandPostCodexProfile(chatStatus);
}

function commandPostTone(
  snapshot: RuntimeControlPlaneSnapshot,
  chatStatus: ChatStatusOut | null,
): RuntimeControlPlaneStatusKind {
  if (awaitingRouteSignal(snapshot, chatStatus)) return "muted";
  if (!snapshot.chatReady) return "error";
  if (blockedLaneDeck(snapshot)) return "error";
  if (commandPostMissingCodex(snapshot, chatStatus)) return "error";
  if (
    snapshot.totalProfileCount > 0 &&
    commandPostCodexProfile(chatStatus)?.available === false
  ) {
    return "error";
  }
  if (
    snapshot.totalProfileCount > 0 &&
    !commandPostPeerProfile(chatStatus)
  ) {
    return "warn";
  }
  if (!snapshot.sessionFeedReady) return "warn";
  if (snapshot.availableProfileCount < snapshot.totalProfileCount) return "warn";
  return "ok";
}

function observatoryShouldMirrorRuntimeError(
  snapshot: RuntimeControlPlaneSnapshot,
): boolean {
  if (snapshot.statusKind !== "error") return false;
  if (snapshot.chatReady) return true;

  return (
    snapshot.totalProfileCount > 0 ||
    snapshot.defaultProfile !== null ||
    snapshot.contractVersion !== "unknown" ||
    snapshot.agentCount > 0 ||
    snapshot.anomalyCount > 0 ||
    snapshot.tracesLastHour > 0
  );
}

function observatoryTone(
  snapshot: RuntimeControlPlaneSnapshot,
): RuntimeControlPlaneStatusKind {
  if (observatoryShouldMirrorRuntimeError(snapshot)) return "error";
  if (!snapshot.healthReady && snapshot.chatReady) return "warn";
  if (snapshot.anomalyCount > 0) return "warn";
  if (snapshot.agentCount > 0 || snapshot.tracesLastHour > 0) return "ok";
  return "muted";
}

function runtimeTransportFailure(
  snapshot: RuntimeControlPlaneSnapshot,
): boolean {
  return snapshot.statusKind === "error" && snapshot.statusLabel === "runtime unreachable";
}

function unreachableSurfaceState(
  snapshot: RuntimeControlPlaneSnapshot,
): Pick<ControlPlaneSurface, "metric" | "detail" | "tone"> {
  return {
    metric: snapshot.statusLabel,
    detail: snapshot.detail,
    tone: "error",
  };
}

function runtimeContractDetail(snapshot: RuntimeControlPlaneSnapshot): string {
  return `Contract ${snapshot.contractVersion} · ${
    snapshot.persistentSessions ? "persistent" : "ephemeral"
  } sessions`;
}

function runtimeSurfaceDetail(snapshot: RuntimeControlPlaneSnapshot): string {
  const contractDetail = runtimeContractDetail(snapshot);

  if (!snapshot.chatReady) {
    return snapshot.detail;
  }

  if (!snapshot.healthReady) {
    return `${contractDetail} · /api/health unavailable`;
  }

  if (!snapshot.sessionFeedReady) {
    return `${contractDetail} · session rail not advertised`;
  }

  if (snapshot.statusKind !== "ok") {
    return `${contractDetail} · ${snapshot.detail}`;
  }

  return contractDetail;
}

function surfaceState(
  routeId: ControlPlaneRouteId,
  snapshot: RuntimeControlPlaneSnapshot,
  chatStatus: ChatStatusOut | null,
): Pick<ControlPlaneSurface, "metric" | "detail" | "tone"> {
  if (runtimeTransportFailure(snapshot)) {
    return unreachableSurfaceState(snapshot);
  }

  if (routeId === "command-post") {
    const codexProfile = commandPostCodexProfile(chatStatus);
    const peerProfile = commandPostPeerProfile(chatStatus);

    if (awaitingRouteSignal(snapshot, chatStatus)) {
      return {
        metric: "Awaiting lanes",
        detail: "Waiting for /api/chat/status to advertise the command lanes.",
        tone: "muted",
      };
    }

    if (blockedLaneDeck(snapshot)) {
      const detail = snapshot.defaultProfile
        ? `All advertised lanes are unavailable. Default lane ${snapshot.defaultProfile.label} is still in the contract but cannot accept work.`
        : "All advertised lanes are unavailable.";

      return {
        metric: `${snapshot.availableProfileCount}/${snapshot.totalProfileCount} lanes ready`,
        detail,
        tone: commandPostTone(snapshot, chatStatus),
      };
    }

    if (commandPostMissingCodex(snapshot, chatStatus)) {
      return {
        metric: "Codex not advertised",
        detail:
          "Codex lane is not currently advertised by the canonical chat contract. Command Post cannot keep the dual-orchestrator relay live without Codex.",
        tone: commandPostTone(snapshot, chatStatus),
      };
    }

    if (snapshot.totalProfileCount > 0 && codexProfile?.available === false) {
      return {
        metric: "Codex unavailable",
        detail: `${unavailableProfileDetail(
          codexProfile,
        )} Command Post cannot keep the dual-orchestrator relay live without Codex.`,
        tone: commandPostTone(snapshot, chatStatus),
      };
    }

    if (snapshot.totalProfileCount > 0 && !peerProfile) {
      return {
        metric: "Peer relay degraded",
        detail:
          "No peer lane is currently available to pair with Codex on the dual-orchestrator relay.",
        tone: commandPostTone(snapshot, chatStatus),
      };
    }

    if (!snapshot.sessionFeedReady) {
      return {
        metric: "Session rail unavailable",
        detail:
          "/api/chat/status is not advertising chat_ws_path_template, so the dual-orchestrator relay cannot mirror live session telemetry.",
        tone: commandPostTone(snapshot, chatStatus),
      };
    }

    return {
      metric:
        snapshot.totalProfileCount > 0
          ? `${snapshot.availableProfileCount}/${snapshot.totalProfileCount} lanes ready`
          : "Awaiting lanes",
      detail: snapshot.defaultProfile
        ? `Default lane ${snapshot.defaultProfile.label} anchors the command relay and shared operator path.`
        : "Waiting for /api/chat/status to advertise the command lanes.",
      tone: commandPostTone(snapshot, chatStatus),
    };
  }

  if (routeId === "qwen35") {
    const qwen = qwenProfile(chatStatus);
    return {
      metric: cleanAvailabilityLabel(qwen),
      detail: qwen
        ? qwen.available === false
          ? unavailableProfileDetail(qwen)
          : `${qwen.model} · ${qwen.status_note ?? qwen.summary}`
        : "Qwen lane is not currently advertised by the canonical chat profile contract.",
      tone: qwenTone(qwen),
    };
  }

  if (routeId === "observatory") {
    if (observatoryShouldMirrorRuntimeError(snapshot)) {
      return {
        metric: `${snapshot.anomalyCount} anomalies · ${snapshot.tracesLastHour} traces/h`,
        detail: snapshot.detail,
        tone: observatoryTone(snapshot),
      };
    }

    if (!snapshot.healthReady && snapshot.chatReady) {
      return {
        metric: snapshot.healthStatusLabel,
        detail: snapshot.detail,
        tone: observatoryTone(snapshot),
      };
    }

    return {
      metric: `${snapshot.anomalyCount} anomalies · ${snapshot.tracesLastHour} traces/h`,
      detail:
        snapshot.agentCount > 0
          ? `${snapshot.agentCount} agents visible in fleet health and activity telemetry.`
          : "Fleet health will appear here once agents and traces report into the canonical backend.",
      tone: observatoryTone(snapshot),
    };
  }

  return {
    metric: snapshot.statusLabel,
    detail: runtimeSurfaceDetail(snapshot),
    tone: snapshot.statusKind,
  };
}

export function buildControlPlaneSurfaces(args: {
  snapshot: RuntimeControlPlaneSnapshot;
  chatStatus: ChatStatusOut | null;
  currentPath?: string;
}): ControlPlaneSurface[] {
  const { snapshot, chatStatus, currentPath } = args;

  return CONTROL_PLANE_ROUTE_DECK.map((route) => ({
    ...route,
    ...surfaceState(route.id, snapshot, chatStatus),
    current: isDashboardPathActive(route.href, currentPath),
  }));
}
