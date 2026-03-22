/**
 * Hook for temporal playback via /api/viz/timeline.
 *
 * Fetches a TimelineSlice for a given time range. Used by the
 * Timeline page for scrubbing through system history.
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { VizEvent } from "./useVizEvents";
import type { VizSnapshot } from "./useVizSnapshot";

export interface TimelineSlice {
  start: number;
  end: number;
  events: VizEvent[];
  snapshot_before: VizSnapshot | null;
  snapshot_after: VizSnapshot | null;
}

export function useTimeline(start: number, end: number, enabled = true) {
  return useQuery<TimelineSlice>({
    queryKey: ["viz-timeline", start, end],
    queryFn: () =>
      apiFetch<TimelineSlice>(`/api/viz/timeline?start=${start}&end=${end}`),
    enabled,
    staleTime: 30_000, // Cache for 30s since historical data doesn't change
  });
}
