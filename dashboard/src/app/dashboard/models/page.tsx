"use client";

/**
 * DHARMA COMMAND -- Model Pool.
 *
 * Shows the actually available chat model profiles sourced from the real
 * /api/chat/status endpoint. Previously this page called /api/pool/top10/status,
 * /api/pool/top10/verify, and /api/pool/models/{id}/profile — none of which
 * exist. This version only shows data the backend actually provides.
 */

import { motion } from "framer-motion";
import {
  CheckCircle2,
  Cpu,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useRuntimeControlPlane } from "@/hooks/useRuntimeControlPlane";
import { getChatProfiles } from "@/lib/chatProfiles";
import { colors } from "@/lib/theme";
import type { ChatProfileOut } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function availabilityTone(profile: ChatProfileOut): {
  color: string;
  border: string;
  bg: string;
} {
  if (profile.available) {
    return {
      color: colors.rokusho,
      border: `color-mix(in srgb, ${colors.rokusho} 35%, transparent)`,
      bg: `color-mix(in srgb, ${colors.rokusho} 8%, transparent)`,
    };
  }
  return {
    color: colors.bengara,
    border: `color-mix(in srgb, ${colors.bengara} 35%, transparent)`,
    bg: `color-mix(in srgb, ${colors.bengara} 8%, transparent)`,
  };
}

function AvailabilityBadge({ profile }: { profile: ChatProfileOut }) {
  const tone = availabilityTone(profile);
  const Icon = profile.available ? CheckCircle2 : XCircle;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]"
      style={{
        color: tone.color,
        borderColor: tone.border,
        backgroundColor: tone.bg,
      }}
    >
      <Icon size={12} />
      {profile.available ? "available" : "unavailable"}
    </span>
  );
}

const ACCENT_COLORS: Record<string, string> = {
  aozora: colors.aozora,
  botan: colors.botan,
  kinpaku: colors.kinpaku,
  rokusho: colors.rokusho,
  bengara: colors.bengara,
  fuji: colors.fuji,
  torinoko: colors.torinoko,
  kitsurubami: colors.kitsurubami,
};

function accentColor(accent: string): string {
  return ACCENT_COLORS[accent] ?? colors.aozora;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ModelsPage() {
  const { chatStatus, isLoading } = useRuntimeControlPlane();
  const profiles = getChatProfiles(chatStatus ?? null);
  const availableCount = profiles.filter((p) => p.available).length;

  return (
    <div className="space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="relative overflow-hidden rounded-[28px] border border-sumi-700/40 bg-sumi-900/90 p-6"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(79,209,217,0.16),transparent_32%),radial-gradient(circle_at_78%_24%,rgba(212,125,181,0.12),transparent_24%),linear-gradient(180deg,rgba(13,14,19,0.25),rgba(13,14,19,0.8))]" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-aozora/30 bg-aozora/10 p-3 text-aozora">
                <Sparkles size={24} />
              </div>
              <div>
                <h1 className="glow-aozora font-heading text-3xl font-bold tracking-tight text-aozora">
                  Model Pool
                </h1>
                <p className="mt-1 max-w-3xl text-sm text-sumi-600">
                  Live model profiles from{" "}
                  <code className="font-mono text-xs">/api/chat/status</code>.
                  Every entry here is backed by the canonical chat contract.
                </p>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <MetricPill label="Advertised Profiles" value={String(profiles.length)} accent={colors.aozora} />
              <MetricPill label="Available Now" value={`${availableCount}/${profiles.length}`} accent={colors.rokusho} />
            </div>
          </div>
        </div>
      </motion.section>

      <div className="grid gap-4 xl:grid-cols-2">
        {profiles.map((profile, index) => (
          <motion.article
            key={profile.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: index * 0.03 }}
            className="glass-panel p-5"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <AvailabilityBadge profile={profile} />
                  {profile.availability_kind && (
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em]"
                      style={{
                        color: colors.sumi[600],
                        backgroundColor: `color-mix(in srgb, ${colors.sumi[600]} 12%, transparent)`,
                      }}
                    >
                      {profile.availability_kind}
                    </span>
                  )}
                </div>
                <div>
                  <h2 className="font-heading text-xl font-semibold text-torinoko">
                    {profile.label}
                  </h2>
                  <p className="mt-1 text-xs text-sumi-600">
                    {profile.summary}
                  </p>
                </div>
              </div>

              <div className="text-right text-xs text-sumi-600">
                <div>{profile.provider}</div>
                <div
                  className="mt-1 inline-block h-2.5 w-2.5 rounded-full"
                  style={{
                    backgroundColor: accentColor(profile.accent),
                    boxShadow: `0 0 6px ${accentColor(profile.accent)}`,
                  }}
                />
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-sumi-700/30 bg-sumi-900/45 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-sumi-600">
                  Model
                </p>
                <p className="mt-2 font-mono text-xs text-torinoko">
                  {profile.model}
                </p>
                <p className="mt-1 text-xs text-sumi-600">
                  {profile.available
                    ? "Callable now"
                    : "Configured but currently unavailable"}
                </p>
              </div>
              <div className="rounded-2xl border border-sumi-700/30 bg-sumi-900/45 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-sumi-600">
                  Status
                </p>
                <p className="mt-2 text-xs text-torinoko">
                  {profile.status_note || "No status note."}
                </p>
              </div>
            </div>
          </motion.article>
        ))}

        {!isLoading && profiles.length === 0 && (
          <div className="glass-panel col-span-full flex min-h-[220px] items-center justify-center text-sm text-sumi-600">
            No model profiles advertised by /api/chat/status.
          </div>
        )}

        {isLoading && (
          <div className="glass-panel col-span-full flex min-h-[220px] items-center justify-center text-sm text-sumi-600">
            <p className="animate-pulse">Loading model profiles…</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricPill({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div
      className="rounded-2xl border px-4 py-3"
      style={{
        borderColor: `color-mix(in srgb, ${accent} 28%, transparent)`,
        backgroundColor: `color-mix(in srgb, ${accent} 8%, transparent)`,
      }}
    >
      <div className="flex items-center gap-2">
        <Cpu size={14} style={{ color: accent }} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-sumi-600">{label}</span>
      </div>
      <p className="mt-2 text-lg font-semibold text-torinoko">{value}</p>
    </div>
  );
}
