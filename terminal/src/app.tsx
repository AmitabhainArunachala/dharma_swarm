import React, {useEffect, useMemo, useReducer, useRef} from "react";
import {Box, useApp, useInput} from "ink";

import {DharmaBridge, type BridgeEvent} from "./bridge.ts";
import {ActivityPane, activityRowCount} from "./components/ActivityPane.tsx";
import {canonicalEventsFromBridgeEvent, localStatusExecutionEvent, userPromptExecutionEvent} from "./executionLog.ts";
import {
  loadSupervisorRepoPreview,
  loadStoredState,
  normalizeRepoPreview,
  loadSupervisorControlPreview,
  loadSupervisorControlState,
  saveSupervisorRepoPreview,
  saveStoredState,
  saveSupervisorControlSummary,
} from "./persistence.ts";
import {Composer} from "./components/Composer.tsx";
import {ApprovalsPane} from "./components/ApprovalsPane.tsx";
import {AgentsPane} from "./components/AgentsPane.tsx";
import {ControlPane, buildControlPaneSections, buildRuntimePaneSections} from "./components/ControlPane.tsx";
import {ModelPicker} from "./components/ModelPicker.tsx";
import {OperatorSummaryBand} from "./components/OperatorSummaryBand.tsx";
import {PaneSwitcher} from "./components/PaneSwitcher.tsx";
import {RepoPane, buildRepoPaneSections} from "./components/RepoPane.tsx";
import {ScenicStrip} from "./components/ScenicStrip.tsx";
import {SessionsPane} from "./components/SessionsPane.tsx";
import {ShellHeader} from "./components/ShellHeader.tsx";
import {Sidebar} from "./components/Sidebar.tsx";
import {StatusFooter} from "./components/StatusFooter.tsx";
import {TabBar} from "./components/TabBar.tsx";
import {TranscriptPane} from "./components/TranscriptPane.tsx";
import {parseControlPulsePreview, parseRuntimeFreshness} from "./freshness.ts";
import {routeLabel, routePolicyFromValue, routeSummary, selectableRouteTargets} from "./routePolicy.ts";
import {focusModeFor, footerHintFor, paneActionsFor, type PaneAction} from "./shellControls.ts";
import {
  buildVerificationSummaryRows,
  isGenericVerificationLabel,
  parseVerificationBundle,
  resolveVerificationEntries,
} from "./verification.ts";
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
  resolveEventActionType,
  resolveEventCommand,
  resolveEventOutput,
  routingDecisionPayloadFromEvent,
  outlineFromTabs,
  runtimePreviewToLines,
  runtimePayloadHasAuthoritativeControlSignal,
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
} from "./protocol.ts";
import {initialState, reduceApp} from "./state.ts";
import type {AppAction, AppState, ApprovalQueueEntry, ApprovalQueueState, CanonicalPermissionDecision, CanonicalPermissionOutcome, CanonicalPermissionResolution, RouteTarget, RuntimeSnapshotPayload, SessionCatalogPayload, SessionDetailPayload, SessionPaneState, SurfaceAuthorityState, TabPreview, TabSpec, TranscriptLine, WorkspaceSnapshotPayload} from "./types.ts";

const SNAPSHOT_REFRESH_INTERVAL_MS = 15000;
const SESSION_CATALOG_LIMIT = 12;
const SESSION_TRANSCRIPT_LIMIT = 40;
const MIN_SCROLL_WINDOW_SIZE = 8;

type ModelChoice = RouteTarget;

type PendingCommandStream = {
  command: string;
  tabId: string;
  lastCompletedText?: string;
};

const shellControlOptions = {
  sessionCatalogLimit: SESSION_CATALOG_LIMIT,
  approvalResolveAction,
};

function bridgeRouteState(state: AppState): {provider: string; model: string; strategy: string} {
  return {
    provider: state.routePolicy.provider,
    model: state.routePolicy.model,
    strategy: state.routePolicy.strategy,
  };
}

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

function queueAppActions(dispatch: React.Dispatch<AppAction>, actions: AppAction[]): void {
  if (actions.length === 0) {
    return;
  }
  if (actions.length === 1) {
    dispatch(actions[0]);
    return;
  }
  dispatch({type: "batch", actions});
}

function markPendingCommandStream(
  pendingCommandStream: React.MutableRefObject<PendingCommandStream | null> | undefined,
  event: Record<string, unknown>,
): void {
  if (!pendingCommandStream) {
    return;
  }
  const command = resolveEventCommand(event);
  if (!command) {
    return;
  }
  pendingCommandStream.current = {
    command,
    tabId: resolveCommandTargetPane(event, commandTargetTab(command)),
    lastCompletedText: undefined,
  };
}

function clearPendingCommandStream(
  pendingCommandStream: React.MutableRefObject<PendingCommandStream | null> | undefined,
): void {
  if (pendingCommandStream) {
    pendingCommandStream.current = null;
  }
}

function reconcilePendingCommandStream(
  pendingCommand: PendingCommandStream | null,
  event: Record<string, unknown>,
): PendingCommandStream | null {
  if (!pendingCommand) {
    return null;
  }

  const command = resolveEventCommand(event) || pendingCommand.command;
  const tabId = resolveSlashCommandResultTabId(event, command, pendingCommand.tabId);
  if (command === pendingCommand.command && tabId === pendingCommand.tabId) {
    return pendingCommand;
  }

  return {
    ...pendingCommand,
    command,
    tabId,
  };
}

function normalizeCommandStreamText(content: unknown): string {
  return typeof content === "string" ? content.trim() : "";
}

function shouldSuppressPendingCommandStreamOutput(pendingCommand: PendingCommandStream | null): boolean {
  if (!pendingCommand) {
    return false;
  }
  return pendingCommand.tabId === "chat";
}

function shouldSuppressDuplicatePendingCommandPatch(
  event: Record<string, unknown>,
  pendingCommand: PendingCommandStream | null,
): boolean {
  if (!pendingCommand?.lastCompletedText) {
    return false;
  }
  const eventType = String(event.type ?? "");
  const isSlashCommandResult =
    eventType === "command.result" || (eventType === "action.result" && resolveEventActionType(event) === "command.run");
  if (!isSlashCommandResult) {
    return false;
  }
  if (normalizeCommandStreamText(resolveEventOutput(event)) !== pendingCommand.lastCompletedText) {
    return false;
  }
  return resolveCommandTargetPane(event, "control") === pendingCommand.tabId;
}

function snapshotActionsForPendingCommandStream(
  pendingCommand: PendingCommandStream | null,
  output: string,
  liveRepoPreview?: TabPreview,
  liveControlPreview?: TabPreview,
  supervisor = loadSupervisorControlState(),
): AppAction[] {
  if (!pendingCommand || !output) {
    return [];
  }

  return commandRunSnapshotActionsForBridgeEvent(
    {
      type: "command.result",
      command: pendingCommand.command,
      target_pane: pendingCommand.tabId,
      output,
    },
    liveRepoPreview,
    liveControlPreview,
    supervisor,
  );
}

export function commandRunEventFromPaneAction(
  action: {summary: string; payload: Record<string, unknown>} | undefined,
): Record<string, unknown> | undefined {
  if (!action || String(action.payload.action_type ?? "") !== "command.run") {
    return undefined;
  }

  return {
    ...action.payload,
    summary: action.summary,
  };
}

function transcriptMetaForTab(tab: TabSpec | undefined): {subtitle: string; emptyState: string; accentColor: string} {
  switch (tab?.kind) {
    case "chat":
      return {
        subtitle: "Live operator exchange, assistant output, and command spillover that still belongs in chat.",
        emptyState: "No operator exchange yet.",
        accentColor: "cyan",
      };
    case "mission":
      return {
        subtitle: "Bootstrap framing, intent routing, and session launch context.",
        emptyState: "Mission bootstrap is waiting on the next session start.",
        accentColor: "magenta",
      };
    case "ontology":
      return {
        subtitle: "Shared world model, foundations, and semantic frame updates.",
        emptyState: "Ontology surface has not been refreshed yet.",
        accentColor: "green",
      };
    case "commands":
      return {
        subtitle: "Registered command graph and operational affordances.",
        emptyState: "Command registry is waiting on refresh.",
        accentColor: "yellow",
      };
    case "evolution":
      return {
        subtitle: "Forward-loop, swarm evolution, and shell continuation surface.",
        emptyState: "Evolution surface has not been materialized yet.",
        accentColor: "blue",
      };
    default:
      return {
        subtitle: "Structured operator transcript.",
        emptyState: "No content yet.",
        accentColor: "gray",
      };
  }
}

function previewField(preview: TabPreview | undefined, label: string): string {
  const value = preview?.[label];
  return typeof value === "string" ? value.trim() : "";
}

function hasPreviewSignal(value: string): boolean {
  return value.length > 0 && value !== "unknown" && value !== "none" && value !== "n/a";
}

const DEFERRED_CONTROL_PREVIEW_FIELDS = [
  "Loop state",
  "Task progress",
  "Active task",
  "Result status",
  "Acceptance",
  "Last result",
  "Loop decision",
  "Next task",
  "Updated",
  "Durable state",
  "Verification summary",
  "Verification bundle",
  "Verification checks",
  "Verification status",
  "Verification passing",
  "Verification failing",
  "Verification updated",
  "Control pulse preview",
  "Control truth preview",
  "Runtime freshness",
] as const;

const DEFERRED_REPO_TOPOLOGY_PREVIEW_FIELDS = [
  "Topology status",
  "Topology peer count",
  "Topology warnings",
  "Topology warning members",
  "Topology warning severity",
  "Topology risk",
  "Risk preview",
  "Topology preview",
  "Topology pressure preview",
  "Primary warning",
  "Primary peer drift",
  "Branch divergence",
  "Detached peers",
  "Primary topology peer",
  "Peer drift markers",
  "Topology peers",
  "Topology pressure",
] as const;

const DEFERRED_REPO_HOTSPOT_PREVIEW_FIELDS = [
  "Hotspot summary",
  "Lead hotspot preview",
  "Hotspot pressure preview",
  "Primary file hotspot",
  "Primary dependency hotspot",
  "Hotspots",
  "Inbound hotspots",
] as const;

function preserveDeferredControlPreview(nextPreview: TabPreview, livePreview?: TabPreview): TabPreview {
  if (!livePreview) {
    return nextPreview;
  }
  const mergedPreview: TabPreview = {...nextPreview};
  for (const field of DEFERRED_CONTROL_PREVIEW_FIELDS) {
    const liveValue = previewField(livePreview, field);
    if (hasPreviewSignal(liveValue)) {
      mergedPreview[field] = liveValue;
    }
  }
  return mergedPreview;
}

function previewSignalPresent(value: string): boolean {
  return value.length > 0 && value !== "unknown" && value !== "none" && value !== "n/a";
}

function preservePreviewFields(
  nextPreview: TabPreview,
  livePreview: TabPreview | undefined,
  fields: readonly string[],
): TabPreview {
  if (!livePreview) {
    return nextPreview;
  }
  const mergedPreview: TabPreview = {...nextPreview};
  for (const field of fields) {
    const liveValue = previewField(livePreview, field);
    if (!previewSignalPresent(liveValue)) {
      continue;
    }
    mergedPreview[field] = liveValue;
  }
  return mergedPreview;
}

