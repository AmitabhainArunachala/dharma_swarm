"use client";

import { use, createContext, useContext } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  RefreshCw,
  Sparkles,
  StopCircle,
  AlertTriangle,
  Activity,
  ListTodo,
  MessageSquare,
  Settings2,
  Cable,
  Brain,
} from "lucide-react";
import { useAgent } from "@/hooks/useAgent";
import type { AgentDetailData } from "@/hooks/useAgent";
import { HPBar } from "@/components/game/HPBar";
import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { BackButton, agentHealthStatus, agentHPPercent, tierColor, stagger } from "@/components/agent-workspace/shared";
import { colors, glowBox } from "@/lib/theme";

/* ─── Context ─────────────────────────────────────────────── */

type AgentWorkspaceContextValue = ReturnType<typeof useAgent>;

const AgentWorkspaceContext = createContext<AgentWorkspaceContextValue | null>(null);

export function useAgentWorkspace() {
  const ctx = useContext(AgentWorkspaceContext);
  if (!ctx) throw new Error("useAgentWorkspace must be used within AgentWorkspaceLayout");
  return ctx;
}

/* ─── Tabs ────────────────────────────────────────────────── */

const TABS = [
  { key: "overview", label: "Overview", icon: Activity, href: "" },
  { key: "tasks", label: "Tasks", icon: ListTodo, href: "/tasks" },
  { key: "chat", label: "Chat", icon: MessageSquare, href: "/chat" },
  { key: "config", label: "Config", icon: Settings2, href: "/config" },
  { key: "connections", label: "Connections", icon: Cable, href: "/connections" },
  { key: "memory", label: "Memory", icon: Brain, href: "/memory" },
] as const;

/* ─── Layout ──────────────────────────────────────────────── */

export default function AgentWorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const agentData = useAgent(id);
  const { agent, config, isLoading, error, stopAgent, respawnAgent } = agentData;

  const basePath = `/dashboard/agents/${id}`;

  function isActiveTab(tabHref: string) {
    const fullPath = basePath + tabHref;
    if (tabHref === "") {
      return pathname === basePath || pathname === basePath + "/";
    }
    return pathname.startsWith(fullPath);
  }

  /* Loading */
  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackButton onClick={() => router.push("/dashboard/agents")} />
        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-aozora/30 border-t-aozora" />
            <p className="animate-pulse text-sm text-sumi-600">Loading agent telemetry...</p>
          </div>
        </div>
      </div>
    );
  }

  /* Error */
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
  const agentTier = config?.tier ?? "unknown";
  const providerStatus = agentData.providerStatus;
  const currentProvider = agent.provider ?? config?.provider;
  const providerEntry = Array.isArray(providerStatus)
    ? providerStatus.find((ps) => ps.provider === currentProvider) ?? providerStatus[0]
    : null;
  const providerAvailable = providerEntry?.available ?? false;

  return (
    <AgentWorkspaceContext.Provider value={agentData}>
      <motion.div
        className="space-y-4"
        variants={stagger.container}
        initial="hidden"
        animate="show"
      >
        {/* ── Back + Actions ──────────────────────────────── */}
        <motion.div variants={stagger.item}>
          <div className="flex items-center justify-between">
            <BackButton onClick={() => router.push("/dashboard/agents")} />
            <div className="flex items-center gap-2">
              <button
                onClick={() => qc.invalidateQueries({ queryKey: ["agent-detail", id] })}
                className="flex items-center gap-1.5 rounded-lg border border-sumi-700/40 px-3 py-1.5 text-xs text-sumi-600 transition-colors hover:border-aozora/30 hover:text-aozora"
              >
                <RefreshCw size={12} /> Refresh
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

        {/* ── Identity Header ─────────────────────────────── */}
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
                  <span
                    className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
                    style={{
                      color: colors.kinpaku,
                      backgroundColor: `color-mix(in srgb, ${colors.kinpaku} 15%, transparent)`,
                    }}
                  >
                    {agent.role}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <HealthBadge status={healthState} size="sm" />
                    <span className="text-xs capitalize text-kitsurubami">{agent.status}</span>
                  </div>
                  <span className="text-sumi-700">|</span>
                  <div className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full"
                      style={{
                        backgroundColor: providerAvailable ? colors.rokusho : colors.bengara,
                        boxShadow: `0 0 6px ${providerAvailable ? colors.rokusho : colors.bengara}80`,
                      }}
                    />
                    <span className="text-xs text-sumi-600">
                      {agent.provider ?? config?.provider ?? "unknown"}
                    </span>
                  </div>
                  <span className="text-sumi-700">|</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs text-kitsurubami">
                      {agent.model ?? config?.model ?? "\u2014"}
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

        {/* ── Error Banner ────────────────────────────────── */}
        {agent.error && (
          <motion.div
            variants={stagger.item}
            className="rounded-lg border border-bengara/30 bg-bengara/5 p-5"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-bengara" />
              <div>
                <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-bengara">Error</h2>
                <p className="mt-1 font-mono text-xs text-bengara/80">{agent.error}</p>
              </div>
            </div>
          </motion.div>
        )}

        {/* ── Tab Bar ─────────────────────────────────────── */}
        <motion.div variants={stagger.item}>
          <div className="glass-panel-subtle flex items-center gap-1 overflow-x-auto px-2 py-1">
            {TABS.map((tab) => {
              const active = isActiveTab(tab.href);
              const Icon = tab.icon;
              return (
                <Link
                  key={tab.key}
                  href={basePath + tab.href}
                  className={`relative flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-medium transition-colors ${
                    active
                      ? "text-aozora"
                      : "text-sumi-600 hover:text-kitsurubami"
                  }`}
                >
                  <Icon size={14} />
                  {tab.label}
                  {active && (
                    <motion.div
                      layoutId="agent-tab-underline"
                      className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-aozora"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                </Link>
              );
            })}
          </div>
        </motion.div>

        {/* ── Tab Content ─────────────────────────────────── */}
        <motion.div variants={stagger.item}>
          {children}
        </motion.div>
      </motion.div>
    </AgentWorkspaceContext.Provider>
  );
}
