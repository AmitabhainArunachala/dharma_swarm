"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Banknote,
  Bot,
  Route,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useVizSnapshot } from "@/hooks/useVizSnapshot";
import { colors, glowBorder, glowBox, statusColor } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";

function formatUsd(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}

function topEntries(record: Record<string, number>, limit = 4): Array<[string, number]> {
  return Object.entries(record)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

export default function TelemetryPage() {
  const {
    overview,
    routing,
    economics,
    agents,
    routes,
    policies,
    interventions,
    economicEvents,
    outcomes,
    isLoading,
  } = useTelemetry();

  const { data: vizSnapshot } = useVizSnapshot(15_000);

  const topPaths = topEntries(routing?.path_counts ?? {});
  const topProviders = topEntries(routing?.provider_counts ?? {});

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <div className="flex items-center gap-3">
          <Sparkles className="text-aozora" size={18} />
          <h1 className="glow-aozora font-heading text-3xl font-bold tracking-tight text-aozora">
            Company Telemetry
          </h1>
        </div>
        <p className="mt-2 max-w-4xl text-sm text-sumi-600">
          Canonical company-state records flowing from the new telemetry plane:
          identity, routing, policy, intervention, economics, and external outcomes.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Active Agents"
          value={overview?.active_agents ?? 0}
          trend={(overview?.active_agents ?? 0) > 0 ? "up" : null}
          trendLabel={`${overview?.agent_count ?? 0} total`}
          accentColor={colors.aozora}
          index={0}
        />
        <MetricCard
          label="Teams"
          value={overview?.team_count ?? 0}
          trend={(overview?.team_count ?? 0) > 0 ? "up" : null}
          trendLabel={`${overview?.reward_event_count ?? 0} reward events`}
          accentColor={colors.rokusho}
          index={1}
        />
        <MetricCard
          label="Routing"
          value={routing?.total_decisions ?? 0}
          trend={(routing?.human_required_count ?? 0) === 0 ? "up" : "down"}
          trendLabel={`${routing?.human_required_count ?? 0} require human`}
          accentColor={colors.kinpaku}
          index={2}
        />
        <MetricCard
          label="Net USD"
          value={formatUsd(economics?.net_usd ?? 0)}
          trend={(economics?.net_usd ?? 0) >= 0 ? "up" : "down"}
          trendLabel={`${formatUsd(economics?.total_revenue_usd ?? 0)} rev / ${formatUsd(economics?.total_cost_usd ?? 0)} cost`}
          accentColor={colors.botan}
          index={3}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.04 }}
          className="glass-panel p-5 xl:col-span-1"
          style={{ boxShadow: `${glowBorder(colors.aozora, 0.2)}, ${glowBox(colors.aozora, 0.18)}` }}
        >
          <div className="mb-4 flex items-center gap-2">
            <Route size={16} className="text-aozora" />
            <h2 className="font-heading text-lg text-torinoko">Routing Topology</h2>
          </div>
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                Paths
              </p>
              <div className="space-y-2">
                {topPaths.length === 0 ? (
                  <p className="text-sm text-sumi-600">No routing decisions yet.</p>
                ) : (
                  topPaths.map(([label, count]) => (
                    <div key={label}>
                      <div className="mb-1 flex items-center justify-between text-sm text-torinoko">
                        <span>{label}</span>
                        <span className="font-mono text-kitsurubami">{count}</span>
                      </div>
                      <div className="h-2 rounded-full bg-sumi-800">
                        <div
                          className="h-2 rounded-full"
                          style={{
                            width: `${Math.max(12, (count / Math.max(topPaths[0]?.[1] ?? 1, 1)) * 100)}%`,
                            background: `linear-gradient(90deg, ${colors.aozora}, ${colors.fuji})`,
                          }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
                Providers
              </p>
              <div className="grid grid-cols-2 gap-2">
                {topProviders.length === 0 ? (
                  <p className="col-span-2 text-sm text-sumi-600">No provider data yet.</p>
                ) : (
                  topProviders.map(([label, count]) => (
                    <div key={label} className="rounded-xl border border-sumi-800 bg-sumi-900/55 p-3">
                      <p className="truncate text-xs uppercase tracking-[0.12em] text-sumi-600">{label || "unknown"}</p>
                      <p className="mt-1 font-mono text-lg text-torinoko">{count}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.08 }}
          className="glass-panel p-5 xl:col-span-2"
          style={{ boxShadow: `${glowBorder(colors.botan, 0.18)}, ${glowBox(colors.botan, 0.16)}` }}
        >
          <div className="mb-4 flex items-center gap-2">
            <Banknote size={16} className="text-botan" />
            <h2 className="font-heading text-lg text-torinoko">Economic Flow</h2>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-sumi-800 bg-sumi-900/55 p-4">
              <p className="text-[11px] uppercase tracking-[0.12em] text-kitsurubami">Revenue</p>
              <p className="mt-2 font-mono text-2xl text-rokusho">{formatUsd(economics?.total_revenue_usd ?? 0)}</p>
            </div>
            <div className="rounded-xl border border-sumi-800 bg-sumi-900/55 p-4">
              <p className="text-[11px] uppercase tracking-[0.12em] text-kitsurubami">Cost</p>
              <p className="mt-2 font-mono text-2xl text-bengara">{formatUsd(economics?.total_cost_usd ?? 0)}</p>
            </div>
            <div className="rounded-xl border border-sumi-800 bg-sumi-900/55 p-4">
              <p className="text-[11px] uppercase tracking-[0.12em] text-kitsurubami">Net</p>
              <p className="mt-2 font-mono text-2xl text-torinoko">{formatUsd(economics?.net_usd ?? 0)}</p>
            </div>
          </div>
          <div className="mt-4 rounded-xl border border-sumi-800 bg-sumi-900/45 p-4">
            <p className="mb-2 text-[11px] uppercase tracking-[0.12em] text-kitsurubami">Currency Breakdown</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(economics?.currency_breakdown ?? {}).length === 0 ? (
                <span className="text-sm text-sumi-600">No economic events yet.</span>
              ) : (
                Object.entries(economics?.currency_breakdown ?? {}).map(([currency, total]) => (
                  <span
                    key={currency}
                    className="rounded-full border border-sumi-800 px-3 py-1 text-xs text-torinoko"
                  >
                    {currency}: {total.toFixed(2)}
                  </span>
                ))
              )}
            </div>
          </div>
        </motion.section>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.12 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <Users size={16} className="text-rokusho" />
            <h2 className="font-heading text-lg text-torinoko">Agent Identity Ledger</h2>
          </div>
          <div className="space-y-3">
            {agents.length === 0 ? (
              <p className="text-sm text-sumi-600">No agent identity records yet.</p>
            ) : (
              agents.slice(0, 8).map((agent) => (
                <div
                  key={agent.agent_id}
                  className="flex items-center justify-between rounded-xl border border-sumi-800 bg-sumi-900/45 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-torinoko">
                      {agent.codename || agent.agent_id}
                    </p>
                    <p className="truncate text-xs text-sumi-600">
                      {(agent.department || "unassigned").toUpperCase()} · {agent.squad_id || "no squad"} · lvl {agent.level}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm text-kitsurubami">{agent.xp.toFixed(1)} xp</p>
                    <p className="text-xs" style={{ color: statusColor(agent.status) }}>
                      {agent.status}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.16 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck size={16} className="text-kinpaku" />
            <h2 className="font-heading text-lg text-torinoko">Intervention + Outcome Feed</h2>
          </div>
          <div className="space-y-3">
            {[...interventions.slice(0, 4), ...outcomes.slice(0, 4)]
              .sort((a, b) => {
                const aTime = new Date("created_at" in a ? a.created_at : 0).getTime();
                const bTime = new Date("created_at" in b ? b.created_at : 0).getTime();
                return bTime - aTime;
              })
              .slice(0, 8)
              .map((entry, index) => {
                const isIntervention = "intervention_id" in entry;
                const key = isIntervention ? entry.intervention_id : entry.outcome_id;
                const title = isIntervention ? entry.intervention_type : entry.outcome_kind;
                const subtitle = isIntervention
                  ? entry.summary || entry.outcome_status
                  : entry.summary || `${entry.value} ${entry.unit}`;
                const status = isIntervention ? entry.outcome_status : entry.status;
                return (
                  <div
                    key={`${key}-${index}`}
                    className="rounded-xl border border-sumi-800 bg-sumi-900/45 px-4 py-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-torinoko">{title}</p>
                      <span className="text-xs" style={{ color: statusColor(status) }}>
                        {status}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-sumi-600">{subtitle}</p>
                    <p className="mt-2 text-[11px] uppercase tracking-[0.12em] text-kitsurubami">
                      {timeAgo(entry.created_at)}
                    </p>
                  </div>
                );
              })}
            {interventions.length + outcomes.length === 0 && (
              <p className="text-sm text-sumi-600">No intervention or outcome records yet.</p>
            )}
          </div>
        </motion.section>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.2 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <Activity size={16} className="text-aozora" />
            <h2 className="font-heading text-lg text-torinoko">Recent Routing + Policy</h2>
          </div>
          <div className="space-y-3">
            {[...routes.slice(0, 5), ...policies.slice(0, 5)]
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .slice(0, 8)
              .map((entry, index) => {
                const isRoute = "route_path" in entry;
                const title = isRoute ? entry.action_name : entry.policy_name;
                const detail = isRoute
                  ? `${entry.route_path} -> ${entry.selected_provider || "unassigned"}`
                  : `${entry.decision}${entry.reason ? ` · ${entry.reason}` : ""}`;
                return (
                  <div
                    key={`${isRoute ? entry.decision_id : entry.decision_id}-${index}`}
                    className="rounded-xl border border-sumi-800 bg-sumi-900/45 px-4 py-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-torinoko">{title}</p>
                      <span className="font-mono text-xs text-kitsurubami">
                        {isRoute ? entry.confidence.toFixed(2) : entry.confidence.toFixed(2)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-sumi-600">{detail}</p>
                  </div>
                );
              })}
            {routes.length + policies.length === 0 && (
              <p className="text-sm text-sumi-600">No routing or policy decisions yet.</p>
            )}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.24 }}
          className="glass-panel p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <Bot size={16} className="text-fuji" />
            <h2 className="font-heading text-lg text-torinoko">Economic Event Feed</h2>
          </div>
          <div className="space-y-3">
            {economicEvents.length === 0 ? (
              <p className="text-sm text-sumi-600">No economic events yet.</p>
            ) : (
              economicEvents.slice(0, 8).map((event) => (
                <div
                  key={event.event_id}
                  className="flex items-center justify-between rounded-xl border border-sumi-800 bg-sumi-900/45 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-torinoko">{event.event_kind}</p>
                    <p className="truncate text-sm text-sumi-600">
                      {event.summary || event.counterparty || "Recorded economic event"}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm text-kitsurubami">
                      {event.currency} {event.amount.toFixed(2)}
                    </p>
                    <p className="text-[11px] uppercase tracking-[0.12em] text-sumi-600">
                      {timeAgo(event.created_at)}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </motion.section>
      </div>

      {/* ── Self-Training Pipeline Metrics ── */}
      {vizSnapshot && (
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.26 }}
        >
          <div className="mb-3 flex items-center gap-2">
            <Sparkles size={14} className="text-kinpaku" />
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Self-Training Pipeline
            </h2>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard
              label="Trajectories"
              value={vizSnapshot.summary.trajectories_completed ?? 0}
              trendLabel={`${vizSnapshot.summary.trajectories_active ?? 0} active`}
              accentColor={colors.kinpaku}
              index={0}
            />
            <MetricCard
              label="Net Balance"
              value={formatUsd(vizSnapshot.summary.net_balance ?? 0)}
              trendLabel={`$${(vizSnapshot.summary.training_budget ?? 0).toFixed(2)} training budget`}
              trend={(vizSnapshot.summary.net_balance ?? 0) > 0 ? "up" : null}
              accentColor={colors.rokusho}
              index={1}
            />
            <MetricCard
              label="Revenue"
              value={formatUsd(vizSnapshot.summary.revenue_total ?? 0)}
              accentColor={colors.rokusho}
              index={2}
            />
            <MetricCard
              label="Expenses"
              value={formatUsd(vizSnapshot.summary.expense_total ?? 0)}
              accentColor={colors.bengara}
              index={3}
            />
          </div>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.28 }}
        className="glass-panel flex items-center justify-between gap-4 p-5"
      >
        <div>
          <p className="text-[11px] uppercase tracking-[0.12em] text-kitsurubami">Build Status</p>
          <p className="mt-1 text-sm text-sumi-600">
            {isLoading
              ? "Refreshing canonical company-state records..."
              : "Telemetry plane is now wired from runtime storage to API to dashboard."}
          </p>
        </div>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-full border border-sumi-800 px-4 py-2 text-sm text-torinoko transition-colors hover:bg-sumi-800/60"
        >
          Back to overview
          <ArrowRight size={14} />
        </Link>
      </motion.div>
    </div>
  );
}
