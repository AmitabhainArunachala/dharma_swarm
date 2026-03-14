"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { StigmergyMarkOut, HeatmapCell, HotPath } from "@/lib/types";

export function useStigmergyHeatmap() {
  const { data, isLoading, error } = useQuery<HeatmapCell[]>({
    queryKey: ["stigmergy", "heatmap"],
    queryFn: () => apiFetch<HeatmapCell[]>("/api/stigmergy/heatmap"),
    refetchInterval: 15_000,
  });

  return { heatmap: data ?? [], isLoading, error };
}

export function useHotPaths() {
  const { data, isLoading, error } = useQuery<HotPath[]>({
    queryKey: ["stigmergy", "hot-paths"],
    queryFn: () => apiFetch<HotPath[]>("/api/stigmergy/hot-paths"),
    refetchInterval: 10_000,
  });

  return { hotPaths: data ?? [], isLoading, error };
}

export function useHighSalience() {
  const { data, isLoading, error } = useQuery<StigmergyMarkOut[]>({
    queryKey: ["stigmergy", "high-salience"],
    queryFn: () => apiFetch<StigmergyMarkOut[]>("/api/stigmergy/high-salience"),
    refetchInterval: 10_000,
  });

  return { marks: data ?? [], isLoading, error };
}
