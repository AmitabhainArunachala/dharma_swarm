import assert from "node:assert/strict";
import test from "node:test";

import type { ApiResponse, ChatStatusOut, HealthOut } from "./types.ts";
import {
  buildRuntimeControlPlaneSnapshot,
  normalizeRuntimeControlPlaneResponses,
} from "./runtimeControlPlane.ts";

function chatOk(data: ChatStatusOut): ApiResponse<ChatStatusOut> {
  return {
    status: "ok",
    data,
    error: "",
    timestamp: "2026-03-20T00:00:00.000Z",
  };
}

function healthOk(data: HealthOut): ApiResponse<HealthOut> {
  return {
    status: "ok",
    data,
    error: "",
    timestamp: "2026-03-20T00:00:00.000Z",
  };
}

test("buildRuntimeControlPlaneSnapshot reflects degraded runtime using the advertised default lane", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    chatOk({
      ready: true,
      model: "openai/gpt-5.4",
      provider: "openrouter",
      tools: 9,
      max_tool_rounds: 2,
      max_tokens: 4096,
      timeout_seconds: 120,
      tool_result_max_chars: 4000,
      history_message_limit: 120,
      temperature: 0,
      persistent_sessions: true,
      chat_contract_version: "2026-03-19-command-post",
      default_profile_id: "codex_operator",
      profiles: [
        {
          id: "qwen35_surgeon",
          label: "Qwen Surgeon",
          provider: "openrouter",
          model: "qwen/qwen3-coder",
          accent: "botan",
          summary: "Surgical code lane.",
          available: false,
          availability_kind: "quota_blocked",
        },
        {
          id: "codex_operator",
          label: "Codex Operator",
          provider: "openai",
          model: "gpt-5.4",
          accent: "aozora",
          summary: "Canonical operator lane.",
          available: true,
        },
      ],
    }),
    healthOk({
      overall_status: "degraded",
      agent_health: [
        {
          agent_name: "codex",
          total_actions: 12,
          failures: 1,
          success_rate: 0.92,
          last_seen: "2026-03-20T00:00:00.000Z",
          status: "busy",
        },
      ],
      anomalies: [
        {
          id: "anom-1",
          detected_at: "2026-03-20T00:00:00.000Z",
          anomaly_type: "provider_restart",
          severity: "warning",
          description: "Provider restarted",
          related_traces: [],
        },
      ],
      total_traces: 32,
      traces_last_hour: 5,
      failure_rate: 0.125,
      mean_fitness: 0.77,
    }),
  );

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);

  assert.equal(snapshot.statusKind, "warn");
  assert.equal(snapshot.statusLabel, "degraded");
  assert.equal(snapshot.defaultProfile?.id, "codex_operator");
  assert.equal(snapshot.availableProfileCount, 1);
  assert.equal(snapshot.unavailableProfileCount, 1);
  assert.equal(snapshot.persistentSessions, true);
  assert.equal(snapshot.contractVersion, "2026-03-19-command-post");
  assert.equal(snapshot.failureRateLabel, "12.5%");
  assert.equal(snapshot.meanFitnessLabel, "0.77");
});

test("buildRuntimeControlPlaneSnapshot keeps the cold-start session rail muted before runtime data arrives", () => {
  const snapshot = buildRuntimeControlPlaneSnapshot({
    chatStatus: null,
    health: null,
    chatError: null,
    healthError: null,
    error: null,
  });

  assert.equal(snapshot.statusKind, "muted");
  assert.equal(snapshot.statusLabel, "syncing");
  assert.equal(snapshot.detail, "Waiting for the canonical runtime sources to report.");
  assert.equal(snapshot.healthStatusLabel, "awaiting health");
  assert.equal(snapshot.sessionFeedLabel, "awaiting session rail");
  assert.equal(snapshot.sessionFeedReady, false);
});

test("normalizeRuntimeControlPlaneResponses keeps health truth when chat status fails", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    {
      status: "error",
      data: undefined as ChatStatusOut,
      error: "chat router unavailable",
      timestamp: "2026-03-20T00:00:00.000Z",
    },
    healthOk({
      overall_status: "ok",
      agent_health: [
        {
          agent_name: "resident",
          total_actions: 4,
          failures: 0,
          success_rate: 1,
          last_seen: "2026-03-20T00:00:00.000Z",
          status: "idle",
        },
        {
          agent_name: "qwen",
          total_actions: 8,
          failures: 1,
          success_rate: 0.875,
          last_seen: "2026-03-20T00:00:00.000Z",
          status: "busy",
        },
      ],
      anomalies: [],
      total_traces: 18,
      traces_last_hour: 7,
      failure_rate: 0.05,
      mean_fitness: null,
    }),
  );

  assert.equal(normalized.error, "chat router unavailable");
  assert.equal(normalized.chatStatus, null);
  assert.equal(normalized.health?.agent_health.length, 2);

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);
  assert.equal(snapshot.statusKind, "error");
  assert.equal(snapshot.statusLabel, "chat unavailable");
  assert.equal(snapshot.defaultProfile, null);
  assert.equal(snapshot.agentCount, 2);
  assert.equal(snapshot.failureRateLabel, "5.0%");
  assert.equal(snapshot.meanFitnessLabel, "n/a");
});

