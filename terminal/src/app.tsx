import React, {useEffect, useMemo, useReducer, useRef} from "react";
import {Box, useApp, useInput} from "ink";

import {DharmaBridge, type BridgeEvent} from "./bridge.js";
import {
  loadSupervisorRepoPreview,
  loadStoredState,
  loadSupervisorControlPreview,
  loadSupervisorControlState,
  saveSupervisorRepoPreview,
  saveStoredState,
  saveSupervisorControlSummary,
} from "./persistence.js";
import {Composer} from "./components/Composer.js";
import {ControlPane} from "./components/ControlPane.js";
import {ModelPicker} from "./components/ModelPicker.js";
import {RepoPane} from "./components/RepoPane.js";
import {ShellHeader} from "./components/ShellHeader.js";
import {Sidebar} from "./components/Sidebar.js";
import {StatusFooter} from "./components/StatusFooter.js";
import {TabBar} from "./components/TabBar.js";
import {TranscriptPane} from "./components/TranscriptPane.js";
import {
  approvalPaneToLines,
  approvalPaneToPreview,
  agentRoutesPayloadFromEvent,
  agentRoutesToLines,
  agentRoutesToPreview,
  buildBridgeTabs,
  normalizeCommandName,
  commandTargetTab,
  commandGraphToLines,
  commandGraphToPreview,
  evolutionSurfaceToLines,
  evolutionSurfaceToPreview,
  eventToTabPatch,
  isSlashCommandPrompt,
  isWorkspaceSnapshotContent,
  modelPolicyToLines,
  modelPolicyToPreview,
  permissionDecisionFromEvent,
  permissionHistoryFromEvent,
  permissionOutcomeFromEvent,
  permissionResolutionFromEvent,
  resolveCommandTargetPane,
  resolveEventCommand,
  routingDecisionPayloadFromEvent,
  outlineFromTabs,
  runtimePreviewToLines,
  runtimePayloadToPreview,
  runtimeSnapshotPayloadFromEvent,
  runtimeSnapshotToLines,
  runtimeSnapshotToPreview,
  sessionCatalogFromEvent,
  sessionDetailFromEvent,
  sessionPaneToLines,
  sessionPaneToPreview,
  sessionBootstrapToLines,
  sessionBootstrapToPreview,
  workspacePreviewToLines,
  workspacePayloadToPreview,
  workspaceSnapshotPayloadFromEvent,
  workspaceSnapshotToPreview,
} from "./protocol.js";
import {initialState, reduceApp} from "./state.js";
import type {AppAction, AppState, ApprovalQueueEntry, ApprovalQueueState, CanonicalPermissionDecision, CanonicalPermissionOutcome, CanonicalPermissionResolution, SessionCatalogPayload, SessionDetailPayload, SessionPaneState, SurfaceAuthorityState, TabPreview, TabSpec, TranscriptLine} from "./types.js";

const SNAPSHOT_REFRESH_INTERVAL_MS = 15000;
const SESSION_CATALOG_LIMIT = 12;
const SESSION_TRANSCRIPT_LIMIT = 40;

type PaneAction = {
  label: string;
  summary: string;
  requestType?: string;
  payload: Record<string, unknown>;
};

type ModelChoice = {
  alias: string;
  label: string;
  provider: string;
  model: string;
};

function ensureRuntimeTabs(stateTabs: TabSpec[]): TabSpec[] {
  const existingIds = new Set(stateTabs.map((tab) => tab.id));
  const missing = buildBridgeTabs().filter((tab) => !existingIds.has(tab.id));
  return [...stateTabs, ...missing];
}

function requestLiveSnapshots(bridge: DharmaBridge, provider: string, model: string, strategy: string): void {
  bridge.send("workspace.snapshot");
  bridge.send("runtime.snapshot");
  bridge.send("model.policy", {provider, model, strategy});
  bridge.send("agent.routes");
  bridge.send("evolution.surface");
}

export function missingAuthoritativeSurfaces(authoritative: SurfaceAuthorityState): Array<keyof SurfaceAuthorityState> {
  return (Object.entries(authoritative) as Array<[keyof SurfaceAuthorityState, boolean]>)
    .filter(([, ready]) => !ready)
    .map(([surface]) => surface);
}

export function authoritativeResyncComplete(authoritative: SurfaceAuthorityState): boolean {
  return missingAuthoritativeSurfaces(authoritative).length === 0;
}

export function markAuthoritativeSurface(
  authoritative: SurfaceAuthorityState,
  surface: keyof SurfaceAuthorityState,
): SurfaceAuthorityState {
  return {
    ...authoritative,
    [surface]: true,
  };
}

export function authoritativeResyncStatus(authoritative: SurfaceAuthorityState): string {
  const remaining = missingAuthoritativeSurfaces(authoritative).length;
  if (remaining === 0) {
    return "operator state live";
  }
  return `resyncing ${remaining} surface${remaining === 1 ? "" : "s"}`;
}

function requestAuthoritativeResync(bridge: DharmaBridge, provider: string, model: string, strategy: string): void {
  bridge.send("status");
  bridge.send("command.graph");
  bridge.send("command.registry");
  bridge.send("ontology.snapshot");
  requestSessionCatalog(bridge);
  requestPermissionHistory(bridge);
  requestLiveSnapshots(bridge, provider, model, strategy);
}

export function requestMissingAuthoritativeSurfaces(
  bridge: DharmaBridge,
  provider: string,
  model: string,
  strategy: string,
  authoritative: SurfaceAuthorityState,
): void {
  for (const surface of missingAuthoritativeSurfaces(authoritative)) {
    if (surface === "repo") {
      bridge.send("workspace.snapshot");
      continue;
    }
    if (surface === "control") {
      bridge.send("runtime.snapshot");
      continue;
    }
    if (surface === "sessions") {
      requestSessionCatalog(bridge);
      continue;
    }
    if (surface === "approvals") {
      requestPermissionHistory(bridge);
      continue;
    }
    if (surface === "models") {
      bridge.send("model.policy", {provider, model, strategy});
      continue;
    }
    if (surface === "agents") {
      bridge.send("agent.routes");
    }
  }
}

function requestSessionCatalog(bridge: DharmaBridge): void {
  bridge.send("session.catalog", {limit: SESSION_CATALOG_LIMIT});
}

function requestPermissionHistory(bridge: DharmaBridge): void {
  bridge.send("permission.history", {limit: 50});
}

function requestSessionDetail(bridge: DharmaBridge, sessionId: string | undefined): void {
  if (!sessionId) {
    return;
  }
  bridge.send("session.detail", {session_id: sessionId, transcript_limit: SESSION_TRANSCRIPT_LIMIT});
}

function nextSessionPaneAfterCatalog(current: SessionPaneState, catalog: SessionCatalogPayload): SessionPaneState {
  const selectedSessionId =
    current.selectedSessionId && catalog.sessions.some((entry) => entry.session.session_id === current.selectedSessionId)
      ? current.selectedSessionId
      : catalog.sessions[0]?.session.session_id;
  return {
    catalog,
    selectedSessionId,
    detailsBySessionId: current.detailsBySessionId,
  };
}

function nextSessionPaneAfterDetail(current: SessionPaneState, detail: SessionDetailPayload): SessionPaneState {
  const catalog = current.catalog;
  return {
    catalog,
    selectedSessionId: detail.session.session_id,
    detailsBySessionId: {
      ...current.detailsBySessionId,
      [detail.session.session_id]: detail,
    },
  };
}

function nextApprovalPaneAfterDecision(
  current: ApprovalQueueState,
  decision: CanonicalPermissionDecision,
  seenAt = new Date().toISOString(),
): ApprovalQueueState {
  const existing = current.entriesByActionId[decision.action_id];
  const pending = decision.decision === "require_approval" && decision.requires_confirmation;
  return {
    selectedActionId: pending ? decision.action_id : current.selectedActionId ?? decision.action_id,
    entriesByActionId: {
      ...current.entriesByActionId,
      [decision.action_id]: {
        decision,
        status: existing?.resolution ? existing.status : pending ? "pending" : "observed",
        firstSeenAt: existing?.firstSeenAt ?? seenAt,
        lastSeenAt: seenAt,
        lastSourceEventType: "permission.decision",
        seenCount: (existing?.seenCount ?? 0) + 1,
        pending,
        resolution: existing?.resolution,
      },
    },
    order: [decision.action_id, ...current.order.filter((actionId) => actionId !== decision.action_id)],
    historyBacked: false,
    lastHistorySyncAt: current.lastHistorySyncAt,
  };
}

