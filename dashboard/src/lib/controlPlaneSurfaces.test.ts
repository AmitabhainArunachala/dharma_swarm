import assert from "node:assert/strict";
import test from "node:test";

import { buildControlPlaneSurfaces } from "./controlPlaneSurfaces.ts";
import type { RuntimeControlPlaneSnapshot } from "./runtimeControlPlane.ts";
import type { ChatStatusOut } from "./types.ts";

function makeSnapshot(
  overrides: Partial<RuntimeControlPlaneSnapshot> = {},
): RuntimeControlPlaneSnapshot {
  return {
    chatReady: true,
    healthReady: true,
    statusKind: "warn",
    statusLabel: "degraded",
    detail: "Runtime health is degraded; keep the shell on canonical routes while providers recover.",
    healthStatusLabel: "2 anomalies · 0.84 fit",
    defaultProfile: {
      id: "claude_opus",
      label: "Claude Opus 4.6",
      provider: "openrouter",
      model: "anthropic/claude-opus-4-6",
      accent: "aozora",
      summary: "Strategic operator",
      available: true,
      availability_kind: "api_key",
      status_note: "Served by the dashboard backend via OpenRouter.",
    },
    totalProfileCount: 4,
    availableProfileCount: 3,
    unavailableProfileCount: 1,
    persistentSessions: false,
    contractVersion: "2026-03-19.chat.v1",
    sessionFeedReady: true,
    sessionFeedLabel: "/ws/chat/session/{session_id}",
    sessionFeedPathTemplate: "/ws/chat/session/{session_id}",
    agentCount: 9,
    anomalyCount: 2,
    tracesLastHour: 37,
    failureRateLabel: "2.8%",
    meanFitnessLabel: "0.84",
    ...overrides,
  };
}

function makeChatStatus(overrides: Partial<ChatStatusOut> = {}): ChatStatusOut {
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
    default_profile_id: "claude_opus",
    chat_contract_version: "2026-03-19.chat.v1",
    profiles: [
      {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "kinpaku",
        summary: "Canonical operator lane.",
        available: true,
        availability_kind: "api_key",
        status_note: "Resident Codex lane is live.",
      },
      {
        id: "claude_opus",
        label: "Claude Opus 4.6",
        provider: "openrouter",
        model: "anthropic/claude-opus-4-6",
        accent: "aozora",
        summary: "Strategic operator",
        available: true,
        availability_kind: "api_key",
        status_note: "Served by the dashboard backend via OpenRouter.",
      },
      {
        id: "qwen35_surgeon",
        label: "Qwen3 Coder",
        provider: "openrouter",
        model: "qwen/qwen3-coder",
        accent: "rokusho",
        summary: "Fast surgical coding lane",
        available: true,
        availability_kind: "api_key",
        status_note: "Served by the dashboard backend via OpenRouter.",
      },
      {
        id: "glm5_researcher",
        label: "GLM-5 Research",
        provider: "openrouter",
        model: "z-ai/glm-5",
        accent: "botan",
        summary: "Research synthesis lane.",
        available: false,
        availability_kind: "provider_unreachable",
        status_note: "Research lane is temporarily unavailable.",
      },
    ],
    ...overrides,
  };
}

test("buildControlPlaneSurfaces returns the canonical route deck with live metrics", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot(),
    chatStatus: makeChatStatus(),
    currentPath: "/dashboard/observatory",
  });

  assert.deepEqual(
    surfaces.map((surface) => surface.id),
    ["command-post", "qwen35", "observatory", "runtime"],
  );

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "3/4 lanes ready");
  assert.match(commandPost.detail, /Default lane Claude Opus 4\.6/);
  assert.equal(commandPost.tone, "warn");

  const qwen = surfaces[1];
  assert.equal(qwen.metric, "available");
  assert.match(qwen.detail, /qwen\/qwen3-coder/);
  assert.equal(qwen.tone, "ok");

  const observatory = surfaces[2];
  assert.equal(observatory.current, true);
  assert.equal(observatory.metric, "2 anomalies · 37 traces/h");
  assert.match(observatory.detail, /9 agents visible/);
  assert.equal(observatory.tone, "warn");

  const runtime = surfaces[3];
  assert.equal(runtime.metric, "degraded");
  assert.match(runtime.detail, /Contract 2026-03-19\.chat\.v1 · ephemeral sessions/);
  assert.equal(runtime.tone, "warn");
});

