"use client";

/**
 * DHARMA COMMAND -- Agent Observatory (L3).
 *
 * The observatory backend (/api/agents/observatory) does not exist yet.
 * This page shows the control-plane shell (which uses real endpoints) and
 * an honest empty state for the observatory-specific sections.
 */

import { motion } from "framer-motion";
import {
  HeartPulse,
  AlertTriangle,
} from "lucide-react";
import { ControlPlanePageSummary } from "@/components/dashboard/ControlPlanePageSummary";
import { ControlPlaneSurfaceGrid } from "@/components/dashboard/ControlPlaneSurfaceGrid";
import { ControlPlaneStrip } from "@/components/dashboard/ControlPlaneStrip";
import { useRuntimeControlPlane } from "@/hooks/useRuntimeControlPlane";
import { buildControlPlanePageMeta } from "@/lib/controlPlanePageMeta";
import { buildControlPlaneSyncState } from "@/lib/controlPlaneShell";
import { buildControlPlaneSurfaces } from "@/lib/controlPlaneSurfaces";
import { colors, glowText } from "@/lib/theme";

const PAGE_META = buildControlPlanePageMeta("observatory");
const PAGE_ACCENT = colors[PAGE_META.accent];

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function ObservatoryPage() {
  const {
    chatStatus,
    snapshot,
    isLoading: controlPlaneLoading,
    isFetching: controlPlaneFetching,
    refresh,
  } = useRuntimeControlPlane();
  const syncState = buildControlPlaneSyncState({
    isLoading: controlPlaneLoading,
    isFetching: controlPlaneFetching,
  });
  const surfaces = buildControlPlaneSurfaces({
    snapshot,
    chatStatus,
    currentPath: "/dashboard/observatory",
  });
  return (
    <motion.div
      className="space-y-6"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* ================================================================ */}
      {/* Header */}
      {/* ================================================================ */}
      <div>
        <div className="flex items-center gap-3">
          <HeartPulse size={22} style={{ color: PAGE_ACCENT }} />
          <h1
            className="font-heading text-2xl font-bold tracking-tight"
            style={{
              color: PAGE_ACCENT,
              textShadow: glowText(PAGE_ACCENT, 0.5),
            }}
          >
            {PAGE_META.pageTitle}
          </h1>
        </div>
        <p className="mt-1.5 text-sm" style={{ color: colors.sumi[600] }}>
          {PAGE_META.pageDetail}
        </p>
      </div>

      <ControlPlanePageSummary
        routeId="observatory"
        snapshot={snapshot}
        surfaces={surfaces}
      />

      <ControlPlaneStrip
        snapshot={snapshot}
        surfaces={surfaces}
        syncState={syncState}
        onRefresh={() => {
          void refresh();
        }}
      />

      <ControlPlaneSurfaceGrid
        surfaces={surfaces}
        title={PAGE_META.deckTitle}
        detail={PAGE_META.deckDetail}
      />

      {/* ================================================================ */}
      {/* Honest empty state — observatory backend not yet implemented */}
      {/* ================================================================ */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="glass-panel flex flex-col items-center justify-center py-16 text-center"
      >
        <AlertTriangle size={28} className="mb-3" style={{ color: colors.kinpaku }} />
        <h2
          className="font-heading text-lg font-semibold"
          style={{ color: colors.torinoko }}
        >
          Observatory backend not yet implemented
        </h2>
        <p className="mt-2 max-w-lg text-sm" style={{ color: colors.sumi[600] }}>
          The fleet-health grid, fitness leaderboard, anomaly feed, and activity
          timeline require a dedicated <code className="font-mono text-xs">/api/agents/observatory</code>{" "}
          endpoint that does not exist yet. The control-plane surface above
          reflects live data from real endpoints.
        </p>
      </motion.div>
    </motion.div>
  );
}
