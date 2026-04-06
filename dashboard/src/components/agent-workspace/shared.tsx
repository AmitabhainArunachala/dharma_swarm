"use client";

import { ArrowLeft, type LucideIcon } from "lucide-react";
import { HPBar } from "@/components/game/HPBar";
import { colors, glowBorder } from "@/lib/theme";

/* ─── Animation Variants ──────────────────────────────────── */

export const stagger = {
  container: {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.06 },
    },
  },
  item: {
    hidden: { opacity: 0, y: 14 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] },
    },
  },
};

/* ─── Helpers ─────────────────────────────────────────────── */

export function agentHealthStatus(
  status: string,
  lastHeartbeat: string | null,
): "healthy" | "degraded" | "critical" | "unknown" {
  const s = status?.toLowerCase();
  if (s === "dead" || s === "stopping") return "critical";
  if (s === "idle" && !lastHeartbeat) return "unknown";
  if (s === "busy" || s === "idle") return "healthy";
  return "degraded";
}

export function agentHPPercent(status: string, lastHeartbeat: string | null): number {
  const h = agentHealthStatus(status, lastHeartbeat);
  if (h === "healthy") return 100;
  if (h === "degraded") return 60;
  if (h === "critical") return 20;
  return 50;
}

export const TIER_COLORS: Record<string, string> = {
  frontier: colors.aozora,
  strong: colors.kinpaku,
  fast: colors.rokusho,
  free: colors.fuji,
};

export function tierColor(tier: string): string {
  return TIER_COLORS[tier?.toLowerCase()] ?? colors.sumi[600];
}

export function truncatePath(p: string, maxLen = 50): string {
  if (p.length <= maxLen) return p;
  const parts = p.split("/");
  if (parts.length <= 3) return p;
  return `.../${parts.slice(-3).join("/")}`;
}

/* ─── Sub-components ──────────────────────────────────────── */

export function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 text-sm text-sumi-600 transition-colors hover:text-torinoko"
    >
      <ArrowLeft size={14} />
      Back to Agents
    </button>
  );
}

export function StatCard({
  icon,
  label,
  value,
  accent,
  sub,
  subColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: string;
  sub?: string;
  subColor?: string;
}) {
  return (
    <div
      className="glass-panel flex flex-col gap-1 p-4"
      style={{ boxShadow: glowBorder(accent, 0.12) }}
    >
      <div className="flex items-center gap-2">
        <span style={{ color: accent }}>{icon}</span>
        <span className="text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
          {label}
        </span>
      </div>
      <span className="font-mono text-xl font-bold text-torinoko">{value}</span>
      {sub && (
        <span className="text-[9px]" style={{ color: subColor ?? colors.sumi[600] }}>
          {sub}
        </span>
      )}
    </div>
  );
}

export function MiniStat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="rounded-lg border border-sumi-700/20 bg-sumi-850/40 px-3 py-2">
      <p className="text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-sm font-bold" style={{ color }}>
        {value}
      </p>
    </div>
  );
}

export function TaskStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const color =
    s === "completed" || s === "done"
      ? colors.rokusho
      : s === "running" || s === "in_progress"
        ? colors.aozora
        : s === "failed"
          ? colors.bengara
          : s === "pending" || s === "queued"
            ? colors.fuji
            : colors.sumi[600];

  return (
    <span
      className="shrink-0 rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
      }}
    >
      {status}
    </span>
  );
}

export function TaskPriorityBadge({ priority }: { priority: string }) {
  const p = priority?.toLowerCase();
  const color =
    p === "critical" || p === "urgent"
      ? colors.bengara
      : p === "high"
        ? colors.kinpaku
        : p === "medium"
          ? colors.fuji
          : colors.sumi[600];

  if (!priority || p === "normal" || p === "low") return null;

  return (
    <span
      className="shrink-0 rounded px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider"
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
      }}
    >
      {priority}
    </span>
  );
}
