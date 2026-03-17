"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { ModuleTruthOut } from "@/lib/types";

export function useModules() {
  const { data, isLoading, error } = useQuery<ModuleTruthOut[]>({
    queryKey: ["modules"],
    queryFn: () => apiFetch<ModuleTruthOut[]>("/api/modules"),
    refetchInterval: 15_000,
  });

  return {
    modules: data ?? [],
    isLoading,
    error,
  };
}