function rawWorkspacePayloadRecord(event: Record<string, unknown>): Record<string, unknown> | undefined {
  const directRecord =
    typeof event.domain === "string" && event.domain === "workspace_snapshot" ? event : undefined;
  if (directRecord) {
    return directRecord;
  }
  const payload = event.payload;
  if (typeof payload !== "object" || payload === null) {
    return undefined;
  }
  return typeof (payload as {domain?: unknown}).domain === "string" &&
    String((payload as {domain?: unknown}).domain) === "workspace_snapshot"
    ? (payload as Record<string, unknown>)
    : undefined;
}

function workspaceEventHasAuthoritativeTopology(event: Record<string, unknown>): boolean {
  const rawPayload = rawWorkspacePayloadRecord(event);
  if (rawPayload) {
    return Object.hasOwn(rawPayload, "topology");
  }
  const content = String(event.content ?? "");
  return /^##\s+Topology\b/m.test(content);
}

function workspaceEventHasAuthoritativeHotspotDetail(event: Record<string, unknown>): boolean {
  const rawPayload = rawWorkspacePayloadRecord(event);
  if (rawPayload) {
    return Object.hasOwn(rawPayload, "largest_python_files") || Object.hasOwn(rawPayload, "most_imported_modules");
  }
  const content = String(event.content ?? "");
  const hasHotspotSummary = /^Git hotspots:\s*(?!none\b).+/im.test(content);
  const hasChangedPathDetail = /^Git changed paths:\s*(?!none\b).+/im.test(content);
  const hasHotspotDetailSection =
    /^##\s+(?:Largest Python files|Most imported local modules)\b/im.test(content) ||
    /^(?:Primary file hotspot|Dependency hotspots|Inbound hotspots):\s*(?!none\b).+/im.test(content);
  return hasHotspotSummary && hasChangedPathDetail && hasHotspotDetailSection;
}

function workspaceEventHasAuthoritativeRepoSignal(event: Record<string, unknown>): boolean {
  return workspaceEventHasAuthoritativeTopology(event) && workspaceEventHasAuthoritativeHotspotDetail(event);
}

function preserveDeferredRepoPreview(nextPreview: TabPreview, livePreview: TabPreview | undefined, event: Record<string, unknown>): TabPreview {
  let mergedPreview = nextPreview;
  if (!workspaceEventHasAuthoritativeTopology(event)) {
    mergedPreview = preservePreviewFields(mergedPreview, livePreview, DEFERRED_REPO_TOPOLOGY_PREVIEW_FIELDS);
  }
  if (!workspaceEventHasAuthoritativeHotspotDetail(event)) {
    mergedPreview = preservePreviewFields(mergedPreview, livePreview, DEFERRED_REPO_HOTSPOT_PREVIEW_FIELDS);
  }
  return mergedPreview;
}

function derivedOperatorRuntimeFreshness(preview: TabPreview | undefined): string {
  const explicit = previewField(preview, "Runtime freshness");
  if (hasPreviewSignal(explicit)) {
    return explicit;
  }
  return parseControlPulsePreview(previewField(preview, "Control pulse preview")).runtimeFreshness ?? "";
}

function normalizeOperatorLoopLabel(loopState: string): string {
  return loopState.replace(/\brunning_cycle\b/gi, "running").replace(/\s+/g, " ").trim();
}

function operatorLoopSummary(preview: TabPreview | undefined): {value: string; tone: "live" | "warn" | "critical" | "neutral"} {
  const explicitLoopState = previewField(preview, "Loop state");
  const loopState = hasPreviewSignal(explicitLoopState)
    ? explicitLoopState
    : parseRuntimeFreshness(derivedOperatorRuntimeFreshness(preview)).loopState || "";
  if (!hasPreviewSignal(loopState)) {
    return {value: "unknown", tone: "neutral"};
  }
  const normalizedLabel = normalizeOperatorLoopLabel(loopState);
  const normalized = normalizedLabel.toLowerCase();
  if (/(fail|error|blocked|stalled)/.test(normalized)) {
    return {value: normalizedLabel, tone: "critical"};
  }
  if (/(wait|pending|verify|review)/.test(normalized)) {
    return {value: normalizedLabel, tone: "warn"};
  }
  return {value: normalizedLabel, tone: "live"};
}

function operatorVerificationSummary(preview: TabPreview | undefined): {value: string; tone: "live" | "warn" | "critical" | "neutral"} {
  const checks = previewField(preview, "Verification checks");
  const summary = previewField(preview, "Verification summary");
  const bundle = resolveVerificationEntries({
    checksText: checks,
    summaryText: summary,
    bundleText: previewField(preview, "Verification bundle"),
    passingText: previewField(preview, "Verification passing"),
    failingText: previewField(preview, "Verification failing"),
  });
  if (bundle.length > 0) {
    const rows = buildVerificationSummaryRows(bundle);
    return {
      value: rows.status,
      tone: rows.failing === "none" ? "live" : "critical",
    };
  }

  const compactBundle = parseRuntimeFreshness(derivedOperatorRuntimeFreshness(preview)).verificationBundle ?? "";
  const parsedCompactBundle = parseVerificationBundle("none", compactBundle);
  if (parsedCompactBundle.length > 0) {
    const rows = buildVerificationSummaryRows(parsedCompactBundle);
    return {
      value: rows.status,
      tone: rows.failing === "none" ? "live" : "critical",
    };
  }

  const status = previewField(preview, "Verification status");
  if (hasPreviewSignal(status)) {
    if (!isGenericVerificationLabel(status)) {
      return {value: status, tone: "warn"};
    }
    const normalized = status.toLowerCase();
    return {
      value: status,
      tone: /(fail|error)/.test(normalized) ? "critical" : /(ok|pass)/.test(normalized) ? "live" : "warn",
    };
  }
  if (hasPreviewSignal(summary) && isGenericVerificationLabel(summary)) {
    const normalized = summary.toLowerCase();
    return {
      value: summary,
      tone: /(fail|error)/.test(normalized) ? "critical" : /(ok|pass)/.test(normalized) ? "live" : "warn",
    };
  }
  return {value: "unknown", tone: "neutral"};
}

function parseRuntimeActivityMetrics(value: string): Record<string, string> {
  if (!hasPreviewSignal(value)) {
    return {};
  }
  return Object.fromEntries(
    Array.from(value.matchAll(/([A-Za-z][A-Za-z0-9]*)=([^\s]+)/g), (match) => [match[1], match[2]]),
  );
}

function operatorRuntimeSummary(
  preview: TabPreview | undefined,
  fallbackSessionCount: number,
): {value: string; tone: "live" | "warn" | "critical" | "neutral"} {
  const runtimeSummary = previewField(preview, "Runtime summary");
  if (hasPreviewSignal(runtimeSummary)) {
    return {value: runtimeSummary, tone: "live"};
  }

  const metrics = parseRuntimeActivityMetrics(previewField(preview, "Runtime activity"));
  const fragments = [
    metrics.Sessions ? `${metrics.Sessions} sessions` : "",
    metrics.Runs ? `${metrics.Runs} runs` : "",
    metrics.ActiveRuns && metrics.ActiveRuns !== "0" ? `${metrics.ActiveRuns} active` : "",
  ].filter((value) => value.length > 0);
  if (fragments.length > 0) {
    return {value: fragments.join(" | "), tone: "live"};
  }

  if (fallbackSessionCount > 0) {
    return {value: `${fallbackSessionCount} sessions`, tone: "live"};
  }

  return {value: "idle", tone: "neutral"};
}

function mergeOperatorSummaryPreviewSources(...previews: Array<TabPreview | undefined>): TabPreview | undefined {
  const merged: TabPreview = {};
  for (const preview of previews) {
    if (!preview) {
      continue;
    }
    for (const [key, rawValue] of Object.entries(preview)) {
      const candidate = rawValue.trim();
      if (!candidate) {
        continue;
      }
      const existing = previewField(merged, key);
      if (!existing || !hasPreviewSignal(existing) || hasPreviewSignal(candidate)) {
        merged[key] = candidate;
      }
    }
  }
  return Object.keys(merged).length > 0 ? merged : undefined;
}

function operatorSummaryPreview(state: AppState): TabPreview | undefined {
  const controlTabPreview = state.tabs.find((tab) => tab.id === "control")?.preview;
  const runtimeTabPreview = state.tabs.find((tab) => tab.id === "runtime")?.preview;
  const repoPreview = mergeOperatorSummaryPreviewSources(
    state.tabs.find((tab) => tab.id === "repo")?.preview,
    state.liveRepoPreview,
  );
  return controlPanePreview(
    mergeOperatorSummaryPreviewSources(controlTabPreview, runtimeTabPreview, state.liveControlPreview),
    repoPreview,
  );
}

export function buildOperatorSummaryItems(state: AppState): Array<{label: string; value: string; tone?: "live" | "warn" | "critical" | "neutral"}> {
  const pendingApprovals = state.approvalPane.order.filter((actionId) => state.approvalPane.entriesByActionId[actionId]?.pending).length;
  const sessionCount = state.sessionPane.catalog?.count ?? state.sessionPane.catalog?.sessions.length ?? 0;
  const route = routeLabel(state.routePolicy);
  const preview = operatorSummaryPreview(state);
  const loop = operatorLoopSummary(preview);
  const verification = operatorVerificationSummary(preview);
  const runtime = operatorRuntimeSummary(preview, sessionCount);
  const approvalsTone = pendingApprovals > 0 ? "warn" : "live";
  const bridgeTone =
    state.bridgeStatus === "connected" ? "live" : state.bridgeStatus === "degraded" ? "warn" : "critical";
  return [
    {label: "bridge", value: state.bridgeStatus, tone: bridgeTone},
    {label: "route", value: `${route} (${state.routePolicy.routeState})`, tone: "neutral"},
    {label: "strategy", value: state.routePolicy.strategy, tone: "neutral"},
    {label: "loop", value: loop.value, tone: loop.tone},
    {label: "verify", value: verification.value, tone: verification.tone},
    {label: "runtime", value: runtime.value, tone: runtime.tone},
    {label: "approvals", value: pendingApprovals === 0 ? "clear" : `${pendingApprovals} pending`, tone: approvalsTone},
    {label: "sessions", value: `${sessionCount}`, tone: sessionCount > 0 ? "live" : "neutral"},
  ];
}

type ConversationMessage = {
  role: "user" | "assistant";
  content: string;
};

const MAX_CONVERSATION_MESSAGES = 24;

function normalizeConversationLine(line: TranscriptLine): ConversationMessage | undefined {
  if (line.kind === "user") {
    const content = line.text.replace(/^>\s*/, "").trim();
    return content ? {role: "user", content} : undefined;
  }
  if (line.kind === "assistant") {
    const content = line.text.trim();
    return content ? {role: "assistant", content} : undefined;
  }
  return undefined;
}

function buildConversationMessages(chatLines: TranscriptLine[], submittedPrompt: string): ConversationMessage[] {
  const firstUserIndex = chatLines.findIndex((line) => line.kind === "user");
  const relevantLines = firstUserIndex >= 0 ? chatLines.slice(firstUserIndex) : [];
  const collapsed: ConversationMessage[] = [];

  for (const line of relevantLines) {
    const normalized = normalizeConversationLine(line);
    if (!normalized) {
      continue;
    }
    const previous = collapsed[collapsed.length - 1];
    if (previous && previous.role === normalized.role) {
      previous.content = `${previous.content}\n${normalized.content}`.trim();
    } else {
      collapsed.push({...normalized});
    }
  }

  const prompt = submittedPrompt.trim();
  if (prompt) {
    const previous = collapsed[collapsed.length - 1];
    if (previous?.role === "user" && previous.content === prompt) {
      return collapsed.slice(-MAX_CONVERSATION_MESSAGES);
    }
    collapsed.push({role: "user", content: prompt});
  }

  return collapsed.slice(-MAX_CONVERSATION_MESSAGES);
}