test("buildControlPlaneSurfaces handles missing lane advertisement without inventing route health", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      chatReady: false,
      statusKind: "error",
      statusLabel: "chat unavailable",
      defaultProfile: null,
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      anomalyCount: 0,
      agentCount: 0,
      tracesLastHour: 0,
      contractVersion: "unknown",
    }),
    chatStatus: makeChatStatus({ ready: false, profiles: [] }),
    currentPath: "/dashboard/runtime",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "Awaiting lanes");
  assert.match(commandPost.detail, /Waiting for \/api\/chat\/status/);
  assert.equal(commandPost.tone, "error");

  const qwen = surfaces[1];
  assert.equal(qwen.metric, "not advertised");
  assert.match(qwen.detail, /Qwen lane is not currently advertised/);
  assert.equal(qwen.tone, "muted");

  const observatory = surfaces[2];
  assert.equal(observatory.metric, "0 anomalies · 0 traces/h");
  assert.equal(observatory.tone, "muted");

  const runtime = surfaces[3];
  assert.equal(runtime.current, true);
  assert.equal(runtime.metric, "chat unavailable");
  assert.equal(runtime.tone, "error");
});

test("buildControlPlaneSurfaces keeps the route deck muted while canonical runtime data is still syncing", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      chatReady: false,
      healthReady: false,
      statusKind: "muted",
      statusLabel: "syncing",
      detail: "Waiting for the canonical runtime sources to report.",
      healthStatusLabel: "awaiting health",
      defaultProfile: null,
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      contractVersion: "unknown",
      sessionFeedReady: false,
      sessionFeedLabel: "awaiting session rail",
      sessionFeedPathTemplate: null,
      agentCount: 0,
      anomalyCount: 0,
      tracesLastHour: 0,
      failureRateLabel: "unknown",
      meanFitnessLabel: "n/a",
    }),
    chatStatus: null,
    currentPath: "/dashboard/command-post",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "Awaiting lanes");
  assert.match(commandPost.detail, /Waiting for \/api\/chat\/status/);
  assert.equal(commandPost.tone, "muted");
  assert.equal(commandPost.current, true);

  const qwen = surfaces[1];
  assert.equal(qwen.metric, "not advertised");
  assert.equal(qwen.tone, "muted");

  const observatory = surfaces[2];
  assert.equal(observatory.metric, "0 anomalies · 0 traces/h");
  assert.equal(observatory.tone, "muted");

  const runtime = surfaces[3];
  assert.equal(runtime.metric, "syncing");
  assert.equal(runtime.tone, "muted");
});

test("buildControlPlaneSurfaces does not invent observatory health when /api/health is unavailable", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      healthReady: false,
      statusKind: "warn",
      statusLabel: "health unavailable",
      detail: "Chat lanes are live, but /api/health is unavailable: health router unavailable",
      healthStatusLabel: "health unavailable",
      anomalyCount: 0,
      agentCount: 0,
      tracesLastHour: 0,
      persistentSessions: true,
    }),
    chatStatus: makeChatStatus(),
    currentPath: "/dashboard/qwen35",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "3/4 lanes ready");

  const observatory = surfaces[2];
  assert.equal(observatory.metric, "health unavailable");
  assert.match(observatory.detail, /\/api\/health/);
  assert.equal(observatory.tone, "warn");

  const runtime = surfaces[3];
  assert.equal(runtime.metric, "health unavailable");
  assert.match(runtime.detail, /Contract 2026-03-19\.chat\.v1 · persistent sessions · \/api\/health unavailable/);
  assert.equal(runtime.tone, "warn");
});

