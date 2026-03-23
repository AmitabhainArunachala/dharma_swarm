import assert from "node:assert/strict";
import test from "node:test";

import {
  buildChatSessionConnectionState,
  startPendingChatSession,
} from "./chatSessionContract.ts";

test("startPendingChatSession keeps the UI pending until the backend emits a session id", () => {
  assert.equal(startPendingChatSession("sess-previous"), "");
  assert.equal(startPendingChatSession(""), "");
});

test("buildChatSessionConnectionState marks a live turn without a backend session as pending", () => {
  const state = buildChatSessionConnectionState({
    sessionId: "",
    isStreaming: true,
    wsConnected: false,
  });

  assert.equal(state.phase, "pending");
  assert.equal(state.sessionLabel, "allocating");
  assert.equal(state.socketLabel, "awaiting session");
});

test("buildChatSessionConnectionState distinguishes between linking and linked websocket states", () => {
  const linking = buildChatSessionConnectionState({
    sessionId: "dash-test-session",
    isStreaming: true,
    wsConnected: false,
  });

  assert.equal(linking.phase, "linking");
  assert.equal(linking.sessionLabel, "dash-test-session");
  assert.equal(linking.socketLabel, "linking");

  const linked = buildChatSessionConnectionState({
    sessionId: "dash-test-session",
    isStreaming: false,
    wsConnected: true,
  });

  assert.equal(linked.phase, "linked");
  assert.equal(linked.sessionLabel, "dash-test-session");
  assert.equal(linked.socketLabel, "linked");
});

test("buildChatSessionConnectionState falls back to idle when no turn is active", () => {
  const state = buildChatSessionConnectionState({
    sessionId: "",
    isStreaming: false,
    wsConnected: false,
  });

  assert.equal(state.phase, "idle");
  assert.equal(state.sessionLabel, "idle");
  assert.equal(state.socketLabel, "idle");
});

test("buildChatSessionConnectionState marks the session rail as degraded when the websocket template is not advertised", () => {
  const state = buildChatSessionConnectionState({
    sessionId: "dash-test-session",
    isStreaming: false,
    wsConnected: false,
    feedAdvertised: false,
  });

  assert.equal(state.phase, "degraded");
  assert.equal(state.sessionLabel, "dash-test-session");
  assert.equal(state.socketLabel, "not advertised");
});

test("buildChatSessionConnectionState keeps pending allocation visible even when the session rail is degraded", () => {
  const state = buildChatSessionConnectionState({
    sessionId: "",
    isStreaming: true,
    wsConnected: false,
    feedAdvertised: false,
  });

  assert.equal(state.phase, "degraded");
  assert.equal(state.sessionLabel, "allocating");
  assert.equal(state.socketLabel, "not advertised");
});
