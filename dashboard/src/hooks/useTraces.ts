"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { TraceOut } from "@/lib/types";

export function useTraces(limit = 15) {
  const { data, isLoading, error } = useQuery<TraceOut[]>({
    queryKey: ["traces", limit],
    queryFn: () => apiFetch<TraceOut[]>(`/api/commands/traces?limit=${limit}`),
    refetchInterval: 5_000,
  });

  return {
    traces: data ?? [],
    isLoading,
    error,
  };
}
