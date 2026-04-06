"use client";

import { motion } from "framer-motion";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, AreaChart, Area,
} from "recharts";
import { Zap, Clock, Activity, CheckCircle2, XCircle, Cpu, DollarSign, FileCode } from "lucide-react";
import { useAgentWorkspace } from "./layout";
import { StatCard, MiniStat, TaskPriorityBadge, TaskStatusBadge, stagger, truncatePath } from "@/components/agent-workspace/shared";
import { HPBar } from "@/components/game/HPBar";
import { colors, statusColor } from "@/lib/theme";
import { timeAgo, formatDuration, clamp } from "@/lib/utils";

export default function AgentOverviewPage() {
  const { agent, config, traces, healthStats, assignedTasks, fitnessHistory, cost, coreFiles, taskHistory } = useAgentWorkspace();
  if (!agent) return null;

  const successRate = healthStats?.success_rate ?? 1;
  const latestFitness = fitnessHistory?.length ? fitnessHistory[fitnessHistory.length - 1] : null;
  const radarData = latestFitness
    ? [
        { axis: "Success", value: clamp(latestFitness.success_rate, 0, 1) },
        { axis: "Speed", value: clamp(latestFitness.speed_score ?? 0, 0, 1) },
        { axis: "Composite", value: clamp(latestFitness.composite_fitness, 0, 1) },
        { axis: "Quality", value: 0.5 },
        { axis: "Efficiency", value: latestFitness.total_cost_usd > 0 ? clamp(1 - Math.min(latestFitness.total_cost_usd / 1, 1), 0, 1) : 0.8 },
      ]
    : null;
  const sparklineData = (fitnessHistory ?? []).map((f, i) => ({ idx: i, fitness: f.composite_fitness }));
  const sortedCoreFiles = [...(coreFiles ?? [])].sort((a, b) => b.salience - a.salience).slice(0, 10);
  const recentTaskHistory = (taskHistory ?? []).slice(0, 20);

  return (
    <motion.div className="space-y-6" variants={stagger.container} initial="hidden" animate="show">
      <motion.div variants={stagger.item} className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard icon={<CheckCircle2 size={15} />} label="Tasks Done" value={String(agent.tasks_completed)} accent={colors.rokusho} />
        <StatCard icon={<Zap size={15} />} label="Turns Used" value={String(agent.turns_used)} accent={colors.aozora} />
        <StatCard icon={<Activity size={15} />} label="Success Rate" value={healthStats ? `${(successRate * 100).toFixed(0)}%` : "--"} accent={successRate >= 0.9 ? colors.rokusho : successRate >= 0.7 ? colors.kinpaku : colors.bengara} />
        <StatCard icon={<Clock size={15} />} label="Last Heartbeat" value={agent.last_heartbeat ? timeAgo(agent.last_heartbeat) : "never"} accent={colors.fuji} />
        <StatCard icon={<Cpu size={15} />} label="Tokens Today" value={latestFitness ? (latestFitness.total_tokens > 1000 ? `${(latestFitness.total_tokens / 1000).toFixed(1)}k` : String(latestFitness.total_tokens)) : "--"} accent={colors.botan} />
        <StatCard icon={<DollarSign size={15} />} label="Est. Daily Cost" value={cost ? `$${cost.daily_spent.toFixed(2)}` : "--"} accent={colors.kinpaku} sub={cost?.budget_status ? (cost.budget_status === "ok" ? "Within budget" : cost.budget_status) : undefined} subColor={cost?.budget_status === "ok" ? colors.rokusho : cost?.budget_status === "warning" ? colors.kinpaku : colors.bengara} />
      </motion.div>

      {agent.current_task && (
        <motion.div variants={stagger.item} className="glass-panel p-5">
          <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Active Task</h2>
          <div className="flex items-center gap-3">
            <div className="relative flex"><span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-aozora opacity-40" /><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-aozora" /></div>
            <span className="font-mono text-sm text-torinoko">{agent.current_task}</span>
          </div>
        </motion.div>
      )}

      <motion.div variants={stagger.item} className="glass-panel p-5">
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Fitness Profile</h2>
        {radarData ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="flex items-center justify-center">
              <ResponsiveContainer width="100%" height={260}>
                <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
                  <PolarGrid stroke={colors.sumi[700]} strokeOpacity={0.5} />
                  <PolarAngleAxis dataKey="axis" tick={{ fill: colors.kitsurubami, fontSize: 10 }} />
                  <PolarRadiusAxis angle={90} domain={[0, 1]} tick={{ fill: colors.sumi[600], fontSize: 9 }} tickFormatter={(v: number) => v.toFixed(1)} axisLine={false} />
                  <Radar name="Fitness" dataKey="value" stroke={colors.aozora} strokeWidth={2} fill={colors.aozora} fillOpacity={0.2} animationDuration={800} />
                  <Tooltip content={({ payload }) => { if (!payload?.length) return null; const item = payload[0]; return (<div className="glass-panel px-3 py-2" style={{ border: `1px solid color-mix(in srgb, ${colors.aozora} 30%, transparent)` }}><p className="text-[10px] font-medium uppercase tracking-wider" style={{ color: colors.kitsurubami }}>{String(item?.name ?? "")}</p><p className="font-mono text-sm font-bold" style={{ color: colors.torinoko }}>{typeof item?.value === "number" ? (item.value * 100).toFixed(0) + "%" : "--"}</p></div>); }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
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
                  <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Fitness Trend</p>
                  <ResponsiveContainer width="100%" height={64}>
                    <AreaChart data={sparklineData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
                      <defs><linearGradient id="agentSparkFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={colors.aozora} stopOpacity={0.3} /><stop offset="95%" stopColor={colors.aozora} stopOpacity={0} /></linearGradient></defs>
                      <Area type="monotone" dataKey="fitness" stroke={colors.aozora} strokeWidth={1.5} fill="url(#agentSparkFill)" animationDuration={600} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        ) : (<div className="py-8 text-center text-xs text-sumi-600">No fitness data recorded yet</div>)}
      </motion.div>

      <motion.div variants={stagger.item} className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3"><h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Task Pipeline <span className="ml-2 text-sumi-600">({assignedTasks.length + recentTaskHistory.length})</span></h2></div>
          {assignedTasks.filter((t) => t.status === "running" || t.status === "in_progress").length > 0 && (
            <div className="border-b border-sumi-700/20 px-5 py-2">
              <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-aozora">Active</p>
              {assignedTasks.filter((t) => t.status === "running" || t.status === "in_progress").map((task) => (
                <div key={task.id} className="mb-2 flex items-center gap-3 last:mb-0"><div className="relative flex"><span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-aozora opacity-30" /><span className="relative inline-flex h-2 w-2 rounded-full bg-aozora" /></div><span className="truncate text-sm text-torinoko">{task.title}</span><TaskPriorityBadge priority={task.priority} /></div>
              ))}
            </div>
          )}
          {recentTaskHistory.length > 0 ? (
            <div className="max-h-[300px] overflow-y-auto">
              {recentTaskHistory.map((th, i) => (
                <div key={`${th.timestamp}-${i}`} className="flex items-center gap-3 border-b border-sumi-700/10 px-5 py-2 last:border-0" style={!th.success ? { backgroundColor: `color-mix(in srgb, ${colors.bengara} 5%, transparent)` } : undefined}>
                  {th.success ? <CheckCircle2 size={13} style={{ color: colors.rokusho }} className="shrink-0" /> : <XCircle size={13} style={{ color: colors.bengara }} className="shrink-0" />}
                  <div className="min-w-0 flex-1"><p className="truncate font-mono text-xs text-torinoko">{th.task}</p>{th.response_preview && <p className="mt-0.5 truncate text-[10px] text-sumi-600">{th.response_preview}</p>}</div>
                  <div className="flex shrink-0 flex-col items-end gap-0.5"><span className="text-[10px] text-sumi-600">{th.latency_ms > 0 ? formatDuration(th.latency_ms / 1000) : "--"}</span>{th.cost_usd > 0 && <span className="font-mono text-[9px] text-sumi-600">${th.cost_usd.toFixed(4)}</span>}</div>
                </div>
              ))}
            </div>
          ) : assignedTasks.length === 0 ? (<div className="py-8 text-center text-xs text-sumi-600">No tasks recorded</div>) : null}
        </div>
        <div className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3"><h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Activity Stream <span className="ml-2 text-sumi-600">({traces.length})</span></h2></div>
          {traces.length === 0 ? (<div className="py-8 text-center text-xs text-sumi-600">No traces recorded</div>) : (
            <div className="max-h-[520px] overflow-y-auto">
              {traces.map((trace, idx) => (
                <div key={trace.id} className="group relative flex gap-3 border-b border-sumi-700/10 px-5 py-2.5 transition-colors hover:bg-sumi-850/30 last:border-0">
                  <div className="flex flex-col items-center"><div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: statusColor(trace.state), boxShadow: `0 0 6px ${statusColor(trace.state)}50` }} />{idx < traces.length - 1 && <div className="mt-0.5 w-px flex-1" style={{ backgroundColor: colors.sumi[700] }} />}</div>
                  <div className="min-w-0 flex-1 pb-1"><div className="flex items-center justify-between gap-2"><p className="truncate font-mono text-xs text-torinoko">{trace.action}</p><span className="shrink-0 text-[10px] text-sumi-600">{trace.timestamp ? timeAgo(trace.timestamp) : ""}</span></div><span className="mt-0.5 inline-block rounded px-1.5 py-px text-[9px] font-medium uppercase tracking-wider" style={{ color: statusColor(trace.state), backgroundColor: `color-mix(in srgb, ${statusColor(trace.state)} 12%, transparent)` }}>{trace.state}</span></div>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>

      {sortedCoreFiles.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3"><h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Core Files <span className="ml-2 text-sumi-600">({sortedCoreFiles.length})</span></h2></div>
          <div className="max-h-[340px] overflow-y-auto">
            <table className="w-full"><thead><tr className="border-b border-sumi-700/20"><th className="px-5 py-2 text-left text-[9px] font-semibold uppercase tracking-widest text-sumi-600">File</th><th className="px-3 py-2 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Touches</th><th className="px-3 py-2 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Last Touch</th><th className="px-5 py-2 text-right text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Salience</th></tr></thead>
            <tbody>{sortedCoreFiles.map((cf) => (
              <tr key={cf.file_path} className="border-b border-sumi-700/10 transition-colors hover:bg-sumi-850/50"><td className="px-5 py-2"><div className="flex items-center gap-2"><FileCode size={12} className="shrink-0 text-sumi-600" /><span className="truncate font-mono text-xs text-torinoko" title={cf.file_path}>{truncatePath(cf.file_path)}</span></div></td><td className="px-3 py-2 text-right font-mono text-xs text-kitsurubami">{cf.count}</td><td className="px-3 py-2 text-right text-[10px] text-sumi-600">{cf.last_touch ? timeAgo(cf.last_touch) : "--"}</td><td className="px-5 py-2"><div className="flex items-center justify-end gap-2"><div className="w-16"><HPBar value={Math.round(cf.salience * 100)} max={100} height={4} /></div><span className="min-w-[32px] text-right font-mono text-[10px] font-medium" style={{ color: cf.salience > 0.7 ? colors.aozora : cf.salience > 0.4 ? colors.kinpaku : colors.sumi[600] }}>{cf.salience.toFixed(2)}</span></div></td></tr>
            ))}</tbody></table>
          </div>
        </motion.div>
      )}

      <motion.div variants={stagger.item} className="glass-panel-subtle px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[10px] text-sumi-600">
          <span><span className="uppercase tracking-wider">ID</span> <span className="font-mono text-kitsurubami">{agent.id}</span></span>
          {agent.started_at && <span><span className="uppercase tracking-wider">Started</span> <span className="font-mono text-kitsurubami">{timeAgo(agent.started_at)}</span></span>}
          <span><span className="uppercase tracking-wider">Provider</span> <span className="font-mono text-kitsurubami">{agent.provider ?? config?.provider ?? "\u2014"}</span></span>
          <span><span className="uppercase tracking-wider">Model</span> <span className="font-mono text-kitsurubami">{agent.model ?? config?.model ?? "\u2014"}</span></span>
          {cost && <span><span className="uppercase tracking-wider">Weekly Cost</span> <span className="font-mono text-kitsurubami">${cost.weekly_spent.toFixed(2)}</span></span>}
          {healthStats?.last_seen && <span><span className="uppercase tracking-wider">Last Seen</span> <span className="font-mono text-kitsurubami">{timeAgo(healthStats.last_seen)}</span></span>}
        </div>
      </motion.div>
    </motion.div>
  );
}