function nextApprovalPaneAfterResolution(
  current: ApprovalQueueState,
  resolution: CanonicalPermissionResolution,
): ApprovalQueueState {
  const existing = current.entriesByActionId[resolution.action_id];
  if (!existing) {
    return current;
  }
  const entriesByActionId = {
    ...current.entriesByActionId,
    [resolution.action_id]: {
      ...existing,
      status: resolution.resolution,
      pending: false,
      resolution,
      lastSeenAt: resolution.resolved_at,
      lastSourceEventType: "permission.resolution",
    },
  };
  const order = [resolution.action_id, ...current.order.filter((actionId) => actionId !== resolution.action_id)];
  const pendingSelection = order.find((actionId) => entriesByActionId[actionId]?.pending);
  return {
    selectedActionId:
      current.selectedActionId === resolution.action_id
        ? pendingSelection ?? order.find((actionId) => Boolean(entriesByActionId[actionId]))
        : current.selectedActionId,
    entriesByActionId,
    order,
    historyBacked: false,
    lastHistorySyncAt: current.lastHistorySyncAt,
  };
}

function nextApprovalPaneAfterOutcome(
  current: ApprovalQueueState,
  outcome: CanonicalPermissionOutcome,
): ApprovalQueueState {
  const existing = current.entriesByActionId[outcome.action_id];
  if (!existing) {
    return current;
  }
  const entriesByActionId = {
    ...current.entriesByActionId,
    [outcome.action_id]: {
      ...existing,
      status: outcome.outcome,
      outcome,
      pending: false,
      lastSeenAt: outcome.outcome_at,
      lastSourceEventType: "permission.outcome",
    },
  };
  const order = [outcome.action_id, ...current.order.filter((actionId) => actionId !== outcome.action_id)];
  return {
    selectedActionId: current.selectedActionId ?? outcome.action_id,
    entriesByActionId,
    order,
    historyBacked: false,
    lastHistorySyncAt: current.lastHistorySyncAt,
  };
}

function approvalPaneFromHistory(history: NonNullable<ReturnType<typeof permissionHistoryFromEvent>>): ApprovalQueueState {
  const order = history.entries.map((entry) => entry.action_id);
  const entriesByActionId = Object.fromEntries(
    history.entries.map((entry) => [
      entry.action_id,
      {
        decision: entry.decision,
        status: entry.status,
        firstSeenAt: entry.first_seen_at,
        lastSeenAt: entry.last_seen_at,
        lastSourceEventType: entry.resolution ? "permission.resolution" : "permission.decision",
        seenCount: entry.seen_count,
        pending: entry.pending,
        resolution: entry.resolution ?? undefined,
        outcome: entry.outcome ?? undefined,
      },
    ]),
  );
  return {
    selectedActionId: order.find((actionId) => entriesByActionId[actionId]?.pending) ?? order[0],
    entriesByActionId,
    order,
    historyBacked: true,
  };
}

function approvalResolveAction(entry: ApprovalQueueEntry, resolution: CanonicalPermissionResolution["resolution"], label: string): PaneAction {
  return {
    label,
    summary: `${resolution} ${entry.decision.action_id}`,
    payload: {
      action_type: "approval.resolve",
      action_id: entry.decision.action_id,
      resolution,
      metadata: entry.decision.metadata,
    },
  };
}

type BridgeHandlerDeps = {
  dispatch: React.Dispatch<AppAction>;
  getState: () => AppState;
  bridge: DharmaBridge;
  pendingBootstraps: React.MutableRefObject<Record<string, {prompt: string; provider: string; model: string}>>;
  requestHandshake?: (reason: "initial" | "reconnect" | "probe") => void;
  resetHandshakeBackoff?: () => void;
};

export function handshakeBackoffDelayMs(attempt: number): number {
  if (attempt <= 1) {
    return 5_000;
  }
  if (attempt === 2) {
    return 15_000;
  }
  if (attempt === 3) {
    return 30_000;
  }
  return 60_000;
}

function modelChoicesFromTab(tab: TabSpec | undefined): ModelChoice[] {
  if (!tab) {
    return [];
  }
  return tab.lines
    .map((line) => line.text)
    .filter((line) => line.startsWith("- ") && line.includes(" -> ") && line.includes("(") && line.includes(":"))
    .map((line) => {
      const cleaned = line.replace(/^- /, "").trim();
      const [aliasPart, rest = ""] = cleaned.split(" -> ");
      const match = rest.match(/^(.*?)\s+\(([^:]+):(.+)\)$/);
      return {
        alias: aliasPart.trim(),
        label: (match?.[1] ?? rest).trim(),
        provider: (match?.[2] ?? "").trim(),
        model: (match?.[3] ?? "").trim(),
      };
    })
    .filter((choice) => choice.alias.length > 0 && choice.provider.length > 0 && choice.model.length > 0);
}

function modelChoicesFromPolicy(value: unknown): ModelChoice[] {
  if (typeof value !== "object" || value === null) {
    return [];
  }
  const record = value as Record<string, unknown>;
  const targetsValue =
    typeof record.domain === "string" && record.domain === "routing_decision" ? record.targets : (record as {targets?: unknown}).targets;
  const policyTargets = (value as {targets?: unknown}).targets;
  const targets = targetsValue ?? policyTargets;
  if (!Array.isArray(targets)) {
    return [];
  }
  return targets
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => ({
      alias: String(item.alias ?? "").trim(),
      label: String(item.label ?? "").trim(),
      provider: String(item.provider ?? "").trim(),
      model: String(item.model ?? "").trim(),
    }))
    .filter((choice) => choice.alias.length > 0 && choice.provider.length > 0 && choice.model.length > 0);
}

function isBareModelCommand(prompt: string): boolean {
  const trimmed = prompt.trim();
  return trimmed === "/model" || trimmed === "/models" || trimmed === "/model list";
}

