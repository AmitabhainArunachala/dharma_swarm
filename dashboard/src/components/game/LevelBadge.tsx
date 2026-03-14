"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { colors } from "@/lib/theme";

const levelNames = [
  "Observer",     // L1
  "Commander",    // L2
  "Architect",    // L3
  "Ontologist",   // L4
  "Composer",     // L5
] as const;

interface LevelBadgeProps {
  level: number;
  className?: string;
  size?: "sm" | "md" | "lg";
}

const sizeConfig = {
  sm: { outer: 36, inner: 28, fontSize: 12, nameSize: 9 },
  md: { outer: 48, inner: 38, fontSize: 16, nameSize: 10 },
  lg: { outer: 64, inner: 50, fontSize: 22, nameSize: 11 },
};

export function LevelBadge({ level, className, size = "md" }: LevelBadgeProps) {
  const clampedLevel = Math.max(1, Math.min(5, level));
  const name = levelNames[clampedLevel - 1];
  const cfg = sizeConfig[size];

  // Glow intensity increases with level
  const glowIntensity = 0.15 + clampedLevel * 0.08;

  return (
    <div className={cn("inline-flex flex-col items-center gap-1.5", className)}>
      {/* Diamond shape via rotated square */}
      <motion.div
        initial={{ scale: 0, rotate: 45 }}
        animate={{ scale: 1, rotate: 45 }}
        transition={{
          type: "spring",
          stiffness: 200,
          damping: 15,
        }}
        className="relative"
        style={{
          width: cfg.outer,
          height: cfg.outer,
        }}
      >
        {/* Outer glow ring */}
        <div
          className="absolute inset-0 rounded-sm"
          style={{
            background: `linear-gradient(135deg, ${colors.aozora}, ${colors.botan})`,
            opacity: glowIntensity,
            filter: "blur(8px)",
          }}
        />

        {/* Border */}
        <div
          className="absolute inset-0 rounded-sm"
          style={{
            background: `linear-gradient(135deg, ${colors.aozora}, color-mix(in srgb, ${colors.botan} 60%, ${colors.aozora}))`,
            padding: 2,
          }}
        >
          {/* Inner fill */}
          <div
            className="flex h-full w-full items-center justify-center rounded-sm"
            style={{
              background: `linear-gradient(135deg, ${colors.sumi[900]}, ${colors.sumi[850]})`,
            }}
          >
            {/* Number (counter-rotate to be upright) */}
            <span
              className="font-bold"
              style={{
                transform: "rotate(-45deg)",
                fontSize: cfg.fontSize,
                color: colors.aozora,
                fontFamily: "var(--font-mono)",
                textShadow: `0 0 8px color-mix(in srgb, ${colors.aozora} 50%, transparent)`,
              }}
            >
              {clampedLevel}
            </span>
          </div>
        </div>
      </motion.div>

      {/* Level name */}
      <motion.span
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.3 }}
        className="font-semibold uppercase tracking-[0.15em]"
        style={{
          fontSize: cfg.nameSize,
          color: colors.kitsurubami,
        }}
      >
        {name}
      </motion.span>
    </div>
  );
}
