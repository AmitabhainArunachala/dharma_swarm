"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { OntologyGraphData, OntologyDetailOut } from "@/lib/types";

export function useOntologyGraph() {
  const { data, isLoading, error } = useQuery<OntologyGraphData>({
    queryKey: ["ontology", "graph"],
    queryFn: () => apiFetch<OntologyGraphData>("/api/ontology/graph"),
    refetchInterval: 30_000,
  });

  return { graph: data ?? null, isLoading, error };
}

export function useOntologyType(name: string | null) {
  const { data, isLoading, error } = useQuery<OntologyDetailOut>({
    queryKey: ["ontology", "type", name],
    queryFn: () => apiFetch<OntologyDetailOut>(`/api/ontology/types/${name}`),
    enabled: !!name,
  });

  return { typeDetail: data ?? null, isLoading, error };
}