function isDuplicateCompletedAssistantPatch(state: AppState, event: Record<string, unknown>): boolean {
  if (String(event.type ?? "") !== "text_complete") {
    return false;
  }
  const content = String(event.content ?? "").trim();
  if (!content) {
    return false;
  }
  const chatLines = state.tabs.find((tab) => tab.id === "chat")?.lines ?? [];
  for (let index = chatLines.length - 1; index >= 0; index -= 1) {
    const line = chatLines[index];
    if (!line) {
      continue;
    }
    if (line.kind !== "assistant") {
      continue;
    }
    return line.text.trim() === content;
  }
  return false;
}

function boundedContinuityMessages(state: AppState, submittedPrompt: string): Array<{role: "user" | "assistant" | "system"; content: string}> {
  const selectedSessionId = state.sessionPane.selectedSessionId;
  const selectedDetail = selectedSessionId ? state.sessionPane.detailsBySessionId[selectedSessionId] : undefined;

  if (selectedDetail) {
    const history: Array<{role: "user" | "assistant" | "system"; content: string}> = [];
    for (const envelope of selectedDetail.recent_events) {
      const payload = envelope.payload ?? {};
      if (envelope.event_type === "text_complete" || envelope.event_type === "text_delta") {
        const content = String(payload.content ?? "").trim();
        if (content) {
          history.push({role: "assistant", content});
        }
        continue;
      }
      if (envelope.event_type === "session_start") {
        const content = String(payload.prompt ?? "").trim();
        if (content) {
          history.push({role: "user", content});
        }
      }
    }
    const prompt = submittedPrompt.trim();
    if (prompt) {
      history.push({role: "user", content: prompt});
    }
    return history.slice(-MAX_CONVERSATION_MESSAGES);
  }

  const chatLines = state.tabs.find((tab) => tab.id === "chat")?.lines ?? [];
  return buildConversationMessages(chatLines, submittedPrompt);
}

