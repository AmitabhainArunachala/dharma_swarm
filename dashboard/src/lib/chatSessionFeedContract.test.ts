import assert from "node:assert/strict";
import test from "node:test";

import {
  buildChatSessionFeedChannel,
  buildChatSessionFeedIdentity,
  normalizeChatSessionFeedTemplate,
} from "./chatSessionFeedContract.ts";

test("buildChatSessionFeedIdentity follows the active operator lane even before a session exists", () => {
  const qwen = buildChatSessionFeedIdentity({
    profileId: "qwen35_surgeon",
    sessionId: "",
    wsPathTemplate: undefined,
  });
  const glm = buildChatSessionFeedIdentity({
    profileId: "glm5_operator",
    sessionId: "",
    wsPathTemplate: undefined,
  });

  assert.notEqual(qwen, glm);
});

test("buildChatSessionFeedIdentity changes when the backend allocates a new session or channel template", () => {
  const previous = buildChatSessionFeedIdentity({
    profileId: "qwen35_surgeon",
    sessionId: "sess-alpha",
    wsPathTemplate: "/ws/chat/{session_id}",
  });
  const nextSession = buildChatSessionFeedIdentity({
    profileId: "qwen35_surgeon",
    sessionId: "sess-beta",
    wsPathTemplate: "/ws/chat/{session_id}",
  });
  const nextTemplate = buildChatSessionFeedIdentity({
    profileId: "qwen35_surgeon",
    sessionId: "sess-alpha",
    wsPathTemplate: "/ws/runtime/{session_id}",
  });

  assert.notEqual(previous, nextSession);
  assert.notEqual(previous, nextTemplate);
});

test("buildChatSessionFeedIdentity stays stable for the same lane session scope", () => {
  const first = buildChatSessionFeedIdentity({
    profileId: "codex_operator",
    sessionId: "sess-codex",
    wsPathTemplate: "/ws/chat/{session_id}",
  });
  const second = buildChatSessionFeedIdentity({
    profileId: "codex_operator",
    sessionId: "sess-codex",
    wsPathTemplate: "/ws/chat/{session_id}",
  });

  assert.equal(first, second);
});

test("normalizeChatSessionFeedTemplate trims and rejects blank session-rail templates", () => {
  assert.equal(normalizeChatSessionFeedTemplate("  /ws/chat/session/{session_id}  "), "/ws/chat/session/{session_id}");
  assert.equal(normalizeChatSessionFeedTemplate("   "), null);
  assert.equal(normalizeChatSessionFeedTemplate(undefined), null);
});

test("buildChatSessionFeedChannel mirrors the backend websocket channel contract", () => {
  assert.equal(
    buildChatSessionFeedChannel({
      sessionId: "dash-test-session",
      wsPathTemplate: "/ws/chat/session/{session_id}",
    }),
    "chat/session/dash-test-session",
  );
});

test("buildChatSessionFeedChannel trims whitespace, encodes session ids, and preserves nested suffixes", () => {
  assert.equal(
    buildChatSessionFeedChannel({
      sessionId: "dash alpha/beta",
      wsPathTemplate: "  /ws/chat/session/{session_id}/events/  ",
    }),
    "chat/session/dash%20alpha%2Fbeta/events",
  );
});

test("buildChatSessionFeedChannel stays dark until the canonical session rail is fully advertised", () => {
  assert.equal(
    buildChatSessionFeedChannel({
      sessionId: "",
      wsPathTemplate: "/ws/chat/session/{session_id}",
    }),
    "",
  );
  assert.equal(
    buildChatSessionFeedChannel({
      sessionId: "dash-test-session",
      wsPathTemplate: " ",
    }),
    "",
  );
});
