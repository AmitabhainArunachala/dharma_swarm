"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { colors } from "@/lib/theme";

interface XPBarProps {
  value: number;
  max?: number;
  label?: string;
  className?: string;
}

export function XPBar({
  value,
  max = 1,
  label = "Fitness",
  className,
}: XPBarProps) {
  const percent = Math.max(0, Math.min(100, (value / max) * 100));

  return (
    <div className={cn("w-full", className)}>
      <div className="mb-1.5 flex items-center justify-between">
        <span
          className="text-[10px] font-semibold uppercase tracking-[0.12em]"
          style={{ color: colors.kitsurubami }}
        >
          {label}
        </span>
        <span
          className="text-xs font-bold"
          style={{ color: colors.torinoko, fontFamily: "var(--font-mono)" }}
        >
          {value.toFixed(3)}
          <span style={{ color: colors.sumi[600] }}> / {max.toFixed(1)}</span>
        </span>
      </div>

      <div
        className="relative overflow-hidden rounded-full"
        style={{
          height: 10,
          backgroundColor: colors.sumi[800],
        }}
      >
        {/* Animated gradient fill */}
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{
            type: "spring",
            stiffness: 80,
            damping: 20,
          }}
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            background: `linear-gradient(90deg, ${colors.aozora}, ${colors.botan})`,
            boxShadow: `0 0 12px color-mix(in srgb, ${colors.aozora} 30%, transparent), 0 0 4px color-mix(in srgb, ${colors.botan} 20%, transparent)`,
          }}
        />

        {/* Shimmer */}
        <div
          className="absolute inset-0 rounded-full opacity-20"
          style={{
            background:
              "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.2) 50%, transparent 100%)",
            backgroundSize: "200% 100%",
            animation: "shimmer 2.5s linear infinite",
          }}
        />
      </div>
    </div>
  );
}
