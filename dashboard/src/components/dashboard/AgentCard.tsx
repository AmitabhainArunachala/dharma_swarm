"use client";

import { motion } from "framer-motion";
import type { AgentOut } from "@/lib/types";
import { colors, accentAt } from "@/lib/theme";
import { HPBar } from "@/components/game/HPBar";
import { HealthBadge } from "./HealthBadge";

function agentHealthStatus(agent: AgentOut): "healthy" | "degraded" | "critical" | "unknown" {
  const s = agent.status?.toLowerCase();
  if (s === "dead" || s === "stopping") return "critical";
  if (s === "idle" && !agent.last_heartbeat) return "unknown";
  if (s === "busy" || s === "idle") return "healthy";
  return "degraded";
}

function agentHealthPercent(agent: AgentOut): number {
  const h = agentHealthStatus(agent);
  if (h === "healthy") return 100;
  if (h === "degraded") return 60;
  if (h === "critical") return 20;
  return 50;
}

function timeAgo(ts: string | null): string {
  if (!ts) return "never";
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

interface AgentCardProps {
  agent: AgentOut;
  index?: number;
  onClick?: () => void;
}

export function AgentCard({ agent, index = 0, onClick }: AgentCardProps) {
  const accent = accentAt(index);
  const hp = agentHealthPercent(agent);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        delay: index * 0.06,
        ease: [0.22, 1, 0.36, 1],
      }}
      whileHover={{ scale: 1.01 }}
      onClick={onClick}
      className="glass-panel-subtle group cursor-pointer p-4 transition-shadow duration-200 hover:shadow-[0_0_16px_rgba(79,209,217,0.08)]"
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <HealthBadge status={agentHealthStatus(agent)} size="sm" />
          <span className="text-sm font-semibold" style={{ color: colors.torinoko }}>
            {agent.name}
          </span>
        </div>
        <span
          className="text-[10px] font-medium uppercase tracking-wider"
          style={{ color: accent }}
        >
          {agent.role}
        </span>
      </div>

      <div className="mb-2">
        <HPBar value={hp} max={100} height={6} />
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[10px]" style={{ color: colors.sumi[600] }}>
          {agent.tasks_completed} tasks
        </span>
        <span className="text-[10px]" style={{ color: colors.sumi[600] }}>
          {timeAgo(agent.last_heartbeat)}
        </span>
      </div>
    </motion.div>
  );
}
