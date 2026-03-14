"use client";

/**
 * DHARMA COMMAND -- Gates page (L3).
 * Dharmic telos gate review with sequential pipeline visualization.
 */

import { motion } from "framer-motion";
import {
  Shield,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  MinusCircle,
} from "lucide-react";
import { useGates, type GateResult } from "@/hooks/useGates";
import { colors } from "@/lib/theme";

const gateDescriptions: Record<string, string> = {
  AHIMSA: "Non-harm. Blocks actions that could cause damage to systems or data.",
  SATYA: "Truth. Prevents credential leaks and ensures honest communication.",
  CONSENT: "Explicit consent required for irreversible operations.",
  VYAVASTHIT: "Natural order. Ensures changes follow evolutionary protocol.",
  REVERSIBILITY: "All mutations must be reversible with lineage tracking.",
  SVABHAAVA: "True nature. Validates alignment with system identity.",
  BHED_GNAN: "Discriminative knowledge. Separates signal from noise.",
  WITNESS: "The act of checking IS witnessing. Observation without interference.",
};

const statusConfig: Record<
  string,
  { icon: typeof CheckCircle2; color: string; label: string }
> = {
  pass: { icon: CheckCircle2, color: colors.rokusho, label: "Pass" },
  fail: { icon: XCircle, color: colors.bengara, label: "Fail" },
  warn: { icon: AlertTriangle, color: colors.kinpaku, label: "Warn" },
  skip: { icon: MinusCircle, color: colors.sumi[600], label: "Skip" },
};

export default function GatesPage() {
  const { gates, isLoading } = useGates();

  const overallColor =
    gates?.overall === "pass"
      ? colors.rokusho
      : gates?.overall === "fail"
        ? colors.bengara
        : gates?.overall === "warn"
          ? colors.kinpaku
          : colors.sumi[600];

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-rokusho" />
          <h1 className="glow-rokusho font-heading text-2xl font-bold tracking-tight text-rokusho">
            Telos Gates
          </h1>
        </div>
        <p className="mt-1 text-sm text-sumi-600">
          {isLoading
            ? "Checking gate status..."
            : gates
              ? `${gates.pass_count} pass, ${gates.fail_count} fail, ${gates.warn_count} warn`
              : "Awaiting gate data."}
        </p>
      </motion.div>

      {/* Overall status */}
      {gates && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-panel flex items-center gap-4 p-5"
        >
          <div
            className="flex h-12 w-12 items-center justify-center rounded-lg"
            style={{
              backgroundColor: `color-mix(in srgb, ${overallColor} 15%, transparent)`,
              border: `1px solid color-mix(in srgb, ${overallColor} 30%, transparent)`,
            }}
          >
            <Shield size={24} style={{ color: overallColor }} />
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Overall Status
            </p>
            <p
              className="font-heading text-xl font-bold uppercase"
              style={{ color: overallColor }}
            >
              {gates.overall}
            </p>
          </div>
          <div className="ml-auto flex gap-6">
            <CountBadge label="Pass" count={gates.pass_count} color={colors.rokusho} />
            <CountBadge label="Fail" count={gates.fail_count} color={colors.bengara} />
            <CountBadge label="Warn" count={gates.warn_count} color={colors.kinpaku} />
          </div>
        </motion.div>
      )}

      {/* Gate pipeline */}
      {isLoading ? (
        <div className="glass-panel flex items-center justify-center py-16">
          <p className="animate-pulse text-sm text-sumi-600">Loading gates...</p>
        </div>
      ) : (
        <div className="relative space-y-0">
          {/* Vertical pipeline line */}
          <div
            className="absolute left-[31px] top-4 bottom-4 w-px"
            style={{
              background: `linear-gradient(to bottom, ${colors.sumi[700]}, color-mix(in srgb, ${colors.sumi[700]} 30%, transparent))`,
            }}
          />

          {gates?.gates.map((gate, i) => (
            <GateRow key={gate.name} gate={gate} index={i} />
          ))}

          {(!gates || gates.gates.length === 0) && (
            <div className="glass-panel flex items-center justify-center py-12">
              <p className="text-sm text-sumi-600">No gate data available</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gate row
// ---------------------------------------------------------------------------

function GateRow({ gate, index }: { gate: GateResult; index: number }) {
  const config = statusConfig[gate.status] ?? statusConfig.skip;
  const Icon = config.icon;
  const desc = gateDescriptions[gate.name] ?? "";

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: index * 0.08 }}
      className="relative flex items-start gap-5 py-3 pl-3"
    >
      {/* Status icon (on the pipeline line) */}
      <div
        className="relative z-10 flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-full"
        style={{
          backgroundColor: `color-mix(in srgb, ${config.color} 15%, ${colors.sumi[900]})`,
          boxShadow: `0 0 10px color-mix(in srgb, ${config.color} 20%, transparent)`,
        }}
      >
        <Icon size={14} style={{ color: config.color }} />
      </div>

      {/* Content card */}
      <div className="glass-panel-subtle flex-1 p-4">
        <div className="mb-1 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h3
              className="font-heading text-sm font-bold uppercase tracking-wider"
              style={{ color: config.color }}
            >
              {gate.name}
            </h3>
            <span
              className="rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider"
              style={{
                color: config.color,
                backgroundColor: `color-mix(in srgb, ${config.color} 10%, transparent)`,
                border: `1px solid color-mix(in srgb, ${config.color} 20%, transparent)`,
              }}
            >
              {config.label}
            </span>
          </div>
          {gate.score > 0 && (
            <span className="font-mono text-xs text-sumi-600">
              {gate.score.toFixed(2)}
            </span>
          )}
        </div>

        <p className="text-xs leading-relaxed text-sumi-600">
          {gate.message || desc}
        </p>

        {desc && gate.message && (
          <p className="mt-1 text-[10px] italic text-sumi-700">{desc}</p>
        )}
      </div>
    </motion.div>
  );
}

function CountBadge({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <div className="flex flex-col items-center">
      <span className="font-mono text-lg font-bold" style={{ color }}>
        {count}
      </span>
      <span className="text-[9px] uppercase tracking-widest text-sumi-600">
        {label}
      </span>
    </div>
  );
}
