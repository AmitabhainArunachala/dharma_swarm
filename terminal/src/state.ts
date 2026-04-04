import {buildInitialOutline, buildInitialTabs} from "./mockContent";
import type {ActivityEntry, AppAction, AppState, ApprovalQueueState, TabSpec} from "./types";
import {mergeExecutionEvents, projectActivityEntries, projectChatTraceLines, projectPaneLines} from "./executionLog";
import {defaultRoutePolicy, routePolicyWithConfig} from "./routePolicy";

const initialTabs = buildInitialTabs();
const initialRoutePolicy = defaultRoutePolicy();
const ACTIVITY_ENTRY_RETENTION = 1000;
const TAB_LINE_RETENTION = 2000;

function activateFallbackTab(tabs: TabSpec[], preferred?: string): string {
  if (preferred && tabs.some((tab) => tab.id === preferred)) {
    return preferred;
  }
  return tabs[0]?.id ?? "chat";
}

function nextSelectedApprovalActionId(approvalPane: ApprovalQueueState, preferred?: string): string | undefined {
  if (preferred && approvalPane.entriesByActionId[preferred]) {
    return preferred;
  }
  for (const actionId of approvalPane.order) {
    const entry = approvalPane.entriesByActionId[actionId];
    if (entry?.pending) {
      return actionId;
    }
  }
  return approvalPane.order.find((actionId) => Boolean(approvalPane.entriesByActionId[actionId]));
}

function mergeActivityEntry(current: ActivityEntry, incoming: ActivityEntry): ActivityEntry {
  const currentDetail = current.detail ?? [];
  const incomingDetail = incoming.detail ?? [];
  const mergedDetail = [...currentDetail];
  for (const line of incomingDetail) {
    if (!mergedDetail.includes(line)) {
      mergedDetail.push(line);
    }
  }
  return {
    ...current,
    ...incoming,
    phase: incoming.phase,
    summary: incoming.summary ?? current.summary,
    detail: mergedDetail.length > 0 ? mergedDetail : undefined,
    raw: incoming.raw ?? current.raw,
    timestamp: incoming.timestamp ?? current.timestamp,
  };
}

function mergeActivityEntries(current: ActivityEntry[], incoming: ActivityEntry[]): ActivityEntry[] {
  let next = [...current];
  for (const entry of incoming) {
    if (entry.correlationId) {
      const index = next.findIndex(
        (candidate) => candidate.correlationId === entry.correlationId && candidate.kind === entry.kind,
      );
      if (index >= 0) {
        const merged = mergeActivityEntry(next[index], entry);
        next = [merged, ...next.filter((_, candidateIndex) => candidateIndex !== index)];
        continue;
      }
    }
    next = [entry, ...next];
  }
  return next.slice(0, ACTIVITY_ENTRY_RETENTION);
}

function activeTabId(state: AppState): string {
  return state.uiMode.activeTabId;
}

function projectedChatTraceLines(state: AppState, executionEventLog: AppState["executionEventLog"]): AppState["chatTraceLines"] {
  return projectChatTraceLines(executionEventLog, {
    visibilityMode: state.activityFeed.visibilityMode,
    showRaw: state.activityFeed.showRaw,
  });
}

export const initialState: AppState = {
  uiMode: {
    activeTabId: "chat",
    activeOverlay: {kind: "none"},
    sidebarVisible: "collapsed",
    sidebarMode: "toc",
    focusedPaneId: "chat",
    compactMode: false,
  },
  bridgeStatus: "booting",
  routePolicy: initialRoutePolicy,
  executionEventLog: [],
  chatTraceLines: [],
  sessionContinuity: {
    continuityMode: "fresh",
    boundedHistory: [],
    historyLimit: 24,
    compactionPolicy: {
      eventCount: 0,
      compactableRatio: 0,
      protectedEventTypes: [],
      recentEventTypes: [],
    },
  },
  prompt: "",
  tabs: initialTabs,
  paneScrollOffsets: {},
  paneFocusIndices: {},
  liveRepoPreview: initialTabs.find((tab) => tab.id === "repo")?.preview,
  liveControlPreview: initialTabs.find((tab) => tab.id === "control")?.preview,
  authoritativeSurfaces: {
    repo: false,
    control: false,
    sessions: false,
    approvals: false,
    models: false,
    agents: false,
  },
  approvalPane: {
    entriesByActionId: {},
    order: [],
    historyBacked: false,
  },
  sessionPane: {
    detailsBySessionId: {},
  },
  activityFeed: {
    entries: [],
    visibilityMode: "expanded",
    showRaw: false,
  },
  outline: buildInitialOutline(),
  statusLine: "bridge booting",
  footerHint: "Keys: Tab/Shift-Tab tabs | \u2190/\u2192 tabs | ^K switch panes | ^B sidebar | 1/2/3 sidebar | ^G ^R ^O ^M ^A ^P ^E ^T ^Y panes | ^H ^J ^N transparency",
};

