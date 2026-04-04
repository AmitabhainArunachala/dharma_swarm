import {describe, expect, test} from "bun:test";

import {initialState, reduceApp} from "../src/state";
import type {AppState} from "../src/types";

function reduce(state: AppState, actions: Parameters<typeof reduceApp>[1][]): AppState {
  return actions.reduce((current, action) => reduceApp(current, action), state);
}

describe("reduceApp UI state", () => {
  test("opens and closes the route picker without changing the active tab", () => {
    const state = reduce(initialState, [
      {type: "tab.activate", tabId: "tools"},
      {type: "modelPicker.open"},
    ]);

    expect(state.uiMode.activeTabId).toBe("tools");
    expect(state.uiMode.activeOverlay).toEqual({
      kind: "modelPicker",
      selectedIndex: 0,
      returnTabId: "tools",
    });

    const closed = reduceApp(state, {type: "modelPicker.close"});
    expect(closed.uiMode.activeTabId).toBe("tools");
    expect(closed.uiMode.activeOverlay).toEqual({kind: "none"});
  });

  test("opens and closes the pane switcher as an overlay instead of a tab jump", () => {
    const state = reduce(initialState, [
      {type: "tab.activate", tabId: "timeline"},
      {type: "paneSwitcher.open"},
    ]);

    expect(state.uiMode.activeTabId).toBe("timeline");
    expect(state.uiMode.activeOverlay.kind).toBe("paneSwitcher");
    expect(state.uiMode.activeOverlay.kind === "paneSwitcher" ? state.uiMode.activeOverlay.selectedIndex : -1).toBeGreaterThanOrEqual(0);

    const closed = reduceApp(state, {type: "paneSwitcher.close"});
    expect(closed.uiMode.activeTabId).toBe("timeline");
    expect(closed.uiMode.activeOverlay).toEqual({kind: "none"});
  });

  test("toggles sidebar visibility through 3 states and forces visibility when switching sidebar modes", () => {
    const hidden = reduceApp(initialState, {type: "sidebar.toggle"});
    expect(hidden.uiMode.sidebarVisible).toBe("hidden");

    const visible = reduceApp(hidden, {type: "sidebar.toggle"});
    expect(visible.uiMode.sidebarVisible).toBe("visible");

    const collapsed = reduceApp(visible, {type: "sidebar.toggle"});
    expect(collapsed.uiMode.sidebarVisible).toBe("collapsed");

    const contextMode = reduceApp(hidden, {type: "sidebar.mode", mode: "context"});
    expect(contextMode.uiMode.sidebarMode).toBe("context");
    expect(contextMode.uiMode.sidebarVisible).toBe("visible");
  });

  test("cycles tabs and supports direct tab activation without unintended jumps", () => {
    const cycled = reduce(initialState, [
      {type: "tab.activate", tabId: "chat"},
      {type: "tab.cycle", direction: 1},
      {type: "tab.cycle", direction: -1},
    ]);

    expect(cycled.uiMode.activeTabId).toBe("chat");

    const direct = reduce(cycled, [
      {type: "modelPicker.open"},
      {type: "tab.activate", tabId: "approvals"},
    ]);

    expect(direct.uiMode.activeTabId).toBe("approvals");
    expect(direct.uiMode.focusedPaneId).toBe("approvals");
    expect(direct.uiMode.activeOverlay).toEqual({kind: "none"});
  });

  test("ingests canonical execution events into chat, tools, thinking, timeline, and activity projections", () => {
    const state = reduceApp(initialState, {
      type: "execution.events.ingest",
      events: [
        {
          id: "prompt-1",
          sourceEventType: "user_prompt",
          kind: "user_prompt",
          phase: "complete",
          title: "Inspect repo health",
          content: "Inspect repo health",
        },
        {
          id: "think-1",
          sourceEventType: "thinking_complete",
          kind: "thinking",
          phase: "complete",
          title: "Inspecting session continuity",
          content: "Inspecting session continuity",
        },
        {
          id: "tool-1",
          sourceEventType: "tool_call_complete",
          kind: "tool_call",
          phase: "running",
          title: "exec_command",
          summary: "git status",
          correlationId: "tool-1",
        },
        {
          id: "tool-1-result",
          sourceEventType: "tool_result",
          kind: "tool_result",
          phase: "complete",
          title: "exec_command",
          summary: "working tree clean",
          correlationId: "tool-1",
        },
        {
          id: "status-1",
          sourceEventType: "session_end",
          kind: "status",
          phase: "complete",
          title: "session ended",
          summary: "sess-1",
        },
      ],
    });

    expect(state.chatTraceLines.some((line) => line.kind === "user" && line.text.includes("Inspect repo health"))).toBe(true);
    expect(state.chatTraceLines.some((line) => line.kind === "system" && line.text.includes("Inspecting session continuity"))).toBe(true);
    expect(state.chatTraceLines.some((line) => line.kind === "tool" && line.text.includes("exec_command"))).toBe(true);
    expect(state.activityFeed.entries.some((entry) => entry.kind === "thinking")).toBe(true);
    expect(state.activityFeed.entries.some((entry) => entry.kind === "tool")).toBe(true);
    expect(state.activityFeed.entries.some((entry) => entry.kind === "status")).toBe(true);
    expect(state.executionEventLog).toHaveLength(5);
    expect(state.tabs.some((tab) => tab.id === "thinking")).toBe(false);
    expect(state.tabs.some((tab) => tab.id === "tools")).toBe(false);
    expect(state.tabs.some((tab) => tab.id === "timeline")).toBe(false);
  });
});
