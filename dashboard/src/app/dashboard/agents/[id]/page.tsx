"use client";

/**
 * DHARMA COMMAND -- Agent Control Panel.
 * Palantir-level inspector: identity, config, fitness radar, core files,
 * task pipeline, activity stream, cost tracking.
 */

import { use } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  AreaChart,
  Area,
} from "recharts";
import {
  ArrowLeft,
  Bot,
  Zap,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Activity,
  StopCircle,
  RefreshCw,
  Cpu,
  DollarSign,
  FileCode,
  ChevronDown,
  Sparkles,
  Hash,
} from "lucide-react";
import { useAgent } from "@/hooks/useAgent";
// apiFetch usage is handled by the useAgent hook mutations
import { HPBar } from "@/components/game/HPBar";
import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { timeAgo, formatDuration, clamp } from "@/lib/utils";
import { colors, statusColor, glowBox, glowBorder } from "@/lib/theme";

/* ─── Helpers ──────────────────────────────────────────────────── */

function agentHealthStatus(
  status: string,
  lastHeartbeat: string | null,
): "healthy" | "degraded" | "critical" | "unknown" {
  const s = status?.toLowerCase();
  if (s === "dead" || s === "stopping") return "critical";
  if (s === "idle" && !lastHeartbeat) return "unknown";
  if (s === "busy" || s === "idle") return "healthy";
  return "degraded";
}

function agentHPPercent(status: string, lastHeartbeat: string | null): number {
  const h = agentHealthStatus(status, lastHeartbeat);
  if (h === "healthy") return 100;
  if (h === "degraded") return 60;
  if (h === "critical") return 20;
  return 50;
}

const TIER_COLORS: Record<string, string> = {
  frontier: colors.aozora,
  strong: colors.kinpaku,
  fast: colors.rokusho,
  free: colors.fuji,
};

function tierColor(tier: string): string {
  return TIER_COLORS[tier?.toLowerCase()] ?? colors.sumi[600];
}

function truncatePath(p: string, maxLen = 50): string {
  if (p.length <= maxLen) return p;
  const parts = p.split("/");
  if (parts.length <= 3) return p;
  return `.../${parts.slice(-3).join("/")}`;
}

