"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ControlPlanePageSummary } from "@/components/dashboard/ControlPlanePageSummary";
import { ControlPlaneSurfaceGrid } from "@/components/dashboard/ControlPlaneSurfaceGrid";
import { ControlPlaneStrip } from "@/components/dashboard/ControlPlaneStrip";
import { API_TRANSPORT_MODE, BASE_URL } from "@/lib/api";
import { buildControlPlanePageMeta } from "@/lib/controlPlanePageMeta";
import {
  buildControlPlaneSyncState,
} from "@/lib/controlPlaneShell";
import { buildRuntimeOperatorHandbook } from "@/lib/runtimeOperatorHandbook";
import { buildControlPlaneSurfaces } from "@/lib/controlPlaneSurfaces";
import { colors, glowText } from "@/lib/theme";
import { useRuntimeControlPlane } from "@/hooks/useRuntimeControlPlane";
import type { ChatProfileOut } from "@/lib/types";

const PAGE_META = buildControlPlanePageMeta("runtime");
const PAGE_ACCENT = colors[PAGE_META.accent];

function transportLabel(): string {
  if (API_TRANSPORT_MODE === "same-origin") {
    return "Same-origin proxy via /api";
  }
  return BASE_URL || "Direct override";
}

function currentOriginLabel(): string {
  if (typeof window === "undefined") {
    return "server";
  }
  return window.location.origin;
}

function badgeClasses(kind: "ok" | "warn" | "error" | "muted"): string {
  switch (kind) {
    case "ok":
      return "border-emerald-900/40 bg-emerald-950/20 text-emerald-300";
    case "warn":
      return "border-amber-900/40 bg-amber-950/20 text-amber-300";
    case "error":
      return "border-red-900/40 bg-red-950/20 text-red-300";
    default:
      return "border-sumi-700/50 bg-sumi-800/50 text-sumi-300";
  }
}

function profileStatusKind(profile: ChatProfileOut): "ok" | "warn" | "error" {
  if (profile.available === true) {
    return "ok";
  }
  if (profile.availability_kind === "quota_blocked") {
    return "warn";
  }
  return "error";
}

function profileStatusLabel(profile: ChatProfileOut): string {
  if (profile.available === true) {
    return "available";
  }
  return profile.availability_kind?.replace(/_/g, " ") ?? "unavailable";
}

