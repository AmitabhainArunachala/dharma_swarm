"use client";

import { motion } from "framer-motion";
import { CheckCircle2, XCircle } from "lucide-react";
import { useAgentWorkspace } from "../layout";
import { TaskPriorityBadge, TaskStatusBadge, stagger } from "@/components/agent-workspace/shared";
import { colors } from "@/lib/theme";
import { timeAgo, formatDuration } from "@/lib/utils";

export default function AgentTasksPage() {
  const { agent, assignedTasks, taskHistory } = useAgentWorkspace();
  if (!agent) return null;

  const recentTaskHistory = (taskHistory ?? []).slice(0, 30);
  const activeTasks = assignedTasks.filter((t) => t.status === "running" || t.status === "in_progress");
  const queuedTasks = assignedTasks.filter((t) => t.status !== "running" && t.status !== "in_progress");

  return (
    <motion.div className="space-y-6" variants={stagger.container} initial="hidden" animate="show">
      {/* ── Active Tasks ──────────────────────────────────── */}
      {activeTasks.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-aozora">
              Active <span className="ml-2 text-sumi-600">({activeTasks.length})</span>
            </h2>
          </div>
          <div className="px-5 py-3 space-y-2">
            {activeTasks.map((task) => (
              <div key={task.id} className="flex items-center gap-3">
                <div className="relative flex">
                  <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-aozora opacity-30" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-aozora" />
                </div>
                <span className="truncate text-sm text-torinoko">{task.title}</span>
                <TaskPriorityBadge priority={task.priority} />
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Queued Tasks ──────────────────────────────────── */}
      {queuedTasks.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Queued <span className="ml-2 text-sumi-600">({queuedTasks.length})</span>
            </h2>
          </div>
          <div className="divide-y divide-sumi-700/10">
            {queuedTasks.map((task) => (
              <div key={task.id} className="flex items-center justify-between px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-torinoko">{task.title}</p>
                  <p className="mt-0.5 text-[10px] text-sumi-600">{task.created_at ? timeAgo(task.created_at) : ""}</p>
                </div>
                <div className="flex items-center gap-2">
                  <TaskPriorityBadge priority={task.priority} />
                  <TaskStatusBadge status={task.status} />
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Task History ──────────────────────────────────── */}
      <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
        <div className="border-b border-sumi-700/30 px-5 py-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
            History <span className="ml-2 text-sumi-600">({recentTaskHistory.length})</span>
          </h2>
        </div>
        {recentTaskHistory.length === 0 ? (
          <div className="py-12 text-center text-xs text-sumi-600">No tasks recorded</div>
        ) : (
          <div className="max-h-[600px] overflow-y-auto">
            {recentTaskHistory.map((th, i) => (
              <div
                key={`${th.timestamp}-${i}`}
                className="flex items-center gap-3 border-b border-sumi-700/10 px-5 py-2 last:border-0"
                style={!th.success ? { backgroundColor: `color-mix(in srgb, ${colors.bengara} 5%, transparent)` } : undefined}
              >
                {th.success ? (
                  <CheckCircle2 size={13} style={{ color: colors.rokusho }} className="shrink-0" />
                ) : (
                  <XCircle size={13} style={{ color: colors.bengara }} className="shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs text-torinoko">{th.task}</p>
                  {th.response_preview && (
                    <p className="mt-0.5 truncate text-[10px] text-sumi-600">{th.response_preview}</p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-0.5">
                  <span className="text-[10px] text-sumi-600">
                    {th.latency_ms > 0 ? formatDuration(th.latency_ms / 1000) : "--"}
                  </span>
                  {th.cost_usd > 0 && (
                    <span className="font-mono text-[9px] text-sumi-600">${th.cost_usd.toFixed(4)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