const stagger = {
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

/* ─── Main Page ────────────────────────────────────────────────── */

export default function AgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const {
    data,
    agent,
    traces,
    healthStats,
    assignedTasks,
    config,
    fitnessHistory,
    cost,
    coreFiles,
    availableModels,
    availableRoles,
    providerStatus,
    taskHistory,
    isLoading,
    error,
    updateConfig,
    stopAgent,
    respawnAgent,
  } = useAgent(id);

  /* Loading state */
  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackButton onClick={() => router.push("/dashboard/agents")} />
        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-aozora/30 border-t-aozora" />
            <p className="animate-pulse text-sm text-sumi-600">
              Loading agent telemetry...
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* Error state */
  if (error || !agent) {
    return (
      <div className="space-y-6">
        <BackButton onClick={() => router.push("/dashboard/agents")} />
        <div className="glass-panel flex flex-col items-center gap-3 py-16">
          <AlertTriangle size={24} className="text-bengara" />
          <p className="text-sm text-bengara">
            {error instanceof Error ? error.message : "Agent not found"}
          </p>
        </div>
      </div>
    );
  }

  const healthState = agentHealthStatus(agent.status, agent.last_heartbeat);
  const hpPercent = agentHPPercent(agent.status, agent.last_heartbeat);
  const successRate = healthStats?.success_rate ?? 1;
  const agentTier = config?.tier ?? "unknown";
  // providerStatus is an array of { provider, available } entries
  const currentProvider = agent.provider ?? config?.provider;
  const providerEntry = Array.isArray(providerStatus)
    ? providerStatus.find((ps) => ps.provider === currentProvider) ?? providerStatus[0]
    : null;
  const providerAvailable = providerEntry?.available ?? false;

  /* Fitness radar data */
  const latestFitness = fitnessHistory?.length ? fitnessHistory[fitnessHistory.length - 1] : null;
  const radarData = latestFitness
    ? [
        { axis: "Success", value: clamp(latestFitness.success_rate, 0, 1) },
        { axis: "Speed", value: clamp(latestFitness.speed_score ?? 0, 0, 1) },
        { axis: "Composite", value: clamp(latestFitness.composite_fitness, 0, 1) },
        { axis: "Quality", value: 0.5 }, // default if not provided
        {
          axis: "Efficiency",
          value: latestFitness.total_cost_usd > 0
            ? clamp(1 - Math.min(latestFitness.total_cost_usd / 1, 1), 0, 1)
            : 0.8,
        },
      ]
    : null;

  /* Fitness sparkline data */
  const sparklineData = (fitnessHistory ?? []).map((f, i) => ({
    idx: i,
    fitness: f.composite_fitness,
  }));

  /* Core files sorted by salience */
  const sortedCoreFiles = [...(coreFiles ?? [])].sort((a, b) => b.salience - a.salience).slice(0, 10);

  /* Model options grouped by tier */
  const modelsByTier = (availableModels ?? []).reduce<Record<string, typeof availableModels>>(
    (acc, m) => {
      const t = m.tier || "other";
      if (!acc[t]) acc[t] = [];
      acc[t]!.push(m);
      return acc;
    },
    {},
  );

  /* Task history (last 20) */
  const recentTaskHistory = (taskHistory ?? []).slice(0, 20);

  return (
    <motion.div
      className="space-y-6"
      variants={stagger.container}
      initial="hidden"
      animate="show"
    >
      {/* ── 1. Identity Header ──────────────────────────────────── */}
      <motion.div variants={stagger.item}>
        <div className="flex items-center justify-between">
          <BackButton onClick={() => router.push("/dashboard/agents")} />
          <div className="flex items-center gap-2">
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ["agent-detail", id] })}
              className="flex items-center gap-1.5 rounded-lg border border-sumi-700/40 px-3 py-1.5 text-xs text-sumi-600 transition-colors hover:border-aozora/30 hover:text-aozora"
            >
              <RefreshCw size={12} />
              Refresh
            </button>
            <button
              onClick={() => respawnAgent.mutate({})}
              disabled={respawnAgent.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-aozora/30 bg-aozora/10 px-3 py-1.5 text-xs font-medium text-aozora transition-all hover:border-aozora/50 hover:bg-aozora/20 disabled:opacity-40"
            >
              <Sparkles size={12} />
              {respawnAgent.isPending ? "Respawning..." : "Respawn"}
            </button>
            <button
              onClick={() => stopAgent.mutate()}
              disabled={stopAgent.isPending || agent.status === "dead"}
              className="flex items-center gap-1.5 rounded-lg border border-bengara/30 bg-bengara/10 px-3 py-1.5 text-xs font-medium text-bengara transition-all hover:border-bengara/50 hover:bg-bengara/20 disabled:opacity-40"
            >
              <StopCircle size={12} />
              {stopAgent.isPending ? "Stopping..." : "Stop Agent"}
            </button>
          </div>
        </div>
      </motion.div>

      <motion.div variants={stagger.item} className="glass-panel p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div
              className="flex h-14 w-14 items-center justify-center rounded-xl"
              style={{
                backgroundColor: `color-mix(in srgb, ${colors.aozora} 12%, transparent)`,
                boxShadow: glowBox(colors.aozora, 0.15),
              }}
            >
              <Bot size={28} style={{ color: colors.aozora }} />
            </div>
            <div>
              <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
                {config?.display_name || agent.name}
              </h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
                {/* Role badge */}
                <span
                  className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
                  style={{
                    color: colors.kinpaku,
                    backgroundColor: `color-mix(in srgb, ${colors.kinpaku} 15%, transparent)`,
                  }}
                >
                  {agent.role}
                </span>

                {/* Status indicator */}
                <div className="flex items-center gap-1.5">
                  <HealthBadge status={healthState} size="sm" />
                  <span className="text-xs capitalize text-kitsurubami">
                    {agent.status}
                  </span>
                </div>

                <span className="text-sumi-700">|</span>

                {/* Provider badge */}
                <div className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{
                      backgroundColor: providerAvailable ? colors.rokusho : colors.bengara,
                      boxShadow: providerAvailable
                        ? `0 0 6px ${colors.rokusho}80`
                        : `0 0 6px ${colors.bengara}80`,
                    }}
                  />
                  <span className="text-xs text-sumi-600">
                    {agent.provider ?? config?.provider ?? "unknown"}
                  </span>
                </div>

                <span className="text-sumi-700">|</span>

                {/* Model + tier */}
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-xs text-kitsurubami">
                    {agent.model ?? config?.model ?? "—"}
                  </span>
                  <span
                    className="rounded px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider"
                    style={{
                      color: tierColor(agentTier),
                      backgroundColor: `color-mix(in srgb, ${tierColor(agentTier)} 15%, transparent)`,
                    }}
                  >
                    {agentTier}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="w-[180px] shrink-0">
            <p className="mb-1 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
              Health
            </p>
            <HPBar value={hpPercent} max={100} height={8} showLabel />
          </div>
        </div>
      </motion.div>

      {/* ── Error Banner ────────────────────────────────────────── */}
      {agent.error && (
        <motion.div
          variants={stagger.item}
          className="rounded-lg border border-bengara/30 bg-bengara/5 p-5"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-bengara" />
            <div>
              <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-bengara">
                Error
              </h2>
              <p className="mt-1 font-mono text-xs text-bengara/80">
                {agent.error}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      {/* ── 2. Config Panel ─────────────────────────────────────── */}
      <motion.div variants={stagger.item} className="glass-panel p-5">
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
          Configuration
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Model selector */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
              Model
            </label>
            <div className="relative">
              <select
                className="w-full appearance-none rounded-lg border border-sumi-700/40 bg-sumi-900 px-3 py-2 pr-8 font-mono text-xs text-torinoko transition-colors focus:border-aozora/50 focus:outline-none"
                value={config?.model ?? agent.model ?? ""}
                onChange={(e) => {
                  if (e.target.value) {
                    updateConfig.mutate({ model: e.target.value });
                  }
                }}
                disabled={updateConfig.isPending}
              >
                {Object.entries(modelsByTier).map(([tier, models]) => (
                  <optgroup key={tier} label={tier.toUpperCase()}>
                    {(models ?? []).map((m) => (
                      <option key={m.model_id} value={m.model_id}>
                        {m.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
                {/* Fallback if current model not in list */}
                {availableModels &&
                  !availableModels.some((m) => m.model_id === (config?.model ?? agent.model)) && (
                    <option value={config?.model ?? agent.model ?? ""}>
                      {config?.model ?? agent.model ?? "unknown"}
                    </option>
                  )}
              </select>
              <ChevronDown
                size={12}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sumi-600"
              />
            </div>
          </div>

          {/* Role selector */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
              Role
            </label>
            <div className="relative">
              <select
                className="w-full appearance-none rounded-lg border border-sumi-700/40 bg-sumi-900 px-3 py-2 pr-8 font-mono text-xs text-torinoko transition-colors focus:border-aozora/50 focus:outline-none"
                value={config?.role ?? agent.role ?? ""}
                onChange={(e) => {
                  if (e.target.value) {
                    updateConfig.mutate({ role: e.target.value });
                  }
                }}
                disabled={updateConfig.isPending}
              >
                {(availableRoles ?? []).map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
                {/* Fallback */}
                {availableRoles &&
                  !availableRoles.includes(config?.role ?? agent.role ?? "") && (
                    <option value={config?.role ?? agent.role ?? ""}>
                      {config?.role ?? agent.role ?? "unknown"}
                    </option>
                  )}
              </select>
              <ChevronDown
                size={12}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sumi-600"
              />
            </div>
          </div>

          {/* Thread */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
              Thread
            </label>
            <div
              className="flex items-center gap-2 rounded-lg border border-sumi-700/20 bg-sumi-850/50 px-3 py-2"
            >
              <Hash size={11} className="shrink-0 text-sumi-600" />
              <span className="truncate font-mono text-xs text-kitsurubami">
                {config?.thread ?? "—"}
              </span>
            </div>
          </div>

          {/* Provider connection */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
              Provider
            </label>
            <div
              className="flex items-center gap-2 rounded-lg border px-3 py-2"
              style={{
                borderColor: providerAvailable
                  ? `color-mix(in srgb, ${colors.rokusho} 30%, transparent)`
                  : `color-mix(in srgb, ${colors.bengara} 30%, transparent)`,
                backgroundColor: providerAvailable
                  ? `color-mix(in srgb, ${colors.rokusho} 5%, transparent)`
                  : `color-mix(in srgb, ${colors.bengara} 5%, transparent)`,
              }}
            >
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{
                  backgroundColor: providerAvailable ? colors.rokusho : colors.bengara,
                  boxShadow: `0 0 8px ${providerAvailable ? colors.rokusho : colors.bengara}60`,
                }}
              />
              <span
                className="text-xs font-medium"
                style={{ color: providerAvailable ? colors.rokusho : colors.bengara }}
              >
                {providerAvailable ? "Connected" : "Disconnected"}
              </span>
            </div>
          </div>
        </div>

        {/* Strengths pills */}
        {config?.strengths && config.strengths.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            <span className="mr-1 self-center text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
              Strengths
            </span>
            {config.strengths.map((s) => (
              <span
                key={s}
                className="rounded-full px-2.5 py-0.5 text-[10px] font-medium"
                style={{
                  color: colors.fuji,
                  backgroundColor: `color-mix(in srgb, ${colors.fuji} 12%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${colors.fuji} 20%, transparent)`,
                }}
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {updateConfig.isPending && (
          <div className="mt-3 flex items-center gap-2 text-[10px] text-aozora">
            <div className="h-3 w-3 animate-spin rounded-full border border-aozora/30 border-t-aozora" />
            Updating configuration...
          </div>
        )}
      </motion.div>

      {/* ── 3. Metrics Row (6 cards) ────────────────────────────── */}
      <motion.div
        variants={stagger.item}
        className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6"
      >
        <StatCard
          icon={<CheckCircle2 size={15} />}
          label="Tasks Done"
          value={String(agent.tasks_completed)}
          accent={colors.rokusho}
        />
        <StatCard
          icon={<Zap size={15} />}
          label="Turns Used"
          value={String(agent.turns_used)}
          accent={colors.aozora}
        />
        <StatCard
          icon={<Activity size={15} />}
          label="Success Rate"
          value={
            healthStats
              ? `${(successRate * 100).toFixed(0)}%`
              : "--"
          }
          accent={successRate >= 0.9 ? colors.rokusho : successRate >= 0.7 ? colors.kinpaku : colors.bengara}
        />
        <StatCard
          icon={<Clock size={15} />}
          label="Last Heartbeat"
          value={agent.last_heartbeat ? timeAgo(agent.last_heartbeat) : "never"}
          accent={colors.fuji}
        />
        <StatCard
          icon={<Cpu size={15} />}
          label="Tokens Today"
          value={
            latestFitness
              ? latestFitness.total_tokens > 1000
                ? `${(latestFitness.total_tokens / 1000).toFixed(1)}k`
                : String(latestFitness.total_tokens)
              : "--"
          }
          accent={colors.botan}
        />
        <StatCard
          icon={<DollarSign size={15} />}
          label="Est. Daily Cost"
          value={cost ? `$${cost.daily_spent.toFixed(2)}` : "--"}
          accent={colors.kinpaku}
          sub={
            cost?.budget_status
              ? cost.budget_status === "ok"
                ? "Within budget"
                : cost.budget_status
              : undefined
          }
          subColor={
            cost?.budget_status === "ok"
              ? colors.rokusho
              : cost?.budget_status === "warning"
                ? colors.kinpaku
                : colors.bengara
          }
        />
      </motion.div>

      {/* ── Current Task ────────────────────────────────────────── */}
      {agent.current_task && (
        <motion.div variants={stagger.item} className="glass-panel p-5">
          <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
            Active Task
          </h2>
          <div className="flex items-center gap-3">
            <div className="relative flex">
              <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-aozora opacity-40" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-aozora" />
            </div>
            <span className="font-mono text-sm text-torinoko">
              {agent.current_task}
            </span>
          </div>
        </motion.div>
      )}

      {/* ── 4. Fitness Radar + Sparkline ────────────────────────── */}
      <motion.div variants={stagger.item} className="glass-panel p-5">
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
          Fitness Profile
        </h2>
        {radarData ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Radar */}
            <div className="flex items-center justify-center">
              <ResponsiveContainer width="100%" height={260}>
                <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
                  <PolarGrid
                    stroke={colors.sumi[700]}
                    strokeOpacity={0.5}
                  />
                  <PolarAngleAxis
                    dataKey="axis"
                    tick={{ fill: colors.kitsurubami, fontSize: 10 }}
                  />
                  <PolarRadiusAxis
                    angle={90}
                    domain={[0, 1]}
                    tick={{ fill: colors.sumi[600], fontSize: 9 }}
                    tickFormatter={(v: number) => v.toFixed(1)}
                    axisLine={false}
                  />
                  <Radar
                    name="Fitness"
                    dataKey="value"
                    stroke={colors.aozora}
                    strokeWidth={2}
                    fill={colors.aozora}
                    fillOpacity={0.2}
                    animationDuration={800}
                  />
                  <Tooltip
                    content={({ payload }) => {
                      if (!payload?.length) return null;
                      const item = payload[0];
                      return (
                        <div
                          className="glass-panel px-3 py-2"
                          style={{
                            border: `1px solid color-mix(in srgb, ${colors.aozora} 30%, transparent)`,
                          }}
                        >
                          <p className="text-[10px] font-medium uppercase tracking-wider" style={{ color: colors.kitsurubami }}>
                            {String(item?.name ?? "")}
                          </p>
                          <p className="font-mono text-sm font-bold" style={{ color: colors.torinoko }}>
                            {typeof item?.value === "number" ? (item.value * 100).toFixed(0) + "%" : "--"}
                          </p>
                        </div>
                      );
                    }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Fitness trend sparkline + stats */}
            <div className="flex flex-col justify-between">
              <div className="grid grid-cols-2 gap-3">
                <MiniStat label="Composite" value={latestFitness?.composite_fitness.toFixed(3) ?? "--"} color={colors.aozora} />
                <MiniStat label="Success" value={latestFitness ? `${(latestFitness.success_rate * 100).toFixed(0)}%` : "--"} color={colors.rokusho} />
                <MiniStat label="Avg Latency" value={latestFitness ? `${latestFitness.avg_latency.toFixed(0)}ms` : "--"} color={colors.kinpaku} />
                <MiniStat label="Speed" value={latestFitness?.speed_score?.toFixed(2) ?? "--"} color={colors.botan} />
                <MiniStat label="Total Calls" value={latestFitness ? String(latestFitness.total_calls) : "--"} color={colors.fuji} />
                <MiniStat label="Total Cost" value={latestFitness ? `$${latestFitness.total_cost_usd.toFixed(3)}` : "--"} color={colors.bengara} />
              </div>

              {sparklineData.length > 1 && (
                <div className="mt-4">
                  <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                    Fitness Trend
                  </p>
                  <ResponsiveContainer width="100%" height={64}>
                    <AreaChart data={sparklineData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
                      <defs>
                        <linearGradient id="agentSparkFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={colors.aozora} stopOpacity={0.3} />
                          <stop offset="95%" stopColor={colors.aozora} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area
                        type="monotone"
                        dataKey="fitness"
                        stroke={colors.aozora}
                        strokeWidth={1.5}
                        fill="url(#agentSparkFill)"
                        animationDuration={600}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-sumi-600">
            No fitness data recorded yet
          </div>
        )}
      </motion.div>

      {/* ── 5. Core Files ───────────────────────────────────────── */}
      {sortedCoreFiles.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Core Files
              <span className="ml-2 text-sumi-600">({sortedCoreFiles.length})</span>
            </h2>
          </div>
          <div className="max-h-[340px] overflow-y-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-sumi-700/20">
                  <th className="px-5 py-2 text-left text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                    File
                  </th>
                  <th className="px-3 py-2 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                    Touches
                  </th>
                  <th className="px-3 py-2 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                    Last Touch
                  </th>
                  <th className="px-5 py-2 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                    Salience
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedCoreFiles.map((cf) => (
                  <tr
                    key={cf.file_path}
                    className="border-b border-sumi-700/10 transition-colors hover:bg-sumi-850/50"
                  >
                    <td className="px-5 py-2">
                      <div className="flex items-center gap-2">
                        <FileCode size={12} className="shrink-0 text-sumi-600" />
                        <span className="truncate font-mono text-xs text-torinoko" title={cf.file_path}>
                          {truncatePath(cf.file_path)}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-kitsurubami">
                      {cf.count}
                    </td>
                    <td className="px-3 py-2 text-right text-[10px] text-sumi-600">
                      {cf.last_touch ? timeAgo(cf.last_touch) : "--"}
                    </td>
                    <td className="px-5 py-2">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16">
                          <HPBar value={Math.round(cf.salience * 100)} max={100} height={4} />
                        </div>
                        <span
                          className="min-w-[32px] text-right font-mono text-[10px] font-medium"
                          style={{
                            color:
                              cf.salience > 0.7
                                ? colors.aozora
                                : cf.salience > 0.4
                                  ? colors.kinpaku
                                  : colors.sumi[600],
                          }}
                        >
                          {cf.salience.toFixed(2)}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      {/* ── 6. Two-column: Task Pipeline + Activity Stream ──────── */}
      <motion.div variants={stagger.item} className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left: Task Pipeline */}
        <div className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Task Pipeline
              <span className="ml-2 text-sumi-600">
                ({assignedTasks.length + recentTaskHistory.length})
              </span>
            </h2>
          </div>

          {/* Active tasks */}
          {assignedTasks.filter((t) => t.status === "running" || t.status === "in_progress").length > 0 && (
            <div className="border-b border-sumi-700/20 px-5 py-2">
              <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-aozora">
                Active
              </p>
              {assignedTasks
                .filter((t) => t.status === "running" || t.status === "in_progress")
                .map((task) => (
                  <div key={task.id} className="mb-2 flex items-center gap-3 last:mb-0">
                    <div className="relative flex">
                      <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-aozora opacity-30" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-aozora" />
                    </div>
                    <span className="truncate text-sm text-torinoko">{task.title}</span>
                    <TaskPriorityBadge priority={task.priority} />
                  </div>
                ))}
            </div>
          )}

          {/* Queued / pending tasks */}
          {assignedTasks.filter((t) => t.status !== "running" && t.status !== "in_progress").length > 0 && (
            <div className="border-b border-sumi-700/20 px-5 py-2">
              <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                Queued
              </p>
              {assignedTasks
                .filter((t) => t.status !== "running" && t.status !== "in_progress")
                .map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between border-b border-sumi-700/10 py-2 last:border-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-torinoko">{task.title}</p>
                      <p className="mt-0.5 text-[10px] text-sumi-600">
                        {task.created_at ? timeAgo(task.created_at) : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <TaskPriorityBadge priority={task.priority} />
                      <TaskStatusBadge status={task.status} />
                    </div>
                  </div>
                ))}
            </div>
          )}

          {/* Task history */}
          {recentTaskHistory.length > 0 ? (
            <div className="max-h-[300px] overflow-y-auto">
              <div className="px-5 py-2">
                <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                  History
                </p>
              </div>
              {recentTaskHistory.map((th, i) => (
                <div
                  key={`${th.timestamp}-${i}`}
                  className="flex items-center gap-3 border-b border-sumi-700/10 px-5 py-2 last:border-0"
                  style={
                    !th.success
                      ? {
                          backgroundColor: `color-mix(in srgb, ${colors.bengara} 5%, transparent)`,
                        }
                      : undefined
                  }
                >
                  {th.success ? (
                    <CheckCircle2 size={13} style={{ color: colors.rokusho }} className="shrink-0" />
                  ) : (
                    <XCircle size={13} style={{ color: colors.bengara }} className="shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-torinoko">
                      {th.task}
                    </p>
                    {th.response_preview && (
                      <p className="mt-0.5 truncate text-[10px] text-sumi-600">
                        {th.response_preview}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-0.5">
                    <span className="text-[10px] text-sumi-600">
                      {th.latency_ms > 0 ? formatDuration(th.latency_ms / 1000) : "--"}
                    </span>
                    {th.cost_usd > 0 && (
                      <span className="font-mono text-[9px] text-sumi-600">
                        ${th.cost_usd.toFixed(4)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : assignedTasks.length === 0 ? (
            <div className="py-8 text-center text-xs text-sumi-600">
              No tasks recorded
            </div>
          ) : null}
        </div>

        {/* Right: Activity Stream */}
        <div className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Activity Stream
              <span className="ml-2 text-sumi-600">({traces.length})</span>
            </h2>
          </div>
          {traces.length === 0 ? (
            <div className="py-8 text-center text-xs text-sumi-600">
              No traces recorded
            </div>
          ) : (
            <div className="max-h-[520px] overflow-y-auto">
              {traces.map((trace, idx) => (
                <div
                  key={trace.id}
                  className="group relative flex gap-3 border-b border-sumi-700/10 px-5 py-2.5 transition-colors hover:bg-sumi-850/30 last:border-0"
                >
                  {/* Timeline connector */}
                  <div className="flex flex-col items-center">
                    <div
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{
                        backgroundColor: statusColor(trace.state),
                        boxShadow: `0 0 6px ${statusColor(trace.state)}50`,
                      }}
                    />
                    {idx < traces.length - 1 && (
                      <div
                        className="mt-0.5 w-px flex-1"
                        style={{ backgroundColor: colors.sumi[700] }}
                      />
                    )}
                  </div>
                  <div className="min-w-0 flex-1 pb-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate font-mono text-xs text-torinoko">
                        {trace.action}
                      </p>
                      <span className="shrink-0 text-[10px] text-sumi-600">
                        {trace.timestamp ? timeAgo(trace.timestamp) : ""}
                      </span>
                    </div>
                    <span
                      className="mt-0.5 inline-block rounded px-1.5 py-px text-[9px] font-medium uppercase tracking-wider"
                      style={{
                        color: statusColor(trace.state),
                        backgroundColor: `color-mix(in srgb, ${statusColor(trace.state)} 12%, transparent)`,
                      }}
                    >
                      {trace.state}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>

      {/* ── 7. Footer ───────────────────────────────────────────── */}
      <motion.div variants={stagger.item} className="glass-panel-subtle px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[10px] text-sumi-600">
          <span>
            <span className="uppercase tracking-wider">ID</span>{" "}
            <span className="font-mono text-kitsurubami">{agent.id}</span>
          </span>
          {agent.started_at && (
            <span>
              <span className="uppercase tracking-wider">Started</span>{" "}
              <span className="font-mono text-kitsurubami">
                {timeAgo(agent.started_at)}
              </span>
            </span>
          )}
          <span>
            <span className="uppercase tracking-wider">Provider</span>{" "}
            <span className="font-mono text-kitsurubami">
              {agent.provider ?? config?.provider ?? "—"}
            </span>
          </span>
          <span>
            <span className="uppercase tracking-wider">Model</span>{" "}
            <span className="font-mono text-kitsurubami">
              {agent.model ?? config?.model ?? "—"}
            </span>
          </span>
          {cost && (
            <span>
              <span className="uppercase tracking-wider">Weekly Cost</span>{" "}
              <span className="font-mono text-kitsurubami">
                ${cost.weekly_spent.toFixed(2)}
              </span>
            </span>
          )}
          {healthStats?.last_seen && (
            <span>
              <span className="uppercase tracking-wider">Last Seen</span>{" "}
              <span className="font-mono text-kitsurubami">
                {timeAgo(healthStats.last_seen)}
              </span>
            </span>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Sub-components ──────────────────────────────────────────── */

function BackButton({ onClick }: { onClick: () => void }) {
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

function StatCard({
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
      style={{
        boxShadow: glowBorder(accent, 0.12),
      }}
    >
      <div className="flex items-center gap-2">
        <span style={{ color: accent }}>{icon}</span>
        <span className="text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
          {label}
        </span>
      </div>
      <span className="font-mono text-xl font-bold text-torinoko">
        {value}
      </span>
      {sub && (
        <span className="text-[9px]" style={{ color: subColor ?? colors.sumi[600] }}>
          {sub}
        </span>
      )}
    </div>
  );
}

function MiniStat({
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

function TaskStatusBadge({ status }: { status: string }) {
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

function TaskPriorityBadge({ priority }: { priority: string }) {
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
