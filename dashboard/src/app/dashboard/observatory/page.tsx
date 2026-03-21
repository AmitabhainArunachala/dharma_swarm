"use client";

/**
 * DHARMA COMMAND -- Agent Observatory (L3).
 * Fleet-wide agent health monitoring: fitness grid, leaderboard,
 * anomaly feed, and activity timeline with 10s auto-refresh.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import {
  HeartPulse,
  Trophy,
  AlertTriangle,
  Activity,
  Clock,
  DollarSign,
  Users,
  Gauge,
  CheckCircle,
  XCircle,
  Zap,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";
import { ControlPlanePageSummary } from "@/components/dashboard/ControlPlanePageSummary";
import { ControlPlaneSurfaceGrid } from "@/components/dashboard/ControlPlaneSurfaceGrid";
import { ControlPlaneStrip } from "@/components/dashboard/ControlPlaneStrip";
import { useRuntimeControlPlane } from "@/hooks/useRuntimeControlPlane";
import { apiFetch } from "@/lib/api";
import { buildControlPlanePageMeta } from "@/lib/controlPlanePageMeta";
import { buildControlPlaneSyncState } from "@/lib/controlPlaneShell";
import { buildControlPlaneSurfaces } from "@/lib/controlPlaneSurfaces";
import { colors, accentAt, glowText } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TaskEntry {
  id: string;
  title: string;
  status: string;
  timestamp: string;
}

interface AgentSummary {
  name: string;
  model: string;
  role: string;
  status: string;
  last_active: string;
  composite_fitness: number;
  success_rate: number;
  avg_latency: number;
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  speed_score: number;
  daily_spent: number;
  weekly_spent: number;
  budget_status: string;
  sparkline: number[];
  recent_tasks: TaskEntry[];
}

interface Anomaly {
  id: string;
  detected_at: string;
  anomaly_type: string;
  severity: string;
  description: string;
}

interface TimelineEntry {
  agent: string;
  task: string;
  success: boolean;
  tokens: number;
  latency_ms: number;
  cost_usd: number;
  timestamp: string;
}

interface ObservatoryData {
  agents: AgentSummary[];
  fleet_fitness: number;
  total_cost_usd: number;
  agent_count: number;
  anomalies: Anomaly[];
  timeline: TimelineEntry[];
  top_performer: string;
  struggling: string[];
}

const PAGE_META = buildControlPlanePageMeta("observatory");
const PAGE_ACCENT = colors[PAGE_META.accent];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fitnessColor(f: number): string {
  if (f >= 0.7) return colors.rokusho;
  if (f >= 0.4) return colors.kinpaku;
  return colors.bengara;
}

function statusDotColor(status: string): string {
  const s = status.toLowerCase();
  if (s === "active" || s === "running" || s === "busy") return colors.rokusho;
  if (s === "idle" || s === "sleeping") return colors.kinpaku;
  return colors.bengara;
}

function severityColor(severity: string): string {
  const s = severity.toLowerCase();
  if (s === "critical" || s === "error") return colors.bengara;
  if (s === "warning" || s === "warn") return colors.kinpaku;
  return colors.aozora;
}

function severityLabel(severity: string): string {
  const s = severity.toLowerCase();
  if (s === "critical" || s === "error") return "CRITICAL";
  if (s === "warning" || s === "warn") return "WARNING";
  return "INFO";
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Tiny recharts sparkline -- no axes, no grid, just the line. */
function Sparkline({ data, color }: { data: number[]; color: string }) {
  const chartData = useMemo(
    () => data.map((v, i) => ({ i, v })),
    [data],
  );

  if (!data.length) return null;

  return (
    <ResponsiveContainer width="100%" height={30}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Horizontal fitness gauge bar (0-1). */
function FitnessGauge({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const barColor = fitnessColor(value);

  return (
    <div className="flex items-center gap-2">
      <div
        className="h-2 flex-1 overflow-hidden rounded-full"
        style={{ backgroundColor: `color-mix(in srgb, ${colors.sumi[700]} 50%, transparent)` }}
      >
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          style={{
            backgroundColor: barColor,
            boxShadow: `0 0 6px color-mix(in srgb, ${barColor} 50%, transparent)`,
          }}
        />
      </div>
      <span className="font-mono text-[10px] font-bold" style={{ color: barColor, minWidth: 32, textAlign: "right" }}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

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
  const { data, isLoading, isError } = useQuery<ObservatoryData>({
    queryKey: ["observatory"],
    queryFn: () => apiFetch<ObservatoryData>("/api/agents/observatory"),
    refetchInterval: 10_000,
  });
  const rankedAgents = [...(data?.agents ?? [])].sort(
    (a, b) => b.composite_fitness - a.composite_fitness,
  );

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
      {/* Fleet Stats Summary Bar */}
      {/* ================================================================ */}
      {data && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="grid grid-cols-2 gap-3 lg:grid-cols-4"
        >
          <StatCard
            icon={<Users size={14} />}
            label="Agents"
            value={String(data.agent_count)}
            accent={colors.aozora}
          />
          <StatCard
            icon={<Gauge size={14} />}
            label="Fleet Fitness"
            value={data.fleet_fitness.toFixed(3)}
            accent={fitnessColor(data.fleet_fitness)}
          />
          <StatCard
            icon={<DollarSign size={14} />}
            label="Total Cost"
            value={formatCost(data.total_cost_usd)}
            accent={colors.kinpaku}
          />
          <StatCard
            icon={<Trophy size={14} />}
            label="Top Performer"
            value={data.top_performer || "---"}
            accent={colors.rokusho}
          />
        </motion.div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="glass-panel flex items-center justify-center py-16">
          <p className="animate-pulse text-sm" style={{ color: colors.sumi[600] }}>
            Loading observatory data...
          </p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="glass-panel flex items-center justify-center py-16">
          <div className="text-center">
            <AlertTriangle size={24} className="mx-auto mb-2" style={{ color: colors.bengara }} />
            <p className="text-sm" style={{ color: colors.bengara }}>
              Failed to load observatory data. Is the API server running?
            </p>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* ============================================================ */}
          {/* Fleet Health Grid */}
          {/* ============================================================ */}
          <section>
            <SectionHeading
              icon={<Activity size={14} />}
              label="Fleet Health"
              accent={colors.aozora}
            />
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {data.agents.map((agent, i) => (
                <motion.div
                  key={agent.name}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: i * 0.04 }}
                  className="glass-panel-subtle p-4 transition-all hover:bg-white/[0.03]"
                >
                  {/* Name row */}
                  <div className="flex items-center justify-between">
                    <span className="truncate text-sm font-bold" style={{ color: colors.torinoko }}>
                      {agent.name}
                    </span>
                    <span
                      className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-full"
                      style={{
                        backgroundColor: statusDotColor(agent.status),
                        boxShadow: `0 0 6px ${statusDotColor(agent.status)}`,
                      }}
                    />
                  </div>

                  {/* Model + role */}
                  <div className="mt-1 flex items-center gap-2">
                    <span className="truncate font-mono text-[10px]" style={{ color: colors.sumi[600] }}>
                      {agent.model}
                    </span>
                  </div>

                  {/* Fitness gauge */}
                  <div className="mt-3">
                    <FitnessGauge value={agent.composite_fitness} />
                  </div>

                  {/* Sparkline */}
                  {agent.sparkline.length > 0 && (
                    <div className="mt-2">
                      <Sparkline data={agent.sparkline} color={accentAt(i)} />
                    </div>
                  )}

                  {/* Bottom stats row */}
                  <div className="mt-3 flex items-center justify-between text-[10px]">
                    <span style={{ color: colors.sumi[600] }}>
                      <span className="font-mono font-bold" style={{ color: colors.torinoko }}>
                        {(agent.success_rate * 100).toFixed(0)}%
                      </span>
                      {" "}success
                    </span>
                    <span style={{ color: colors.sumi[600] }}>
                      <span className="font-mono font-bold" style={{ color: colors.torinoko }}>
                        {agent.total_calls}
                      </span>
                      {" "}calls
                    </span>
                    <span className="font-mono font-bold" style={{ color: colors.kinpaku }}>
                      {formatCost(agent.total_cost_usd)}
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>

            {data.agents.length === 0 && (
              <div
                className="glass-panel-subtle flex items-center justify-center py-8 text-sm"
                style={{ color: colors.sumi[600] }}
              >
                No agents reporting data.
              </div>
            )}
          </section>

          {/* ============================================================ */}
          {/* Fitness Leaderboard */}
          {/* ============================================================ */}
          <section>
            <SectionHeading
              icon={<Trophy size={14} />}
              label="Fitness Leaderboard"
              accent={colors.kinpaku}
            />
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="glass-panel mt-3 overflow-hidden"
            >
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr
                      className="border-b text-[10px] font-semibold uppercase tracking-wider"
                      style={{ borderColor: colors.sumi[700], color: colors.sumi[600] }}
                    >
                      <th className="px-5 py-2.5 w-12">#</th>
                      <th className="px-5 py-2.5">Agent</th>
                      <th className="px-5 py-2.5 w-[180px]">Fitness</th>
                      <th className="px-5 py-2.5">Success Rate</th>
                      <th className="px-5 py-2.5">Avg Latency</th>
                      <th className="px-5 py-2.5">Total Calls</th>
                      <th className="px-5 py-2.5">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankedAgents.map((agent, i) => (
                      <tr
                        key={agent.name}
                        className="border-b transition-colors hover:bg-white/[0.02]"
                        style={{
                          borderColor: `color-mix(in srgb, ${colors.sumi[700]} 30%, transparent)`,
                          backgroundColor: i % 2 === 0
                            ? "transparent"
                            : `color-mix(in srgb, ${colors.sumi[850]} 30%, transparent)`,
                        }}
                      >
                        <td className="px-5 py-2.5">
                          <span
                            className="font-mono text-xs font-bold"
                            style={{
                              color: i === 0 ? colors.kinpaku : i === 1 ? colors.torinoko : i === 2 ? colors.kitsurubami : colors.sumi[600],
                            }}
                          >
                            {i + 1}
                          </span>
                        </td>
                        <td className="px-5 py-2.5">
                          <div className="flex items-center gap-2">
                            <span
                              className="inline-block h-2 w-2 rounded-full"
                              style={{ backgroundColor: statusDotColor(agent.status) }}
                            />
                            <span className="font-medium" style={{ color: colors.torinoko }}>
                              {agent.name}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-2.5">
                          <div className="flex items-center gap-2">
                            <div
                              className="h-1.5 w-20 overflow-hidden rounded-full"
                              style={{ backgroundColor: `color-mix(in srgb, ${colors.sumi[700]} 50%, transparent)` }}
                            >
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.max(0, Math.min(1, agent.composite_fitness)) * 100}%`,
                                  backgroundColor: fitnessColor(agent.composite_fitness),
                                }}
                              />
                            </div>
                            <span
                              className="font-mono text-xs font-bold"
                              style={{ color: fitnessColor(agent.composite_fitness) }}
                            >
                              {agent.composite_fitness.toFixed(3)}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-2.5">
                          <span className="font-mono text-xs" style={{ color: colors.torinoko }}>
                            {(agent.success_rate * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="px-5 py-2.5">
                          <span className="font-mono text-xs" style={{ color: colors.torinoko }}>
                            {formatLatency(agent.avg_latency)}
                          </span>
                        </td>
                        <td className="px-5 py-2.5">
                          <span className="font-mono text-xs" style={{ color: colors.torinoko }}>
                            {agent.total_calls.toLocaleString()}
                          </span>
                        </td>
                        <td className="px-5 py-2.5">
                          <span className="font-mono text-xs" style={{ color: colors.kinpaku }}>
                            {formatCost(agent.total_cost_usd)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {rankedAgents.length === 0 && (
                <div className="py-8 text-center text-sm" style={{ color: colors.sumi[600] }}>
                  No agents to rank.
                </div>
              )}
            </motion.div>
          </section>

          {/* ============================================================ */}
          {/* Anomaly Feed */}
          {/* ============================================================ */}
          <section>
            <SectionHeading
              icon={<AlertTriangle size={14} />}
              label="Anomaly Feed"
              accent={colors.bengara}
            />
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mt-3 space-y-2"
            >
              {data.anomalies.length === 0 ? (
                <div
                  className="glass-panel-subtle flex items-center justify-center py-8 text-sm"
                  style={{ color: colors.sumi[600] }}
                >
                  No anomalies detected
                </div>
              ) : (
                data.anomalies.map((anomaly) => {
                  const sColor = severityColor(anomaly.severity);
                  return (
                    <div
                      key={anomaly.id}
                      className="glass-panel-subtle flex items-start gap-3 p-4"
                    >
                      {/* Severity badge */}
                      <span
                        className="mt-0.5 inline-flex flex-shrink-0 items-center rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor: `color-mix(in srgb, ${sColor} 15%, transparent)`,
                          color: sColor,
                          border: `1px solid color-mix(in srgb, ${sColor} 30%, transparent)`,
                        }}
                      >
                        {severityLabel(anomaly.severity)}
                      </span>

                      {/* Content */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span
                            className="text-xs font-semibold uppercase tracking-wide"
                            style={{ color: sColor }}
                          >
                            {anomaly.anomaly_type}
                          </span>
                          <span className="text-[10px]" style={{ color: colors.sumi[600] }}>
                            {timeAgo(anomaly.detected_at)}
                          </span>
                        </div>
                        <p className="mt-1 text-xs leading-relaxed" style={{ color: colors.torinoko }}>
                          {anomaly.description}
                        </p>
                      </div>
                    </div>
                  );
                })
              )}
            </motion.div>
          </section>

          {/* ============================================================ */}
          {/* Activity Timeline */}
          {/* ============================================================ */}
          <section>
            <SectionHeading
              icon={<Clock size={14} />}
              label="Activity Timeline"
              accent={colors.fuji}
            />
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="glass-panel mt-3 overflow-hidden"
            >
              <div className="max-h-[480px] overflow-y-auto">
                {data.timeline.length === 0 ? (
                  <div className="py-8 text-center text-sm" style={{ color: colors.sumi[600] }}>
                    No recent activity.
                  </div>
                ) : (
                  <div className="divide-y" style={{ borderColor: `color-mix(in srgb, ${colors.sumi[700]} 25%, transparent)` }}>
                    {data.timeline.map((entry, i) => (
                      <div
                        key={`${entry.timestamp}-${entry.agent}-${i}`}
                        className="flex items-center gap-4 px-5 py-3 transition-colors hover:bg-white/[0.02]"
                        style={{
                          borderColor: `color-mix(in srgb, ${colors.sumi[700]} 25%, transparent)`,
                        }}
                      >
                        {/* Timestamp */}
                        <span
                          className="w-16 flex-shrink-0 font-mono text-[10px]"
                          style={{ color: colors.sumi[600] }}
                        >
                          {timeAgo(entry.timestamp)}
                        </span>

                        {/* Agent name */}
                        <span
                          className="w-28 flex-shrink-0 truncate text-xs font-semibold"
                          style={{ color: accentAt(i % 6) }}
                        >
                          {entry.agent}
                        </span>

                        {/* Task description */}
                        <span
                          className="min-w-0 flex-1 truncate text-xs"
                          style={{ color: colors.torinoko }}
                        >
                          {entry.task}
                        </span>

                        {/* Success / fail badge */}
                        {entry.success ? (
                          <span className="flex flex-shrink-0 items-center gap-1 text-[10px] font-semibold" style={{ color: colors.rokusho }}>
                            <CheckCircle size={11} />
                            OK
                          </span>
                        ) : (
                          <span className="flex flex-shrink-0 items-center gap-1 text-[10px] font-semibold" style={{ color: colors.bengara }}>
                            <XCircle size={11} />
                            FAIL
                          </span>
                        )}

                        {/* Latency */}
                        <span
                          className="w-16 flex-shrink-0 text-right font-mono text-[10px]"
                          style={{ color: colors.sumi[600] }}
                        >
                          {formatLatency(entry.latency_ms)}
                        </span>

                        {/* Cost */}
                        <span
                          className="w-16 flex-shrink-0 text-right font-mono text-[10px]"
                          style={{ color: colors.kinpaku }}
                        >
                          {formatCost(entry.cost_usd)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          </section>

          {/* ============================================================ */}
          {/* Struggling Agents Banner */}
          {/* ============================================================ */}
          {data.struggling.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              className="rounded-xl border p-4"
              style={{
                borderColor: `color-mix(in srgb, ${colors.bengara} 30%, transparent)`,
                backgroundColor: `color-mix(in srgb, ${colors.bengara} 6%, transparent)`,
              }}
            >
              <div className="flex items-center gap-2">
                <Zap size={14} style={{ color: colors.bengara }} />
                <span className="text-xs font-semibold" style={{ color: colors.bengara }}>
                  Agents Needing Attention
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {data.struggling.map((name) => (
                  <span
                    key={name}
                    className="rounded-full px-2.5 py-0.5 font-mono text-[10px] font-medium"
                    style={{
                      backgroundColor: `color-mix(in srgb, ${colors.bengara} 12%, transparent)`,
                      color: colors.bengara,
                    }}
                  >
                    {name}
                  </span>
                ))}
              </div>
            </motion.div>
          )}
        </>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Reusable sub-components
// ---------------------------------------------------------------------------

function StatCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="glass-panel-subtle flex items-center gap-3 p-4">
      <div
        className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg"
        style={{
          backgroundColor: `color-mix(in srgb, ${accent} 12%, transparent)`,
          color: accent,
        }}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: colors.sumi[600] }}>
          {label}
        </p>
        <p className="truncate font-mono text-sm font-bold" style={{ color: colors.torinoko }}>
          {value}
        </p>
      </div>
    </div>
  );
}

function SectionHeading({
  icon,
  label,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  accent: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span style={{ color: accent }}>{icon}</span>
      <h2
        className="font-heading text-sm font-semibold"
        style={{ color: colors.torinoko }}
      >
        {label}
      </h2>
    </div>
  );
}
