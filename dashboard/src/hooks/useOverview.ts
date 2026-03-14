"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { SwarmOverview } from "@/lib/types";

export function useOverview() {
  const { data, isLoading, error } = useQuery<SwarmOverview>({
    queryKey: ["overview"],
    queryFn: () => apiFetch<SwarmOverview>("/api/overview"),
    refetchInterval: 5_000,
  });

  return {
    overview: data ?? null,
    isLoading,
    error,
  };
}
