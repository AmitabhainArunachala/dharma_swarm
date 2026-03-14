"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { HealthOut } from "@/lib/types";

export function useHealth() {
  const { data, isLoading, error } = useQuery<HealthOut>({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthOut>("/api/health"),
    refetchInterval: 5_000,
  });

  return {
    health: data ?? null,
    isLoading,
    error,
  };
}
