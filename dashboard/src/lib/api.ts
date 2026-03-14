/**
 * DHARMA COMMAND -- Typed fetch helpers for the FastAPI backend.
 */

import type {
  AgentOut,
  AnomalyOut,
  ApiResponse,
  ArchiveEntryOut,
  ChatStatusOut,
  HeatmapCell,
  HealthOut,
  ImpactOut,
  LineageEdgeOut,
  OntologyTypeOut,
  ProvenanceOut,
  StigmergyMarkOut,
  SwarmOverview,
  TaskOut,
  TraceOut,
} from "./types";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function _fetchWrapped<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResponse<T>> {
  const url = `${BASE_URL}${path}`;

  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...init?.headers,
      },
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "Unknown error");
      return {
        status: "error",
        data: undefined as unknown as T,
        error: `${res.status} ${res.statusText}: ${body}`,
        timestamp: new Date().toISOString(),
      };
    }

    const data: T = await res.json();
    return {
      status: "ok",
      data,
      error: "",
      timestamp: new Date().toISOString(),
    };
  } catch (err) {
    return {
      status: "error",
      data: undefined as unknown as T,
      error: err instanceof Error ? err.message : String(err),
      timestamp: new Date().toISOString(),
    };
  }
}

// ---------------------------------------------------------------------------
// GET helper
// ---------------------------------------------------------------------------

function apiGet<T>(path: string): Promise<ApiResponse<T>> {
  return _fetchWrapped<T>(path, { method: "GET" });
}

// ---------------------------------------------------------------------------
// POST helper
// ---------------------------------------------------------------------------

function apiPost<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  return _fetchWrapped<T>(path, {
    method: "POST",
    body: body != null ? JSON.stringify(body) : undefined,
  });
}

// ---------------------------------------------------------------------------
// Endpoint functions
// ---------------------------------------------------------------------------

// -- Swarm ------------------------------------------------------------------

export function fetchSwarmOverview(): Promise<ApiResponse<SwarmOverview>> {
  return apiGet<SwarmOverview>("/api/swarm/overview");
}

// -- Agents -----------------------------------------------------------------

export function fetchAgents(): Promise<ApiResponse<AgentOut[]>> {
  return apiGet<AgentOut[]>("/api/agents");
}

export function fetchAgent(id: string): Promise<ApiResponse<AgentOut>> {
  return apiGet<AgentOut>(`/api/agents/${encodeURIComponent(id)}`);
}

// -- Tasks ------------------------------------------------------------------

export function fetchTasks(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ApiResponse<TaskOut[]>> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.limit != null) sp.set("limit", String(params.limit));
  if (params?.offset != null) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  return apiGet<TaskOut[]>(`/api/tasks${qs ? `?${qs}` : ""}`);
}

export function fetchTask(id: string): Promise<ApiResponse<TaskOut>> {
  return apiGet<TaskOut>(`/api/tasks/${encodeURIComponent(id)}`);
}

export function createTask(body: {
  title: string;
  description?: string;
  priority?: string;
}): Promise<ApiResponse<TaskOut>> {
  return apiPost<TaskOut>("/api/tasks", body);
}

// -- Health -----------------------------------------------------------------

export function fetchHealth(): Promise<ApiResponse<HealthOut>> {
  return apiGet<HealthOut>("/api/health");
}

export function fetchAnomalies(): Promise<ApiResponse<AnomalyOut[]>> {
  return apiGet<AnomalyOut[]>("/api/health/anomalies");
}

// -- Evolution --------------------------------------------------------------

export function fetchEvolutionArchive(params?: {
  limit?: number;
  offset?: number;
}): Promise<ApiResponse<ArchiveEntryOut[]>> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set("limit", String(params.limit));
  if (params?.offset != null) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  return apiGet<ArchiveEntryOut[]>(`/api/evolution/archive${qs ? `?${qs}` : ""}`);
}

export function fetchFitnessTrend(): Promise<
  ApiResponse<{ generation: number; fitness: number }[]>
> {
  return apiGet<{ generation: number; fitness: number }[]>(
    "/api/evolution/fitness-trend",
  );
}

// -- Traces / Lineage -------------------------------------------------------

export function fetchTraces(params?: {
  agent_id?: string;
  task_id?: string;
  limit?: number;
}): Promise<ApiResponse<TraceOut[]>> {
  const sp = new URLSearchParams();
  if (params?.agent_id) sp.set("agent_id", params.agent_id);
  if (params?.task_id) sp.set("task_id", params.task_id);
  if (params?.limit != null) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return apiGet<TraceOut[]>(`/api/traces${qs ? `?${qs}` : ""}`);
}

export function fetchLineage(entryId: string): Promise<ApiResponse<LineageEdgeOut[]>> {
  return apiGet<LineageEdgeOut[]>(
    `/api/evolution/lineage/${encodeURIComponent(entryId)}`,
  );
}

// -- Ontology ---------------------------------------------------------------

export function fetchOntology(): Promise<ApiResponse<OntologyTypeOut[]>> {
  return apiGet<OntologyTypeOut[]>("/api/ontology");
}

// -- Stigmergy --------------------------------------------------------------

export function fetchStigmergy(params?: {
  limit?: number;
  min_salience?: number;
}): Promise<ApiResponse<StigmergyMarkOut[]>> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set("limit", String(params.limit));
  if (params?.min_salience != null) sp.set("min_salience", String(params.min_salience));
  const qs = sp.toString();
  return apiGet<StigmergyMarkOut[]>(`/api/stigmergy${qs ? `?${qs}` : ""}`);
}

// -- Heatmap ----------------------------------------------------------------

export function fetchHeatmap(metric: string): Promise<ApiResponse<HeatmapCell[]>> {
  return apiGet<HeatmapCell[]>(
    `/api/heatmap/${encodeURIComponent(metric)}`,
  );
}

// -- Provenance -------------------------------------------------------------

export function fetchProvenance(
  artifactId: string,
): Promise<ApiResponse<ProvenanceOut>> {
  return apiGet<ProvenanceOut>(
    `/api/provenance/${encodeURIComponent(artifactId)}`,
  );
}

// -- Impact -----------------------------------------------------------------

export function fetchImpact(): Promise<ApiResponse<ImpactOut[]>> {
  return apiGet<ImpactOut[]>("/api/impact");
}

// -- Chat -------------------------------------------------------------------

export function fetchChatStatus(): Promise<ApiResponse<ChatStatusOut>> {
  return apiGet<ChatStatusOut>("/api/chat/status");
}

// ---------------------------------------------------------------------------
// Export base URL for WebSocket derivation
// ---------------------------------------------------------------------------

export function wsBaseUrl(): string {
  return BASE_URL.replace(/^http/, "ws");
}

export { BASE_URL };

// ---------------------------------------------------------------------------
// Legacy apiFetch -- backward-compatible with existing hooks.
// Returns T directly (unwrapped) and throws on failure.
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }

  const json = await res.json();
  // Backend wraps responses in {status, data, error, timestamp}
  // Unwrap if present, otherwise return as-is
  if (json && typeof json === "object" && "data" in json && "status" in json) {
    if (json.status === "error") {
      throw new ApiError(json.error || "Unknown error", res.status, JSON.stringify(json));
    }
    return json.data as T;
  }
  return json as T;
}
