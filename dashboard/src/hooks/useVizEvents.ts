/**
 * Hook for visualization events stream.
 *
 * Polls /api/viz/events for recent events — stigmergy marks, trajectory
 * completions, agent status changes, economic transactions. Uses
 * incremental since-timestamp to avoid re-fetching old events.
 */

import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { apiFetch } from "@/lib/api";

export interface VizEvent {
  timestamp: number;
  event_type: string;
  node_id: string | null;
  edge_id: string | null;
  data: Record<string, unknown>;
}

export function useVizEvents(refetchInterval = 5_000, limit = 50) {
  const sinceRef = useRef<number>(Date.now() / 1000 - 3600); // Start: last hour

  const query = useQuery<VizEvent[]>({
    queryKey: ["viz-events", limit],
    queryFn: async () => {
      const events = await apiFetch<VizEvent[]>(
        `/api/viz/events?since=${sinceRef.current}&limit=${limit}`,
      );
      // Advance the watermark so next poll only gets new events
      if (events.length > 0) {
        const maxTs = Math.max(...events.map((e) => e.timestamp));
        sinceRef.current = maxTs;
      }
      return events;
    },
    refetchInterval,
  });

  return query;
}
