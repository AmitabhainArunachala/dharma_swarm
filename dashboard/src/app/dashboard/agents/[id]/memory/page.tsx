"use client";

import { motion } from "framer-motion";
import { Brain, Archive, User, Clock, Eye, Tag } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAgentWorkspace } from "../layout";
import { stagger } from "@/components/agent-workspace/shared";
import { colors, glowBorder, glowBox } from "@/lib/theme";
import { HPBar } from "@/components/game/HPBar";
import { apiFetch } from "@/lib/api";

/* ─── Types ────────────────────────────────────────────────── */

interface MemoryEntry {
  key: string;
  value: string;
  category: "working" | "archival" | "persona" | "lesson" | "pattern";
  importance: number;
  access_count: number;
  created_at: string;
  updated_at: string;
  source: string;
}

interface AgentMemory {
  working: MemoryEntry[];
  archival: MemoryEntry[];
  persona: MemoryEntry[];
}

/* ─── Helpers ──────────────────────────────────────────────── */

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function categoryBadge(category: string, accent: string) {
  return (
    <span
      className="shrink-0 rounded px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider"
      style={{
        color: accent,
        backgroundColor: `color-mix(in srgb, ${accent} 14%, transparent)`,
      }}
    >
      {category}
    </span>
  );
}

/* ─── Memory Entry Card ────────────────────────────────────── */