test("buildControlPlaneSurfaces marks Qwen as blocked when the advertised coding lane is unavailable", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "ok",
      statusLabel: "ok",
      detail: "Chat status and backend health agree on the canonical runtime path.",
      healthStatusLabel: "0 anomalies · 0.91 fit",
      availableProfileCount: 2,
      unavailableProfileCount: 2,
      anomalyCount: 0,
      tracesLastHour: 11,
    }),
    chatStatus: makeChatStatus({
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "kinpaku",
          summary: "Canonical operator lane.",
          available: true,
          availability_kind: "api_key",
          status_note: "Resident Codex lane is live.",
        },
        {
          id: "claude_opus",
          label: "Claude Opus 4.6",
          provider: "openrouter",
          model: "anthropic/claude-opus-4-6",
          accent: "aozora",
          summary: "Strategic operator",
          available: true,
          availability_kind: "api_key",
          status_note: "Served by the dashboard backend via OpenRouter.",
        },
        {
          id: "qwen35_surgeon",
          label: "Qwen3 Coder",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "rokusho",
          summary: "Fast surgical coding lane",
          available: false,
          availability_kind: "provider_unreachable",
          status_note: "Qwen provider is restarting and cannot take work.",
        },
        {
          id: "glm5_researcher",
          label: "GLM-5 Research",
          provider: "openrouter",
          model: "z-ai/glm-5",
          accent: "botan",
          summary: "Research synthesis lane.",
          available: false,
          availability_kind: "provider_unreachable",
          status_note: "Research lane is temporarily unavailable.",
        },
      ],
    }),
    currentPath: "/dashboard/command-post",
  });

  const qwen = surfaces[1];
  assert.equal(qwen.metric, "provider unreachable");
  assert.match(qwen.detail, /Qwen3 Coder is provider unreachable/i);
  assert.equal(qwen.tone, "error");
});

test("buildControlPlaneSurfaces keeps nested runtime paths on the canonical runtime surface", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot(),
    chatStatus: makeChatStatus(),
    currentPath: "/dashboard/runtime/contracts",
  });

  assert.equal(surfaces[3]?.id, "runtime");
  assert.equal(surfaces[3]?.current, true);
  assert.equal(surfaces.filter((surface) => surface.current).length, 1);
});

test("buildControlPlaneSurfaces marks command post as failed when every advertised lane is blocked", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "error",
      statusLabel: "lanes unavailable",
      detail:
        "Chat status is live, but no advertised lanes are currently available. Default lane Codex Operator is blocked.",
      defaultProfile: {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "aozora",
        summary: "Canonical operator lane.",
        available: false,
        availability_kind: "quota_blocked",
        status_note: "Quota exhausted on the canonical operator lane.",
      },
      totalProfileCount: 2,
      availableProfileCount: 0,
      unavailableProfileCount: 2,
      anomalyCount: 0,
      agentCount: 1,
      tracesLastHour: 3,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "codex_operator",
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: false,
          availability_kind: "quota_blocked",
          status_note: "Quota exhausted on the canonical operator lane.",
        },
        {
          id: "qwen35_surgeon",
          label: "Qwen Surgeon",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "rokusho",
          summary: "Fast surgical coding lane",
          available: false,
          availability_kind: "provider_unreachable",
          status_note: "Provider unreachable.",
        },
      ],
    }),
    currentPath: "/dashboard/command-post",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.current, true);
  assert.equal(commandPost.metric, "0/2 lanes ready");
  assert.equal(commandPost.tone, "error");
  assert.match(commandPost.detail, /all advertised lanes are unavailable/i);
  assert.match(commandPost.detail, /Codex Operator/);

  const qwen = surfaces[1];
  assert.equal(qwen.metric, "provider unreachable");
  assert.match(qwen.detail, /Qwen Surgeon is provider unreachable/i);
  assert.equal(qwen.tone, "error");

  const runtime = surfaces[3];
  assert.equal(runtime.metric, "lanes unavailable");
  assert.equal(runtime.tone, "error");
});