export function reduceApp(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "batch":
      return action.actions.reduce(reduceApp, state);
    case "state.replace":
      return action.state;
    case "prompt.append":
      return {...state, prompt: state.prompt + action.value};
    case "prompt.backspace":
      return {...state, prompt: state.prompt.slice(0, -1)};
    case "prompt.clear":
      return {...state, prompt: ""};
    case "bridge.status":
      return {...state, bridgeStatus: action.status};
    case "bridge.config": {
      const nextStrategy = action.strategy ?? state.routePolicy.strategy;
      return {
        ...state,
        routePolicy: routePolicyWithConfig(state.routePolicy, action.provider, action.model, nextStrategy),
      };
    }
    case "route.policy.set":
      return {...state, routePolicy: action.policy};
    case "execution.events.ingest": {
      const executionEventLog = mergeExecutionEvents(state.executionEventLog, action.events);
      const chatTraceLines = projectedChatTraceLines(state, executionEventLog);
      const thinkingLines = projectPaneLines("thinking", executionEventLog);
      const toolLines = projectPaneLines("tools", executionEventLog);
      const timelineLines = projectPaneLines("timeline", executionEventLog);
      return {
        ...state,
        executionEventLog,
        chatTraceLines,
        activityFeed: {
          ...state.activityFeed,
          entries: projectActivityEntries(executionEventLog),
        },
        tabs: state.tabs.map((tab) => {
          if (tab.id === "thinking") {
            return {...tab, lines: thinkingLines};
          }
          if (tab.id === "tools") {
            return {...tab, lines: toolLines};
          }
          if (tab.id === "timeline") {
            return {...tab, lines: timelineLines};
          }
          return tab;
        }),
      };
    }
    case "ui.compact.set":
      return {
        ...state,
        uiMode:
          state.uiMode.compactMode === action.compact
            ? state.uiMode
            : {
                ...state.uiMode,
                compactMode: action.compact,
              },
      };
    case "modelPicker.open":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {
            kind: "modelPicker",
            selectedIndex: 0,
            returnTabId: action.returnTabId ?? activeTabId(state),
          },
        },
      };
    case "modelPicker.close":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {kind: "none"},
        },
      };
    case "modelPicker.move": {
      const currentIndex = state.uiMode.activeOverlay.kind === "modelPicker" ? state.uiMode.activeOverlay.selectedIndex : 0;
      const returnTabId = state.uiMode.activeOverlay.kind === "modelPicker"
        ? state.uiMode.activeOverlay.returnTabId
        : activeTabId(state);
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {
            kind: "modelPicker",
            selectedIndex: Math.max(0, currentIndex + action.direction),
            returnTabId,
          },
        },
      };
    }
    case "modelPicker.set":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {
            kind: "modelPicker",
            selectedIndex: Math.max(0, action.index),
            returnTabId:
              state.uiMode.activeOverlay.kind === "modelPicker"
                ? state.uiMode.activeOverlay.returnTabId
                : activeTabId(state),
          },
        },
      };
    case "paneSwitcher.open":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {
            kind: "paneSwitcher",
            selectedIndex: Math.max(
              0,
              state.tabs.findIndex((tab) => tab.id === activeTabId(state)),
            ),
          },
        },
      };
    case "paneSwitcher.close":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {kind: "none"},
        },
      };
    case "paneSwitcher.set":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeOverlay: {
            kind: "paneSwitcher",
            selectedIndex: Math.max(0, action.index),
          },
        },
      };
    case "tab.replace":
      return {
        ...state,
        tabs: state.tabs.map((tab) =>
          tab.id === action.tabId
            ? {
                ...tab,
                lines: action.lines.slice(-TAB_LINE_RETENTION),
                preview: action.preview ?? tab.preview,
              }
            : tab,
        ),
      };
    case "status.set":
      return {...state, statusLine: action.value};
    case "footer.set":
      return {...state, footerHint: action.value};
    case "sidebar.toggle": {
      const cycle = {visible: "collapsed", collapsed: "hidden", hidden: "visible"} as const;
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          sidebarVisible: cycle[state.uiMode.sidebarVisible] ?? "visible",
        },
      };
    }
    case "sidebar.mode":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          sidebarMode: action.mode,
          sidebarVisible: "visible",
        },
      };
    case "tab.activate":
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeTabId: action.tabId,
          focusedPaneId: action.tabId,
          activeOverlay: {kind: "none"},
        },
      };
    case "tab.cycle": {
      const index = state.tabs.findIndex((tab) => tab.id === activeTabId(state));
      if (index === -1) {
        return state;
      }
      const nextIndex = (index + action.direction + state.tabs.length) % state.tabs.length;
      return {
        ...state,
        uiMode: {
          ...state.uiMode,
          activeTabId: state.tabs[nextIndex].id,
          focusedPaneId: state.tabs[nextIndex].id,
        },
      };
    }
    case "pane.scroll": {
      const current = state.paneScrollOffsets[action.tabId] ?? 0;
      const next = Math.min(Math.max(current + action.delta, 0), Math.max(action.maxOffset, 0));
      if (next === current) {
        return state;
      }
      return {
        ...state,
        paneScrollOffsets: {
          ...state.paneScrollOffsets,
          [action.tabId]: next,
        },
      };
    }
    case "pane.scroll.reset": {
      if ((state.paneScrollOffsets[action.tabId] ?? 0) === 0) {
        return state;
      }
      return {
        ...state,
        paneScrollOffsets: {
          ...state.paneScrollOffsets,
          [action.tabId]: 0,
        },
      };
    }
    case "pane.focus.set":
      if ((state.paneFocusIndices[action.tabId] ?? 0) === action.index) {
        return state;
      }
      return {
        ...state,
        paneFocusIndices: {
          ...state.paneFocusIndices,
          [action.tabId]: Math.max(0, action.index),
        },
        paneScrollOffsets: {
          ...state.paneScrollOffsets,
          [action.tabId]: 0,
        },
      };
    case "tab.ensure": {
      const existing = state.tabs.find((tab) => tab.id === action.tab.id);
      if (existing) {
        return state;
      }
      return {
        ...state,
        tabs: [...state.tabs, action.tab],
        uiMode: {
          ...state.uiMode,
          activeTabId: action.tab.id,
          focusedPaneId: action.tab.id,
        },
      };
    }
    case "tab.close": {
      const tabs = state.tabs.filter((tab) => tab.id !== action.tabId || !tab.closable);
      const nextActiveTabId = activateFallbackTab(
        tabs,
        activeTabId(state) === action.tabId ? undefined : activeTabId(state),
      );
      return {
        ...state,
        tabs,
        uiMode: {
          ...state.uiMode,
          activeTabId: nextActiveTabId,
          focusedPaneId: nextActiveTabId,
        },
      };
    }
    case "tab.append":
      return {
        ...state,
        tabs: state.tabs.map((tab) =>
          tab.id === action.tabId ? {...tab, lines: [...tab.lines, ...action.lines].slice(-TAB_LINE_RETENTION)} : tab,
        ),
      };
    case "live.repo.set":
      return {...state, liveRepoPreview: action.preview};
    case "live.control.set":
      return {...state, liveControlPreview: action.preview};
    case "surface.truth.reset":
      return {
        ...state,
        authoritativeSurfaces: {
          repo: false,
          control: false,
          sessions: false,
          approvals: false,
          models: false,
          agents: false,
        },
      };
    case "surface.truth.mark":
      return {
        ...state,
        authoritativeSurfaces: {
          ...state.authoritativeSurfaces,
          [action.surface]: true,
        },
      };
    case "approval.history.set":
      return {
        ...state,
        approvalPane: {
          ...action.approvalPane,
          historyBacked: true,
          lastHistorySyncAt: new Date().toISOString(),
        },
      };
    case "approval.decision.set": {
      const existing = state.approvalPane.entriesByActionId[action.decision.action_id];
      const lastSeenAt = action.lastSeenAt ?? new Date().toISOString();
      const pending = action.decision.decision === "require_approval" && action.decision.requires_confirmation;
      const status = existing?.resolution ? existing.status : pending ? "pending" : "observed";
      return {
        ...state,
        approvalPane: {
          historyBacked: false,
          lastHistorySyncAt: state.approvalPane.lastHistorySyncAt,
          selectedActionId: pending ? action.decision.action_id : state.approvalPane.selectedActionId ?? action.decision.action_id,
          entriesByActionId: {
            ...state.approvalPane.entriesByActionId,
            [action.decision.action_id]: {
              decision: action.decision,
              status,
              firstSeenAt: existing?.firstSeenAt ?? lastSeenAt,
              lastSeenAt,
              lastSourceEventType: action.sourceEventType ?? existing?.lastSourceEventType ?? "permission.decision",
              seenCount: (existing?.seenCount ?? 0) + 1,
              pending,
              resolution: existing?.resolution,
            },
          },
          order: [
            action.decision.action_id,
            ...state.approvalPane.order.filter((actionId) => actionId !== action.decision.action_id),
          ],
        },
      };
    }
    case "approval.resolution.set": {
      const existing = state.approvalPane.entriesByActionId[action.resolution.action_id];
      if (!existing) {
        return state;
      }
      const updatedApprovalPane = {
        historyBacked: false,
        lastHistorySyncAt: state.approvalPane.lastHistorySyncAt,
        selectedActionId: nextSelectedApprovalActionId(
          {
            ...state.approvalPane,
            entriesByActionId: {
              ...state.approvalPane.entriesByActionId,
              [action.resolution.action_id]: {
                ...existing,
                status: action.resolution.resolution,
                pending: false,
                resolution: action.resolution,
                lastSeenAt: action.resolution.resolved_at,
                lastSourceEventType: action.sourceEventType ?? "permission.resolution",
              },
            },
          },
          state.approvalPane.selectedActionId === action.resolution.action_id
            ? undefined
            : state.approvalPane.selectedActionId,
        ),
        entriesByActionId: {
          ...state.approvalPane.entriesByActionId,
          [action.resolution.action_id]: {
            ...existing,
            status: action.resolution.resolution,
            pending: false,
            resolution: action.resolution,
            lastSeenAt: action.resolution.resolved_at,
            lastSourceEventType: action.sourceEventType ?? "permission.resolution",
          },
        },
        order: [
          action.resolution.action_id,
          ...state.approvalPane.order.filter((actionId) => actionId !== action.resolution.action_id),
        ],
      };
      return {
        ...state,
        approvalPane: updatedApprovalPane,
      };
    }
    case "approval.outcome.set": {
      const existing = state.approvalPane.entriesByActionId[action.outcome.action_id];
      if (!existing) {
        return state;
      }
      return {
        ...state,
        approvalPane: {
          historyBacked: false,
          lastHistorySyncAt: state.approvalPane.lastHistorySyncAt,
          selectedActionId: state.approvalPane.selectedActionId,
          entriesByActionId: {
            ...state.approvalPane.entriesByActionId,
            [action.outcome.action_id]: {
              ...existing,
              status: action.outcome.outcome,
              outcome: action.outcome,
              pending: false,
              lastSeenAt: action.outcome.outcome_at,
              lastSourceEventType: action.sourceEventType ?? "permission.outcome",
            },
          },
          order: [
            action.outcome.action_id,
            ...state.approvalPane.order.filter((actionId) => actionId !== action.outcome.action_id),
          ],
        },
      };
    }
    case "approval.select":
      return {
        ...state,
        approvalPane: {
          ...state.approvalPane,
          selectedActionId: action.actionId,
        },
      };
    case "session.catalog.set":
      return {
        ...state,
        sessionPane: {
          ...state.sessionPane,
          catalog: action.catalog,
          selectedSessionId:
            action.selectedSessionId ??
            state.sessionPane.selectedSessionId ??
            action.catalog.sessions[0]?.session.session_id,
        },
      };
    case "session.detail.set":
      return {
        ...state,
        sessionPane: {
          ...state.sessionPane,
          selectedSessionId: action.detail.session.session_id,
          detailsBySessionId: {
            ...state.sessionPane.detailsBySessionId,
            [action.detail.session.session_id]: action.detail,
          },
        },
      };
    case "session.continuity.set":
      return {
        ...state,
        sessionContinuity: action.continuity,
      };
    case "session.select":
      return {
        ...state,
        sessionPane: {
          ...state.sessionPane,
          selectedSessionId: action.sessionId,
        },
      };
    case "activity.ingest":
      return {
        ...state,
        activityFeed: {
          ...state.activityFeed,
          entries: mergeActivityEntries(state.activityFeed.entries, action.entries),
        },
      };
    case "activity.visibility.toggle":
      return {
        ...state,
        activityFeed: {
          ...state.activityFeed,
          visibilityMode: state.activityFeed.visibilityMode === "compact" ? "expanded" : "compact",
        },
        chatTraceLines: projectedChatTraceLines(
          {
            ...state,
            activityFeed: {
              ...state.activityFeed,
              visibilityMode: state.activityFeed.visibilityMode === "compact" ? "expanded" : "compact",
            },
          },
          state.executionEventLog,
        ),
      };
    case "activity.raw.toggle":
      return {
        ...state,
        activityFeed: {
          ...state.activityFeed,
          showRaw: !state.activityFeed.showRaw,
        },
        chatTraceLines: projectedChatTraceLines(
          {
            ...state,
            activityFeed: {
              ...state.activityFeed,
              showRaw: !state.activityFeed.showRaw,
            },
          },
          state.executionEventLog,
        ),
      };
    case "outline.set":
      return {...state, outline: action.outline};
    default:
      return state;
  }
}
