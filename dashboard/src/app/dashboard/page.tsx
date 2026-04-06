"use client";

/**
 * DHARMA COMMAND -- Dashboard Overview (L1 page).
 * MetricCards, FitnessTrend, Agent cards, Activity table.
 */

import { motion } from "framer-motion";
import { useOverview } from "@/hooks/useOverview";
import { useAgents } from "@/hooks/useAgents";
import { useHealth } from "@/hooks/useHealth";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { FitnessTrend } from "@/components/dashboard/FitnessTrend";
import { AgentCard } from "@/components/dashboard/AgentCard";
import { ActivityTable } from "@/components/dashboard/ActivityTable";
import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { colors, statusColor } from "@/lib/theme";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06 },
  },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
};

export default function DashboardOverview() {
  const { overview, isLoading: overviewLoading } = useOverview();
  const { agents } = useAgents();
  const { health } = useHealth();

  const agentCount = overview?.agent_count ?? agents.length;
  const taskCount = overview?.task_count ?? 0;
  const fitness = overview?.mean_fitness ?? 0;
  const healthStatus = overview?.health_status ?? health?.overall_status ?? "unknown";

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* Page heading */}
      <motion.div variants={item}>
        <div className="flex items-center gap-3">
          <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
            System Overview
          </h1>
          <HealthBadge
            status={healthStatus as "healthy" | "degraded" | "critical" | "unknown"}
            label
            size="md"
          />
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          {overviewLoading
            ? "Connecting to swarm..."
            : overview
              ? `Uptime ${Math.floor(overview.uptime_seconds / 3600)}h · ${overview.stigmergy_density} marks · ${overview.evolution_entries} evolution entries`
              : "Awaiting swarm telemetry."}
        </p>
      </motion.div>

      {/* Metric cards */}
      <motion.div
        variants={item}
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <MetricCard
          label="Agents"
          value={agentCount}
          trend={agentCount > 0 ? "up" : null}
          trendLabel={`${agents.filter((a) => a.status === "busy").length} active`}
          accentColor={colors.aozora}
          index={0}
          expandable
          href="/dashboard/agents"
          expandContent={
            <div className="space-y-1.5">
              {agents.slice(0, 8).map((a) => (
                <div key={a.id} className="flex items-center gap-2">
                  <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: statusColor(a.status) }} />
                  <span className="truncate text-xs text-torinoko">{a.display_name || a.name}</span>
                  <span className="ml-auto text-[9px] text-sumi-600">{a.role}</span>
                </div>
              ))}
            </div>
          }
        />
        <MetricCard
          label="Tasks"
          value={taskCount}
          trend={
            overview && overview.tasks_completed > overview.tasks_failed
              ? "up"
              : overview && overview.tasks_failed > 0
                ? "down"
                : null
          }
          trendLabel={
            overview
              ? `${overview.tasks_completed} done, ${overview.tasks_failed} failed`
              : undefined
          }
          accentColor={colors.botan}
          index={1}
          expandable
          href="/dashboard/tasks"
          expandContent={<p className="text-xs text-sumi-600">Click to manage tasks</p>}
        />
        <MetricCard
          label="Fitness"
          value={fitness.toFixed(3)}
          trend={fitness > 0.5 ? "up" : fitness > 0 ? "down" : null}
          trendLabel={`${overview?.evolution_entries ?? 0} entries`}
          accentColor={colors.kinpaku}
          index={2}
          expandable
          href="/dashboard/evolution"
          expandContent={<p className="text-xs text-sumi-600">{overview?.evolution_entries ?? 0} evolution entries recorded</p>}
        />
        <MetricCard
          label="Health"
          value={healthStatus}
          trend={healthStatus === "healthy" ? "up" : healthStatus === "critical" ? "down" : null}
          trendLabel={`${health?.anomalies?.length ?? 0} anomalies`}
          accentColor={healthStatus === "healthy" ? colors.rokusho : healthStatus === "critical" ? colors.bengara : colors.kinpaku}
          index={3}
          expandable
          href="/dashboard/audit"
          expandContent={<p className="text-xs text-sumi-600">{health?.anomalies?.length ?? 0} anomalies detected</p>}
        />
      </motion.div>

      {/* Middle section: Fitness trend + Agent list */}
      <motion.div
        variants={item}
        className="grid grid-cols-1 gap-4 lg:grid-cols-3"
      >
        <FitnessTrend className="lg:col-span-2" />

        <div className="space-y-3">
          <h3
            className="text-[11px] font-semibold uppercase tracking-[0.12em]"
            style={{ color: colors.kitsurubami }}
          >
            Active Agents
          </h3>
          {agents.length === 0 ? (
            <div className="glass-panel-subtle flex items-center justify-center py-8">
              <p className="text-sm text-sumi-600">No agents spawned</p>
            </div>
          ) : (
            <div className="space-y-2">
              {agents.slice(0, 6).map((agent, i) => (
                <AgentCard key={agent.id} agent={agent} index={i} />
              ))}
              {agents.length > 6 && (
                <p className="text-center text-xs text-sumi-600">
                  +{agents.length - 6} more
                </p>
              )}
            </div>
          )}
        </div>
      </motion.div>

      {/* Activity table */}
      <motion.div variants={item}>
        <ActivityTable />
      </motion.div>
    </motion.div>
  );
}
