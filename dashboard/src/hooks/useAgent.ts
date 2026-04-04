"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  AgentOut,
  AgentConfigOut,
  AgentCostOut,
  CoreFileOut,
  AvailableModelOut,
  FitnessHistoryEntry,
  TaskLogEntry,
} from "@/lib/types";

export interface AgentDetailData {
  agent: AgentOut;
  config: AgentConfigOut;
  recent_traces: {
    id: string;
    timestamp: string;
    action: string;
    state: string;
    metadata: Record<string, unknown>;
  }[];
  health_stats: {
    total_actions: number;
    failures: number;
    success_rate: number;
    last_seen: string | null;
  };
  assigned_tasks: {
    id: string;
    title: string;
    status: string;
    priority: string;
    created_at: string;
    result: string | null;
  }[];
  fitness_history: FitnessHistoryEntry[];
  cost: AgentCostOut;
  core_files: CoreFileOut[];
  available_models: AvailableModelOut[];
  available_roles: string[];
  provider_status: { provider: string; available: boolean }[];
  task_history: TaskLogEntry[];
}

export function useAgent(id: string) {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery<AgentDetailData>({
    queryKey: ["agent-detail", id],
    queryFn: () =>
      apiFetch<AgentDetailData>(
        `/api/agents/${encodeURIComponent(id)}/detail`,
      ),
    refetchInterval: 5_000,
    enabled: !!id,
  });

  const updateConfig = useMutation<
    void,
    Error,
    { model?: string; role?: string; provider?: string }
  >({
    mutationFn: (body) =>
      apiFetch(`/api/agents/${encodeURIComponent(id)}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const stopAgent = useMutation<void, Error, void>({
    mutationFn: () =>
      apiFetch(`/api/agents/${encodeURIComponent(id)}/stop`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const respawnAgent = useMutation<void, Error, Record<string, unknown>>({
    mutationFn: (body) =>
      apiFetch(`/api/fleet/respawn`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: id, ...body }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  return {
    data: data ?? null,
    agent: data?.agent ?? null,
    config: data?.config ?? null,
    traces: data?.recent_traces ?? [],
    healthStats: data?.health_stats ?? null,
    assignedTasks: data?.assigned_tasks ?? [],
    fitnessHistory: data?.fitness_history ?? [],
    cost: data?.cost ?? null,
    coreFiles: data?.core_files ?? [],
    availableModels: data?.available_models ?? [],
    availableRoles: data?.available_roles ?? [],
    providerStatus: data?.provider_status ?? [],
    taskHistory: data?.task_history ?? [],
    isLoading,
    error,
    updateConfig,
    stopAgent,
    respawnAgent,
  };
}