test("buildRuntimeControlPlaneSnapshot marks health as unavailable when chat is live but /api/health fails", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    chatOk({
      ready: true,
      model: "openai/gpt-5.4",
      provider: "openai",
      tools: 9,
      max_tool_rounds: 2,
      max_tokens: 4096,
      timeout_seconds: 120,
      tool_result_max_chars: 4000,
      history_message_limit: 120,
      temperature: 0,
      persistent_sessions: true,
      chat_contract_version: "2026-03-20.control-plane",
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
      ],
    }),
    {
      status: "error",
      data: undefined as HealthOut,
      error: "health router unavailable",
      timestamp: "2026-03-20T00:00:00.000Z",
    },
  );

  assert.equal(normalized.chatError, null);
  assert.equal(normalized.healthError, "health router unavailable");
  assert.equal(normalized.error, "health router unavailable");

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);
  assert.equal(snapshot.chatReady, true);
  assert.equal(snapshot.healthReady, false);
  assert.equal(snapshot.statusKind, "warn");
  assert.equal(snapshot.statusLabel, "health unavailable");
  assert.equal(snapshot.healthStatusLabel, "health unavailable");
  assert.match(snapshot.detail, /\/api\/health is unavailable: health router unavailable/);
  assert.equal(snapshot.availableProfileCount, 1);
  assert.equal(snapshot.failureRateLabel, "unknown");
  assert.equal(snapshot.meanFitnessLabel, "n/a");
});

test("buildRuntimeControlPlaneSnapshot degrades runtime when the default lane is blocked but fallback lanes remain live", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    chatOk({
      ready: true,
      model: "openai/gpt-5.4",
      provider: "openai",
      tools: 9,
      max_tool_rounds: 2,
      max_tokens: 4096,
      timeout_seconds: 120,
      tool_result_max_chars: 4000,
      history_message_limit: 120,
      temperature: 0,
      persistent_sessions: true,
      chat_contract_version: "2026-03-20.control-plane",
      chat_ws_path_template: "/ws/chat/session/{session_id}",
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
          summary: "Strategic operator lane.",
          available: true,
        },
      ],
    }),
    healthOk({
      overall_status: "ok",
      agent_health: [
        {
          agent_name: "codex",
          total_actions: 8,
          failures: 1,
          success_rate: 0.875,
          last_seen: "2026-03-20T00:00:00.000Z",
          status: "busy",
        },
      ],
      anomalies: [],
      total_traces: 21,
      traces_last_hour: 4,
      failure_rate: 0.05,
      mean_fitness: 0.9,
    }),
  );

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);

  assert.equal(snapshot.chatReady, true);
  assert.equal(snapshot.healthReady, true);
  assert.equal(snapshot.statusKind, "warn");
  assert.equal(snapshot.statusLabel, "default lane unavailable");
  assert.equal(snapshot.availableProfileCount, 1);
  assert.equal(snapshot.unavailableProfileCount, 1);
  assert.match(snapshot.detail, /Default lane Codex Operator is blocked/i);
  assert.match(snapshot.detail, /Quota exhausted on the canonical operator lane/i);
  assert.match(snapshot.detail, /1 fallback lane remains live/i);
});

test("buildRuntimeControlPlaneSnapshot marks the session rail as degraded when chat status omits the websocket template", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    chatOk({
      ready: true,
      model: "openai/gpt-5.4",
      provider: "openai",
      tools: 9,
      max_tool_rounds: 2,
      max_tokens: 4096,
      timeout_seconds: 120,
      tool_result_max_chars: 4000,
      history_message_limit: 120,
      temperature: 0,
      persistent_sessions: false,
      chat_contract_version: "2026-03-20.control-plane",
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
          id: "claude_opus",
          label: "Claude Opus 4.6",
          provider: "openrouter",
          model: "anthropic/claude-opus-4-6",
          accent: "aozora",
          summary: "Strategic operator lane.",
          available: true,
        },
      ],
    }),
    healthOk({
      overall_status: "ok",
      agent_health: [
        {
          agent_name: "codex",
          total_actions: 4,
          failures: 0,
          success_rate: 1,
          last_seen: "2026-03-20T00:00:00.000Z",
          status: "busy",
        },
      ],
      anomalies: [],
      total_traces: 9,
      traces_last_hour: 2,
      failure_rate: 0,
      mean_fitness: 0.93,
    }),
  );

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);

  assert.equal(snapshot.statusKind, "warn");
  assert.equal(snapshot.statusLabel, "session feed unavailable");
  assert.equal(snapshot.sessionFeedReady, false);
  assert.equal(snapshot.sessionFeedLabel, "not advertised");
  assert.equal(snapshot.sessionFeedPathTemplate, null);
  assert.match(snapshot.detail, /chat_ws_path_template/i);
});

