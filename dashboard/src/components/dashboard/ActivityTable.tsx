"use client";

import { motion } from "framer-motion";
import { useTraces } from "@/hooks/useTraces";
import { colors } from "@/lib/theme";

const stateColorMap: Record<string, string> = {
  done: colors.rokusho,
  completed: colors.rokusho,
  active: colors.kinpaku,
  running: colors.kinpaku,
  failed: colors.bengara,
  pending: colors.fuji,
  cancelled: colors.sumi[600],
};

function stateColor(state: string): string {
  return stateColorMap[state.toLowerCase()] ?? colors.sumi[600];
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

interface ActivityTableProps {
  className?: string;
}

export function ActivityTable({ className }: ActivityTableProps) {
  const { traces, isLoading } = useTraces(15);

  if (isLoading) {
    return (
      <div
        className={`glass-panel p-5 ${className ?? ""}`}
        style={{ minHeight: 200 }}
      >
        <p className="animate-pulse text-sm" style={{ color: colors.sumi[600] }}>
          Loading activity...
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className={`glass-panel overflow-hidden p-5 ${className ?? ""}`}
    >
      <h3
        className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em]"
        style={{ color: colors.kitsurubami }}
      >
        Recent Activity
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr
              className="border-b text-[10px] font-semibold uppercase tracking-wider"
              style={{ borderColor: colors.sumi[700], color: colors.sumi[600] }}
            >
              <th className="pb-2 pr-4">Time</th>
              <th className="pb-2 pr-4">Agent</th>
              <th className="pb-2 pr-4">Action</th>
              <th className="pb-2 pr-4">State</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((trace, i) => (
              <motion.tr
                key={trace.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{
                  duration: 0.3,
                  delay: i * 0.06,
                  ease: "easeOut",
                }}
                className="border-b transition-colors hover:bg-white/[0.02]"
                style={{
                  borderColor: `color-mix(in srgb, ${colors.sumi[700]} 30%, transparent)`,
                }}
              >
                <td className="py-2.5 pr-4 text-xs" style={{ color: colors.sumi[600] }}>
                  {timeAgo(trace.timestamp)}
                </td>
                <td className="py-2.5 pr-4 font-medium" style={{ color: colors.torinoko }}>
                  {trace.agent}
                </td>
                <td
                  className="py-2.5 pr-4"
                  style={{
                    color: colors.kitsurubami,
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                  }}
                >
                  {trace.action}
                </td>
                <td className="py-2.5 pr-4">
                  <span
                    className="inline-flex items-center gap-1.5 text-xs font-medium capitalize"
                    style={{ color: stateColor(trace.state) }}
                  >
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: stateColor(trace.state) }}
                    />
                    {trace.state}
                  </span>
                </td>
              </motion.tr>
            ))}

            {traces.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  className="py-8 text-center text-sm"
                  style={{ color: colors.sumi[600] }}
                >
                  No recent activity
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