test("buildControlPlaneSurfaces blocks Command Post when the Codex operator lane is unavailable", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "warn",
      statusLabel: "degraded",
      detail: "Codex lane is blocked while peer lanes remain live.",
      defaultProfile: {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "aozora",
        summary: "Canonical operator lane.",
        available: false,
        availability_kind: "quota_blocked",
        status_note: "Quota exhausted on the canonical operator lane.",
      },
      totalProfileCount: 2,
      availableProfileCount: 1,
      unavailableProfileCount: 1,
      anomalyCount: 0,
      agentCount: 2,
      tracesLastHour: 5,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "codex_operator",
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: false,
          availability_kind: "quota_blocked",
          status_note: "Quota exhausted on the canonical operator lane.",
        },
        {
          id: "claude_opus",
          label: "Claude Opus 4.6",
          provider: "openrouter",
          model: "anthropic/claude-opus-4-6",
          accent: "aozora",
          summary: "Strategic operator",
          available: true,
          availability_kind: "api_key",
          status_note: "Served by the dashboard backend via OpenRouter.",
        },
      ],
    }),
    currentPath: "/dashboard/command-post",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.current, true);
  assert.equal(commandPost.metric, "Codex unavailable");
  assert.equal(commandPost.tone, "error");
  assert.match(commandPost.detail, /Quota exhausted on the canonical operator lane/i);
  assert.match(commandPost.detail, /dual-orchestrator relay/i);
});

test("buildControlPlaneSurfaces blocks Command Post when the Codex operator lane is not advertised", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "ok",
      statusLabel: "ok",
      detail: "Chat status and backend health agree on the canonical runtime path.",
      defaultProfile: {
        id: "claude_opus",
        label: "Claude Opus 4.6",
        provider: "openrouter",
        model: "anthropic/claude-opus-4-6",
        accent: "aozora",
        summary: "Strategic operator",
        available: true,
        availability_kind: "api_key",
        status_note: "Served by the dashboard backend via OpenRouter.",
      },
      totalProfileCount: 2,
      availableProfileCount: 2,
      unavailableProfileCount: 0,
      anomalyCount: 0,
      agentCount: 4,
      tracesLastHour: 12,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "claude_opus",
      profiles: [
        {
          id: "claude_opus",
          label: "Claude Opus 4.6",
          provider: "openrouter",
          model: "anthropic/claude-opus-4-6",
          accent: "aozora",
          summary: "Strategic operator",
          available: true,
          availability_kind: "api_key",
          status_note: "Served by the dashboard backend via OpenRouter.",
        },
        {
          id: "qwen35_surgeon",
          label: "Qwen Surgeon",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "rokusho",
          summary: "Fast surgical coding lane",
          available: true,
          availability_kind: "api_key",
          status_note: "Provider healthy.",
        },
      ],
    }),
    currentPath: "/dashboard/command-post",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.current, true);
  assert.equal(commandPost.metric, "Codex not advertised");
  assert.equal(commandPost.tone, "error");
  assert.match(commandPost.detail, /Codex lane is not currently advertised/i);
  assert.match(commandPost.detail, /dual-orchestrator relay/i);
});

test("buildControlPlaneSurfaces warns when Command Post loses its peer relay", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "warn",
      statusLabel: "degraded",
      detail: "Codex remains live, but the peer relay is unavailable.",
      defaultProfile: {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "aozora",
        summary: "Canonical operator lane.",
        available: true,
      },
      totalProfileCount: 2,
      availableProfileCount: 1,
      unavailableProfileCount: 1,
      anomalyCount: 0,
      agentCount: 2,
      tracesLastHour: 5,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "codex_operator",
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: true,
        },
        {
          id: "qwen35_surgeon",
          label: "Qwen Surgeon",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "rokusho",
          summary: "Fast surgical coding lane",
          available: false,
          availability_kind: "provider_unreachable",
          status_note: "Provider unreachable.",
        },
      ],
    }),
    currentPath: "/dashboard/command-post",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "Peer relay degraded");
  assert.equal(commandPost.tone, "warn");
  assert.match(commandPost.detail, /no peer lane is currently available/i);
  assert.match(commandPost.detail, /Codex/i);
});