test("buildRuntimeControlPlaneSnapshot treats a fully blocked lane deck as runtime failure", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    chatOk({
      ready: true,
      model: "openai/gpt-5.4",
      provider: "openai",
      tools: 9,
      max_tool_rounds: 2,
      max_tokens: 4096,
      timeout_seconds: 120,
      tool_result_max_chars: 4000,
      history_message_limit: 120,
      temperature: 0,
      persistent_sessions: true,
      chat_contract_version: "2026-03-20.control-plane",
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
          summary: "Fallback coding lane.",
          available: false,
          availability_kind: "provider_unreachable",
        },
      ],
    }),
    healthOk({
      overall_status: "ok",
      agent_health: [
        {
          agent_name: "codex",
          total_actions: 12,
          failures: 1,
          success_rate: 0.92,
          last_seen: "2026-03-20T00:00:00.000Z",
          status: "blocked",
        },
      ],
      anomalies: [],
      total_traces: 32,
      traces_last_hour: 5,
      failure_rate: 0.125,
      mean_fitness: 0.77,
    }),
  );

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);

  assert.equal(snapshot.chatReady, true);
  assert.equal(snapshot.statusKind, "error");
  assert.equal(snapshot.statusLabel, "lanes unavailable");
  assert.equal(snapshot.availableProfileCount, 0);
  assert.equal(snapshot.unavailableProfileCount, 2);
  assert.match(snapshot.detail, /no advertised lanes are currently available/i);
  assert.match(snapshot.detail, /Codex Operator/);
});

test("buildRuntimeControlPlaneSnapshot surfaces transport-level query failures instead of pretending the lane contract is merely absent", () => {
  const snapshot = buildRuntimeControlPlaneSnapshot({
    chatStatus: null,
    health: null,
    chatError: null,
    healthError: null,
    error: "network timeout while loading runtime control plane",
  });

  assert.equal(snapshot.statusKind, "error");
  assert.equal(snapshot.statusLabel, "runtime unreachable");
  assert.equal(snapshot.healthStatusLabel, "runtime unreachable");
  assert.match(snapshot.detail, /network timeout while loading runtime control plane/i);
});

test("buildRuntimeControlPlaneSnapshot treats dual transport failures as runtime unreachable instead of lane absence", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    {
      status: "error",
      data: undefined as ChatStatusOut,
      error: "fetch failed",
      timestamp: "2026-03-20T00:00:00.000Z",
    },
    {
      status: "error",
      data: undefined as HealthOut,
      error: "fetch failed",
      timestamp: "2026-03-20T00:00:00.000Z",
    },
  );

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);

  assert.equal(snapshot.chatReady, false);
  assert.equal(snapshot.healthReady, false);
  assert.equal(snapshot.statusKind, "error");
  assert.equal(snapshot.statusLabel, "runtime unreachable");
  assert.equal(snapshot.healthStatusLabel, "runtime unreachable");
  assert.match(snapshot.detail, /canonical runtime query failed/i);
  assert.match(snapshot.detail, /fetch failed/i);
});

test("buildRuntimeControlPlaneSnapshot treats mirrored proxy upstream failures as runtime unreachable", () => {
  const normalized = normalizeRuntimeControlPlaneResponses(
    {
      status: "error",
      data: undefined as ChatStatusOut,
      error: "502 Bad Gateway: upstream connect error or disconnect/reset before headers",
      timestamp: "2026-03-20T00:00:00.000Z",
    },
    {
      status: "error",
      data: undefined as HealthOut,
      error: "502 Bad Gateway: upstream connect error or disconnect/reset before headers",
      timestamp: "2026-03-20T00:00:00.000Z",
    },
  );

  const snapshot = buildRuntimeControlPlaneSnapshot(normalized);

  assert.equal(snapshot.statusKind, "error");
  assert.equal(snapshot.statusLabel, "runtime unreachable");
  assert.equal(snapshot.healthStatusLabel, "runtime unreachable");
  assert.match(snapshot.detail, /bad gateway/i);
});
