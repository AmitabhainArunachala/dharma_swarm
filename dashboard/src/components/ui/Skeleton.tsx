"use client";

import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
  /** Width as tailwind class or inline style */
  width?: string;
  /** Height as tailwind class or inline style */
  height?: string;
  /** Round variant for avatars / indicators */
  round?: boolean;
}

export function Skeleton({ className, width, height, round }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-shimmer bg-sumi-800",
        round ? "rounded-full" : "rounded-md",
        width,
        height,
        className,
      )}
      style={{
        backgroundImage:
          "linear-gradient(90deg, transparent, rgba(255,255,255,0.04), transparent)",
        backgroundSize: "200% 100%",
      }}
    />
  );
}

/** Skeleton row for tables — full-width bar with optional column count */
export function SkeletonRow({ cols = 4 }: { cols?: number }) {
  return (
    <div className="flex items-center gap-4 px-5 py-3">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn("h-4", i === 0 ? "w-32" : "w-20")}
        />
      ))}
    </div>
  );
}

/** Multiple skeleton rows for loading tables */
export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-1">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} cols={cols} />
      ))}
    </div>
  );
}

/** Skeleton card for loading metric cards */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("glass-panel space-y-3 p-4", className)}>
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-8 w-16" />
    </div>
  );
}