export default function RuntimePage() {
  const [currentOrigin, setCurrentOrigin] = useState("loading");
  const transportMode = API_TRANSPORT_MODE;
  const transportDetail = transportLabel();
  const {
    chatStatus,
    health,
    error,
    snapshot,
    isLoading,
    isFetching,
    refresh,
  } = useRuntimeControlPlane();
  const syncState = buildControlPlaneSyncState({ isLoading, isFetching });

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      setCurrentOrigin(currentOriginLabel());
    });
    return () => window.cancelAnimationFrame(frameId);
  }, []);

  const profiles = useMemo(() => chatStatus?.profiles ?? [], [chatStatus]);
  const runtimeHandbook = useMemo(() => buildRuntimeOperatorHandbook(), []);
  const surfaces = useMemo(
    () =>
      buildControlPlaneSurfaces({
        snapshot,
        chatStatus,
        currentPath: "/dashboard/runtime",
      }),
    [chatStatus, snapshot],
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div>
        <div>
          <h1
            className="font-heading text-2xl font-bold tracking-tight"
            style={{
              color: PAGE_ACCENT,
              textShadow: glowText(PAGE_ACCENT, 0.5),
            }}
          >
            {PAGE_META.pageTitle}
          </h1>
          <p className="max-w-2xl text-sm text-sumi-400">
            {PAGE_META.pageDetail}
          </p>
        </div>
      </div>

      <ControlPlanePageSummary
        routeId="runtime"
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

      <div className="grid gap-4 xl:grid-cols-4 md:grid-cols-2">
        <RuntimeCard
          label="Runtime Status"
          value={snapshot.statusLabel}
          detail={error ?? "Launchd-backed local runtime is the canonical operator path."}
          badge={badgeClasses(snapshot.statusKind)}
        />
        <RuntimeCard
          label="Browser Origin"
          value={currentOrigin}
          detail="This stays stable in the browser. The app shell wraps the same routes in a native window."
          badge={badgeClasses("muted")}
        />
        <RuntimeCard
          label="API Transport"
          value={transportMode}
          detail={transportDetail}
          badge={badgeClasses(transportMode === "same-origin" ? "ok" : "warn")}
        />
        <RuntimeCard
          label="Chat Contract"
          value={snapshot.contractVersion}
          detail={`Default profile: ${snapshot.defaultProfile?.label ?? "unknown"}`}
          badge={badgeClasses(chatStatus?.chat_contract_version ? "ok" : "muted")}
        />
      </div>

      {isLoading && !chatStatus && !health ? (
        <div className="py-12 text-center text-sumi-500">Loading runtime status...</div>
      ) : (
        <>
          <section className="rounded-2xl border border-sumi-700/50 bg-sumi-900/60 p-5 shadow-[0_0_0_1px_rgba(80,90,110,0.08)]">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-heading text-lg text-sumi-100">Chat Lanes</h2>
                <p className="text-sm text-sumi-400">
                  Server-advertised profiles only. The frontend now renders what the API
                  declares instead of relying on stale hardcoded lanes.
                </p>
              </div>
              <div className="text-xs text-sumi-500">
                Persistent sessions: {chatStatus?.persistent_sessions ? "on" : "off"}
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {profiles.length === 0 ? (
                <div className="rounded-xl border border-sumi-700/40 bg-sumi-800/30 p-4 text-sm text-sumi-500">
                  No profiles advertised by `/api/chat/status`.
                </div>
              ) : (
                profiles.map((profile) => (
                  <div
                    key={profile.id}
                    className="rounded-xl border border-sumi-700/40 bg-sumi-800/30 p-4"
                  >
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-sumi-100">{profile.label}</div>
                        <div className="text-xs text-sumi-500">
                          {profile.provider} · {profile.model}
                        </div>
                      </div>
                      <span
                        className={`rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${badgeClasses(
                          profileStatusKind(profile),
                        )}`}
                      >
                        {profileStatusLabel(profile)}
                      </span>
                    </div>
                    <p className="text-sm text-sumi-300">{profile.summary}</p>
                    {profile.status_note ? (
                      <p className="mt-3 text-xs text-sumi-500">{profile.status_note}</p>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-2xl border border-sumi-700/50 bg-sumi-900/60 p-5">
              <h2 className="font-heading text-lg text-sumi-100">Backend Health</h2>
              <p className="mt-1 text-sm text-sumi-400">
                This is the server truth behind the dashboard shell, not a separate app
                health check.
              </p>

              <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <MiniStat
                  label="Overall"
                  value={health?.overall_status ?? "unknown"}
                />
                <MiniStat
                  label="Agents"
                  value={String(health?.agent_health.length ?? 0)}
                />
                <MiniStat
                  label="Anomalies"
                  value={String(health?.anomalies.length ?? 0)}
                />
                <MiniStat
                  label="Failure Rate"
                  value={
                    health ? `${(health.failure_rate * 100).toFixed(1)}%` : "unknown"
                  }
                />
              </div>

              <div className="mt-5 space-y-3">
                {(health?.agent_health ?? []).slice(0, 8).map((agent) => (
                  <div
                    key={agent.agent_name}
                    className="flex items-center justify-between rounded-xl border border-sumi-700/40 bg-sumi-800/30 px-4 py-3"
                  >
                    <div>
                      <div className="text-sm font-medium text-sumi-100">
                        {agent.agent_name}
                      </div>
                      <div className="text-xs text-sumi-500">
                        last seen {agent.last_seen ?? "never"}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-sumi-200">
                        {(agent.success_rate * 100).toFixed(0)}%
                      </div>
                      <div className="text-xs text-sumi-500">{agent.status}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-sumi-700/50 bg-sumi-900/60 p-5">
              <h2 className="font-heading text-lg text-sumi-100">Product Shell Path</h2>
              <p className="mt-1 text-sm text-sumi-400">
                Runtime truth stays on the launchd-backed dashboard shell, the overnight
                tmux watch path, and the morning artifacts they emit. Wrapper experiments
                should stay downstream of that authority.
              </p>

              <div className="mt-5 grid gap-4 xl:grid-cols-2 text-sm text-sumi-300">
                <div className="rounded-xl border border-sumi-700/40 bg-sumi-800/30 p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.16em] text-sumi-500">
                    Stable routes
                  </div>
                  <div className="space-y-1 font-mono text-xs text-sumi-300">
                    {runtimeHandbook.stableRoutes.map((href) => (
                      <div key={href}>{href}</div>
                    ))}
                  </div>
                </div>

                {runtimeHandbook.sections.map((section) => (
                  <div
                    key={section.id}
                    className="rounded-xl border border-sumi-700/40 bg-sumi-800/30 p-4"
                  >
                    <div className="mb-2 text-xs uppercase tracking-[0.16em] text-sumi-500">
                      {section.title}
                    </div>
                    <p className="text-sm text-sumi-300">{section.detail}</p>
                    <div className="mt-3 space-y-1 font-mono text-xs text-sumi-300">
                      {section.entries.map((entry) => (
                        <div key={entry}>{entry}</div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-xl border border-sumi-700/40 bg-sumi-800/30 p-4">
                <div className="mb-2 text-xs uppercase tracking-[0.16em] text-sumi-500">
                  Wrapper path
                </div>
                <p className="text-sm text-sumi-300">{runtimeHandbook.wrapperDetail}</p>
                <Link
                  href={runtimeHandbook.nextStep.href}
                  className="mt-3 inline-flex text-sm text-aozora transition-colors hover:text-aozora/80"
                >
                  {`Open ${runtimeHandbook.nextStep.label}`}
                </Link>
              </div>
            </div>
          </section>
        </>
      )}
    </motion.div>
  );
}

function RuntimeCard({
  label,
  value,
  detail,
  badge,
}: {
  label: string;
  value: string;
  detail: string;
  badge: string;
}) {
  return (
    <div className="rounded-2xl border border-sumi-700/50 bg-sumi-900/60 p-4">
      <div className="text-xs uppercase tracking-[0.16em] text-sumi-500">{label}</div>
      <div className="mt-3 flex items-center gap-3">
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${badge}`}>
          {value}
        </span>
      </div>
      <p className="mt-3 text-sm text-sumi-400">{detail}</p>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-sumi-700/40 bg-sumi-800/30 p-4">
      <div className="text-xs uppercase tracking-[0.16em] text-sumi-500">{label}</div>
      <div className="mt-2 text-xl font-medium text-sumi-100">{value}</div>
    </div>
  );
}