function paneActionsFor(tabId: string, state: AppState): {refresh: PaneAction; primary?: PaneAction; secondary?: PaneAction; tertiary?: PaneAction} {
  const modelTarget = `${state.provider}:${state.model}`;
  switch (tabId) {
    case "repo":
      return {
        refresh: {label: "refresh repo", summary: "refresh repo snapshot", payload: {action_type: "surface.refresh", surface: "repo"}},
        primary: {label: "/git", summary: "run /git", payload: {action_type: "command.run", command: "/git"}},
      };
    case "commands":
      return {
        refresh: {label: "refresh commands", summary: "refresh command registry", payload: {action_type: "surface.refresh", surface: "commands"}},
        primary: {label: "/runtime", summary: "run /runtime", payload: {action_type: "command.run", command: "/runtime"}},
        secondary: {label: "/git", summary: "run /git", payload: {action_type: "command.run", command: "/git"}},
        tertiary: {label: "/foundations", summary: "run /foundations", payload: {action_type: "command.run", command: "/foundations"}},
      };
    case "models":
      return {
        refresh: {
          label: "refresh models",
          summary: "refresh model policy",
          requestType: "model.policy",
          payload: {provider: state.provider, model: state.model, strategy: state.strategy},
        },
        primary: {label: "codex responsive", summary: "route to Codex 5.4 responsive", payload: {action_type: "model.set", provider: "codex", model: "gpt-5.4", strategy: "responsive"}},
        secondary: {label: "opus genius", summary: "route to Claude Opus 4.6 genius", payload: {action_type: "model.set", provider: "claude", model: "claude-opus-4-6", strategy: "genius"}},
        tertiary: {label: "cost on current", summary: `apply cost strategy to ${modelTarget}`, payload: {action_type: "model.set", provider: state.provider, model: state.model, strategy: "cost"}},
      };
    case "ontology":
      return {
        refresh: {label: "refresh ontology", summary: "refresh ontology snapshot", payload: {action_type: "surface.refresh", surface: "ontology"}},
        primary: {label: "/foundations", summary: "run /foundations", payload: {action_type: "command.run", command: "/foundations"}},
        secondary: {label: "/context", summary: "run /context", payload: {action_type: "command.run", command: "/context"}},
      };
    case "control":
    case "runtime":
      return {
        refresh: {label: "refresh control", summary: "refresh runtime snapshot", requestType: "runtime.snapshot", payload: {}},
        primary: {label: "/runtime", summary: "run /runtime", payload: {action_type: "command.run", command: "/runtime"}},
        secondary: {label: "/dashboard", summary: "run /dashboard", payload: {action_type: "command.run", command: "/dashboard"}},
      };
    case "agents":
      return {
        refresh: {label: "refresh agents", summary: "refresh operator and routing view", requestType: "agent.routes", payload: {}},
        primary: {label: "deep_code_work", summary: "preview deep-code route", payload: {action_type: "agent.route", intent: "deep_code_work"}},
        secondary: {label: "/swarm", summary: "run /swarm", payload: {action_type: "command.run", command: "/swarm"}},
        tertiary: {label: "architecture_research", summary: "preview architecture route", payload: {action_type: "agent.route", intent: "architecture_research"}},
      };
    case "evolution":
      return {
        refresh: {label: "refresh evolution", summary: "refresh evolution surface", payload: {action_type: "surface.refresh", surface: "evolution"}},
        primary: {label: "/loops", summary: "open loops lane", payload: {action_type: "evolution.run", command: "/loops"}},
        secondary: {label: "/cascade code", summary: "prepare code cascade", payload: {action_type: "evolution.run", command: "/cascade code"}},
        tertiary: {label: "/evolve shell", summary: "prepare shell evolution", payload: {action_type: "evolution.run", command: "/evolve terminal forward"}},
      };
    case "sessions":
      return {
        refresh: {label: "refresh sessions", summary: "refresh session catalog", requestType: "session.catalog", payload: {limit: SESSION_CATALOG_LIMIT}},
        primary: state.sessionPane.selectedSessionId
          ? {
              label: "refresh detail",
              summary: "refresh selected session detail",
              requestType: "session.detail",
              payload: {session_id: state.sessionPane.selectedSessionId, transcript_limit: SESSION_TRANSCRIPT_LIMIT},
            }
          : undefined,
        secondary: {label: "/archive", summary: "run /archive", payload: {action_type: "command.run", command: "/archive"}},
        tertiary: {label: "/memory", summary: "run /memory", payload: {action_type: "command.run", command: "/memory"}},
      };
    case "approvals":
      {
        const selectedEntry = state.approvalPane.selectedActionId
          ? state.approvalPane.entriesByActionId[state.approvalPane.selectedActionId]
          : undefined;
        const primary =
          selectedEntry && selectedEntry.pending
            ? approvalResolveAction(selectedEntry, "approved", "approve")
            : selectedEntry && selectedEntry.status === "observed"
              ? approvalResolveAction(selectedEntry, "resolved", "mark resolved")
              : {
                  label: "focus approval",
                  summary: "focus selected approval",
                  payload: {},
                };
        const secondary =
          selectedEntry && selectedEntry.pending ? approvalResolveAction(selectedEntry, "denied", "deny") : undefined;
        const tertiary =
          selectedEntry && selectedEntry.pending
            ? approvalResolveAction(selectedEntry, "dismissed", "dismiss")
            : undefined;
        return {
          refresh: {label: "refresh approvals", summary: "refresh approval history", requestType: "permission.history", payload: {limit: 50}},
          primary: selectedEntry ? primary : undefined,
          secondary,
          tertiary,
        };
      }
    default:
      return {
        refresh: {label: "refresh shell", summary: "refresh live snapshots", payload: {action_type: "surface.refresh", surface: "control"}},
      };
  }
}

function footerHintFor(tabId: string, state: AppState): string {
  const actions = paneActionsFor(tabId, state);
  const parts = [state.footerHint, `^L ${actions.refresh.label}`];
  if (actions.primary) {
    parts.push(`^X ${actions.primary.label}`);
  }
  if (actions.secondary) {
    parts.push(`^F ${actions.secondary.label}`);
  }
  if (actions.tertiary) {
    parts.push(`^V ${actions.tertiary.label}`);
  }
  return parts.join(" | ");
}

function mergePreview(current: Record<string, string> | undefined, incoming: Record<string, string> | undefined): Record<string, string> | undefined {
  if (!incoming) {
    return current;
  }
  return {...(current ?? {}), ...incoming};
}

function asPreviewRecord(value: unknown): TabPreview | undefined {
  if (typeof value !== "object" || value === null) {
    return undefined;
  }
  const entries = Object.entries(value as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === "string");
  if (entries.length === 0) {
    return undefined;
  }
  return Object.fromEntries(entries);
}

function authorityLabel(surface: "repo" | "control", bridgeStatus: AppState["bridgeStatus"], authoritative: boolean): string {
  if (bridgeStatus === "connected") {
    return authoritative ? "live | authoritative" : `resyncing | awaiting authoritative ${surface} refresh`;
  }
  if (authoritative) {
    return `stale | bridge ${bridgeStatus} | last authoritative ${surface} snapshot`;
  }
  return `placeholder | bridge ${bridgeStatus} | awaiting authoritative ${surface} refresh`;
}

function decorateSurfacePreview(
  preview: TabPreview | undefined,
  surface: "repo" | "control",
  bridgeStatus: AppState["bridgeStatus"],
  authoritativeSurfaces: SurfaceAuthorityState,
): TabPreview | undefined {
  if (!preview) {
    return undefined;
  }
  return {
    ...preview,
    Authority: authorityLabel(surface, bridgeStatus, authoritativeSurfaces[surface]),
  };
}

function isStructuredControlSnapshotContent(output: string): boolean {
  return output.includes("# Runtime") || /^(Runtime DB|Durable state):\s+/m.test(output);
}

export function commandRunSnapshotActionsForBridgeEvent(
  event: BridgeEvent,
  liveRepoPreview?: TabPreview,
  liveControlPreview?: TabPreview,
  supervisor = loadSupervisorControlState(),
): AppAction[] {
  const typed = event as Record<string, unknown>;
  const eventType = String(typed.type ?? "");
  const isCommandRunAction = eventType === "action.result" && String(typed.action_type ?? "") === "command.run";
  if (eventType !== "command.result" && !isCommandRunAction) {
    return [];
  }

  const targetPane = resolveCommandTargetPane(typed, "control");

  const output = String(typed.output ?? "");
  if (targetPane === "repo") {
    if (!isWorkspaceSnapshotContent(output)) {
      return [];
    }

    const preview = workspaceSnapshotToPreview(output);
    const mergedPreview = mergePreview(liveRepoPreview, preview);
    return [
      {
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      },
      {type: "live.repo.set", preview: mergedPreview},
    ];
  }

  if ((targetPane === "control" || targetPane === "runtime") && isStructuredControlSnapshotContent(output)) {
    const preview = runtimeSnapshotToPreview(output, supervisor);
    const mergedPreview = mergePreview(liveControlPreview, preview);
    return [
      {
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      },
      {
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      },
      {type: "live.control.set", preview: mergedPreview},
    ];
  }

  return [];
}

export function persistControlPreview(preview?: TabPreview): void {
  if (!preview) {
    return;
  }
  const supervisor = loadSupervisorControlState();
  if (supervisor) {
    saveSupervisorControlSummary(supervisor, preview);
  }
}

export function persistRepoPreview(preview?: TabPreview): void {
  if (!preview) {
    return;
  }
  const supervisor = loadSupervisorControlState();
  if (supervisor) {
    saveSupervisorRepoPreview(supervisor, preview);
  }
}

export function snapshotActionsForBridgeEvent(
  event: BridgeEvent,
  liveRepoPreview?: TabPreview,
  liveControlPreview?: TabPreview,
): AppAction[] {
  const typed = event as Record<string, unknown>;
  const eventType = String(typed.type ?? "");

  if (eventType === "workspace.snapshot.result") {
    const typedPayload = workspaceSnapshotPayloadFromEvent(typed);
    const preview = typedPayload
      ? workspacePayloadToPreview(typedPayload)
      : workspaceSnapshotToPreview(String(typed.content ?? ""));
    return [
      {
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(preview),
        preview,
      },
      {type: "live.repo.set", preview},
    ];
  }

  if (eventType === "session.bootstrap.result") {
    const actions: AppAction[] = [];
    const workspacePreview = asPreviewRecord(typed.workspace_preview);
    const runtimePreview = asPreviewRecord(typed.runtime_preview);

    if (workspacePreview) {
      const mergedWorkspacePreview = mergePreview(liveRepoPreview, workspacePreview);
      actions.push({
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(mergedWorkspacePreview ?? workspacePreview),
        preview: mergedWorkspacePreview,
      });
      actions.push({
        type: "live.repo.set",
        preview: mergedWorkspacePreview,
      });
    }

    if (runtimePreview) {
      const mergedRuntimePreview = mergePreview(liveControlPreview, runtimePreview);
      actions.push({
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(mergedRuntimePreview ?? runtimePreview),
        preview: mergedRuntimePreview,
      });
      actions.push({
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(mergedRuntimePreview ?? runtimePreview),
        preview: mergedRuntimePreview,
      });
      actions.push({
        type: "live.control.set",
        preview: mergedRuntimePreview,
      });
    }

    return actions;
  }

  return [];
}

