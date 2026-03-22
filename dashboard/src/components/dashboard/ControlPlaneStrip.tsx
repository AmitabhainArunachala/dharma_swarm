"use client";

import Link from "next/link";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import {
  buildControlPlanePosture,
  buildControlPlaneStripCells,
  buildControlPlaneStripSupport,
  buildControlPlaneSyncState,
  type ControlPlaneSyncState,
} from "@/lib/controlPlaneShell";
import type { ControlPlaneSurface } from "@/lib/controlPlaneSurfaces";
import { colors } from "@/lib/theme";
import type { RuntimeControlPlaneSnapshot } from "@/lib/runtimeControlPlane";

interface ControlPlaneStripProps {
  snapshot: RuntimeControlPlaneSnapshot;
  surfaces?: ControlPlaneSurface[];
  syncState?: ControlPlaneSyncState;
  onRefresh?: () => void;
}

function toneColor(kind: RuntimeControlPlaneSnapshot["statusKind"]): string {
  if (kind === "ok") return colors.rokusho;
  if (kind === "warn") return colors.kinpaku;
  if (kind === "error") return colors.bengara;
  return colors.sumi[600];
}

export function ControlPlaneStrip({
  snapshot,
  surfaces,
  syncState,
  onRefresh,
}: ControlPlaneStripProps) {
  const currentSyncState = syncState ?? buildControlPlaneSyncState();
  const posture = surfaces?.length ? buildControlPlanePosture(surfaces) : null;
  const cells = buildControlPlaneStripCells({ snapshot, surfaces });
  const support = buildControlPlaneStripSupport(snapshot, surfaces);
  const refreshLabel =
    currentSyncState.label === "refreshing"
      ? "Refreshing"
      : currentSyncState.label === "syncing"
        ? "Syncing"
        : "Refresh";
  const summaryDetail = posture
    ? `${posture.postureDetail} ${snapshot.detail}`
    : snapshot.detail;

  return (
    <section className="rounded-2xl border border-sumi-700/40 bg-sumi-900/55 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sumi-500">
            Canonical Control Plane
          </div>
          <p className="mt-1 text-sm text-sumi-400">{summaryDetail}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="rounded-full border border-sumi-700/40 bg-sumi-950/70 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-sumi-300"
            title={currentSyncState.detail}
          >
            {currentSyncState.label}
          </span>
          {onRefresh ? (
            <button
              onClick={onRefresh}
              disabled={currentSyncState.busy}
              className="inline-flex items-center gap-2 rounded-lg border border-sumi-700/40 bg-sumi-950/70 px-3 py-1.5 text-[11px] font-medium text-sumi-300 transition-colors hover:bg-sumi-900 disabled:cursor-not-allowed disabled:opacity-70"
            >
              <RefreshCw size={12} className={currentSyncState.busy ? "animate-spin" : ""} />
              {refreshLabel}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {cells.map((cell) => (
          <StripCell
            key={cell.label}
            label={cell.label}
            value={cell.value}
            accent={toneColor(cell.tone)}
          />
        ))}
      </div>

      {support ? (
        <div
          className="mt-4 rounded-xl border px-4 py-3"
          style={{
            borderColor: `color-mix(in srgb, ${toneColor(support.tone)} 28%, transparent)`,
            backgroundColor: `color-mix(in srgb, ${toneColor(support.tone)} 10%, transparent)`,
          }}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div
                className="text-[10px] font-semibold uppercase tracking-[0.14em]"
                style={{ color: toneColor(support.tone) }}
              >
                {support.title}
              </div>
              <p className="mt-1 max-w-3xl text-sm text-sumi-300">{support.detail}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {support.commands.map((command) => (
                <code
                  key={command}
                  className="rounded bg-sumi-950/75 px-2 py-1 text-[10px] text-sumi-300"
                >
                  {command}
                </code>
              ))}
              {support.href && support.actionLabel ? (
                <Link
                  href={support.href}
                  className="inline-flex items-center gap-1 rounded-lg border border-sumi-700/40 bg-sumi-950/70 px-3 py-1.5 text-[11px] font-medium transition-colors hover:bg-sumi-900"
                  style={{ color: toneColor(support.tone) }}
                >
                  {support.actionLabel}
                  <ArrowUpRight size={12} />
                </Link>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function StripCell({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-sumi-700/30 bg-sumi-950/55 px-3 py-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-sumi-500">{label}</div>
      <div className="mt-2 text-sm font-medium" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}
