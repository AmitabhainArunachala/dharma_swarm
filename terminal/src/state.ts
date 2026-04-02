import {buildInitialOutline, buildInitialTabs} from "./mockContent.js";
import type {AppAction, AppState, ApprovalQueueState, TabSpec} from "./types.js";

const initialTabs = buildInitialTabs();

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

export const initialState: AppState = {
  sidebarVisible: true,
  sidebarMode: "toc",
  bridgeStatus: "booting",
  provider: "codex",
  model: "gpt-5.4",
  strategy: "responsive",
  modelTargets: [],
  modelPickerVisible: false,
  modelPickerIndex: 0,
  modelPickerReturnTabId: "chat",
  prompt: "",
  activeTabId: "chat",
  tabs: initialTabs,
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
  outline: buildInitialOutline(),
  statusLine: "bridge booting",
  footerHint: "Keys: Tab/Shift-Tab tabs | \u2190/\u2192 tabs | ^B sidebar | 1/2/3 sidebar | ^G ^R ^O ^M ^A ^P ^E ^T ^Y panes",
};

export function reduceApp(state: AppState, action: AppAction): AppState {
  switch (action.type) {
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
    case "bridge.config":
      return {...state, provider: action.provider, model: action.model, strategy: action.strategy ?? state.strategy};
    case "modelPicker.open":
      return {
        ...state,
        modelPickerVisible: true,
        modelPickerIndex: 0,
        modelPickerReturnTabId: action.returnTabId ?? (state.activeTabId === "models" ? "chat" : state.activeTabId),
        activeTabId: "models",
      };
    case "modelPicker.close":
      return {
        ...state,
        modelPickerVisible: false,
        activeTabId: state.activeTabId === "models" ? state.modelPickerReturnTabId || "chat" : state.activeTabId,
      };
    case "modelPicker.move": {
      return {
        ...state,
        modelPickerVisible: true,
        modelPickerIndex: Math.max(0, state.modelPickerIndex + action.direction),
      };
    }
    case "modelPicker.set":
      return {...state, modelPickerVisible: true, modelPickerIndex: Math.max(0, action.index)};
    case "tab.replace":
      return {
        ...state,
        modelTargets: action.tabId === "models" && Array.isArray(action.modelTargets) ? action.modelTargets : state.modelTargets,
        tabs: state.tabs.map((tab) =>
          tab.id === action.tabId
            ? {
                ...tab,
                lines: action.lines.slice(-200),
                preview: action.preview ?? tab.preview,
              }
            : tab,
        ),
      };
    case "status.set":
      return {...state, statusLine: action.value};
    case "footer.set":
      return {...state, footerHint: action.value};
    case "sidebar.toggle":
      return {...state, sidebarVisible: !state.sidebarVisible};
    case "sidebar.mode":
      return {...state, sidebarMode: action.mode, sidebarVisible: true};
    case "tab.activate":
      return {
        ...state,
        activeTabId: action.tabId,
        modelPickerVisible: action.tabId === "models" ? state.modelPickerVisible : false,
      };
    case "tab.cycle": {
      const index = state.tabs.findIndex((tab) => tab.id === state.activeTabId);
      if (index === -1) {
        return state;
      }
      const nextIndex = (index + action.direction + state.tabs.length) % state.tabs.length;
      return {...state, activeTabId: state.tabs[nextIndex].id};
    }
    case "tab.ensure": {
      const existing = state.tabs.find((tab) => tab.id === action.tab.id);
      if (existing) {
        return state;
      }
      return {
        ...state,
        tabs: [...state.tabs, action.tab],
        activeTabId: action.tab.id,
      };
    }
    case "tab.close": {
      const tabs = state.tabs.filter((tab) => tab.id !== action.tabId || !tab.closable);
      return {
        ...state,
        tabs,
        activeTabId: activateFallbackTab(tabs, state.activeTabId === action.tabId ? undefined : state.activeTabId),
      };
    }
    case "tab.append":
      return {
        ...state,
        tabs: state.tabs.map((tab) =>
          tab.id === action.tabId ? {...tab, lines: [...tab.lines, ...action.lines].slice(-200)} : tab,
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
    case "session.select":
      return {
        ...state,
        sessionPane: {
          ...state.sessionPane,
          selectedSessionId: action.sessionId,
        },
      };
    case "outline.set":
      return {...state, outline: action.outline};
    default:
      return state;
  }
}