function providerResumeSessionId(detail: SessionDetailPayload | undefined): string | undefined {
  const metadata = detail?.session.metadata;
  if (!metadata || typeof metadata !== "object") {
    return undefined;
  }
  const value = (metadata as Record<string, unknown>).provider_session_id;
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

function displayedTranscriptLinesForTab(activeTab: TabSpec | undefined, state: AppState): TranscriptLine[] {
  if (activeTab?.kind !== "chat") {
    return activeTab?.lines ?? [];
  }
  const firstUserIndex = activeTab.lines.findIndex((line) => line.kind === "user");
  const chatPreludeLines = firstUserIndex >= 0 ? activeTab.lines.slice(0, firstUserIndex) : activeTab.lines;
  return [...chatPreludeLines, ...state.chatTraceLines];
}

export function continuityStateFromSession(state: AppState, detail: SessionDetailPayload | undefined): AppState["sessionContinuity"] {
  if (!detail) {
    return {
      ...state.sessionContinuity,
      activeSessionId: undefined,
      resumeSessionId: undefined,
      activeRouteId: state.routePolicy.routeId,
      continuityMode: "fresh",
      boundedHistory: [],
      compactionPolicy: {
        eventCount: 0,
        compactableRatio: 0,
        protectedEventTypes: [],
        recentEventTypes: [],
      },
      compactedSummary: undefined,
    };
  }

  const boundedHistory = boundedContinuityMessages(state, "").slice(-state.sessionContinuity.historyLimit).map((entry) => ({
    ...entry,
    source: "session_detail" as const,
  }));
  const resumableProviderSessionId = providerResumeSessionId(detail);
  const sameProviderAsActiveRoute = detail.session.provider_id === state.routePolicy.provider;
  const canResumeProviderSession = detail.replay_ok && sameProviderAsActiveRoute && Boolean(resumableProviderSessionId);

  return {
    ...state.sessionContinuity,
    activeSessionId: detail.session.session_id,
    resumeSessionId: canResumeProviderSession ? resumableProviderSessionId : undefined,
    activeRouteId: `${detail.session.provider_id}:${detail.session.model_id}`,
    continuityMode: canResumeProviderSession ? "resume" : "fresh",
    boundedHistory,
    compactionPolicy: {
      eventCount: detail.compaction_preview.event_count,
      compactableRatio: detail.compaction_preview.compactable_ratio,
      protectedEventTypes: detail.compaction_preview.protected_event_types,
      recentEventTypes: detail.compaction_preview.recent_event_types,
    },
    compactedSummary: detail.session.summary ?? undefined,
  };
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
  pendingBootstraps: React.MutableRefObject<Record<string, {prompt: string; provider: string; model: string; messages: Array<{role: "user" | "assistant" | "system"; content: string}>; resumeSessionId?: string}>>;
  pendingCommandStream?: React.MutableRefObject<PendingCommandStream | null>;
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

function scrollMaxOffsetForTab(activeTab: TabSpec | undefined, state: AppState, windowSize: number): number {
  if (!activeTab) {
    return 0;
  }
  if (activeTab.kind === "chat") {
    return Math.max(displayedTranscriptLinesForTab(activeTab, state).length - windowSize, 0);
  }
  if (activeTab.kind === "thinking" || activeTab.kind === "tools" || activeTab.kind === "timeline") {
    return Math.max(activityRowCount(activeTab.kind, state.activityFeed) - windowSize, 0);
  }
  if (activeTab.kind === "repo") {
    const sections = buildRepoPaneSections(
      state.liveRepoPreview ?? activeTab.preview,
      activeTab.lines,
      state.liveControlPreview ?? state.tabs.find((tab) => tab.id === "control")?.preview,
      state.tabs.find((tab) => tab.id === "control")?.lines ?? [],
    );
    const selected = sections[state.paneFocusIndices[activeTab.id] ?? 0];
    return Math.max((selected?.rows.length ?? 0) - Math.max(windowSize - 4, MIN_SCROLL_WINDOW_SIZE), 0);
  }
  if (activeTab.kind === "control") {
    const preview = state.liveControlPreview ?? activeTab.preview ?? state.tabs.find((tab) => tab.id === "control")?.preview;
    const sections = buildControlPaneSections(preview, activeTab.lines);
    const selected = sections[state.paneFocusIndices[activeTab.id] ?? 0];
    return Math.max((selected?.rows.length ?? 0) - Math.max(windowSize - 4, MIN_SCROLL_WINDOW_SIZE), 0);
  }
  if (activeTab.kind === "runtime") {
    const runtimeLines =
      activeTab.lines.length === 0 ? (state.tabs.find((tab) => tab.id === "control")?.lines ?? []) : activeTab.lines;
    const preview = state.liveControlPreview ?? activeTab.preview ?? state.tabs.find((tab) => tab.id === "control")?.preview;
    const sections = buildRuntimePaneSections(preview, runtimeLines);
    const selected = sections[state.paneFocusIndices[activeTab.id] ?? 0];
    return Math.max((selected?.rows.length ?? 0) - Math.max(windowSize - 4, MIN_SCROLL_WINDOW_SIZE), 0);
  }
  return Math.max((activeTab.lines.length || 0) - windowSize, 0);
}

function isBareModelCommand(prompt: string): boolean {
  const trimmed = prompt.trim();
  return trimmed === "/model" || trimmed === "/models" || trimmed === "/model list";
}

function stepApprovalSelection(state: AppState, direction: 1 | -1): string | undefined {
  const order = state.approvalPane.order;
  if (order.length === 0) {
    return undefined;
  }
  const currentIndex = state.approvalPane.selectedActionId ? order.indexOf(state.approvalPane.selectedActionId) : -1;
  const nextIndex = currentIndex === -1 ? 0 : Math.min(Math.max(currentIndex + direction, 0), order.length - 1);
  return order[nextIndex];
}

function stepSessionSelection(state: AppState, direction: 1 | -1): string | undefined {
  const sessions = state.sessionPane.catalog?.sessions ?? [];
  if (sessions.length === 0) {
    return undefined;
  }
  const currentIndex = state.sessionPane.selectedSessionId
    ? sessions.findIndex((entry) => entry.session.session_id === state.sessionPane.selectedSessionId)
    : -1;
  const nextIndex = currentIndex === -1 ? 0 : Math.min(Math.max(currentIndex + direction, 0), sessions.length - 1);
  return sessions[nextIndex]?.session.session_id;
}

function stepPaneSectionFocus(
  currentIndex: number | undefined,
  sectionCount: number,
  direction: 1 | -1,
): number | undefined {
  if (sectionCount <= 0) {
    return undefined;
  }
  const baseIndex = currentIndex ?? 0;
  return Math.min(Math.max(baseIndex + direction, 0), sectionCount - 1);
}

function agentRouteCount(lines: TranscriptLine[]): number {
  return lines.filter((line) => /^\s*-\s+.+? -> .+?:.+? \| effort .+ \| role .+$/.test(line.text)).length;
}

function paneSectionCount(activeTab: TabSpec | undefined, state: AppState): number {
  if (!activeTab) {
    return 0;
  }
  if (activeTab.kind === "repo") {
    return buildRepoPaneSections(
      state.liveRepoPreview ?? activeTab.preview,
      activeTab.lines,
      state.liveControlPreview ?? state.tabs.find((tab) => tab.id === "control")?.preview,
      state.tabs.find((tab) => tab.id === "control")?.lines ?? [],
    ).length;
  }
  if (activeTab.kind === "control") {
    const preview = state.liveControlPreview ?? activeTab.preview ?? state.tabs.find((tab) => tab.id === "control")?.preview;
    return buildControlPaneSections(preview, activeTab.lines).length;
  }
  if (activeTab.kind === "runtime") {
    const runtimeLines =
      activeTab.lines.length === 0 ? (state.tabs.find((tab) => tab.id === "control")?.lines ?? []) : activeTab.lines;
    const preview = state.liveControlPreview ?? activeTab.preview ?? state.tabs.find((tab) => tab.id === "control")?.preview;
    return buildRuntimePaneSections(preview, runtimeLines).length;
  }
  return 0;
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

export function controlPanePreview(
  controlPreview: TabPreview | undefined,
  repoPreview: TabPreview | undefined,
): TabPreview | undefined {
  if (!controlPreview && !repoPreview) {
    return undefined;
  }
  const repoControlPreview = repoPreview?.["Repo/control preview"];
  if (typeof repoControlPreview !== "string" || repoControlPreview.length === 0) {
    return controlPreview;
  }
  return {
    ...(controlPreview ?? {}),
    ...(typeof controlPreview?.["Repo/control preview"] === "string" && controlPreview["Repo/control preview"].length > 0
      ? {}
      : {"Repo/control preview": repoControlPreview}),
  };
}

function synchronizeRepoControlPreviews(
  repoPreview: TabPreview | undefined,
  controlPreview: TabPreview | undefined,
  now: Date = new Date(),
) {
  return normalizeRepoPreview(repoPreview, controlPreview, now);
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
  const isCommandRunAction = eventType === "action.result" && resolveEventActionType(typed) === "command.run";
  if (eventType !== "command.result" && !isCommandRunAction) {
    return [];
  }

  const targetPane = resolveCommandTargetPane(typed, "control");
  const workspacePayload = workspaceSnapshotPayloadFromEvent(typed);
  const runtimePayload = runtimeSnapshotPayloadFromEvent(typed);
  if (targetPane === "repo") {
    if (workspacePayload) {
      const preview = workspacePayloadToPreview(workspacePayload);
      const synchronizedPreview = synchronizeRepoControlPreviews(preview, liveControlPreview);
      return [
        {
          type: "tab.replace",
          tabId: "repo",
          lines: workspacePreviewToLines(synchronizedPreview ?? preview),
          preview: synchronizedPreview ?? preview,
        },
        {type: "live.repo.set", preview: synchronizedPreview ?? preview},
      ];
    }

    const output = resolveEventOutput(typed);
    if (!isWorkspaceSnapshotContent(output)) {
      return [];
    }

    const preview = workspaceSnapshotToPreview(output);
    const synchronizedPreview = synchronizeRepoControlPreviews(preview, liveControlPreview);
    return [
      {
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(synchronizedPreview ?? preview),
        preview: synchronizedPreview ?? preview,
      },
      {type: "live.repo.set", preview: synchronizedPreview ?? preview},
    ];
  }

  if (targetPane === "control" || targetPane === "runtime") {
    if (runtimePayload) {
      const preview = runtimePayloadToPreview(runtimePayload, supervisor);
      const synchronizedRepoPreview = synchronizeRepoControlPreviews(liveRepoPreview, preview);
      return [
        {
          type: "tab.replace",
          tabId: "control",
          lines: runtimePreviewToLines(preview),
          preview,
        },
        {
          type: "tab.replace",
          tabId: "runtime",
          lines: runtimePreviewToLines(preview),
          preview,
        },
        {type: "live.control.set", preview},
        ...(synchronizedRepoPreview ? [{type: "live.repo.set", preview: synchronizedRepoPreview} as const] : []),
      ];
    }

    const output = resolveEventOutput(typed);
    if (!isStructuredControlSnapshotContent(output)) {
      return [];
    }

    const preview = runtimeSnapshotToPreview(output, supervisor);
    const synchronizedRepoPreview = synchronizeRepoControlPreviews(liveRepoPreview, preview);
    return [
      {
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(preview),
        preview,
      },
      {
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(preview),
        preview,
      },
      {type: "live.control.set", preview},
      ...(synchronizedRepoPreview ? [{type: "live.repo.set", preview: synchronizedRepoPreview} as const] : []),
    ];
  }

  return [];
}

export function persistControlPreview(preview?: TabPreview, runtimePayload?: RuntimeSnapshotPayload): void {
  if (!preview) {
    return;
  }
  const supervisor = loadSupervisorControlState();
  if (supervisor) {
    saveSupervisorControlSummary(supervisor, preview, {runtimePayload});
  }
}

export function persistRepoPreview(preview?: TabPreview, workspacePayload?: WorkspaceSnapshotPayload): void {
  if (!preview) {
    return;
  }
  const supervisor = loadSupervisorControlState();
  if (supervisor) {
    saveSupervisorRepoPreview(supervisor, preview, {workspacePayload});
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
    const effectivePreview = preserveDeferredRepoPreview(preview, liveRepoPreview, typed);
    const synchronizedPreview = synchronizeRepoControlPreviews(effectivePreview, liveControlPreview);
    return [
      {
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(synchronizedPreview ?? effectivePreview),
        preview: synchronizedPreview ?? effectivePreview,
      },
      {type: "live.repo.set", preview: synchronizedPreview ?? effectivePreview},
    ];
  }

  if (eventType === "session.bootstrap.result") {
    const actions: AppAction[] = [];
    const workspacePayload = workspaceSnapshotPayloadFromEvent(typed);
    const runtimePayload = runtimeSnapshotPayloadFromEvent(typed);
    const rawWorkspacePreview = workspacePayload
      ? workspacePayloadToPreview(workspacePayload)
      : asPreviewRecord(typed.workspace_preview) ?? liveRepoPreview;
    const runtimePreview = runtimePayload
      ? runtimePayloadToPreview(runtimePayload)
      : asPreviewRecord(typed.runtime_preview) ?? liveControlPreview;
    const workspacePreview = synchronizeRepoControlPreviews(
      rawWorkspacePreview,
      runtimePreview,
    );

    if (workspacePreview) {
      actions.push({
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(workspacePreview),
        preview: workspacePreview,
      });
      actions.push({
        type: "live.repo.set",
        preview: workspacePreview,
      });
    }

    if (runtimePreview) {
      actions.push({
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(runtimePreview),
        preview: runtimePreview,
      });
      actions.push({
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(runtimePreview),
        preview: runtimePreview,
      });
      actions.push({
        type: "live.control.set",
        preview: runtimePreview,
      });
    }

    return actions;
  }

  return [];
}

export function commandResultActionsForBridgeEvent(
  event: BridgeEvent,
  fallbackCommand?: string,
  fallbackTabId?: string,
): AppAction[] {
  const typed = event as Record<string, unknown>;
  if (String(typed.type ?? "") !== "command.result") {
    return [];
  }

  return slashCommandResultActions(
    typed,
    String(typed.summary ?? "action applied"),
    fallbackCommand,
    fallbackTabId,
  );
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

function commandIntentFromBootstrapIntent(intent: Record<string, unknown>, command: string): Record<string, unknown> {
  const commandIntent: Record<string, unknown> = {command};
  for (const key of [
    "target_surface",
    "targetSurface",
    "target_surface_id",
    "targetSurfaceId",
    "target_pane",
    "targetPane",
    "surface",
    "surface_id",
    "surfaceId",
    "target_pane_id",
    "targetPaneId",
    "target_tab",
    "targetTab",
    "target_tab_id",
    "targetTabId",
    "pane",
    "pane_id",
    "paneId",
    "tab",
    "tab_id",
    "tabId",
  ]) {
    const value = intent[key];
    if (typeof value === "string" && value.trim()) {
      commandIntent[key] = value;
    }
  }
  return commandIntent;
}

export function actionResultActionsForBridgeEvent(
  event: BridgeEvent,
  fallbackCommand?: string,
  fallbackTabId?: string,
): AppAction[] {
  const typed = event as Record<string, unknown>;
  if (String(typed.type ?? "") !== "action.result") {
    return [];
  }

  if (resolveEventActionType(typed) !== "command.run") {
    return [];
  }

  return slashCommandResultActions(
    typed,
    String(typed.summary ?? "action applied"),
    fallbackCommand,
    fallbackTabId,
  );
}

function isOperationalResultTab(tabId: string): boolean {
  return tabId.length > 0 && tabId !== "chat" && tabId !== "commands";
}

function sanitizeSlashCommandFallbackTabId(tabId: string | undefined): string {
  return tabId === "commands" ? "" : tabId ?? "";
}

function resolveSlashCommandResultTabId(
  event: Record<string, unknown>,
  fallbackCommand?: string,
  fallbackTabId?: string,
): string {
  const eventCommand = resolveEventCommand(event);
  const command = eventCommand || fallbackCommand || "";
  const resolvedTabId = resolveCommandTargetPane(event, "");
  const fallbackCommandTabId = fallbackCommand ? commandTargetTab(fallbackCommand) : "";
  const preferredFallbackTabId =
    [fallbackTabId ?? "", fallbackCommandTabId].find((tabId) => isOperationalResultTab(tabId)) ?? fallbackTabId ?? "";
  const sanitizedFallbackTabId = sanitizeSlashCommandFallbackTabId(fallbackTabId);
  if (!eventCommand && isOperationalResultTab(sanitizedFallbackTabId) && resolvedTabId !== sanitizedFallbackTabId) {
    return sanitizedFallbackTabId;
  }
  return (
    isOperationalResultTab(preferredFallbackTabId) && !isOperationalResultTab(resolvedTabId)
      ? preferredFallbackTabId
      : resolvedTabId || sanitizedFallbackTabId || "control"
  );
}

function slashCommandResultActions(
  event: Record<string, unknown>,
  fallbackStatus = String(event.summary ?? "action applied"),
  fallbackCommand?: string,
  fallbackTabId?: string,
): AppAction[] {
  const command = resolveEventCommand(event) || fallbackCommand || "";
  const normalized = normalizeCommandName(command);
  const tabId = resolveSlashCommandResultTabId(event, fallbackCommand, fallbackTabId);
  const statusValue = normalized ? `/${normalized} -> ${tabId}` : fallbackStatus;
  return [
    {type: "tab.activate", tabId},
    {type: "status.set", value: statusValue},
  ];
}

function enrichSparseCommandResultEvent(
  event: Record<string, unknown>,
  pendingCommand: PendingCommandStream | null,
): Record<string, unknown> {
  if (!pendingCommand) {
    return event;
  }

  const eventType = String(event.type ?? "");
  const isCommandResult = eventType === "command.result";
  const isCommandRunAction = eventType === "action.result" && resolveEventActionType(event) === "command.run";
  if (!isCommandResult && !isCommandRunAction) {
    return event;
  }

  const command = resolveEventCommand(event);
  const targetPane = resolveCommandTargetPane(event, "");
  const shouldOverrideTargetPane =
    isOperationalResultTab(pendingCommand.tabId) &&
    (!isOperationalResultTab(targetPane) || (!command && targetPane !== pendingCommand.tabId));
  if (command && targetPane && !shouldOverrideTargetPane) {
    return event;
  }

  return {
    ...event,
    ...(command ? {} : {command: pendingCommand.command}),
    ...((targetPane && !shouldOverrideTargetPane) ? {} : {target_pane: pendingCommand.tabId}),
  };
}

export function createBridgeEventHandler({
  dispatch,
  getState,
  bridge,
  pendingBootstraps,
  pendingCommandStream,
  requestHandshake,
  resetHandshakeBackoff,
}: BridgeHandlerDeps): (event: BridgeEvent) => void {
  let awaitingAuthoritativeResync = true;
  let resyncPending = false;
  let reconnectRequested = false;
  const reconnectingCodes = new Set(["bridge_exit", "bridge_spawn_error", "bridge_send_failed", "bridge_stdin_unavailable"]);
  let malformedBridgeEvents = 0;
  const apply = (actions: AppAction[]): void => queueAppActions(dispatch, actions);

  function requestReconnect(status: string, offline = false): void {
    awaitingAuthoritativeResync = true;
    resyncPending = false;
    apply([
      {type: "surface.truth.reset"},
      {type: "bridge.status", status: offline ? "offline" : "degraded"},
      {type: "status.set", value: status},
    ]);
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
    const state = getState();
    const originalPendingCommand = pendingCommandStream?.current ?? null;
    const streamedPendingCommand =
      String((event as Record<string, unknown>).type ?? "") === "text_delta" ||
      String((event as Record<string, unknown>).type ?? "") === "text_complete"
        ? reconcilePendingCommandStream(originalPendingCommand, event as Record<string, unknown>)
        : originalPendingCommand;
    if (pendingCommandStream && streamedPendingCommand !== originalPendingCommand) {
      pendingCommandStream.current = streamedPendingCommand;
    }
    const pendingCommand = streamedPendingCommand;
    const typed = enrichSparseCommandResultEvent(event as Record<string, unknown>, pendingCommand);
    const eventType = String(typed.type ?? "");
    const canonicalEvents = canonicalEventsFromBridgeEvent(typed);
    if (canonicalEvents.length > 0) {
      apply([{type: "execution.events.ingest", events: canonicalEvents}]);
    }
    if (eventType !== "bridge.error" && eventType !== "error") {
      malformedBridgeEvents = 0;
    }
    if (eventType === "bridge.ready") {
      apply([
        {type: "bridge.status", status: "connected"},
        {type: "status.set", value: "bridge ready"},
      ]);
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
          apply([
            {type: "bridge.status", status: "degraded"},
            {type: "status.set", value: `bridge output invalid (${malformedBridgeEvents}/3)`},
          ]);
        }
      } else {
        apply([
          {type: "bridge.status", status: "degraded"},
          {type: "status.set", value: message},
        ]);
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
      apply([{
        type: "bridge.config",
        provider,
        model,
        strategy: state.routePolicy.strategy,
      }]);
      malformedBridgeEvents = 0;
      reconnectRequested = false;
      resetHandshakeBackoff?.();
      apply([
        {type: "bridge.status", status: "connected"},
        {type: "status.set", value: "backend connected"},
      ]);
      if (awaitingAuthoritativeResync) {
        awaitingAuthoritativeResync = false;
        resyncPending = true;
        requestAuthoritativeResync(bridge, provider, model, getState().routePolicy.strategy);
        apply([{type: "status.set", value: authoritativeResyncStatus(state.authoritativeSurfaces)}]);
      }
    }
    if (eventType === "command.result") {
      const command = resolveEventCommand(typed);
      const commandName = normalizeCommandName(command);
      apply(commandResultActionsForBridgeEvent(
        typed,
        pendingCommand?.command,
        pendingCommand?.tabId,
      ));
      const commandSnapshotActions = commandRunSnapshotActionsForBridgeEvent(
        typed,
        state.liveRepoPreview,
        state.liveControlPreview,
      );
      apply(commandSnapshotActions);
      const persistedRepoPreview = commandSnapshotActions.find((action) => action.type === "live.repo.set");
      if (persistedRepoPreview?.type === "live.repo.set") {
        persistRepoPreview(persistedRepoPreview.preview, workspaceSnapshotPayloadFromEvent(typed));
      }
      const persistedControlPreview = commandSnapshotActions.find((action) => action.type === "live.control.set");
      if (persistedControlPreview?.type === "live.control.set") {
        persistControlPreview(persistedControlPreview.preview, runtimeSnapshotPayloadFromEvent(typed));
      }
      if (isBareModelCommand(command)) {
        apply([{type: "modelPicker.open", returnTabId: state.uiMode.activeTabId}]);
      }
      const currentRoute = bridgeRouteState(getState());
      requestLiveSnapshots(bridge, currentRoute.provider, currentRoute.model, currentRoute.strategy);
    }
    if (eventType === "workspace.snapshot.result") {
      const actions = snapshotActionsForBridgeEvent(typed, state.liveRepoPreview, state.liveControlPreview);
      const repoIsAuthoritative = workspaceEventHasAuthoritativeRepoSignal(typed);
      apply(repoIsAuthoritative ? [...actions, {type: "surface.truth.mark", surface: "repo"}] : actions);
      if (repoIsAuthoritative && resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "repo");
        apply([{type: "status.set", value: authoritativeResyncStatus(nextAuthority)}]);
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const persistedRepoPreview = actions.find((action) => action.type === "live.repo.set");
      if (persistedRepoPreview?.type === "live.repo.set") {
        persistRepoPreview(persistedRepoPreview.preview, workspaceSnapshotPayloadFromEvent(typed));
      }
    }
    if (eventType === "permission.decision") {
      const decision = permissionDecisionFromEvent(typed);
      if (decision) {
        const nextApprovalPane = nextApprovalPaneAfterDecision(state.approvalPane, decision);
        apply([
          {type: "approval.decision.set", decision, sourceEventType: eventType},
          {
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(nextApprovalPane),
          preview: approvalPaneToPreview(nextApprovalPane),
          },
        ]);
        if (decision.decision === "require_approval" && decision.requires_confirmation) {
          apply([
            {type: "status.set", value: `approval required ${decision.tool_name} (${decision.risk})`},
          ]);
        }
        requestPermissionHistory(bridge);
      }
    }
    if (eventType === "permission.history.result") {
      const history = permissionHistoryFromEvent(typed);
      if (history) {
        apply([{type: "surface.truth.mark", surface: "approvals"}]);
        if (resyncPending && state.bridgeStatus === "connected") {
          const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "approvals");
          apply([{type: "status.set", value: authoritativeResyncStatus(nextAuthority)}]);
          resyncPending = !authoritativeResyncComplete(nextAuthority);
        }
        const approvalPane = approvalPaneFromHistory(history);
        apply([
          {type: "approval.history.set", approvalPane},
          {
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(approvalPane),
          preview: approvalPaneToPreview(approvalPane),
          },
        ]);
      }
    }
    if (eventType === "permission.resolution") {
      const resolution = permissionResolutionFromEvent(typed);
      if (resolution) {
        const nextApprovalPane = nextApprovalPaneAfterResolution(state.approvalPane, resolution);
        apply([
          {type: "approval.resolution.set", resolution, sourceEventType: eventType},
          {
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(nextApprovalPane),
          preview: approvalPaneToPreview(nextApprovalPane),
          },
          {type: "status.set", value: `${resolution.resolution} ${resolution.action_id} (${resolution.enforcement_state})`},
        ]);
        requestPermissionHistory(bridge);
      }
    }
    if (eventType === "permission.outcome") {
      const outcome = permissionOutcomeFromEvent(typed);
      if (outcome) {
        const nextApprovalPane = nextApprovalPaneAfterOutcome(state.approvalPane, outcome);
        apply([
          {type: "approval.outcome.set", outcome, sourceEventType: eventType},
          {
          type: "tab.replace",
          tabId: "approvals",
          lines: approvalPaneToLines(nextApprovalPane),
          preview: approvalPaneToPreview(nextApprovalPane),
          },
          {type: "status.set", value: `${outcome.outcome} ${outcome.action_id}`},
        ]);
        requestPermissionHistory(bridge);
      }
    }
    if (eventType === "session.catalog.result") {
      const catalog = sessionCatalogFromEvent(typed);
      if (catalog) {
        apply([{type: "surface.truth.mark", surface: "sessions"}]);
        if (resyncPending && state.bridgeStatus === "connected") {
          const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "sessions");
          apply([{type: "status.set", value: authoritativeResyncStatus(nextAuthority)}]);
          resyncPending = !authoritativeResyncComplete(nextAuthority);
        }
        const nextSessionPane = nextSessionPaneAfterCatalog(state.sessionPane, catalog);
        apply([
          {type: "session.catalog.set", catalog, selectedSessionId: nextSessionPane.selectedSessionId},
          {
          type: "tab.replace",
          tabId: "sessions",
          lines: sessionPaneToLines(nextSessionPane),
          preview: sessionPaneToPreview(nextSessionPane),
          },
        ]);
        if (
          nextSessionPane.selectedSessionId &&
          !nextSessionPane.detailsBySessionId[nextSessionPane.selectedSessionId]
        ) {
          requestSessionDetail(bridge, nextSessionPane.selectedSessionId);
        } else {
          const selectedDetail = nextSessionPane.selectedSessionId
            ? nextSessionPane.detailsBySessionId[nextSessionPane.selectedSessionId]
            : undefined;
          apply([{type: "session.continuity.set", continuity: continuityStateFromSession(state, selectedDetail)}]);
        }
      }
    }
    if (eventType === "session.detail.result") {
      const detail = sessionDetailFromEvent(typed);
      if (detail) {
        const nextSessionPane = nextSessionPaneAfterDetail(state.sessionPane, detail);
        apply([
          {type: "session.detail.set", detail},
          {type: "session.continuity.set", continuity: continuityStateFromSession(state, detail)},
          {
          type: "tab.replace",
          tabId: "sessions",
          lines: sessionPaneToLines(nextSessionPane),
          preview: sessionPaneToPreview(nextSessionPane),
          },
        ]);
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
      const typedPayload = runtimeSnapshotPayloadFromEvent(typed);
      const runtimeIsAuthoritative = typedPayload ? runtimePayloadHasAuthoritativeControlSignal(typedPayload) : true;
      if (runtimeIsAuthoritative) {
        apply([{type: "surface.truth.mark", surface: "control"}]);
      }
      if (runtimeIsAuthoritative && resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "control");
        apply([{type: "status.set", value: authoritativeResyncStatus(nextAuthority)}]);
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const supervisor = loadSupervisorControlState();
      const content = String(typed.content ?? "");
      const preview = typedPayload ? runtimePayloadToPreview(typedPayload, supervisor) : runtimeSnapshotToPreview(content, supervisor);
      const effectivePreview = runtimeIsAuthoritative ? preview : preserveDeferredControlPreview(preview, state.liveControlPreview);
      const synchronizedRepoPreview = synchronizeRepoControlPreviews(state.liveRepoPreview, effectivePreview);
      if (synchronizedRepoPreview) {
        persistRepoPreview(synchronizedRepoPreview);
      }
      persistControlPreview(effectivePreview, typedPayload ?? undefined);
      apply([{
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(effectivePreview),
        preview: effectivePreview,
      }, {
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(effectivePreview),
        preview: effectivePreview,
      }, {type: "live.control.set", preview: effectivePreview},
      ...(synchronizedRepoPreview ? [{type: "live.repo.set", preview: synchronizedRepoPreview} as const] : [])]);
    }
    if (eventType === "model.policy.result") {
      const suppressRouteStatus = resyncPending && state.bridgeStatus === "connected";
      apply([{type: "surface.truth.mark", surface: "models"}]);
      if (resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "models");
        apply([{type: "status.set", value: authoritativeResyncStatus(nextAuthority)}]);
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const routingPayload = routingDecisionPayloadFromEvent(typed);
      const policyRecord =
        typeof typed.policy === "object" && typed.policy !== null ? (typed.policy as Record<string, unknown>) : undefined;
      const nextRoutePolicy = routePolicyFromValue(routingPayload ?? policyRecord ?? typed, state.routePolicy);
      const activeChoice = nextRoutePolicy.targets.find(
        (choice) => choice.provider === nextRoutePolicy.provider && choice.model === nextRoutePolicy.model,
      );
      apply([{
        type: "route.policy.set",
        policy: nextRoutePolicy,
      }, {
        type: "tab.replace",
        tabId: "models",
        lines: modelPolicyToLines(routingPayload ? {payload: routingPayload} : typed),
        preview: modelPolicyToPreview(routingPayload ? {payload: routingPayload} : typed),
      }]);
      if (activeChoice) {
        const actions: AppAction[] = [{
          type: "bridge.config",
          provider: activeChoice.provider,
          model: activeChoice.model,
          strategy: nextRoutePolicy.strategy,
        }];
        if (!suppressRouteStatus) {
          actions.push({
            type: "status.set",
            value: activeChoice.selectable ? `route confirmed -> ${routeLabel(nextRoutePolicy)}` : `route constrained -> ${routeSummary(nextRoutePolicy)}`,
          });
        }
        apply(actions);
      }
    }
    if (eventType === "agent.routes.result") {
      apply([{type: "surface.truth.mark", surface: "agents"}]);
      if (resyncPending && state.bridgeStatus === "connected") {
        const nextAuthority = markAuthoritativeSurface(state.authoritativeSurfaces, "agents");
        apply([{type: "status.set", value: authoritativeResyncStatus(nextAuthority)}]);
        resyncPending = !authoritativeResyncComplete(nextAuthority);
      }
      const routesPayload = agentRoutesPayloadFromEvent(typed);
      apply([{
        type: "tab.replace",
        tabId: "agents",
        lines: agentRoutesToLines(routesPayload ? {payload: routesPayload} : typed),
        preview: agentRoutesToPreview(routesPayload ? {payload: routesPayload} : typed),
      }]);
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
      dispatch({
        type: "tab.replace",
        tabId: "mission",
        lines: sessionBootstrapToLines(typed),
        preview: sessionBootstrapToPreview(typed),
      });
      const actions = snapshotActionsForBridgeEvent(typed, state.liveRepoPreview, state.liveControlPreview);
      actions.forEach((action) => dispatch(action));
      const persistedRepoPreview = actions.find((action) => action.type === "live.repo.set");
      if (persistedRepoPreview?.type === "live.repo.set") {
        persistRepoPreview(persistedRepoPreview.preview, workspaceSnapshotPayloadFromEvent(typed));
      }
      const persistedControlPreview = actions.find((action) => action.type === "live.control.set");
      if (persistedControlPreview?.type === "live.control.set") {
        persistControlPreview(persistedControlPreview.preview, runtimeSnapshotPayloadFromEvent(typed));
      }

      const selectedProvider = String(typed.selected_provider ?? pending?.provider ?? state.routePolicy.provider);
      const selectedModel = String(typed.selected_model ?? pending?.model ?? state.routePolicy.model);
      const selectedStrategy = String(typed.routing_strategy ?? state.routePolicy.strategy ?? "responsive");
      dispatch({type: "bridge.config", provider: selectedProvider, model: selectedModel, strategy: selectedStrategy});

      const intent = typed.intent as Record<string, unknown> | undefined;
      if (intent && String(intent.kind ?? "") === "command" && Boolean(intent.auto_execute)) {
        const command = `/${String(intent.command ?? "")}`;
        const commandIntent = commandIntentFromBootstrapIntent(intent, command);
        const tabId = resolveCommandTargetPane(commandIntent, commandTargetTab(command));
        dispatch({type: "tab.activate", tabId});
        markPendingCommandStream(pendingCommandStream, commandIntent);
        bridge.send("command.run", commandIntent);
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
            messages: pending.messages,
            resume_session_id: pending.resumeSessionId,
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
            messages: pending.messages,
            resume_session_id: pending.resumeSessionId,
            bootstrap: typed,
            system_prompt: String(typed.system_prompt ?? ""),
          });
        }
      } else if (pending) {
        bridge.send("session.start", {
          provider: selectedProvider,
          model: selectedModel,
          prompt: pending.prompt,
          messages: pending.messages,
          resume_session_id: pending.resumeSessionId,
          bootstrap: typed,
          system_prompt: String(typed.system_prompt ?? ""),
        });
        dispatch({type: "status.set", value: `running ${selectedProvider}:${selectedModel}`});
      }
      delete pendingBootstraps.current[requestId];
    }
    if (eventType === "session_end") {
      const currentRoute = bridgeRouteState(getState());
      requestLiveSnapshots(bridge, currentRoute.provider, currentRoute.model, currentRoute.strategy);
      requestSessionCatalog(bridge);
    }
    if (eventType === "action.result") {
      const actionType = resolveEventActionType(typed);
      const command = resolveEventCommand(typed);
      if (actionType === "command.run") {
        clearPendingCommandStream(pendingCommandStream);
        actionResultActionsForBridgeEvent(
          typed,
          pendingCommand?.command,
          pendingCommand?.tabId,
        ).forEach((action) => dispatch(action));
        if (isBareModelCommand(command)) {
          dispatch({type: "modelPicker.open", returnTabId: state.uiMode.activeTabId});
        }
      } else {
        actionResultActionsForBridgeEvent(typed).forEach((action) => dispatch(action));
      }
      const pane =
        actionType === "command.run"
          ? resolveSlashCommandResultTabId(typed, pendingCommand?.command, pendingCommand?.tabId)
          : String(typed.target_pane ?? "control");
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
        persistRepoPreview(persistedRepoPreview.preview, workspaceSnapshotPayloadFromEvent(typed));
      }
      const persistedControlPreview = [...commandRunSnapshotActions, ...surfaceRefreshActions].find(
        (action) => action.type === "live.control.set",
      );
      if (persistedControlPreview?.type === "live.control.set") {
        persistControlPreview(persistedControlPreview.preview, runtimeSnapshotPayloadFromEvent(typed));
      }
      const output = resolveEventOutput(typed).trim();
      const policy =
        typeof typed.policy === "object" && typed.policy !== null ? (typed.policy as Record<string, unknown>) : null;
      const routingPayload = routingDecisionPayloadFromEvent(typed);
      let refreshProvider = getState().routePolicy.provider;
      let refreshModel = getState().routePolicy.model;
      let refreshStrategy = getState().routePolicy.strategy;
      if (policy || routingPayload) {
        const nextRoutePolicy = routePolicyFromValue(routingPayload ?? policy, getState().routePolicy);
        refreshProvider = nextRoutePolicy.provider;
        refreshModel = nextRoutePolicy.model;
        refreshStrategy = nextRoutePolicy.strategy;
        dispatch({
          type: "bridge.config",
          provider: refreshProvider,
          model: refreshModel,
          strategy: refreshStrategy,
        });
        dispatch({type: "route.policy.set", policy: nextRoutePolicy});
        dispatch({
          type: "tab.replace",
          tabId: "models",
          lines: modelPolicyToLines(routingPayload ? {payload: routingPayload} : {policy}),
          preview: modelPolicyToPreview(routingPayload ? {payload: routingPayload} : {policy}),
        });
      }
      if (
        output &&
        commandRunSnapshotActions.length === 0 &&
        surfaceRefreshActions.length === 0 &&
        !(pane === "models" && (policy || routingPayload)) &&
        !(actionType === "command.run" && shouldSuppressDuplicatePendingCommandPatch(typed, pendingCommand))
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
      requestLiveSnapshots(bridge, refreshProvider, refreshModel, refreshStrategy);
    }

    if (eventType === "command.result") {
      clearPendingCommandStream(pendingCommandStream);
    }

    if (eventType === "text_delta" && pendingCommand && !shouldSuppressPendingCommandStreamOutput(pendingCommand)) {
      dispatch({type: "tab.activate", tabId: pendingCommand.tabId});
    }

    if (eventType === "text_complete" && pendingCommand) {
      const output = normalizeCommandStreamText(typed.content);
      if (output) {
        pendingCommand.lastCompletedText = output;
        const streamSnapshotActions = snapshotActionsForPendingCommandStream(
          pendingCommand,
          output,
          state.liveRepoPreview,
          state.liveControlPreview,
        );
        if (!shouldSuppressPendingCommandStreamOutput(pendingCommand)) {
          dispatch({type: "tab.activate", tabId: pendingCommand.tabId});
          if (streamSnapshotActions.length > 0) {
            queueAppActions(dispatch, streamSnapshotActions);
            const persistedRepoPreview = streamSnapshotActions.find((action) => action.type === "live.repo.set");
            if (persistedRepoPreview?.type === "live.repo.set") {
              persistRepoPreview(persistedRepoPreview.preview);
            }
            const persistedControlPreview = streamSnapshotActions.find((action) => action.type === "live.control.set");
            if (persistedControlPreview?.type === "live.control.set") {
              persistControlPreview(persistedControlPreview.preview);
            }
          } else {
            dispatch({
              type: "tab.append",
              tabId: pendingCommand.tabId,
              lines: [{id: `command-stream-${Date.now()}`, kind: "system", text: output}],
            });
          }
        }
      }
    }

    const suppressChatPatch =
      (eventType === "text_delta" || eventType === "text_complete") && Boolean(pendingCommand);
    const suppressDuplicateCommandPatch = shouldSuppressDuplicatePendingCommandPatch(typed, pendingCommand);
    const suppressDuplicateCompletedAssistantPatch = isDuplicateCompletedAssistantPatch(getState(), typed);
    const canonicalLogOwnsTranscriptPatch =
      canonicalEvents.length > 0 &&
      eventType !== "text_delta" &&
      eventType !== "text_complete" &&
      eventType !== "command.result";
    const patches =
      suppressChatPatch || suppressDuplicateCommandPatch || suppressDuplicateCompletedAssistantPatch || canonicalLogOwnsTranscriptPatch
        ? []
        : eventToTabPatch(typed);
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
    const output = resolveEventOutput(typed);
    if (!workspacePayload && !output.trim()) {
      return [];
    }
    const preview = workspacePayload ? workspacePayloadToPreview(workspacePayload) : workspaceSnapshotToPreview(output);
    const synchronizedPreview = synchronizeRepoControlPreviews(preview, liveControlPreview);
    return [
      {
        type: "tab.replace",
        tabId: "repo",
        lines: workspacePreviewToLines(synchronizedPreview ?? preview),
        preview: synchronizedPreview ?? preview,
      },
      {type: "live.repo.set", preview: synchronizedPreview ?? preview},
    ];
  }

  if (surface === "control" || surface === "runtime") {
    const typedPayload = runtimeSnapshotPayloadFromEvent(typed);
    const output = resolveEventOutput(typed);
    if (!typedPayload && !output.trim()) {
      return [];
    }
    const preview = typedPayload ? runtimePayloadToPreview(typedPayload, supervisor) : runtimeSnapshotToPreview(output, supervisor);
    const synchronizedRepoPreview = synchronizeRepoControlPreviews(liveRepoPreview, preview);
    return [
      {
        type: "tab.replace",
        tabId: "control",
        lines: runtimePreviewToLines(preview),
        preview,
      },
      {
        type: "tab.replace",
        tabId: "runtime",
        lines: runtimePreviewToLines(preview),
        preview,
      },
      {type: "live.control.set", preview},
      ...(synchronizedRepoPreview ? [{type: "live.repo.set", preview: synchronizedRepoPreview} as const] : []),
    ];
  }

  const output = resolveEventOutput(typed);
  if (!output.trim()) {
    return [];
  }

  return [];
}

