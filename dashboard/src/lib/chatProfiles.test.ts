import assert from "node:assert/strict";
import test from "node:test";

import {
  findAdvertisedChatProfile,
  isAdvertisedChatProfileAvailable,
  resolveCanonicalChatStatus,
  resolveChatProfileId,
  resolveCommandPostPeerProfileId,
  shortProfileLabel,
} from "./chatProfiles.ts";
import type { ChatStatusOut } from "./types.ts";

function makeStatus(overrides: Partial<ChatStatusOut> = {}): ChatStatusOut {
  return {
    ready: true,
    model: "anthropic/claude-opus-4-6",
    provider: "openrouter",
    tools: 18,
    max_tool_rounds: 40,
    max_tokens: 8192,
    timeout_seconds: 300,
    tool_result_max_chars: 24000,
    history_message_limit: 120,
    temperature: 0.3,
    persistent_sessions: false,
    default_profile_id: "codex_operator",
    chat_contract_version: "2026-03-20.chat.v1",
    profiles: [
      {
        id: "codex_operator",
        label: "Codex 5.4",
        provider: "openai",
        model: "openai/gpt-5-codex",
        accent: "kinpaku",
        summary: "Implementation-focused control agent.",
        available: true,
      },
      {
        id: "claude_opus",
        label: "Claude Opus 4.6",
        provider: "openrouter",
        model: "anthropic/claude-opus-4-6",
        accent: "aozora",
        summary: "Strategic operator.",
        available: true,
      },
      {
        id: "qwen35_surgeon",
        label: "Qwen3 Coder",
        provider: "openrouter",
        model: "qwen/qwen3-coder",
        accent: "rokusho",
        summary: "Fast surgical coding lane.",
        available: true,
      },
    ],
    ...overrides,
  };
}

test("resolveCommandPostPeerProfileId prefers Claude on the canonical command-post relay", () => {
  assert.equal(resolveCommandPostPeerProfileId(makeStatus()), "claude_opus");
});

test("resolveCommandPostPeerProfileId falls back to the first non-Codex lane when Claude is absent", () => {
  assert.equal(
    resolveCommandPostPeerProfileId(
      makeStatus({
        profiles: [
          {
            id: "codex_operator",
            label: "Codex 5.4",
            provider: "openai",
            model: "openai/gpt-5-codex",
            accent: "kinpaku",
            summary: "Implementation-focused control agent.",
            available: true,
          },
          {
            id: "qwen35_surgeon",
            label: "Qwen3 Coder",
            provider: "openrouter",
            model: "qwen/qwen3-coder",
            accent: "rokusho",
            summary: "Fast surgical coding lane.",
            available: true,
          },
          {
            id: "glm5_researcher",
            label: "GLM-5 Research",
            provider: "openrouter",
            model: "z-ai/glm-5",
            accent: "botan",
            summary: "Research synthesis lane.",
            available: true,
          },
        ],
      }),
    ),
    "qwen35_surgeon",
  );
});

test("resolveCommandPostPeerProfileId returns null when Codex is the only advertised lane", () => {
  assert.equal(
    resolveCommandPostPeerProfileId(
      makeStatus({
        profiles: [
          {
            id: "codex_operator",
            label: "Codex 5.4",
            provider: "openai",
            model: "openai/gpt-5-codex",
            accent: "kinpaku",
            summary: "Implementation-focused control agent.",
            available: true,
          },
        ],
      }),
    ),
    null,
  );
});

test("resolveChatProfileId can preserve an unadvertised peer lane when fallback is disabled", () => {
  const status = makeStatus({
    profiles: [
      {
        id: "codex_operator",
        label: "Codex 5.4",
        provider: "openai",
        model: "openai/gpt-5-codex",
        accent: "kinpaku",
        summary: "Implementation-focused control agent.",
        available: true,
      },
    ],
  });

  assert.equal(resolveChatProfileId(status, "claude_opus"), "codex_operator");
  assert.equal(
    resolveChatProfileId(status, "claude_opus", {
      allowAdvertisedFallback: false,
    }),
    "claude_opus",
  );
});

