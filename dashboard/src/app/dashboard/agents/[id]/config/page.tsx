"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, Hash } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAgentWorkspace } from "../layout";
import { stagger, tierColor, MiniStat } from "@/components/agent-workspace/shared";
import { apiFetch } from "@/lib/api";
import { colors } from "@/lib/theme";

const AUTONOMY_COLORS: Record<string, string> = {
  LOCKED: colors.bengara,
  CAUTIOUS: colors.kinpaku,
  BALANCED: colors.aozora,
  AGGRESSIVE: colors.botan,
  FULL: colors.rokusho,
};

interface AgentProfile {
  autonomy: string;
  tasks_succeeded: number;
  tasks_failed: number;
  gate_pass_rate: number;
  token_usage: number;
  avg_duration: number;
  specializations: string[];
  adapted_at: string | null;
}

interface NoteEntry {
  filename: string;
  content: string;
  size: number;
  modified: number;
}

interface AgentNotes {
  notes: NoteEntry[];
}

function NoteBlock({ note }: { note: NoteEntry }) {
  const [expanded, setExpanded] = useState(false);
  const truncated = note.content.length > 2000 && !expanded;
  const display = truncated ? note.content.slice(0, 2000) : note.content;
  const modifiedDate = new Date(note.modified * 1000).toLocaleString();
  const sizeKb = (note.size / 1024).toFixed(1);

  return (
    <div className="glass-panel p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="font-mono text-xs font-semibold text-torinoko">{note.filename}</span>
        <div className="flex shrink-0 items-center gap-3 text-[10px] text-sumi-600">
          <span>{sizeKb} KB</span>
          <span>{modifiedDate}</span>
        </div>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs font-mono text-torinoko leading-relaxed">
        {display}
      </pre>
      {note.content.length > 2000 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 text-[10px] font-semibold text-aozora transition-colors hover:text-aozora/80"
        >
          {expanded ? "Show less" : `Show more (${note.content.length - 2000} chars remaining)`}
        </button>
      )}
    </div>
  );
}

