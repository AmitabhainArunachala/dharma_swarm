/**
 * Hook for the visualization data plane snapshot.
 *
 * Fetches the current system state from /api/viz/snapshot — includes
 * agent nodes, subsystem topology, stigmergy edges, and summary
 * metrics (alive/stuck counts, revenue, trajectories).
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface VizNode {
  id: string;
  label: string;
  node_type: string;
  status: string;
  metrics: Record<string, number>;
  position: { x: number; y: number } | null;
  metadata: Record<string, unknown>;
}

export interface VizEdge {
  id: string;
  source: string;
  target: string;
  edge_type: string;
  weight: number;
  metadata: Record<string, unknown>;
}

export interface VizSnapshot {
  timestamp: number;
  nodes: VizNode[];
  edges: VizEdge[];
  summary: Record<string, number>;
}

export function useVizSnapshot(refetchInterval = 10_000) {
  return useQuery<VizSnapshot>({
    queryKey: ["viz-snapshot"],
    queryFn: () => apiFetch<VizSnapshot>("/api/viz/snapshot"),
    refetchInterval,
  });
}