export function commandResultActionsForBridgeEvent(event: BridgeEvent): AppAction[] {
  const typed = event as Record<string, unknown>;
  if (String(typed.type ?? "") !== "command.result") {
    return [];
  }

  return slashCommandResultActions(typed);
}

export function slashCommandStartActions(event: Record<string, unknown>, statusPrefix = "command"): AppAction[] {
  const command = resolveEventCommand(event);
  if (!command) {
    return [];
  }

  const tabId = resolveCommandTargetPane(event, commandTargetTab(command));
  return [
    {type: "tab.activate", tabId},
    {type: "status.set", value: `${statusPrefix} ${command} -> ${tabId}`},
  ];
}

export function actionResultActionsForBridgeEvent(event: BridgeEvent): AppAction[] {
  const typed = event as Record<string, unknown>;
  if (String(typed.type ?? "") !== "action.result") {
    return [];
  }

  if (String(typed.action_type ?? "") !== "command.run") {
    return [];
  }

  const tabId = resolveCommandTargetPane(typed, "control");
  return [{type: "tab.activate", tabId}];
}

function slashCommandResultActions(
  event: Record<string, unknown>,
  fallbackStatus = String(event.summary ?? "action applied"),
): AppAction[] {
  const command = resolveEventCommand(event);
  const normalized = normalizeCommandName(command);
  const tabId = resolveCommandTargetPane(event, "control");
  const statusValue = normalized ? `/${normalized} -> ${tabId}` : fallbackStatus;
  return [
    {type: "tab.activate", tabId},
    {type: "status.set", value: statusValue},
  ];
}