export default function AgentConfigPage() {
  const { agent, config, availableModels, availableRoles, providerStatus, updateConfig } = useAgentWorkspace();
  if (!agent) return null;

  const agentId = agent.agent_slug;

  const currentProvider = agent.provider ?? config?.provider;
  const providerEntry = Array.isArray(providerStatus)
    ? providerStatus.find((ps) => ps.provider === currentProvider) ?? providerStatus[0]
    : null;
  const providerAvailable = providerEntry?.available ?? false;

  const modelsByTier = (availableModels ?? []).reduce<Record<string, typeof availableModels>>(
    (acc, m) => {
      const t = m.tier || "other";
      if (!acc[t]) acc[t] = [];
      acc[t]!.push(m);
      return acc;
    },
    {},
  );

  const profileQuery = useQuery<AgentProfile>({
    queryKey: ["agent-profile", agentId],
    queryFn: () => apiFetch<AgentProfile>(`/api/agents/${encodeURIComponent(agentId)}/profile`),
    enabled: !!agentId,
    refetchInterval: 30_000,
  });

  const notesQuery = useQuery<AgentNotes>({
    queryKey: ["agent-notes", agentId],
    queryFn: () => apiFetch<AgentNotes>(`/api/agents/${encodeURIComponent(agentId)}/notes`),
    enabled: !!agentId,
    refetchInterval: 60_000,
  });

  const profile = profileQuery.data;
  const notes = notesQuery.data?.notes ?? [];

  return (
    <motion.div className="space-y-6" variants={stagger.container} initial="hidden" animate="show">
      <motion.div variants={stagger.item} className="glass-panel p-5">
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Configuration</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Model selector */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Model</label>
            <div className="relative">
              <select
                className="w-full appearance-none rounded-lg border border-sumi-700/40 bg-sumi-900 px-3 py-2 pr-8 font-mono text-xs text-torinoko transition-colors focus:border-aozora/50 focus:outline-none"
                value={config?.model ?? agent.model ?? ""}
                onChange={(e) => { if (e.target.value) updateConfig.mutate({ model: e.target.value }); }}
                disabled={updateConfig.isPending}
              >
                {Object.entries(modelsByTier).map(([tier, models]) => (
                  <optgroup key={tier} label={tier.toUpperCase()}>
                    {(models ?? []).map((m) => (
                      <option key={m.model_id} value={m.model_id}>{m.label}</option>
                    ))}
                  </optgroup>
                ))}
                {availableModels && !availableModels.some((m) => m.model_id === (config?.model ?? agent.model)) && (
                  <option value={config?.model ?? agent.model ?? ""}>{config?.model ?? agent.model ?? "unknown"}</option>
                )}
              </select>
              <ChevronDown size={12} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sumi-600" />
            </div>
          </div>

          {/* Role selector */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Role</label>
            <div className="relative">
              <select
                className="w-full appearance-none rounded-lg border border-sumi-700/40 bg-sumi-900 px-3 py-2 pr-8 font-mono text-xs text-torinoko transition-colors focus:border-aozora/50 focus:outline-none"
                value={config?.role ?? agent.role ?? ""}
                onChange={(e) => { if (e.target.value) updateConfig.mutate({ role: e.target.value }); }}
                disabled={updateConfig.isPending}
              >
                {(availableRoles ?? []).map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
                {availableRoles && !availableRoles.includes(config?.role ?? agent.role ?? "") && (
                  <option value={config?.role ?? agent.role ?? ""}>{config?.role ?? agent.role ?? "unknown"}</option>
                )}
              </select>
              <ChevronDown size={12} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sumi-600" />
            </div>
          </div>

          {/* Thread */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Thread</label>
            <div className="flex items-center gap-2 rounded-lg border border-sumi-700/20 bg-sumi-850/50 px-3 py-2">
              <Hash size={11} className="shrink-0 text-sumi-600" />
              <span className="truncate font-mono text-xs text-kitsurubami">{config?.thread ?? "\u2014"}</span>
            </div>
          </div>

          {/* Provider connection */}
          <div>
            <label className="mb-1 block text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Provider</label>
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
              <span className="text-xs font-medium" style={{ color: providerAvailable ? colors.rokusho : colors.bengara }}>
                {providerAvailable ? "Connected" : "Disconnected"}
              </span>
            </div>
          </div>
        </div>

        {/* Strengths pills */}
        {config?.strengths && config.strengths.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            <span className="mr-1 self-center text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Strengths</span>
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

      {/* ── Provider Status Table ─────────────────────────── */}
      {Array.isArray(providerStatus) && providerStatus.length > 0 && (
        <motion.div variants={stagger.item} className="glass-panel overflow-hidden">
          <div className="border-b border-sumi-700/30 px-5 py-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Provider Status</h2>
          </div>
          <div className="divide-y divide-sumi-700/10">
            {providerStatus.map((ps) => (
              <div key={ps.provider} className="flex items-center justify-between px-5 py-3">
                <span className="font-mono text-xs text-torinoko">{ps.provider}</span>
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{
                      backgroundColor: ps.available ? colors.rokusho : colors.bengara,
                      boxShadow: `0 0 6px ${ps.available ? colors.rokusho : colors.bengara}60`,
                    }}
                  />
                  <span className="text-xs" style={{ color: ps.available ? colors.rokusho : colors.bengara }}>
                    {ps.available ? "Available" : "Unavailable"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Agent Profile ─────────────────────────────────── */}
      {profile && profile.autonomy && (
        <motion.div variants={stagger.item} className="glass-panel p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Agent Profile</h2>
            <span
              className="rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest"
              style={{
                color: AUTONOMY_COLORS[profile.autonomy] ?? colors.sumi[600],
                backgroundColor: `color-mix(in srgb, ${AUTONOMY_COLORS[profile.autonomy] ?? colors.sumi[600]} 15%, transparent)`,
                border: `1px solid color-mix(in srgb, ${AUTONOMY_COLORS[profile.autonomy] ?? colors.sumi[600]} 25%, transparent)`,
              }}
            >
              {profile.autonomy}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <MiniStat
              label="Tasks Succeeded"
              value={String(profile.tasks_succeeded)}
              color={colors.rokusho}
            />
            <MiniStat
              label="Tasks Failed"
              value={String(profile.tasks_failed)}
              color={profile.tasks_failed > 0 ? colors.bengara : colors.sumi[600]}
            />
            <MiniStat
              label="Gate Pass Rate"
              value={profile.gate_pass_rate != null ? `${(profile.gate_pass_rate * 100).toFixed(1)}%` : "--"}
              color={(profile.gate_pass_rate ?? 0) >= 0.9 ? colors.rokusho : (profile.gate_pass_rate ?? 0) >= 0.7 ? colors.kinpaku : colors.bengara}
            />
            <MiniStat
              label="Token Usage"
              value={profile.token_usage != null ? (profile.token_usage >= 1000 ? `${(profile.token_usage / 1000).toFixed(1)}k` : String(profile.token_usage)) : "--"}
              color={colors.aozora}
            />
            <MiniStat
              label="Avg Duration"
              value={profile.avg_duration != null ? `${profile.avg_duration.toFixed(1)}s` : "--"}
              color={colors.fuji}
            />
            <MiniStat
              label="Specializations"
              value={profile.specializations.length > 0 ? String(profile.specializations.length) : "—"}
              color={colors.kitsurubami}
            />
          </div>

          {profile.specializations.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="mr-1 self-center text-[9px] font-semibold uppercase tracking-widest text-sumi-600">Specializations</span>
              {profile.specializations.map((spec) => (
                <span
                  key={spec}
                  className="rounded-full px-2.5 py-0.5 text-[10px] font-medium"
                  style={{
                    color: colors.aozora,
                    backgroundColor: `color-mix(in srgb, ${colors.aozora} 12%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${colors.aozora} 20%, transparent)`,
                  }}
                >
                  {spec}
                </span>
              ))}
            </div>
          )}

          {profile.adapted_at && (
            <p className="mt-3 text-[10px] text-sumi-600">
              Last adapted: <span className="text-kitsurubami">{new Date(profile.adapted_at).toLocaleString()}</span>
            </p>
          )}
        </motion.div>
      )}

      {/* ── Agent Notes ───────────────────────────────────── */}
      {notes.length > 0 && (
        <motion.div variants={stagger.item} className="space-y-3">
          <h2 className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">Agent Notes</h2>
          {notes.map((note) => (
            <NoteBlock key={note.filename} note={note} />
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
