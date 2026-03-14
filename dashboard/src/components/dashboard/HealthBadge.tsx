"use client";

import { cn } from "@/lib/utils";

type HealthStatus = "healthy" | "degraded" | "critical" | "unknown";

interface HealthBadgeProps {
  status: HealthStatus;
  label?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const statusConfig: Record<
  HealthStatus,
  { color: string; pulse: string; label: string }
> = {
  healthy: {
    color: "var(--color-rokusho)",
    pulse: "animate-pulse-gentle",
    label: "Healthy",
  },
  degraded: {
    color: "var(--color-kinpaku)",
    pulse: "animate-pulse-fast",
    label: "Degraded",
  },
  critical: {
    color: "var(--color-bengara)",
    pulse: "animate-pulse-rapid",
    label: "Critical",
  },
  unknown: {
    color: "var(--color-fuji)",
    pulse: "",
    label: "Unknown",
  },
};

const sizeMap = {
  sm: "h-2 w-2",
  md: "h-2.5 w-2.5",
  lg: "h-3 w-3",
};

/* Pulse keyframes are in globals.css:
   animate-pulse-gentle: 3s
   animate-pulse-fast: 1.5s
   animate-pulse-rapid: 0.8s
*/

export function HealthBadge({
  status,
  label: showLabel = false,
  size = "md",
  className,
}: HealthBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.unknown;

  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="relative flex">
        {/* Glow ring */}
        {config.pulse && (
          <span
            className={cn("absolute inset-0 rounded-full", config.pulse)}
            style={{
              backgroundColor: config.color,
              opacity: 0.4,
              transform: "scale(1.8)",
              filter: "blur(3px)",
            }}
          />
        )}
        {/* Solid dot */}
        <span
          className={cn("relative rounded-full", sizeMap[size], config.pulse)}
          style={{ backgroundColor: config.color }}
        />
      </span>
      {showLabel && (
        <span
          className="text-xs font-medium capitalize"
          style={{ color: config.color }}
        >
          {config.label}
        </span>
      )}
    </span>
  );
}