export function createBridgeEventHandler({
  dispatch,
  getState,
  bridge,
  pendingBootstraps,
  requestHandshake,
  resetHandshakeBackoff,
}: BridgeHandlerDeps): (event: BridgeEvent) => void {
  let awaitingAuthoritativeResync = true;
  let resyncPending = false;
  let reconnectRequested = false;
  const reconnectingCodes = new Set(["bridge_exit", "bridge_spawn_error", "bridge_send_failed", "bridge_stdin_unavailable"]);
  let malformedBridgeEvents = 0;

  function requestReconnect(status: string, offline = false): void {
    awaitingAuthoritativeResync = true;
    resyncPending = false;
    dispatch({type: "surface.truth.reset"});
    dispatch({type: "bridge.status", status: offline ? "offline" : "degraded"});
    dispatch({type: "status.set", value: status});
    if (reconnectRequested) {
      return;
    }
    reconnectRequested = true;
    if (requestHandshake) {
      requestHandshake("reconnect");
    } else {
      bridge.send("handshake");
    }
  }

  return (event: BridgeEvent) => {
    const typed = event as Record<string, unknown>;
    const eventType = String(typed.type ?? "");
    const state = getState();
    if (eventType !== "bridge.error" && eventType !== "error") {
      malformedBridgeEvents = 0;
    }
    if (eventType === "bridge.ready") {
      dispatch({type: "bridge.status", status: "connected"});
      dispatch({type: "status.set", value: "bridge ready"});
    }
    if (eventType === "bridge.error" || eventType === "error") {
      const code = String(typed.code ?? "");
      const message = String(typed.message ?? typed.code ?? "bridge error");
      if (reconnectingCodes.has(code)) {
        malformedBridgeEvents = 0;
        requestReconnect(code === "bridge_exit" ? "bridge exited, reconnecting" : "backend offline, retrying", code !== "bridge_exit");
      } else if (code === "invalid_bridge_json") {
        malformedBridgeEvents += 1;
        if (malformedBridgeEvents >= 3) {
          malformedBridgeEvents = 0;
          requestReconnect("bridge unhealthy, reconnecting");
        } else {
          dispatch({type: "bridge.status", status: "degraded"});
          dispatch({type: "status.set", value: `bridge output invalid (${malformedBridgeEvents}/3)`});
        }
      } else {
        dispatch({type: "bridge.status", status: "degraded"});
        dispatch({type: "status.set", value: message});
      }
    }
    if (eventType === "handshake.result") {
      const providers = Array.isArray(typed.providers) ? typed.providers : [];
      const defaultProviderId = String(typed.default_provider ?? "").trim();
      const selectedProvider = providers.find(
        (entry) =>
          typeof entry === "object" &&
          entry !== null &&
          String((entry as {provider_id?: string}).provider_id ?? "") === defaultProviderId,
      ) as {provider_id?: string; default_model?: string} | undefined;
      const fallbackProvider = providers.find((entry) => typeof entry === "object" && entry !== null) as
        | {provider_id?: string; default_model?: string}
        | undefined;
      const provider = selectedProvider?.provider_id ?? fallbackProvider?.provider_id ?? "codex";
      const model = selectedProvider?.default_model ?? fallbackProvider?.default_model ?? "gpt-5.4";
      dispatch({
        type: "bridge.config",
        provider,
        model,
        strategy: state.strategy,
      });
      malformedBridgeEvents = 0;
      reconnectRequested = false;
      resetHandshakeBackoff?.();
      dispatch({type: "bridge.status", status: "connected"});
      dispatch({type: "status.set", value: "backend connected"});
      if (awaitingAuthoritativeResync) {
        awaitingAuthoritativeResync = false;
        resyncPending = true;
        requestAuthoritativeResync(bridge, provider, model, state.strategy);
        dispatch({type: "status.set", value: authoritativeResyncStatus(state.authoritativeSurfaces)});
      }
    }
    if (eventType === "command.result") {
      const commandName = normalizeCommandName(resolveEventCommand(typed));
      commandResultActionsForBridgeEvent(typed).forEach((action) => dispatch(action));
      const commandSnapshotActions = commandRunSnapshotActionsForBridgeEvent(
        typed,
        state.liveRepoPreview,
        state.liveControlPreview,
      );
      commandSnapshotActions.forEach((action) => dispatch(action));
      const persistedRepoPreview = commandSnapshotActions.find((action) => action.type === "live.repo.set");
      if (persistedRepoPreview?.type === "live.repo.set") {
        persistRepoPreview(persistedRepoPreview.preview);
      }
      const persistedControlPreview = commandSnapshotActions.find((action) => action.type === "live.control.set");
      if (persistedControlPreview?.type === "live.control.set") {
        persistControlPreview(persistedControlPreview.preview);
      }
      if (commandName === "model") {
        dispatch({type: "modelPicker.open", returnTabId: state.activeTabId === "models" ? "chat" : state.activeTabId});
        bridge.send("model.policy", {
          provider: state.provider,
          model: state.model,
          strategy: state.strategy,
        });
      }
      requestLiveSnapshots(bridge, state.provider, state.model, state.strategy);
    }
    if (eventType === "workspace.snapshot.result") {
      const actions = snapshotActionsForBridgeEvent(typed, state.liveRepoPreview, state.liveControlPreview);
      actions.forEach((action) => dispatch(action));
      dispatch({type: "surface.truth.mark", surface: "repo"});
      if (resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "repo");
        dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const persistedRepoPreview = actions.find((action) => action.type === "live.repo.set");
      if (persistedRepoPreview?.type === "live.repo.set") {
        persistRepoPreview(persistedRepoPreview.preview);
      }
    }
    if (eventType === "permission.decision") {
      const decision = permissionDecisionFromEvent(typed);
      if (decision) {
        const nextApprovalPane = nextApprovalPaneAfterDecision(state.approvalPane, decision);
        dispatch({type: "approval.decision.set", decision, sourceEventType: eventType});
        dispatch({
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(nextApprovalPane),
          preview: approvalPaneToPreview(nextApprovalPane),
        });
        if (decision.decision === "require_approval" && decision.requires_confirmation) {
          dispatch({type: "tab.activate", tabId: "approvals"});
          dispatch({type: "status.set", value: `approval required ${decision.tool_name} (${decision.risk})`});
        }
        requestPermissionHistory(bridge);
      }
    }
    if (eventType === "permission.history.result") {
      const history = permissionHistoryFromEvent(typed);
      if (history) {
        dispatch({type: "surface.truth.mark", surface: "approvals"});
        if (resyncPending && state.bridgeStatus === "connected") {
          const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "approvals");
          dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
          resyncPending = !authoritativeResyncComplete(nextAuthority);
        }
        const approvalPane = approvalPaneFromHistory(history);
        dispatch({type: "approval.history.set", approvalPane});
        dispatch({
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(approvalPane),
          preview: approvalPaneToPreview(approvalPane),
        });
      }
    }
    if (eventType === "permission.resolution") {
      const resolution = permissionResolutionFromEvent(typed);
      if (resolution) {
        const nextApprovalPane = nextApprovalPaneAfterResolution(state.approvalPane, resolution);
        dispatch({type: "approval.resolution.set", resolution, sourceEventType: eventType});
        dispatch({
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(nextApprovalPane),
          preview: approvalPaneToPreview(nextApprovalPane),
        });
        dispatch({type: "status.set", value: `${resolution.resolution} ${resolution.action_id} (${resolution.enforcement_state})`});
        requestPermissionHistory(bridge);
      }
    }
    if (eventType === "permission.outcome") {
      const outcome = permissionOutcomeFromEvent(typed);
      if (outcome) {
        const nextApprovalPane = nextApprovalPaneAfterOutcome(state.approvalPane, outcome);
        dispatch({type: "approval.outcome.set", outcome, sourceEventType: eventType});
        dispatch({
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(nextApprovalPane),
          preview: approvalPaneToPreview(nextApprovalPane),
        });
        dispatch({type: "status.set", value: `${outcome.outcome} ${outcome.action_id}`});
        requestPermissionHistory(bridge);
      }
    }
    if (eventType === "session.catalog.result") {
      const catalog = sessionCatalogFromEvent(typed);
      if (catalog) {
        dispatch({type: "surface.truth.mark", surface: "sessions"});
        if (resyncPending && state.bridgeStatus === "connected") {
          const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "sessions");
          dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
          resyncPending = !authoritativeResyncComplete(nextAuthority);
        }
        const nextSessionPane = nextSessionPaneAfterCatalog(state.sessionPane, catalog);
        dispatch({type: "session.catalog.set", catalog, selectedSessionId: nextSessionPane.selectedSessionId});
        dispatch({
          type: "tab.replace",
          tabId: "sessions",
          lines: sessionPaneToLines(nextSessionPane),
          preview: sessionPaneToPreview(nextSessionPane),
        });
        if (
          nextSessionPane.selectedSessionId &&
          !nextSessionPane.detailsBySessionId[nextSessionPane.selectedSessionId]
        ) {
          requestSessionDetail(bridge, nextSessionPane.selectedSessionId);
        }
      }
    }
    if (eventType === "session.detail.result") {
      const detail = sessionDetailFromEvent(typed);
      if (detail) {
        const nextSessionPane = nextSessionPaneAfterDetail(state.sessionPane, detail);
        dispatch({type: "session.detail.set", detail});
        dispatch({
          type: "tab.replace",
          tabId: "sessions",
          lines: sessionPaneToLines(nextSessionPane),
          preview: sessionPaneToPreview(nextSessionPane),
        });
      }
    }
    if (eventType === "command.graph.result") {
      dispatch({
        type: "tab.replace",
        tabId: "commands",
        lines: commandGraphToLines(typed),
        preview: commandGraphToPreview(typed),
      });
    }
    if (eventType === "command.registry.result") {
      const existingTab = state.tabs.find((tab) => tab.id === "commands");
      const registry = typeof typed.registry === "object" && typed.registry !== null ? (typed.registry as Record<string, unknown>) : {};
      dispatch({
        type: "tab.replace",
        tabId: "commands",
        lines: (existingTab?.lines.slice(0, 3) ??
          commandGraphToLines({
            graph: {
              count: registry.count ?? 0,
              async_count: 0,
              categories: {},
            },
          })).concat(
          String(typed.content ?? "")
            .split("\n")
            .filter((line) => line.trim().length > 0)
            .slice(3)
            .map((line, index) => ({
              id: `command-registry-${index}-${Date.now()}`,
              kind: "system" as const,
              text: line,
            })),
        ),
        preview: {
          ...(existingTab?.preview ?? {}),
          Commands: String(registry.count ?? 0),
        },
      });
    }
    if (eventType === "ontology.snapshot.result") {
      const content = String(typed.content ?? "");
      dispatch({
        type: "tab.replace",
        tabId: "ontology",
        lines: content
          .split("\n")
          .filter((line) => line.trim().length > 0)
          .map((line, index) => ({
            id: `ontology-${index}-${Date.now()}`,
            kind: "system",
            text: line,
          })),
      });
    }
    if (eventType === "runtime.snapshot.result") {
      dispatch({type: "surface.truth.mark", surface: "control"});
      if (resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "control");
        dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const supervisor = loadSupervisorControlState();
      const typedPayload = runtimeSnapshotPayloadFromEvent(typed);
      const content = String(typed.content ?? "");
      const preview = typedPayload ? runtimePayloadToPreview(typedPayload, supervisor) : runtimeSnapshotToPreview(content, supervisor);
      const mergedPreview = mergePreview(state.liveControlPreview, preview);
      persistControlPreview(mergedPreview);
      dispatch({
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      });
      dispatch({
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      });
      dispatch({type: "live.control.set", preview: mergedPreview});
    }
    if (eventType === "model.policy.result") {
      dispatch({type: "surface.truth.mark", surface: "models"});
      if (resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "models");
        dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const routingPayload = routingDecisionPayloadFromEvent(typed);
      const modelTargets = modelChoicesFromPolicy(routingPayload ?? typed.policy);
      dispatch({
        type: "tab.replace",
        tabId: "models",
        lines: modelPolicyToLines(routingPayload ? {payload: routingPayload} : typed),
        preview: modelPolicyToPreview(routingPayload ? {payload: routingPayload} : typed),
        modelTargets,
      });
    }
    if (eventType === "agent.routes.result") {
      dispatch({type: "surface.truth.mark", surface: "agents"});
      if (resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "agents");
        dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const routesPayload = agentRoutesPayloadFromEvent(typed);
      dispatch({
        type: "tab.replace",
        tabId: "agents",
        lines: agentRoutesToLines(routesPayload ? {payload: routesPayload} : typed),
        preview: agentRoutesToPreview(routesPayload ? {payload: routesPayload} : typed),
      });
    }
    if (eventType === "evolution.surface.result") {
      dispatch({
        type: "tab.replace",
        tabId: "evolution",
        lines: evolutionSurfaceToLines(typed),
        preview: evolutionSurfaceToPreview(typed),
      });
    }
    if (eventType === "session.bootstrap.result") {
      const requestId = String(typed.request_id ?? "");
      const pending = pendingBootstraps.current[requestId];
      persistRepoPreview(mergePreview(state.liveRepoPreview, asPreviewRecord(typed.workspace_preview)));
      persistControlPreview(mergePreview(state.liveControlPreview, asPreviewRecord(typed.runtime_preview)));
      dispatch({
        type: "tab.replace",
        tabId: "mission",
        lines: sessionBootstrapToLines(typed),
        preview: sessionBootstrapToPreview(typed),
      });
      const actions = snapshotActionsForBridgeEvent(typed, state.liveRepoPreview, state.liveControlPreview);
      actions.forEach((action) => dispatch(action));

      const selectedProvider = String(typed.selected_provider ?? pending?.provider ?? state.provider);
      const selectedModel = String(typed.selected_model ?? pending?.model ?? state.model);
      const selectedStrategy = String(typed.routing_strategy ?? state.strategy ?? "responsive");
      dispatch({type: "bridge.config", provider: selectedProvider, model: selectedModel, strategy: selectedStrategy});

      const intent = typed.intent as Record<string, unknown> | undefined;
      if (intent && String(intent.kind ?? "") === "command" && Boolean(intent.auto_execute)) {
        const command = `/${String(intent.command ?? "")}`;
        const tabId = commandTargetTab(command);
        dispatch({type: "tab.activate", tabId});
        bridge.send("command.run", {command});
        dispatch({type: "status.set", value: `intent ${command} -> ${tabId}`});
      } else if (intent && String(intent.kind ?? "") === "model_switch") {
        bridge.send("action.run", {
          action_type: "model.set",
          provider: selectedProvider,
          model: selectedModel,
          strategy: String(intent.strategy ?? selectedStrategy),
        });
        dispatch({
          type: "bridge.config",
          provider: selectedProvider,
          model: selectedModel,
          strategy: String(intent.strategy ?? selectedStrategy),
        });
        dispatch({
          type: "status.set",
          value: `model route -> ${selectedProvider}:${selectedModel} (${String(intent.strategy ?? selectedStrategy)})`,
        });
        dispatch({
          type: "tab.append",
          tabId: "chat",
          lines: [
            {
              id: `model-switch-${Date.now()}`,
              kind: "assistant",
              text: `Switched route to ${selectedProvider}:${selectedModel} (${String(intent.strategy ?? selectedStrategy)}).`,
            },
          ],
        });
      } else if (intent && String(intent.kind ?? "") === "agent") {
        dispatch({type: "tab.activate", tabId: "agents"});
        bridge.send("agent.routes");
        dispatch({type: "status.set", value: "agent routing surface ready"});
        if (pending) {
          bridge.send("session.start", {
            provider: selectedProvider,
            model: selectedModel,
            prompt: pending.prompt,
            bootstrap: typed,
            system_prompt: String(typed.system_prompt ?? ""),
          });
        }
      } else if (intent && String(intent.kind ?? "") === "evolution") {
        dispatch({type: "tab.activate", tabId: "evolution"});
        bridge.send("evolution.surface");
        dispatch({type: "status.set", value: "evolution surface ready"});
        if (pending) {
          bridge.send("session.start", {
            provider: selectedProvider,
            model: selectedModel,
            prompt: pending.prompt,
            bootstrap: typed,
            system_prompt: String(typed.system_prompt ?? ""),
          });
        }
      } else if (pending) {
        bridge.send("session.start", {
          provider: selectedProvider,
          model: selectedModel,
          prompt: pending.prompt,
          bootstrap: typed,
          system_prompt: String(typed.system_prompt ?? ""),
        });
        dispatch({type: "status.set", value: `running ${selectedProvider}:${selectedModel}`});
      }
      delete pendingBootstraps.current[requestId];
    }
    if (eventType === "session_end") {
      requestLiveSnapshots(bridge, state.provider, state.model, state.strategy);
      requestSessionCatalog(bridge);
    }
    if (eventType === "action.result") {
      const actionType = String(typed.action_type ?? "");
      if (actionType === "command.run") {
        slashCommandResultActions(typed).forEach((action) => dispatch(action));
      } else {
        actionResultActionsForBridgeEvent(typed).forEach((action) => dispatch(action));
      }
      const pane =
        actionType === "command.run" ? resolveCommandTargetPane(typed, "control") : String(typed.target_pane ?? "control");
      const commandRunSnapshotActions = commandRunSnapshotActionsForBridgeEvent(
        typed,
        state.liveRepoPreview,
        state.liveControlPreview,
      );
      commandRunSnapshotActions.forEach((action) => dispatch(action));
      const surfaceRefreshActions = surfaceRefreshActionsForBridgeEvent(
        typed,
        state.liveRepoPreview,
        state.liveControlPreview,
        state.sessionPane,
      );
      surfaceRefreshActions.forEach((action) => dispatch(action));
      if (actionType === "surface.refresh") {
        const surface = String(typed.surface ?? "").trim().toLowerCase();
        if (surface === "repo" || surface === "workspace") {
          dispatch({type: "surface.truth.mark", surface: "repo"});
          if (resyncPending && state.bridgeStatus === "connected") {
            const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "repo");
            dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
            resyncPending = !authoritativeResyncComplete(nextAuthority);
          }
        }
        if (surface === "control" || surface === "runtime") {
          dispatch({type: "surface.truth.mark", surface: "control"});
          if (resyncPending && state.bridgeStatus === "connected") {
            const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "control");
            dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
            resyncPending = !authoritativeResyncComplete(nextAuthority);
          }
        }
        if (surface === "sessions" || surface === "session") {
          dispatch({type: "surface.truth.mark", surface: "sessions"});
          if (resyncPending && state.bridgeStatus === "connected") {
            const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "sessions");
            dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
            resyncPending = !authoritativeResyncComplete(nextAuthority);
          }
        }
        if (surface === "models" || surface === "model") {
          dispatch({type: "surface.truth.mark", surface: "models"});
          if (resyncPending && state.bridgeStatus === "connected") {
            const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "models");
            dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
            resyncPending = !authoritativeResyncComplete(nextAuthority);
          }
        }
        if (surface === "agents" || surface === "agent") {
          dispatch({type: "surface.truth.mark", surface: "agents"});
          if (resyncPending && state.bridgeStatus === "connected") {
            const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "agents");
            dispatch({type: "status.set", value: authoritativeResyncStatus(nextAuthority)});
            resyncPending = !authoritativeResyncComplete(nextAuthority);
          }
        }
      }
      const persistedRepoPreview = [...commandRunSnapshotActions, ...surfaceRefreshActions].find(
        (action) => action.type === "live.repo.set",
      );
      if (persistedRepoPreview?.type === "live.repo.set") {
        persistRepoPreview(persistedRepoPreview.preview);
      }
      const persistedControlPreview = [...commandRunSnapshotActions, ...surfaceRefreshActions].find(
        (action) => action.type === "live.control.set",
      );
      if (persistedControlPreview?.type === "live.control.set") {
        persistControlPreview(persistedControlPreview.preview);
      }
      const output = String(typed.output ?? "").trim();
      const policy =
        typeof typed.policy === "object" && typed.policy !== null ? (typed.policy as Record<string, unknown>) : null;
      const routingPayload = routingDecisionPayloadFromEvent(typed);
      if (policy || routingPayload) {
        const modelTargets = modelChoicesFromPolicy(routingPayload ?? policy);
        dispatch({
          type: "bridge.config",
          provider: String(
            routingPayload?.decision.provider_id ?? policy?.selected_provider ?? state.provider,
          ),
          model: String(routingPayload?.decision.model_id ?? policy?.selected_model ?? state.model),
          strategy: String(routingPayload?.decision.strategy ?? policy?.strategy ?? state.strategy),
        });
        dispatch({
          type: "tab.replace",
          tabId: "models",
          lines: modelPolicyToLines(routingPayload ? {payload: routingPayload} : {policy}),
          preview: modelPolicyToPreview(routingPayload ? {payload: routingPayload} : {policy}),
          modelTargets,
        });
      }
      if (
        output &&
        actionType !== "command.run" &&
        commandRunSnapshotActions.length === 0 &&
        surfaceRefreshActions.length === 0 &&
        !(pane === "models" && (policy || routingPayload))
      ) {
        dispatch({
          type: "tab.append",
          tabId: pane,
          lines: [{id: `action-${Date.now()}`, kind: "system", text: output}],
        });
      }
      if (actionType !== "command.run" && !(actionType === "surface.refresh" && resyncPending)) {
        dispatch({type: "status.set", value: String(typed.summary ?? "action applied")});
      }
      requestLiveSnapshots(bridge, state.provider, state.model, state.strategy);
    }

    const patches = eventToTabPatch(typed);
    for (const patch of patches) {
      dispatch({type: "tab.append", tabId: patch.tabId, lines: patch.lines});
    }
  };
}

