"use client";

import { motion } from "framer-motion";
import { Cable, Server, Cpu, Shield, Wrench } from "lucide-react";
import { useAgentWorkspace } from "../layout";
import { stagger, tierColor } from "@/components/agent-workspace/shared";
import { colors, glowBorder } from "@/lib/theme";

export default function AgentConnectionsPage() {
  const { agent, config, providerStatus, availableModels } = useAgentWorkspace();
  if (!agent) return null;

  const currentProvider = agent.provider ?? config?.provider ?? "unknown";
  const currentModel = agent.model ?? config?.model ?? "unknown";
  const agentTier = config?.tier ?? "unknown";

  return (
    <motion.div className="space-y-6" variants={stagger.container} initial="hidden" animate="show">
      {/* ── Connection Cards ──────────────────────────────── */}
      <motion.div variants={stagger.item} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Provider */}
        <div className="glass-panel p-5" style={{ boxShadow: glowBorder(colors.aozora, 0.1) }}>
          <div className="flex items-center gap-2 mb-3">
            <Server size={16} style={{ color: colors.aozora }} />
            <h3 className="text-[10px] font-semibold uppercase tracking-widest text-kitsurubami">Provider</h3>
          </div>
          <p className="font-mono text-lg font-bold text-torinoko">{currentProvider}</p>
          <p className="mt-1 text-[10px] text-sumi-600">LLM inference provider</p>
        </div>

        {/* Model */}
        <div className="glass-panel p-5" style={{ boxShadow: glowBorder(colors.kinpaku, 0.1) }}>
          <div className="flex items-center gap-2 mb-3">
            <Cpu size={16} style={{ color: colors.kinpaku }} />
            <h3 className="text-[10px] font-semibold uppercase tracking-widest text-kitsurubami">Model</h3>
          </div>
          <p className="font-mono text-lg font-bold text-torinoko">{currentModel}</p>
          <div className="mt-1 flex items-center gap-2">
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

        {/* Role */}
        <div className="glass-panel p-5" style={{ boxShadow: glowBorder(colors.rokusho, 0.1) }}>
          <div className="flex items-center gap-2 mb-3">
            <Shield size={16} style={{ color: colors.rokusho }} />
            <h3 className="text-[10px] font-semibold uppercase tracking-widest text-kitsurubami">Role</h3>
          </div>
          <p className="font-mono text-lg font-bold capitalize text-torinoko">{agent.role}</p>
          <p className="mt-1 text-[10px] text-sumi-600">Behavioral specialization</p>
        </div>
      </motion.div>

      {/* ── Strengths ─────────────────────────────────────── */}
      {config?.strengths && config.strengths.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel p-5">
          <div className="flex items-center gap-2 mb-3">
            <Wrench size={16} style={{ color: colors.fuji }} />
            <h3 className="text-[10px] font-semibold uppercase tracking-widest text-kitsurubami">Capabilities</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {config.strengths.map((s) => (
              <span
                key={s}
                className="rounded-lg px-3 py-1.5 text-xs font-medium"
                style={{
                  color: colors.fuji,
                  backgroundColor: `color-mix(in srgb, ${colors.fuji} 10%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${colors.fuji} 20%, transparent)`,
                }}
              >
                {s}
              </span>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Available Models ──────────────────────────────── */}
      {availableModels && availableModels.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Available Models <span className="ml-2 text-sumi-600">({availableModels.length})</span>
            </h3>
          </div>
          <div className="divide-y divide-sumi-700/10">
            {availableModels.map((m) => (
              <div key={m.model_id} className="flex items-center justify-between px-5 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-torinoko">{m.label}</span>
                  {m.model_id === currentModel && (
                    <span className="rounded bg-aozora/15 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-aozora">
                      active
                    </span>
                  )}
                </div>
                <span
                  className="rounded px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider"
                  style={{
                    color: tierColor(m.tier ?? "unknown"),
                    backgroundColor: `color-mix(in srgb, ${tierColor(m.tier ?? "unknown")} 15%, transparent)`,
                  }}
                >
                  {m.tier}
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Provider Network ──────────────────────────────── */}
      {Array.isArray(providerStatus) && providerStatus.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Provider Network <span className="ml-2 text-sumi-600">({providerStatus.length})</span>
            </h3>
          </div>
          <div className="divide-y divide-sumi-700/10">
            {providerStatus.map((ps) => (
              <div key={ps.provider} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3">
                  <Cable size={14} className="text-sumi-600" />
                  <span className="font-mono text-xs text-torinoko">{ps.provider}</span>
                  {ps.provider === currentProvider && (
                    <span className="rounded bg-aozora/15 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-aozora">
                      active
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{
                      backgroundColor: ps.available ? colors.rokusho : colors.bengara,
                      boxShadow: `0 0 6px ${ps.available ? colors.rokusho : colors.bengara}60`,
                    }}
                  />
                  <span className="text-xs" style={{ color: ps.available ? colors.rokusho : colors.bengara }}>
                    {ps.available ? "Online" : "Offline"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}
