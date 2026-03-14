"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string | number;
  trend?: "up" | "down" | null;
  trendLabel?: string;
  accentColor?: string;
  className?: string;
  index?: number;
}

export function MetricCard({
  label,
  value,
  trend,
  trendLabel,
  accentColor = "var(--color-aozora)",
  className,
  index = 0,
}: MetricCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: 0.5,
        delay: index * 0.08,
        ease: [0.22, 1, 0.36, 1],
      }}
      whileHover={{
        scale: 1.02,
        transition: { duration: 0.2 },
      }}
      className={cn(
        "glass-panel group relative overflow-hidden p-5",
        "transition-shadow duration-300",
        className,
      )}
      style={{
        ["--accent" as string]: accentColor,
      }}
    >
      {/* Hover glow border */}
      <div
        className="pointer-events-none absolute inset-0 rounded-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${accentColor} 30%, transparent), 0 0 20px color-mix(in srgb, ${accentColor} 10%, transparent)`,
          borderRadius: "inherit",
        }}
      />

      {/* Top accent line */}
      <div
        className="absolute left-4 right-4 top-0 h-px opacity-40"
        style={{
          background: `linear-gradient(90deg, transparent, ${accentColor}, transparent)`,
        }}
      />

      <p
        className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em]"
        style={{ color: "var(--color-kitsurubami)" }}
      >
        {label}
      </p>

      <div className="flex items-end justify-between gap-3">
        <p
          className="text-[28px] font-bold leading-none tracking-tight"
          style={{
            color: "var(--color-torinoko)",
            fontFamily: "var(--font-mono)",
          }}
        >
          {value}
        </p>

        {trend && (
          <div
            className={cn(
              "flex items-center gap-1 text-xs font-medium",
              trend === "up" ? "text-rokusho" : "text-bengara",
            )}
          >
            {trend === "up" ? (
              <TrendingUp className="h-3.5 w-3.5" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5" />
            )}
            {trendLabel && <span>{trendLabel}</span>}
          </div>
        )}
      </div>
    </motion.div>
  );
}