export function surfaceRefreshActionsForBridgeEvent(
  event: BridgeEvent,
  liveRepoPreview?: TabPreview,
  liveControlPreview?: TabPreview,
  sessionPane?: SessionPaneState,
  supervisor = loadSupervisorControlState(),
): AppAction[] {
  const typed = event as Record<string, unknown>;
  if (String(typed.type ?? "") !== "action.result" || String(typed.action_type ?? "") !== "surface.refresh") {
    return [];
  }

  const surface = String(typed.surface ?? typed.target_pane ?? "").trim().toLowerCase();
  if (surface === "sessions" || surface === "session") {
    const catalog = sessionCatalogFromEvent(typed);
    if (catalog) {
      const nextSessionPane = nextSessionPaneAfterCatalog(sessionPane ?? {detailsBySessionId: {}} as SessionPaneState, catalog);
      return [
        {type: "session.catalog.set", catalog, selectedSessionId: nextSessionPane.selectedSessionId},
        {
          type: "tab.replace",
          tabId: "sessions",
          lines: sessionPaneToLines(nextSessionPane),
          preview: sessionPaneToPreview(nextSessionPane),
        },
      ];
    }
  }
  if (surface === "agents" || surface === "agent") {
    const routesPayload = agentRoutesPayloadFromEvent(typed);
    if (routesPayload) {
      return [
        {
          type: "tab.replace",
          tabId: "agents",
          lines: agentRoutesToLines({payload: routesPayload}),
          preview: agentRoutesToPreview({payload: routesPayload}),
        },
      ];
    }
  }

  if (surface === "repo" || surface === "workspace") {
    const workspacePayload = workspaceSnapshotPayloadFromEvent(typed);
    const output = String(typed.output ?? "");
    if (!workspacePayload && !output.trim()) {
      return [];
    }
    const preview = workspacePayload ? workspacePayloadToPreview(workspacePayload) : workspaceSnapshotToPreview(output);
    const mergedPreview = mergePreview(liveRepoPreview, preview);
    return [
      {
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      },
      {type: "live.repo.set", preview: mergedPreview},
    ];
  }

  if (surface === "control" || surface === "runtime") {
    const typedPayload = runtimeSnapshotPayloadFromEvent(typed);
    const output = String(typed.output ?? "");
    if (!typedPayload && !output.trim()) {
      return [];
    }
    const preview = typedPayload ? runtimePayloadToPreview(typedPayload, supervisor) : runtimeSnapshotToPreview(output, supervisor);
    const mergedPreview = mergePreview(liveControlPreview, preview);
    return [
      {
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      },
      {
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(mergedPreview ?? preview),
        preview: mergedPreview,
      },
      {type: "live.control.set", preview: mergedPreview},
    ];
  }

  const output = String(typed.output ?? "");
  if (!output.trim()) {
    return [];
  }

  return [];
}

