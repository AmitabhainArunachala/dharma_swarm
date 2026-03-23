"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchChatStatus, fetchHealth } from "@/lib/api";
import {
  buildRuntimeControlPlaneSnapshot,
  normalizeRuntimeControlPlaneResponses,
  type RuntimeControlPlaneData,
} from "@/lib/runtimeControlPlane";

const DEFAULT_REFRESH_INTERVAL_MS = 30_000;

async function loadRuntimeControlPlane(): Promise<RuntimeControlPlaneData> {
  const [chatResponse, healthResponse] = await Promise.all([
    fetchChatStatus(),
    fetchHealth(),
  ]);
  return normalizeRuntimeControlPlaneResponses(chatResponse, healthResponse);
}

export function useRuntimeControlPlane(options?: { refetchInterval?: number }) {
  const query = useQuery<RuntimeControlPlaneData>({
    queryKey: ["runtime-control-plane"],
    queryFn: loadRuntimeControlPlane,
    refetchInterval: options?.refetchInterval ?? DEFAULT_REFRESH_INTERVAL_MS,
  });

  const data = query.data ?? {
    chatStatus: null,
    health: null,
    chatError: null,
    healthError: null,
    error: null,
  };
  const error =
    data.error ??
    (query.error instanceof Error ? query.error.message : query.error ? String(query.error) : null);

  return {
    ...query,
    chatStatus: data.chatStatus,
    health: data.health,
    error,
    snapshot: buildRuntimeControlPlaneSnapshot({
      chatStatus: data.chatStatus,
      health: data.health,
      chatError: data.chatError,
      healthError: data.healthError,
      error,
    }),
    refresh: query.refetch,
  };
}