test("buildControlPlaneSurfaces degrades Command Post when the session rail is not advertised", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "warn",
      statusLabel: "session feed unavailable",
      detail:
        "Chat status and backend health agree on the canonical runtime path. /api/chat/status is not advertising chat_ws_path_template for the session relay.",
      defaultProfile: {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "aozora",
        summary: "Canonical operator lane.",
        available: true,
      },
      totalProfileCount: 3,
      availableProfileCount: 3,
      unavailableProfileCount: 0,
      anomalyCount: 0,
      agentCount: 3,
      tracesLastHour: 8,
      sessionFeedReady: false,
      sessionFeedLabel: "not advertised",
      sessionFeedPathTemplate: null,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "codex_operator",
      chat_ws_path_template: undefined,
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: true,
        },
        {
          id: "claude_opus",
          label: "Claude Opus 4.6",
          provider: "openrouter",
          model: "anthropic/claude-opus-4-6",
          accent: "aozora",
          summary: "Strategic operator",
          available: true,
          availability_kind: "api_key",
          status_note: "Served by the dashboard backend via OpenRouter.",
        },
        {
          id: "qwen35_surgeon",
          label: "Qwen3 Coder",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "rokusho",
          summary: "Fast surgical coding lane",
          available: true,
          availability_kind: "api_key",
          status_note: "Served by the dashboard backend via OpenRouter.",
        },
      ],
    }),
    currentPath: "/dashboard/command-post",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "Session rail unavailable");
  assert.equal(commandPost.tone, "warn");
  assert.match(commandPost.detail, /chat_ws_path_template/i);
  assert.match(commandPost.detail, /dual-orchestrator relay/i);

  const runtime = surfaces[3];
  assert.equal(runtime.metric, "session feed unavailable");
  assert.match(runtime.detail, /session rail not advertised/i);
  assert.equal(runtime.tone, "warn");
});

test("buildControlPlaneSurfaces keeps runtime fault detail visible when the default lane is blocked", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "warn",
      statusLabel: "default lane unavailable",
      detail:
        "Default lane Codex Operator is blocked: Quota exhausted on the canonical operator lane. 1 fallback lane remains live.",
      defaultProfile: {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "aozora",
        summary: "Canonical operator lane.",
        available: false,
        availability_kind: "quota_blocked",
        status_note: "Quota exhausted on the canonical operator lane.",
      },
      totalProfileCount: 2,
      availableProfileCount: 1,
      unavailableProfileCount: 1,
      anomalyCount: 0,
      agentCount: 2,
      tracesLastHour: 5,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "codex_operator",
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: false,
          availability_kind: "quota_blocked",
          status_note: "Quota exhausted on the canonical operator lane.",
        },
        {
          id: "claude_opus",
          label: "Claude Opus 4.6",
          provider: "openrouter",
          model: "anthropic/claude-opus-4-6",
          accent: "aozora",
          summary: "Strategic operator",
          available: true,
          availability_kind: "api_key",
          status_note: "Served by the dashboard backend via OpenRouter.",
        },
      ],
    }),
    currentPath: "/dashboard/runtime",
  });

  const runtime = surfaces[3];
  assert.equal(runtime.current, true);
  assert.equal(runtime.metric, "default lane unavailable");
  assert.equal(runtime.tone, "warn");
  assert.match(runtime.detail, /Contract 2026-03-19\.chat\.v1 · ephemeral sessions/i);
  assert.match(runtime.detail, /Default lane Codex Operator is blocked/i);
  assert.match(runtime.detail, /1 fallback lane remains live/i);
});