export function paneActionStartActions(action: {summary: string; payload: Record<string, unknown>} | undefined): AppAction[] {
  if (!action) {
    return [];
  }

  if (String(action.payload.action_type ?? "") === "command.run") {
    return slashCommandStartActions(
      {
        ...action.payload,
        summary: action.summary,
      },
      "command",
    );
  }

  if (action.summary === "focus selected approval") {
    return [{type: "tab.activate", tabId: "approvals"}, {type: "status.set", value: action.summary}];
  }

  return [{type: "status.set", value: action.summary}];
}

export function App(): React.ReactElement {
  const {exit} = useApp();
  const [state, dispatch] = useReducer(reduceApp, initialState, createInitialAppState);

  const activeTab = state.tabs.find((tab) => tab.id === state.activeTabId) ?? state.tabs[0];
  const outline = useMemo(() => outlineFromTabs(state.tabs), [state.tabs]);
  const modelChoices = state.modelTargets.length > 0 ? state.modelTargets : modelChoicesFromTab(state.tabs.find((tab) => tab.id === "models"));
  const stateRef = useRef(state);
  const pendingBootstraps = useRef<Record<string, {prompt: string; provider: string; model: string}>>({});
  const bridgeRef = useRef<DharmaBridge | null>(null);
  const handshakeBackoffRef = useRef({attempt: 0, nextAllowedAt: 0});
  const persistTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function requestHandshake(reason: "initial" | "reconnect" | "probe"): void {
    const bridgeInstance = bridgeRef.current;
    if (!bridgeInstance) {
      return;
    }
    const now = Date.now();
    const meta = handshakeBackoffRef.current;
    if (reason === "initial") {
      meta.attempt = 0;
      meta.nextAllowedAt = now + 1_000;
      bridgeInstance.send("handshake");
      return;
    }
    if (now < meta.nextAllowedAt) {
      return;
    }
    meta.attempt += 1;
    meta.nextAllowedAt = now + handshakeBackoffDelayMs(meta.attempt);
    bridgeInstance.send("handshake");
  }

  function resetHandshakeBackoff(): void {
    handshakeBackoffRef.current = {attempt: 0, nextAllowedAt: 0};
  }

  const bridge = useMemo(
    () => {
      let onEvent: (event: BridgeEvent) => void = () => undefined;
      const instance = new DharmaBridge((event: BridgeEvent) => onEvent(event));
      bridgeRef.current = instance;
      onEvent = createBridgeEventHandler({
        dispatch,
        getState: () => stateRef.current,
        bridge: instance,
        pendingBootstraps,
        requestHandshake: (reason) => requestHandshake(reason),
        resetHandshakeBackoff,
      });
      return instance;
    },
    [],
  );

  useEffect(() => {
    requestHandshake("initial");
    const intervalId = setInterval(() => {
      if (stateRef.current.bridgeStatus === "connected") {
        requestAuthoritativeResync(bridge, stateRef.current.provider, stateRef.current.model, stateRef.current.strategy);
      } else {
        requestHandshake("probe");
      }
    }, SNAPSHOT_REFRESH_INTERVAL_MS);
    return () => {
      clearInterval(intervalId);
      bridge.close();
    };
  }, [bridge]);

  useEffect(() => {
    if (state.bridgeStatus !== "connected" || authoritativeResyncComplete(state.authoritativeSurfaces)) {
      return;
    }
    const repairId = setTimeout(() => {
      requestMissingAuthoritativeSurfaces(
        bridge,
        stateRef.current.provider,
        stateRef.current.model,
        stateRef.current.strategy,
        stateRef.current.authoritativeSurfaces,
      );
    }, 3_000);
    return () => {
      clearTimeout(repairId);
    };
  }, [bridge, state.bridgeStatus, state.authoritativeSurfaces]);

  useEffect(() => {
    stateRef.current = state;
    if (persistTimeoutRef.current) {
      clearTimeout(persistTimeoutRef.current);
    }
    persistTimeoutRef.current = setTimeout(() => {
      saveStoredState({...state, outline});
      persistTimeoutRef.current = null;
    }, 120);
    return () => {
      if (persistTimeoutRef.current) {
        clearTimeout(persistTimeoutRef.current);
        persistTimeoutRef.current = null;
      }
    };
  }, [state, outline]);

  function submitPrompt(prompt: string): void {
    const submitted = prompt.trim();
    if (!submitted) {
      return;
    }
    dispatch({type: "prompt.clear"});
    if (isBareModelCommand(submitted)) {
      dispatch({
        type: "modelPicker.open",
        returnTabId: stateRef.current.activeTabId === "models" ? "chat" : stateRef.current.activeTabId,
      });
      bridge.send("model.policy", {
        provider: stateRef.current.provider,
        model: stateRef.current.model,
        strategy: stateRef.current.strategy,
      });
      dispatch({type: "status.set", value: "model picker ready"});
      return;
    }
    if (isSlashCommandPrompt(submitted)) {
      slashCommandStartActions({command: submitted}, "command").forEach((action) => dispatch(action));
      bridge.send("command.run", {command: submitted});
    } else {
      const userLine: TranscriptLine = {
        id: `user-${Date.now()}`,
        kind: "user",
        text: `> ${submitted}`,
      };
      dispatch({type: "tab.append", tabId: "chat", lines: [userLine]});
      const requestId = bridge.send("session.bootstrap", {
        provider: state.provider,
        model: state.model,
        strategy: state.strategy,
        prompt: submitted,
        active_tab: state.activeTabId,
      });
      pendingBootstraps.current[requestId] = {
        prompt: submitted,
        provider: state.provider,
        model: state.model,
      };
      dispatch({type: "status.set", value: `bootstrapping ${state.provider}:${state.model} (${state.strategy})`});
    }
  }

  function runPaneAction(action: PaneAction | undefined): void {
    if (!action) {
      return;
    }
    paneActionStartActions(action).forEach((dispatchAction) => dispatch(dispatchAction));
    if (action.summary === "focus selected approval") {
      return;
    }
    bridge.send(action.requestType ?? "action.run", action.payload);
  }

  function applyModelChoice(index: number): void {
    const modelsTab = stateRef.current.tabs.find((tab) => tab.id === "models");
    const choices = modelChoicesFromTab(modelsTab);
    const clampedIndex = Math.min(Math.max(index, 0), Math.max(choices.length - 1, 0));
    const choice = choices[clampedIndex];
    if (!choice) {
      dispatch({type: "status.set", value: "no model targets available"});
      return;
    }
    dispatch({type: "modelPicker.set", index: clampedIndex});
    dispatch({
      type: "bridge.config",
      provider: choice.provider,
      model: choice.model,
      strategy: stateRef.current.strategy,
    });
    bridge.send("action.run", {
      action_type: "model.set",
      provider: choice.provider,
      model: choice.model,
      strategy: stateRef.current.strategy,
    });
    dispatch({type: "modelPicker.close"});
    dispatch({type: "tab.activate", tabId: stateRef.current.modelPickerReturnTabId || "chat"});
    dispatch({type: "status.set", value: `model route -> ${choice.alias}`});
  }

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      bridge.close();
      exit();
      return;
    }
    if (state.modelPickerVisible) {
      const modelsTab = state.tabs.find((tab) => tab.id === "models");
      const choices = modelChoicesFromTab(modelsTab);
      const maxIndex = Math.max(choices.length - 1, 0);
      if (key.escape) {
        dispatch({type: "modelPicker.close"});
        dispatch({type: "status.set", value: "model picker closed"});
        return;
      }
      if (input === "j" || key.downArrow) {
        dispatch({type: "modelPicker.set", index: Math.min(state.modelPickerIndex + 1, maxIndex)});
        return;
      }
      if (input === "k" || key.upArrow) {
        dispatch({type: "modelPicker.set", index: Math.max(state.modelPickerIndex - 1, 0)});
        return;
      }
      if (key.return) {
        applyModelChoice(state.modelPickerIndex);
        return;
      }
      if (/^[1-9]$/.test(input)) {
        const numericIndex = Number.parseInt(input, 10) - 1;
        if (numericIndex <= maxIndex) {
          applyModelChoice(numericIndex);
        }
        return;
      }
    }
    if (key.ctrl && input === "b") {
      dispatch({type: "sidebar.toggle"});
      return;
    }
    if (key.ctrl && input === "l") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state).refresh);
      return;
    }
    if (key.ctrl && input === "w" && activeTab?.closable) {
      dispatch({type: "tab.close", tabId: activeTab.id});
      return;
    }
    if (key.ctrl && input === "x") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state).primary);
      return;
    }
    if (key.ctrl && input === "f") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state).secondary);
      return;
    }
    if (key.ctrl && input === "v") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state).tertiary);
      return;
    }
    if (key.tab || key.rightArrow) {
      dispatch({type: "tab.cycle", direction: 1});
      return;
    }
    if (key.leftArrow || (key.shift && key.tab)) {
      dispatch({type: "tab.cycle", direction: -1});
      return;
    }
    if (input === "[") {
      dispatch({type: "tab.cycle", direction: -1});
      return;
    }
    if (input === "]") {
      dispatch({type: "tab.cycle", direction: 1});
      return;
    }
    if (key.ctrl && input === "g") {
      dispatch({type: "tab.activate", tabId: "chat"});
      return;
    }
    if (key.ctrl && input === "r") {
      dispatch({type: "tab.activate", tabId: "repo"});
      return;
    }
    if (key.ctrl && input === "o") {
      dispatch({type: "tab.activate", tabId: "ontology"});
      return;
    }
    if (key.ctrl && input === "m") {
      dispatch({type: "tab.activate", tabId: "commands"});
      return;
    }
    if (key.ctrl && input === "a") {
      dispatch({type: "tab.activate", tabId: "agents"});
      return;
    }
    if (key.ctrl && input === "p") {
      dispatch({
        type: "modelPicker.open",
        returnTabId: state.activeTabId === "models" ? "chat" : state.activeTabId,
      });
      bridge.send("model.policy", {
        provider: stateRef.current.provider,
        model: stateRef.current.model,
        strategy: stateRef.current.strategy,
      });
      dispatch({type: "status.set", value: "model picker ready"});
      return;
    }
    if (key.ctrl && input === "e") {
      dispatch({type: "tab.activate", tabId: "evolution"});
      return;
    }
    if (key.ctrl && input === "t") {
      dispatch({type: "tab.activate", tabId: "control"});
      return;
    }
    if (key.ctrl && input === "y") {
      dispatch({type: "tab.activate", tabId: "runtime"});
      return;
    }
    if (input === "1") {
      dispatch({type: "sidebar.mode", mode: "toc"});
      return;
    }
    if (input === "2") {
      dispatch({type: "sidebar.mode", mode: "context"});
      return;
    }
    if (input === "3") {
      dispatch({type: "sidebar.mode", mode: "help"});
      return;
    }
    if (key.return) {
      submitPrompt(state.prompt);
      return;
    }
    if (key.backspace || key.delete) {
      dispatch({type: "prompt.backspace"});
      return;
    }
    if (!key.ctrl && !key.meta && input && !/[\u0000-\u001f\u007f]/.test(input)) {
      dispatch({type: "prompt.append", value: input});
    }
  });

  return (
    <Box flexDirection="column">
      <ShellHeader
        provider={state.provider}
        model={state.model}
        bridgeStatus={state.bridgeStatus}
        activeTitle={activeTab?.title ?? "Workspace"}
      />
      <TabBar tabs={state.tabs} activeTabId={state.activeTabId} />
      <Box marginTop={1}>
        {state.sidebarVisible && !state.modelPickerVisible ? (
          <Sidebar
            mode={state.sidebarMode}
            outline={outline}
            activeTabTitle={activeTab?.title ?? "Workspace"}
            provider={state.provider}
            model={state.model}
            bridgeStatus={state.bridgeStatus}
            tabs={state.tabs}
            repoPreview={decorateSurfacePreview(state.liveRepoPreview, "repo", state.bridgeStatus, state.authoritativeSurfaces)}
            controlPreview={decorateSurfacePreview(state.liveControlPreview, "control", state.bridgeStatus, state.authoritativeSurfaces)}
          />
        ) : null}
        {state.modelPickerVisible ? (
          <ModelPicker
            choices={modelChoices}
            selectedIndex={Math.min(state.modelPickerIndex, Math.max(modelChoices.length - 1, 0))}
          />
        ) : activeTab?.kind === "repo" ? (
          <RepoPane
            title={activeTab.title}
            preview={decorateSurfacePreview(state.liveRepoPreview ?? activeTab.preview, "repo", state.bridgeStatus, state.authoritativeSurfaces)}
            controlPreview={decorateSurfacePreview(state.liveControlPreview ?? state.tabs.find((tab) => tab.id === "control")?.preview, "control", state.bridgeStatus, state.authoritativeSurfaces)}
            controlLines={state.tabs.find((tab) => tab.id === "control")?.lines ?? []}
            lines={activeTab.lines}
          />
        ) : activeTab?.kind === "control" || activeTab?.kind === "runtime" ? (
          <ControlPane
            title={activeTab.title}
            mode={activeTab.kind}
            preview={
              decorateSurfacePreview(
                state.liveControlPreview ??
                  activeTab.preview ??
                  state.tabs.find((tab) => tab.id === "control")?.preview,
                "control",
                state.bridgeStatus,
                state.authoritativeSurfaces,
              )
            }
            lines={
              activeTab.kind === "runtime" && activeTab.lines.length === 0
                ? (state.tabs.find((tab) => tab.id === "control")?.lines ?? [])
                : activeTab.lines
            }
          />
        ) : (
          <TranscriptPane title={activeTab?.title ?? "Workspace"} lines={activeTab?.lines ?? []} />
        )}
      </Box>
      <Composer prompt={state.prompt} />
      <StatusFooter statusLine={state.statusLine} footerHint={footerHintFor(activeTab?.id ?? "chat", state)} />
    </Box>
  );
}

