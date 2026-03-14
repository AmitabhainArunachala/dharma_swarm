"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { AgentOut } from "@/lib/types";

export function useAgents() {
  const { data, isLoading, error } = useQuery<AgentOut[]>({
    queryKey: ["agents"],
    queryFn: () => apiFetch<AgentOut[]>("/api/agents"),
    refetchInterval: 5_000,
  });

  return {
    agents: data ?? [],
    isLoading,
    error,
  };
}
