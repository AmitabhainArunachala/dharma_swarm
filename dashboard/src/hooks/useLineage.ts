"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface LineageDag {
  nodes: {
    id: string;
    label: string;
    type: string;
    timestamp: string;
  }[];
  edges: {
    source: string;
    target: string;
    label: string;
  }[];
}

export function useLineageDag(artifactId: string | null) {
  const { data, isLoading, error } = useQuery<LineageDag>({
    queryKey: ["lineage", artifactId],
    queryFn: () => apiFetch<LineageDag>(`/api/lineage/${artifactId}/dag`),
    enabled: !!artifactId,
  });

  return { dag: data ?? null, isLoading, error };
}
