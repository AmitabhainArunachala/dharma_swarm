"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, TrendingDown, ChevronDown } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string | number;
  trend?: "up" | "down" | null;
  trendLabel?: string;
  accentColor?: string;
  className?: string;
  index?: number;
  expandable?: boolean;
  expandContent?: React.ReactNode;
  href?: string;
}

export function MetricCard({
  label,
  value,
  trend,
  trendLabel,
  accentColor = "var(--color-aozora)",
  className,
  index = 0,
  expandable,
  expandContent,
  href,
}: MetricCardProps) {
  const [expanded, setExpanded] = useState(false);

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
        scale: expandable ? 1.0 : 1.02,
        transition: { duration: 0.2 },
      }}
      onClick={expandable ? () => setExpanded((v) => !v) : undefined}
      className={cn(
        "glass-panel group relative overflow-hidden p-5",
        "transition-shadow duration-300",
        expandable && "cursor-pointer",
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

        <div className="flex items-center gap-2">
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
          {expandable && (
            <ChevronDown className={cn("h-4 w-4 text-sumi-600 transition-transform duration-300", expanded && "rotate-180")} />
          )}
        </div>
      </div>

      <AnimatePresence initial={false}>
        {expanded && expandContent && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-3 border-t border-sumi-700/30 pt-3">
              {expandContent}
              {href && (
                <Link
                  href={href}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-2 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-aozora transition-colors hover:text-aozora/80"
                >
                  View All →
                </Link>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