test("buildControlPlaneSurfaces keeps observatory aligned with shared runtime failures", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      statusKind: "error",
      statusLabel: "lanes unavailable",
      detail:
        "Chat status is live, but no advertised lanes are currently available. Default lane Codex Operator is blocked.",
      defaultProfile: {
        id: "codex_operator",
        label: "Codex Operator",
        provider: "openai",
        model: "gpt-5.4",
        accent: "aozora",
        summary: "Canonical operator lane.",
        available: false,
        availability_kind: "quota_blocked",
        status_note: "Quota exhausted on the canonical operator lane.",
      },
      totalProfileCount: 2,
      availableProfileCount: 0,
      unavailableProfileCount: 2,
      anomalyCount: 1,
      agentCount: 5,
      tracesLastHour: 11,
    }),
    chatStatus: makeChatStatus({
      default_profile_id: "codex_operator",
      profiles: [
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: false,
          availability_kind: "quota_blocked",
          status_note: "Quota exhausted on the canonical operator lane.",
        },
        {
          id: "qwen35_surgeon",
          label: "Qwen Surgeon",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "rokusho",
          summary: "Fast surgical coding lane",
          available: false,
          availability_kind: "provider_unreachable",
          status_note: "Provider unreachable.",
        },
      ],
    }),
    currentPath: "/dashboard/observatory",
  });

  const observatory = surfaces[2];
  assert.equal(observatory.current, true);
  assert.equal(observatory.metric, "1 anomalies · 11 traces/h");
  assert.equal(observatory.tone, "error");
  assert.match(observatory.detail, /no advertised lanes are currently available/i);
});

test("buildControlPlaneSurfaces keeps observatory aligned when chat control is down but telemetry is still live", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      chatReady: false,
      statusKind: "error",
      statusLabel: "chat unavailable",
      detail: "Chat status unavailable: chat router unavailable",
      defaultProfile: null,
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      contractVersion: "unknown",
      anomalyCount: 0,
      agentCount: 2,
      tracesLastHour: 7,
    }),
    chatStatus: makeChatStatus({
      ready: false,
      default_profile_id: "",
      profiles: [],
    }),
    currentPath: "/dashboard/observatory",
  });

  const observatory = surfaces[2];
  assert.equal(observatory.current, true);
  assert.equal(observatory.metric, "0 anomalies · 7 traces/h");
  assert.equal(observatory.tone, "error");
  assert.match(observatory.detail, /chat status unavailable/i);
});

test("buildControlPlaneSurfaces propagates runtime transport failures across the canonical route deck", () => {
  const surfaces = buildControlPlaneSurfaces({
    snapshot: makeSnapshot({
      chatReady: false,
      healthReady: false,
      statusKind: "error",
      statusLabel: "runtime unreachable",
      detail: "Canonical runtime query failed: network timeout while loading runtime control plane",
      healthStatusLabel: "runtime unreachable",
      defaultProfile: null,
      totalProfileCount: 0,
      availableProfileCount: 0,
      unavailableProfileCount: 0,
      contractVersion: "unknown",
      anomalyCount: 0,
      agentCount: 0,
      tracesLastHour: 0,
    }),
    chatStatus: null,
    currentPath: "/dashboard/runtime",
  });

  const commandPost = surfaces[0];
  assert.equal(commandPost.metric, "runtime unreachable");
  assert.equal(commandPost.tone, "error");
  assert.match(commandPost.detail, /canonical runtime query failed/i);

  const qwen = surfaces[1];
  assert.equal(qwen.metric, "runtime unreachable");
  assert.equal(qwen.tone, "error");
  assert.match(qwen.detail, /network timeout/i);

  const observatory = surfaces[2];
  assert.equal(observatory.metric, "runtime unreachable");
  assert.equal(observatory.tone, "error");
  assert.match(observatory.detail, /runtime query failed/i);

  const runtime = surfaces[3];
  assert.equal(runtime.current, true);
  assert.equal(runtime.metric, "runtime unreachable");
  assert.equal(runtime.tone, "error");
  assert.match(runtime.detail, /network timeout/i);
});
