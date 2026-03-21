"use client";

import { motion } from "framer-motion";
import { ControlPlanePageSummary } from "@/components/dashboard/ControlPlanePageSummary";
import { ControlPlaneSurfaceGrid } from "@/components/dashboard/ControlPlaneSurfaceGrid";
import { ControlPlaneStrip } from "@/components/dashboard/ControlPlaneStrip";
import { CommandPostWorkspace } from "@/components/chat/CommandPostWorkspace";
import { useRuntimeControlPlane } from "@/hooks/useRuntimeControlPlane";
import { buildControlPlanePageMeta } from "@/lib/controlPlanePageMeta";
import { buildControlPlaneSyncState } from "@/lib/controlPlaneShell";
import { buildControlPlaneSurfaces } from "@/lib/controlPlaneSurfaces";

const PAGE_META = buildControlPlanePageMeta("command-post");

export default function CommandPostPage() {
  const { chatStatus, snapshot, isLoading, isFetching, refresh } = useRuntimeControlPlane();
  const syncState = buildControlPlaneSyncState({ isLoading, isFetching });
  const surfaces = buildControlPlaneSurfaces({
    snapshot,
    chatStatus,
    currentPath: "/dashboard/command-post",
  });

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h1 className="glow-aozora font-heading text-3xl font-bold tracking-tight text-aozora">
          {PAGE_META.pageTitle}
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-sumi-600">{PAGE_META.pageDetail}</p>
      </motion.div>

      <ControlPlanePageSummary
        routeId="command-post"
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

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.05 }}
      >
        <CommandPostWorkspace
          variant="page"
          runtimeChatStatus={chatStatus}
        />
      </motion.div>
    </div>
  );
}