export function createInitialAppState(baseState: AppState): AppState {
  const restored = loadStoredState();
  const restoredTabs = ensureRuntimeTabs(baseState.tabs);
  const bootRepoPreview = loadSupervisorRepoPreview();
  const bootControlPreview = loadSupervisorControlPreview();
  const restoredRepoPreview = mergePreview(restoredTabs.find((tab) => tab.id === "repo")?.preview, bootRepoPreview ?? undefined);
  const restoredControlPreview = mergePreview(restoredTabs.find((tab) => tab.id === "control")?.preview, bootControlPreview ?? undefined);
  const bootRepoLines = restoredRepoPreview ? workspacePreviewToLines(restoredRepoPreview) : undefined;
  const bootControlLines = restoredControlPreview ? runtimePreviewToLines(restoredControlPreview) : undefined;
  const hydratedTabs = restoredTabs.map((tab) => {
    if (tab.id === "repo" && restoredRepoPreview && (!tab.preview || tab.lines.length <= 2)) {
      return {
        ...tab,
        lines: bootRepoLines ?? tab.lines,
        preview: restoredRepoPreview,
      };
    }
    if ((tab.id === "control" || tab.id === "runtime") && restoredControlPreview && (!tab.preview || tab.lines.length <= 3)) {
      return {
        ...tab,
        lines: bootControlLines ?? tab.lines,
        preview: restoredControlPreview,
      };
    }
    return tab;
  });

  return {
    ...baseState,
    sidebarVisible: restored?.sidebarVisible ?? baseState.sidebarVisible,
    sidebarMode: restored?.sidebarMode ?? baseState.sidebarMode,
    activeTabId: baseState.activeTabId,
    tabs: hydratedTabs,
    liveRepoPreview: mergePreview(baseState.liveRepoPreview, restoredRepoPreview),
    liveControlPreview: mergePreview(baseState.liveControlPreview, restoredControlPreview),
    outline: outlineFromTabs(hydratedTabs),
  };
}
