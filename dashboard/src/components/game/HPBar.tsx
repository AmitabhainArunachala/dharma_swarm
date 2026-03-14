"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { colors } from "@/lib/theme";

interface HPBarProps {
  value: number;
  max?: number;
  height?: number;
  showLabel?: boolean;
  statusIcons?: React.ReactNode;
  className?: string;
}

function getHPGradient(percent: number): string {
  if (percent > 70) {
    // Green gradient (healthy)
    return `linear-gradient(90deg, ${colors.rokusho}, #A8C4AA)`;
  }
  if (percent > 30) {
    // Yellow gradient (degraded)
    return `linear-gradient(90deg, ${colors.kinpaku}, #E0C46A)`;
  }
  // Red gradient (critical)
  return `linear-gradient(90deg, ${colors.bengara}, #D4A0A0)`;
}

function getHPGlowColor(percent: number): string {
  if (percent > 70) return colors.rokusho;
  if (percent > 30) return colors.kinpaku;
  return colors.bengara;
}

export function HPBar({
  value,
  max = 100,
  height = 8,
  showLabel = false,
  statusIcons,
  className,
}: HPBarProps) {
  const percent = Math.max(0, Math.min(100, (value / max) * 100));
  const glowColor = getHPGlowColor(percent);

  return (
    <div className={cn("relative", className)}>
      {showLabel && (
        <div className="mb-1 flex items-center justify-between">
          <span
            className="text-[10px] font-medium uppercase tracking-wider"
            style={{ color: colors.kitsurubami }}
          >
            HP
          </span>
          <span
            className="text-[10px] font-bold"
            style={{ color: colors.torinoko, fontFamily: "var(--font-mono)" }}
          >
            {Math.round(value)}/{max}
          </span>
        </div>
      )}

      <div
        className="relative overflow-hidden rounded-full"
        style={{
          height,
          backgroundColor: colors.sumi[800],
        }}
      >
        {/* Fill bar */}
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{
            duration: 0.8,
            ease: [0.22, 1, 0.36, 1],
          }}
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            background: getHPGradient(percent),
            boxShadow: `0 0 8px color-mix(in srgb, ${glowColor} 40%, transparent)`,
          }}
        />

        {/* Shimmer overlay */}
        <div
          className="absolute inset-0 rounded-full opacity-30"
          style={{
            background:
              "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 50%, transparent 100%)",
            backgroundSize: "200% 100%",
            animation: "shimmer 3s linear infinite",
          }}
        />

        {/* Status icons overlay */}
        {statusIcons && (
          <div className="absolute inset-0 flex items-center justify-end pr-1">
            {statusIcons}
          </div>
        )}
      </div>
    </div>
  );
}