test("resolveChatProfileId keeps an advertised but unavailable surface pinned to its own lane", () => {
  const status = makeStatus({
    profiles: [
      {
        id: "codex_operator",
        label: "Codex 5.4",
        provider: "openai",
        model: "openai/gpt-5-codex",
        accent: "kinpaku",
        summary: "Implementation-focused control agent.",
        available: true,
      },
      {
        id: "qwen35_surgeon",
        label: "Qwen3 Coder",
        provider: "openrouter",
        model: "qwen/qwen3-coder",
        accent: "rokusho",
        summary: "Fast surgical coding lane.",
        available: false,
        availability_kind: "provider_unreachable",
      },
    ],
  });

  assert.equal(resolveChatProfileId(status, "qwen35_surgeon"), "qwen35_surgeon");
});

test("resolveCanonicalChatStatus prefers the runtime-advertised contract over stale lane-local status", () => {
  const runtimeStatus = makeStatus({
    default_profile_id: "claude_opus",
    chat_contract_version: "2026-03-20.runtime.v2",
  });
  const laneLocalStatus = makeStatus({
    default_profile_id: "codex_operator",
    chat_contract_version: "2026-03-19.command-post.v1",
  });

  assert.equal(
    resolveCanonicalChatStatus(runtimeStatus, laneLocalStatus),
    runtimeStatus,
  );
});

test("resolveCanonicalChatStatus falls back to the first available lane-local status when runtime truth is absent", () => {
  const codexLaneStatus = makeStatus({
    default_profile_id: "codex_operator",
    chat_contract_version: "2026-03-20.codex.v1",
  });
  const peerLaneStatus = makeStatus({
    default_profile_id: "claude_opus",
    chat_contract_version: "2026-03-20.peer.v1",
  });

  assert.equal(
    resolveCanonicalChatStatus(null, codexLaneStatus, peerLaneStatus),
    codexLaneStatus,
  );
  assert.equal(resolveCanonicalChatStatus(null, null, undefined), null);
});

test("findAdvertisedChatProfile only returns explicitly advertised lanes", () => {
  const status = makeStatus();

  assert.equal(findAdvertisedChatProfile(status, "qwen35_surgeon")?.id, "qwen35_surgeon");
  assert.equal(findAdvertisedChatProfile(status, "missing_lane"), null);
});

test("isAdvertisedChatProfileAvailable distinguishes advertised readiness from missing telemetry agents", () => {
  const advertisedReady = makeStatus();
  const advertisedUnavailable = makeStatus({
    profiles: [
      {
        id: "qwen35_surgeon",
        label: "Qwen3 Coder",
        provider: "openrouter",
        model: "qwen/qwen3-coder",
        accent: "rokusho",
        summary: "Fast surgical coding lane.",
        available: false,
      },
    ],
  });

  assert.equal(isAdvertisedChatProfileAvailable(advertisedReady, "qwen35_surgeon"), true);
  assert.equal(
    isAdvertisedChatProfileAvailable(advertisedUnavailable, "qwen35_surgeon"),
    false,
  );
  assert.equal(isAdvertisedChatProfileAvailable(advertisedReady, "missing_lane"), false);
});

test("shortProfileLabel keeps certified peer lanes compact in the dropdown", () => {
  assert.equal(
    shortProfileLabel({
      id: "sonnet46_operator",
      label: "Claude Sonnet 4.6",
      provider: "claude_code",
      model: "claude-sonnet-4-6",
      accent: "fuji",
      summary: "Certified execution peer.",
      available: true,
    }),
    "Sonnet",
  );
  assert.equal(
    shortProfileLabel({
      id: "kimi_k25_scout",
      label: "Kimi K2.5 Scout",
      provider: "openrouter",
      model: "moonshotai/kimi-k2.5",
      accent: "bengara",
      summary: "Certified reconnaissance lane.",
      available: true,
    }),
    "Kimi",
  );
});