export function paneActionStartActions(action: {summary: string; payload: Record<string, unknown>} | undefined): AppAction[] {
  const commandRunEvent = commandRunEventFromPaneAction(action);
  if (commandRunEvent) {
    return slashCommandStartActions(commandRunEvent, "command");
  }

  if (!action) {
    return [];
  }

  if (action.summary === "focus selected approval") {
    return [{type: "status.set", value: action.summary}];
  }

  return [{type: "status.set", value: action.summary}];
}

export function App(): React.ReactElement {
  const {exit} = useApp();
  const [state, dispatch] = useReducer(reduceApp, initialState, createInitialAppState);

  const activeTab = state.tabs.find((tab) => tab.id === state.uiMode.activeTabId) ?? state.tabs[0];
  const terminalWidth = (process.stdout.columns ?? Number(process.env.COLUMNS ?? "0")) || 120;
  const terminalHeight = (process.stdout.rows ?? Number(process.env.LINES ?? "0")) || 30;
  const compactShell = terminalWidth <= 90;
  const paneWindowSize = Math.max(MIN_SCROLL_WINDOW_SIZE, terminalHeight - (compactShell ? 14 : 18));
  const outline = useMemo(() => outlineFromTabs(state.tabs), [state.tabs]);
  const modelChoices = selectableRouteTargets(state.routePolicy);
  const displayedTranscriptLines = displayedTranscriptLinesForTab(activeTab, state);
  const transcriptMeta = transcriptMetaForTab(activeTab);
  const operatorSummaryItems = buildOperatorSummaryItems(state);
  const activeScrollOffset = Math.min(
    state.paneScrollOffsets[activeTab?.id ?? ""] ?? 0,
    scrollMaxOffsetForTab(activeTab, state, paneWindowSize),
  );
  const stateRef = useRef(state);
  const pendingBootstraps = useRef<Record<string, {prompt: string; provider: string; model: string; messages: Array<{role: "user" | "assistant" | "system"; content: string}>; resumeSessionId?: string}>>({});
  const pendingCommandStream = useRef<PendingCommandStream | null>(null);
  const bridgeRef = useRef<DharmaBridge | null>(null);
  const handshakeBackoffRef = useRef({attempt: 0, nextAllowedAt: 0});
  const persistTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveSnapshotRequestRef = useRef(0);

  function requestLiveSnapshotsIfStale(provider: string, model: string, strategy: string, minIntervalMs = 900): void {
    const now = Date.now();
    if (now - liveSnapshotRequestRef.current < minIntervalMs) {
      return;
    }
    liveSnapshotRequestRef.current = now;
    requestLiveSnapshots(bridge, provider, model, strategy);
  }

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
        pendingCommandStream,
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
        requestAuthoritativeResync(
          bridge,
          stateRef.current.routePolicy.provider,
          stateRef.current.routePolicy.model,
          stateRef.current.routePolicy.strategy,
        );
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
        stateRef.current.routePolicy.provider,
        stateRef.current.routePolicy.model,
        stateRef.current.routePolicy.strategy,
        stateRef.current.authoritativeSurfaces,
      );
    }, 3_000);
    return () => {
      clearTimeout(repairId);
    };
  }, [bridge, state.bridgeStatus, state.authoritativeSurfaces]);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const selectedDetail = state.sessionPane.selectedSessionId
      ? state.sessionPane.detailsBySessionId[state.sessionPane.selectedSessionId]
      : undefined;
    const nextContinuity = continuityStateFromSession(state, selectedDetail);
    const current = state.sessionContinuity;
    if (
      current.activeSessionId === nextContinuity.activeSessionId &&
      current.resumeSessionId === nextContinuity.resumeSessionId &&
      current.activeRouteId === nextContinuity.activeRouteId &&
      current.continuityMode === nextContinuity.continuityMode &&
      current.compactedSummary === nextContinuity.compactedSummary &&
      JSON.stringify(current.compactionPolicy) === JSON.stringify(nextContinuity.compactionPolicy) &&
      JSON.stringify(current.boundedHistory) === JSON.stringify(nextContinuity.boundedHistory)
    ) {
      return;
    }
    dispatch({type: "session.continuity.set", continuity: nextContinuity});
  }, [state.sessionPane.selectedSessionId, state.sessionPane.detailsBySessionId, state.routePolicy.routeId]);

  useEffect(() => {
    if (persistTimeoutRef.current) {
      clearTimeout(persistTimeoutRef.current);
    }
    persistTimeoutRef.current = setTimeout(() => {
      saveStoredState(state);
      persistTimeoutRef.current = null;
    }, 120);
    return () => {
      if (persistTimeoutRef.current) {
        clearTimeout(persistTimeoutRef.current);
        persistTimeoutRef.current = null;
      }
    };
  }, [state.uiMode.sidebarVisible, state.uiMode.sidebarMode, outline]);

  useEffect(() => {
    dispatch({type: "ui.compact.set", compact: compactShell});
  }, [compactShell]);

  function submitPrompt(prompt: string): void {
    const submitted = prompt.trim();
    if (!submitted) {
      return;
    }
    dispatch({type: "prompt.clear"});
    if (isBareModelCommand(submitted)) {
      dispatch({
        type: "modelPicker.open",
        returnTabId: stateRef.current.uiMode.activeTabId,
      });
      bridge.send("model.policy", {
        provider: stateRef.current.routePolicy.provider,
        model: stateRef.current.routePolicy.model,
        strategy: stateRef.current.routePolicy.strategy,
      });
      dispatch({type: "status.set", value: "route picker ready"});
      return;
    }
    if (isSlashCommandPrompt(submitted)) {
      queueAppActions(dispatch, slashCommandStartActions({command: submitted}, "command"));
      markPendingCommandStream(pendingCommandStream, {command: submitted});
      bridge.send("command.run", {command: submitted});
    } else {
      const messages = boundedContinuityMessages(state, submitted);
      const userLine: TranscriptLine = {
        id: `user-${Date.now()}`,
        kind: "user",
        text: `> ${submitted}`,
      };
      const route = routeLabel(state.routePolicy);
      queueAppActions(dispatch, [
        {type: "tab.append", tabId: "chat", lines: [userLine]},
        {
          type: "execution.events.ingest",
          events: [
            userPromptExecutionEvent(submitted),
            localStatusExecutionEvent("bootstrapping context", route, "queued"),
            localStatusExecutionEvent("selecting route", `${route} (${state.routePolicy.strategy})`, "queued"),
          ],
        },
      ]);
      const requestId = bridge.send("session.bootstrap", {
        provider: state.routePolicy.provider,
        model: state.routePolicy.model,
        strategy: state.routePolicy.strategy,
        prompt: submitted,
        active_tab: state.uiMode.activeTabId,
        resume_session_id: state.sessionContinuity.resumeSessionId,
      });
      pendingBootstraps.current[requestId] = {
        prompt: submitted,
        provider: state.routePolicy.provider,
        model: state.routePolicy.model,
        messages,
        resumeSessionId: state.sessionContinuity.resumeSessionId,
      };
      dispatch({
        type: "status.set",
        value:
          state.sessionContinuity.resumeSessionId
            ? `resuming ${state.sessionContinuity.resumeSessionId} via ${routeLabel(state.routePolicy)} (${state.routePolicy.strategy})`
            : `bootstrapping ${routeLabel(state.routePolicy)} (${state.routePolicy.strategy})`,
      });
    }
  }

  function runPaneAction(action: PaneAction | undefined): void {
    if (!action) {
      return;
    }
    queueAppActions(dispatch, paneActionStartActions(action));
    if (action.summary === "focus selected approval") {
      return;
    }
    const commandRunEvent = commandRunEventFromPaneAction(action);
    if (commandRunEvent) {
      markPendingCommandStream(pendingCommandStream, commandRunEvent);
    }
    bridge.send(action.requestType ?? "action.run", action.payload);
  }

  function applyModelChoice(index: number): void {
    const choices = selectableRouteTargets(stateRef.current.routePolicy);
    const clampedIndex = Math.min(Math.max(index, 0), Math.max(choices.length - 1, 0));
    const choice = choices[clampedIndex];
    if (!choice) {
      dispatch({type: "status.set", value: "no model targets available"});
      return;
    }
    queueAppActions(dispatch, [
      {type: "modelPicker.set", index: clampedIndex},
    ]);
    bridge.send("action.run", {
      action_type: "model.set",
      provider: choice.provider,
      model: choice.model,
      strategy: stateRef.current.routePolicy.strategy,
    });
    queueAppActions(dispatch, [
      {type: "modelPicker.close"},
      {type: "status.set", value: `requesting route -> ${choice.provider}:${choice.model}`},
    ]);
  }

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      bridge.close();
      exit();
      return;
    }
    if (state.uiMode.activeOverlay.kind === "paneSwitcher") {
      const maxIndex = Math.max(state.tabs.length - 1, 0);
      if (key.escape) {
        dispatch({type: "paneSwitcher.close"});
        dispatch({type: "status.set", value: "pane switcher closed"});
        return;
      }
      if (input === "j" || key.downArrow) {
        dispatch({type: "paneSwitcher.set", index: Math.min(state.uiMode.activeOverlay.selectedIndex + 1, maxIndex)});
        return;
      }
      if (input === "k" || key.upArrow) {
        dispatch({type: "paneSwitcher.set", index: Math.max(state.uiMode.activeOverlay.selectedIndex - 1, 0)});
        return;
      }
      if (key.return) {
        const target = state.tabs[state.uiMode.activeOverlay.selectedIndex];
        if (target) {
          queueAppActions(dispatch, [
            {type: "paneSwitcher.close"},
            {type: "tab.activate", tabId: target.id},
            {type: "status.set", value: `pane -> ${target.title}`},
          ]);
        }
        return;
      }
    }
      if (state.uiMode.activeOverlay.kind === "modelPicker") {
        const choices = modelChoices;
        const maxIndex = Math.max(choices.length - 1, 0);
        if (key.escape) {
          dispatch({type: "modelPicker.close"});
          dispatch({type: "status.set", value: "model picker closed"});
          return;
        }
      if (input === "j" || key.downArrow) {
        dispatch({type: "modelPicker.set", index: Math.min(state.uiMode.activeOverlay.selectedIndex + 1, maxIndex)});
        return;
      }
      if (input === "k" || key.upArrow) {
        dispatch({type: "modelPicker.set", index: Math.max(state.uiMode.activeOverlay.selectedIndex - 1, 0)});
        return;
      }
      if (key.return) {
        applyModelChoice(state.uiMode.activeOverlay.selectedIndex);
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
    if (activeTab?.kind === "sessions") {
      if (input === "j") {
        const nextSessionId = stepSessionSelection(stateRef.current, 1);
        if (nextSessionId) {
          dispatch({type: "session.select", sessionId: nextSessionId});
          dispatch({type: "status.set", value: `session -> ${nextSessionId}`});
        }
        return;
      }
      if (input === "k") {
        const nextSessionId = stepSessionSelection(stateRef.current, -1);
        if (nextSessionId) {
          dispatch({type: "session.select", sessionId: nextSessionId});
          dispatch({type: "status.set", value: `session -> ${nextSessionId}`});
        }
        return;
      }
      if (key.return) {
        if (state.sessionPane.selectedSessionId) {
          requestSessionDetail(bridge, state.sessionPane.selectedSessionId);
          dispatch({type: "status.set", value: `refresh detail ${state.sessionPane.selectedSessionId}`});
        }
        return;
      }
    }
    if (activeTab?.kind === "approvals") {
      if (input === "j") {
        const nextActionId = stepApprovalSelection(stateRef.current, 1);
        if (nextActionId) {
          dispatch({type: "approval.select", actionId: nextActionId});
          dispatch({type: "status.set", value: `approval -> ${nextActionId}`});
        }
        return;
      }
      if (input === "k") {
        const nextActionId = stepApprovalSelection(stateRef.current, -1);
        if (nextActionId) {
          dispatch({type: "approval.select", actionId: nextActionId});
          dispatch({type: "status.set", value: `approval -> ${nextActionId}`});
        }
        return;
      }
    }
    if (activeTab?.kind === "agents") {
      if (input === "j" || input === "k" || key.upArrow || key.downArrow) {
        const direction: 1 | -1 = input === "k" || key.upArrow ? -1 : 1;
        const nextIndex = stepPaneSectionFocus(
          stateRef.current.paneFocusIndices[activeTab.id],
          agentRouteCount(activeTab.lines),
          direction,
        );
        if (typeof nextIndex === "number") {
          dispatch({type: "pane.focus.set", tabId: activeTab.id, index: nextIndex});
          dispatch({
            type: "status.set",
            value: `agent route ${nextIndex + 1}/${Math.max(agentRouteCount(activeTab.lines), 1)}`,
          });
        }
        return;
      }
    }
    if (activeTab?.kind === "repo" || activeTab?.kind === "control" || activeTab?.kind === "runtime") {
      if (input === "j" || input === "k" || key.upArrow || key.downArrow) {
        const direction: 1 | -1 = input === "k" || key.upArrow ? -1 : 1;
        const nextIndex = stepPaneSectionFocus(
          stateRef.current.paneFocusIndices[activeTab.id],
          paneSectionCount(activeTab, stateRef.current),
          direction,
        );
        if (typeof nextIndex === "number") {
          dispatch({type: "pane.focus.set", tabId: activeTab.id, index: nextIndex});
          dispatch({
            type: "status.set",
            value: `${activeTab.title.toLowerCase()} section ${nextIndex + 1}/${Math.max(paneSectionCount(activeTab, stateRef.current), 1)}`,
          });
        }
        return;
      }
    }
    if ((key.upArrow || key.downArrow) && activeTab?.kind === "sessions") {
      const nextSessionId = stepSessionSelection(stateRef.current, key.downArrow ? 1 : -1);
      if (nextSessionId) {
        dispatch({type: "session.select", sessionId: nextSessionId});
        dispatch({type: "status.set", value: `session -> ${nextSessionId}`});
      }
      return;
    }
    if ((key.upArrow || key.downArrow) && activeTab?.kind === "approvals") {
      const nextActionId = stepApprovalSelection(stateRef.current, key.downArrow ? 1 : -1);
      if (nextActionId) {
        dispatch({type: "approval.select", actionId: nextActionId});
        dispatch({type: "status.set", value: `approval -> ${nextActionId}`});
      }
      return;
    }
    if ((key.upArrow || key.downArrow) && activeTab) {
      dispatch({
        type: "pane.scroll",
        tabId: activeTab.id,
        delta: key.upArrow ? -1 : 1,
        maxOffset: scrollMaxOffsetForTab(activeTab, stateRef.current, paneWindowSize),
      });
      return;
    }
    if (key.ctrl && input === "b") {
      const nextSidebarVisible = !stateRef.current.uiMode.sidebarVisible;
      dispatch({type: "sidebar.toggle"});
      dispatch({
        type: "status.set",
        value: nextSidebarVisible ? `sidebar -> ${stateRef.current.uiMode.sidebarMode}` : "sidebar hidden",
      });
      return;
    }
    if (key.ctrl && input === "l") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state, shellControlOptions).refresh);
      return;
    }
    if (key.ctrl && input === "w" && activeTab?.closable) {
      dispatch({type: "tab.close", tabId: activeTab.id});
      return;
    }
    if (key.ctrl && input === "x") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state, shellControlOptions).primary);
      return;
    }
    if (key.ctrl && input === "f") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state, shellControlOptions).secondary);
      return;
    }
    if (key.ctrl && input === "v") {
      runPaneAction(paneActionsFor(activeTab?.id ?? "chat", state, shellControlOptions).tertiary);
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
        returnTabId: state.uiMode.activeTabId,
      });
      bridge.send("model.policy", {
        provider: stateRef.current.routePolicy.provider,
        model: stateRef.current.routePolicy.model,
        strategy: stateRef.current.routePolicy.strategy,
      });
      dispatch({type: "status.set", value: "route picker ready"});
      return;
    }
    if (key.ctrl && input === "k") {
      dispatch({type: "paneSwitcher.open"});
      dispatch({type: "status.set", value: "pane switcher ready"});
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
    if (key.ctrl && input === "h") {
      dispatch({type: "tab.activate", tabId: "thinking"});
      return;
    }
    if (key.ctrl && input === "j") {
      dispatch({type: "tab.activate", tabId: "tools"});
      return;
    }
    if (key.ctrl && input === "n") {
      dispatch({type: "tab.activate", tabId: "timeline"});
      return;
    }
    if (key.ctrl && input === "u") {
      dispatch({type: "activity.visibility.toggle"});
      return;
    }
    if (key.ctrl && input === "i") {
      dispatch({type: "activity.raw.toggle"});
      return;
    }
    if (input === "1") {
      dispatch({type: "sidebar.mode", mode: "toc"});
      dispatch({type: "status.set", value: "sidebar -> toc"});
      return;
    }
    if (input === "2") {
      dispatch({type: "sidebar.mode", mode: "context"});
      dispatch({type: "status.set", value: "sidebar -> context"});
      return;
    }
    if (input === "3") {
      dispatch({type: "sidebar.mode", mode: "help"});
      dispatch({type: "status.set", value: "sidebar -> help"});
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
        routePolicy={state.routePolicy}
        bridgeStatus={state.bridgeStatus}
        activeTitle={activeTab?.title ?? "Workspace"}
        focusMode={focusModeFor(activeTab, state)}
        activeCount={state.tabs.length}
        compact={compactShell}
      />
      {!compactShell ? (
        <OperatorSummaryBand items={operatorSummaryItems} compact={compactShell} />
      ) : null}
      <TabBar tabs={state.tabs} activeTabId={state.uiMode.activeTabId} compact={compactShell} />
      {activeTab?.kind === "chat" && !compactShell ? <ScenicStrip /> : null}
      <Box marginTop={1}>
        {state.uiMode.sidebarVisible && state.uiMode.activeOverlay.kind !== "modelPicker" && !compactShell ? (
          <Sidebar
            mode={state.uiMode.sidebarMode}
            outline={outline}
            activeTabTitle={activeTab?.title ?? "Workspace"}
            provider={state.routePolicy.provider}
            model={state.routePolicy.model}
            bridgeStatus={state.bridgeStatus}
            tabs={state.tabs}
            repoPreview={decorateSurfacePreview(state.liveRepoPreview, "repo", state.bridgeStatus, state.authoritativeSurfaces)}
            controlPreview={decorateSurfacePreview(state.liveControlPreview, "control", state.bridgeStatus, state.authoritativeSurfaces)}
            compact={compactShell}
          />
        ) : null}
        {state.uiMode.activeOverlay.kind === "paneSwitcher" ? (
          <PaneSwitcher
            tabs={state.tabs}
            selectedIndex={Math.min(state.uiMode.activeOverlay.selectedIndex, Math.max(state.tabs.length - 1, 0))}
          />
        ) : state.uiMode.activeOverlay.kind === "modelPicker" ? (
          <ModelPicker
            choices={modelChoices}
            selectedIndex={Math.min(state.uiMode.activeOverlay.selectedIndex, Math.max(modelChoices.length - 1, 0))}
            title="Model Picker"
            compact={compactShell}
          />
        ) : activeTab?.kind === "repo" ? (
          <RepoPane
            title={activeTab.title}
            preview={decorateSurfacePreview(state.liveRepoPreview ?? activeTab.preview, "repo", state.bridgeStatus, state.authoritativeSurfaces)}
            controlPreview={decorateSurfacePreview(state.liveControlPreview ?? state.tabs.find((tab) => tab.id === "control")?.preview, "control", state.bridgeStatus, state.authoritativeSurfaces)}
            controlLines={state.tabs.find((tab) => tab.id === "control")?.lines ?? []}
            lines={activeTab.lines}
            scrollOffset={activeScrollOffset}
            windowSize={paneWindowSize}
            selectedSectionIndex={state.paneFocusIndices[activeTab.id] ?? 0}
          />
        ) : activeTab?.kind === "control" || activeTab?.kind === "runtime" ? (
          <ControlPane
            title={activeTab.title}
            mode={activeTab.kind}
            preview={
              decorateSurfacePreview(
                controlPanePreview(
                  state.liveControlPreview ??
                    activeTab.preview ??
                    state.tabs.find((tab) => tab.id === "control")?.preview,
                  state.liveRepoPreview ?? state.tabs.find((tab) => tab.id === "repo")?.preview,
                ),
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
            scrollOffset={activeScrollOffset}
            windowSize={paneWindowSize}
            selectedSectionIndex={state.paneFocusIndices[activeTab.id] ?? 0}
          />
        ) : activeTab?.kind === "approvals" ? (
          <ApprovalsPane title={activeTab.title} approvalPane={state.approvalPane} />
        ) : activeTab?.kind === "sessions" ? (
          <SessionsPane title={activeTab.title} sessionPane={state.sessionPane} />
        ) : activeTab?.kind === "agents" ? (
          <AgentsPane
            title={activeTab.title}
            lines={activeTab.lines}
            selectedRouteIndex={state.paneFocusIndices[activeTab.id] ?? 0}
          />
        ) : activeTab?.kind === "thinking" || activeTab?.kind === "tools" || activeTab?.kind === "timeline" ? (
          <ActivityPane
            title={activeTab.title}
            paneKind={activeTab.kind}
            feed={state.activityFeed}
            scrollOffset={activeScrollOffset}
            windowSize={paneWindowSize}
          />
        ) : (
          <TranscriptPane
            title={activeTab?.title ?? "Workspace"}
            lines={displayedTranscriptLines}
            scrollOffset={activeScrollOffset}
            windowSize={paneWindowSize}
            subtitle={transcriptMeta.subtitle}
            emptyState={transcriptMeta.emptyState}
            accentColor={transcriptMeta.accentColor}
          />
        )}
      </Box>
      <Composer prompt={state.prompt} compact={compactShell} />
      <StatusFooter
        statusLine={state.statusLine}
        routeSummary={routeSummary(state.routePolicy)}
        focusMode={focusModeFor(activeTab, state)}
        footerHint={footerHintFor(activeTab?.id ?? "chat", state, shellControlOptions, compactShell)}
        compact={compactShell}
      />
    </Box>
  );
}

export function createInitialAppState(baseState: AppState): AppState {
  const restored = loadStoredState();
  const restoredTabs = ensureRuntimeTabs(baseState.tabs);
  const bootRepoPreview = loadSupervisorRepoPreview();
  const bootControlPreview = loadSupervisorControlPreview();
  const restoredControlSurfacePreview = mergePreview(
    restoredTabs.find((tab) => tab.id === "control")?.preview,
    restoredTabs.find((tab) => tab.id === "runtime")?.preview,
  );
  const restoredControlPreview = mergePreview(restoredControlSurfacePreview, bootControlPreview ?? undefined);
  const restoredRepoPreview = normalizeRepoPreview(
    mergePreview(restoredTabs.find((tab) => tab.id === "repo")?.preview, bootRepoPreview ?? undefined),
    restoredControlPreview,
  );
  const bootRepoLines = restoredRepoPreview ? workspacePreviewToLines(restoredRepoPreview) : undefined;
  const bootControlLines = restoredControlPreview ? runtimePreviewToLines(restoredControlPreview) : undefined;
  const hydratedTabs = restoredTabs.map((tab) => {
    if (tab.id === "repo" && restoredRepoPreview) {
      return {
        ...tab,
        lines: bootRepoLines ?? tab.lines,
        preview: restoredRepoPreview,
      };
    }
    if ((tab.id === "control" || tab.id === "runtime") && restoredControlPreview) {
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
    uiMode: {
      ...baseState.uiMode,
      sidebarVisible: restored?.sidebarVisible ?? baseState.uiMode.sidebarVisible,
      sidebarMode: restored?.sidebarMode ?? baseState.uiMode.sidebarMode,
      activeTabId: baseState.uiMode.activeTabId,
      focusedPaneId: baseState.uiMode.focusedPaneId,
    },
    paneScrollOffsets: baseState.paneScrollOffsets,
    tabs: hydratedTabs,
    liveRepoPreview: mergePreview(baseState.liveRepoPreview, restoredRepoPreview),
    liveControlPreview: mergePreview(baseState.liveControlPreview, restoredControlPreview),
    outline: outlineFromTabs(hydratedTabs),
  };
}
