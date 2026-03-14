"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  ArchiveEntryOut,
  FitnessTrendPoint,
  DagData,
} from "@/lib/types";

export function useEvolutionArchive() {
  const { data, isLoading, error } = useQuery<ArchiveEntryOut[]>({
    queryKey: ["evolution", "archive"],
    queryFn: () => apiFetch<ArchiveEntryOut[]>("/api/evolution/archive"),
    refetchInterval: 10_000,
  });

  return {
    archive: data ?? [],
    isLoading,
    error,
  };
}

export function useFitnessTrend() {
  const { data, isLoading, error } = useQuery<FitnessTrendPoint[]>({
    queryKey: ["evolution", "fitness-trend"],
    queryFn: () => apiFetch<FitnessTrendPoint[]>("/api/evolution/fitness-trend"),
    refetchInterval: 10_000,
  });

  return {
    trend: data ?? [],
    isLoading,
    error,
  };
}

export function useEvolutionDag() {
  const { data, isLoading, error } = useQuery<DagData>({
    queryKey: ["evolution", "dag"],
    queryFn: () => apiFetch<DagData>("/api/evolution/dag"),
    refetchInterval: 15_000,
  });

  return {
    dag: data ?? null,
    isLoading,
    error,
  };
}
