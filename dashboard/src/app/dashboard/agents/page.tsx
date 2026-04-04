"use client";

/**
 * DHARMA COMMAND -- Agents page (L2).
 * Data table with agent list, inline HP bars, status dots.
 * Click row to open detail drawer. Spawn / Stop controls.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, Plus, X, StopCircle, Clock, Zap } from "lucide-react";
import { useAgents } from "@/hooks/useAgents";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { HPBar } from "@/components/game/HPBar";
import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { timeAgo } from "@/lib/utils";
import { colors, accentAt } from "@/lib/theme";
import type { AgentOut } from "@/lib/types";

function agentHealthStatus(agent: AgentOut): "healthy" | "degraded" | "critical" | "unknown" {
  const s = agent.status?.toLowerCase();
  if (s === "dead" || s === "stopping") return "critical";
  if (s === "idle" && !agent.last_heartbeat) return "unknown";
  if (s === "busy" || s === "idle") return "healthy";
  return "degraded";
}

function agentHPPercent(agent: AgentOut): number {
  const h = agentHealthStatus(agent);
  if (h === "healthy") return 100;
  if (h === "degraded") return 60;
  if (h === "critical") return 20;
  return 50;
}

export default function AgentsPage() {
  const router = useRouter();
  const { agents, isLoading } = useAgents();
  const [selectedAgent, setSelectedAgent] = useState<AgentOut | null>(null);
  const [showSpawnDialog, setShowSpawnDialog] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="glow-aozora font-heading text-2xl font-bold tracking-tight text-aozora">
            Agents
          </h1>
          <p className="mt-1 text-sm text-sumi-600">
            {agents.length} agents registered, {agents.filter((a) => a.status === "busy").length} active
          </p>
        </div>
        <button
          onClick={() => setShowSpawnDialog(true)}
          className="flex items-center gap-2 rounded-lg border border-aozora/30 bg-aozora/10 px-4 py-2 text-sm font-medium text-aozora transition-all hover:border-aozora/50 hover:bg-aozora/20"
        >
          <Plus size={14} />
          Spawn Agent
        </button>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="glass-panel overflow-hidden"
      >
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <p className="animate-pulse text-sm text-sumi-600">Loading agents...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr
                  className="border-b text-[10px] font-semibold uppercase tracking-wider"
                  style={{ borderColor: colors.sumi[700], color: colors.sumi[600] }}
                >
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Tasks</th>
                  <th className="px-5 py-3 w-[140px]">HP</th>
                  <th className="px-5 py-3">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent, i) => (
                  <motion.tr
                    key={agent.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.04 }}
                    onClick={() => router.push(`/dashboard/agents/${agent.id}`)}
                    className="cursor-pointer border-b transition-colors hover:bg-white/[0.02]"
                    style={{
                      borderColor: `color-mix(in srgb, ${colors.sumi[700]} 30%, transparent)`,
                    }}
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2.5">
                        <Bot size={14} style={{ color: accentAt(i) }} />
                        <div className="min-w-0">
                          <div className="truncate font-medium text-torinoko">
                            {agent.display_name || agent.name}
                          </div>
                          {agent.model_label && (
                            <div className="truncate text-[10px] text-sumi-600">
                              {agent.model_label}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className="text-xs font-medium uppercase tracking-wider"
                        style={{ color: accentAt(i) }}
                      >
                        {agent.role}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <HealthBadge status={agentHealthStatus(agent)} size="sm" />
                        <span className="text-xs capitalize text-kitsurubami">{agent.status}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span className="font-mono text-xs text-torinoko">
                        {agent.tasks_completed}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <HPBar value={agentHPPercent(agent)} max={100} height={6} />
                    </td>
                    <td className="px-5 py-3 text-xs text-sumi-600">
                      {agent.last_heartbeat ? timeAgo(agent.last_heartbeat) : "never"}
                    </td>
                  </motion.tr>
                ))}
                {agents.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-sm text-sumi-600">
                      No agents registered. Spawn one to begin.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </motion.div>

      <AnimatePresence>
        {selectedAgent && (
          <AgentDrawer agent={selectedAgent} onClose={() => setSelectedAgent(null)} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showSpawnDialog && <SpawnDialog onClose={() => setShowSpawnDialog(false)} />}
      </AnimatePresence>
    </div>
  );
}

function AgentDrawer({ agent, onClose }: { agent: AgentOut; onClose: () => void }) {
  const qc = useQueryClient();
  const stopMutation = useMutation({
    mutationFn: () => apiFetch(`/api/agents/${agent.id}/stop`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      onClose();
    },
  });

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
      />
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="fixed right-0 top-0 z-50 flex h-full w-[420px] flex-col border-l border-sumi-700/40 bg-sumi-900/95 backdrop-blur-md"
      >
        <div className="flex items-center justify-between border-b border-sumi-700/30 px-6 py-4">
          <div className="flex items-center gap-3">
            <Bot size={18} className="text-aozora" />
            <div>
              <h2 className="font-heading text-lg font-bold text-torinoko">
                {agent.display_name || agent.name}
              </h2>
              {agent.agent_slug && (
                <p className="font-mono text-[10px] text-sumi-600">{agent.agent_slug}</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            aria-label="Close drawer"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="space-y-3">
            <DetailRow label="Status" value={agent.status} />
            <DetailRow label="Role" value={agent.role} />
            <DetailRow label="Provider" value={agent.provider || "—"} />
            <DetailRow label="Model" value={agent.model_label || agent.model || "—"} />
            {agent.model_key && <DetailRow label="Model Key" value={agent.model_key} />}
            <DetailRow label="Turns Used" value={String(agent.turns_used)} />
            <DetailRow label="Last Heartbeat" value={agent.last_heartbeat ? timeAgo(agent.last_heartbeat) : "never"} />
            {agent.current_task && <DetailRow label="Current Task" value={agent.current_task} />}
            {agent.error && <DetailRow label="Error" value={agent.error} />}
          </div>

          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Health
            </p>
            <HPBar value={agentHPPercent(agent)} max={100} height={10} showLabel />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <StatBox icon={<Zap size={14} />} label="Tasks Done" value={String(agent.tasks_completed)} />
            <StatBox icon={<Clock size={14} />} label="Turns" value={String(agent.turns_used)} />
          </div>
        </div>

        <div className="border-t border-sumi-700/30 px-6 py-4">
          <button
            onClick={() => stopMutation.mutate()}
            disabled={stopMutation.isPending || agent.status === "dead"}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-bengara/30 bg-bengara/10 px-4 py-2.5 text-sm font-medium text-bengara transition-all hover:border-bengara/50 hover:bg-bengara/20 disabled:opacity-40"
          >
            <StopCircle size={14} />
            {stopMutation.isPending ? "Stopping..." : "Stop Agent"}
          </button>
        </div>
      </motion.div>
    </>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-sumi-600">{label}</span>
      <span className="font-mono text-xs capitalize text-torinoko">{value}</span>
    </div>
  );
}

function StatBox({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="glass-panel-subtle flex flex-col items-center gap-1 p-3">
      <span className="text-aozora">{icon}</span>
      <span className="font-mono text-lg font-bold text-torinoko">{value}</span>
      <span className="text-[9px] uppercase tracking-widest text-sumi-600">{label}</span>
    </div>
  );
}

function SpawnDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("researcher");
  const qc = useQueryClient();

  const spawnMutation = useMutation({
    mutationFn: () =>
      apiFetch("/api/agents/spawn", {
        method: "POST",
        body: JSON.stringify({ name, role }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      onClose();
    },
  });

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        className="fixed left-1/2 top-1/2 z-50 w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-sumi-700/40 bg-sumi-900/95 p-6 shadow-2xl backdrop-blur-md"
      >
        <h2 className="mb-5 font-heading text-lg font-bold text-torinoko">Spawn Agent</h2>

        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. researcher-01"
              className="w-full rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko placeholder-sumi-600 outline-none transition-colors focus:border-aozora/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko outline-none transition-colors focus:border-aozora/50"
            >
              <option value="researcher">Researcher</option>
              <option value="architect">Architect</option>
              <option value="archeologist">Archeologist</option>
              <option value="coder">Coder</option>
              <option value="tester">Tester</option>
              <option value="general">General</option>
            </select>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-sumi-600 transition-colors hover:text-torinoko"
          >
            Cancel
          </button>
          <button
            onClick={() => spawnMutation.mutate()}
            disabled={!name.trim() || spawnMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-aozora/20 px-4 py-2 text-sm font-medium text-aozora transition-all hover:bg-aozora/30 disabled:opacity-40"
          >
            <Plus size={14} />
            {spawnMutation.isPending ? "Spawning..." : "Spawn"}
          </button>
        </div>

        {spawnMutation.isError && (
          <p className="mt-3 text-xs text-bengara">
            Failed to spawn agent. Check the API server.
          </p>
        )}
      </motion.div>
    </>
  );
}