function MemoryCard({
  entry,
  accent,
  hot = false,
}: {
  entry: MemoryEntry;
  accent: string;
  hot?: boolean;
}) {
  const importancePct = Math.round(entry.importance * 100);

  return (
    <div
      className="glass-panel p-4 transition-all"
      style={{
        boxShadow: hot
          ? `${glowBorder(accent, 0.18)}, ${glowBox(accent, 0.04)}`
          : glowBorder(accent, 0.08),
      }}
    >
      {/* Key + category row */}
      <div className="flex items-start justify-between gap-2">
        <span
          className="font-mono text-sm font-bold leading-snug"
          style={{ color: accent }}
        >
          {entry.key}
        </span>
        {categoryBadge(entry.category, accent)}
      </div>

      {/* Value */}
      <p className="mt-2 text-xs leading-relaxed text-torinoko">{entry.value}</p>

      {/* Importance bar */}
      <div className="mt-3">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
            Importance
          </span>
          <span
            className="font-mono text-[9px] font-bold"
            style={{ color: accent }}
          >
            {importancePct}%
          </span>
        </div>
        <HPBar value={importancePct} max={100} height={4} />
      </div>

      {/* Footer: source + timestamps + access count */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-sumi-700/20 pt-2">
        {entry.source && (
          <div className="flex items-center gap-1 text-[9px] text-sumi-600">
            <Tag size={9} />
            <span>{entry.source}</span>
          </div>
        )}
        <div className="flex items-center gap-1 text-[9px] text-sumi-600">
          <Eye size={9} />
          <span>{entry.access_count} reads</span>
        </div>
        <div className="flex items-center gap-1 text-[9px] text-sumi-600">
          <Clock size={9} />
          <span>updated {formatTs(entry.updated_at)}</span>
        </div>
      </div>
    </div>
  );
}

/* ─── Section ──────────────────────────────────────────────── */

function MemorySection({
  icon,
  title,
  subtitle,
  entries,
  accent,
  hot = false,
  emptyMsg = "No entries",
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  entries: MemoryEntry[];
  accent: string;
  hot?: boolean;
  emptyMsg?: string;
}) {
  return (
    <motion.div variants={stagger.item}>
      <div className="glass-panel overflow-hidden">
        {/* Section header */}
        <div
          className="flex items-center justify-between border-b border-sumi-700/30 px-5 py-3"
          style={
            hot
              ? { borderBottomColor: `color-mix(in srgb, ${accent} 20%, transparent)` }
              : {}
          }
        >
          <div className="flex items-center gap-2">
            <span style={{ color: accent }}>{icon}</span>
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              {title}
            </h2>
            {subtitle && (
              <span className="text-[9px] text-sumi-600">{subtitle}</span>
            )}
          </div>
          <span
            className="rounded px-2 py-0.5 text-[9px] font-bold"
            style={{
              color: accent,
              backgroundColor: `color-mix(in srgb, ${accent} 12%, transparent)`,
            }}
          >
            {entries.length}
          </span>
        </div>

        {/* Entries or empty state */}
        <div className="p-4">
          {entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10">
              <span className="text-sm text-sumi-600">{emptyMsg}</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {entries.map((entry, i) => (
                <MemoryCard key={`${entry.key}-${i}`} entry={entry} accent={accent} hot={hot} />
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* ─── Page ─────────────────────────────────────────────────── */

export default function AgentMemoryPage() {
  const { agent } = useAgentWorkspace();

  const { data, isLoading, error } = useQuery<AgentMemory>({
    queryKey: ["agent-memory", agent?.id],
    queryFn: () => apiFetch<AgentMemory>(`/api/agents/${encodeURIComponent(agent!.id)}/memory`),
    enabled: !!agent?.id,
    staleTime: 30_000,
  });

  if (!agent) return null;

  /* ── Loading ── */
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="flex flex-col items-center gap-3">
          <div
            className="h-8 w-8 animate-spin rounded-full border-2 border-t-transparent"
            style={{ borderColor: `${colors.fuji}40`, borderTopColor: colors.fuji }}
          />
          <p className="animate-pulse text-sm text-sumi-600">Loading memory...</p>
        </div>
      </div>
    );
  }

  /* ── Error ── */
  if (error || !data) {
    return (
      <div className="glass-panel flex flex-col items-center gap-3 py-16">
        <Brain size={24} style={{ color: colors.bengara }} />
        <p className="text-sm text-bengara">
          {error instanceof Error ? error.message : "Memory unavailable"}
        </p>
      </div>
    );
  }

  const working = data.working ?? [];
  const archival = data.archival ?? [];
  const persona = data.persona ?? [];

  return (
    <motion.div
      className="space-y-6"
      variants={stagger.container}
      initial="hidden"
      animate="show"
    >
      {/* ── Summary row ────────────────────────────────────── */}
      <motion.div variants={stagger.item}>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Working", count: working.length, max: 10, accent: colors.aozora },
            { label: "Archival", count: archival.length, max: 100, accent: colors.rokusho },
            { label: "Persona", count: persona.length, max: 5, accent: colors.fuji },
          ].map(({ label, count, max, accent }) => (
            <div
              key={label}
              className="glass-panel p-4"
              style={{ boxShadow: glowBorder(accent, 0.12) }}
            >
              <p className="text-[9px] font-semibold uppercase tracking-widest text-sumi-600">
                {label}
              </p>
              <p className="mt-1 font-mono text-2xl font-bold" style={{ color: accent }}>
                {count}
                <span className="ml-1 text-sm font-normal text-sumi-600">/ {max}</span>
              </p>
              <div className="mt-2">
                <HPBar value={count} max={max} height={3} />
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ── Working Memory (hot) ─────────────────────────── */}
      <MemorySection
        icon={<Brain size={15} />}
        title="Working Memory"
        subtitle="hot — always in context"
        entries={working}
        accent={colors.aozora}
        hot
        emptyMsg="No working memory recorded yet"
      />

      {/* ── Archival Memory ──────────────────────────────── */}
      <MemorySection
        icon={<Archive size={15} />}
        title="Archival Memory"
        subtitle="searchable on demand"
        entries={archival}
        accent={colors.rokusho}
        emptyMsg="No archival memory recorded yet"
      />

      {/* ── Persona ──────────────────────────────────────── */}
      <MemorySection
        icon={<User size={15} />}
        title="Persona"
        subtitle="self-description"
        entries={persona}
        accent={colors.fuji}
        emptyMsg="No persona memory recorded yet"
      />
    </motion.div>
  );
}
