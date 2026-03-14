"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface GateResult {
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  message: string;
  score: number;
  timestamp: string;
}

export interface GatesSummary {
  gates: GateResult[];
  overall: "pass" | "fail" | "warn";
  pass_count: number;
  fail_count: number;
  warn_count: number;
}

export function useGates() {
  const { data, isLoading, error } = useQuery<GatesSummary>({
    queryKey: ["gates"],
    queryFn: () => apiFetch<GatesSummary>("/api/commands/dharma"),
    refetchInterval: 10_000,
  });

  return { gates: data ?? null, isLoading, error };
}
