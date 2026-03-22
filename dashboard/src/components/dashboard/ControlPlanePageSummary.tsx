"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import {
  buildControlPlanePageSummary,
  type ControlPlanePageSummaryItem,
} from "@/lib/controlPlaneShell";
import type { ControlPlaneRouteId, ControlPlaneSurface } from "@/lib/controlPlaneSurfaces";
import { colors } from "@/lib/theme";
import type { RuntimeControlPlaneSnapshot } from "@/lib/runtimeControlPlane";

interface ControlPlanePageSummaryProps {
  routeId: ControlPlaneRouteId;
  snapshot: RuntimeControlPlaneSnapshot;
  surfaces: ControlPlaneSurface[];
}

function toneStyles(tone: ControlPlanePageSummaryItem["tone"]): {
  border: string;
  background: string;
  text: string;
} {
  if (tone === "ok") {
    return {
      border: `color-mix(in srgb, ${colors.rokusho} 24%, transparent)`,
      background: `color-mix(in srgb, ${colors.rokusho} 8%, transparent)`,
      text: colors.rokusho,
    };
  }
  if (tone === "warn") {
    return {
      border: `color-mix(in srgb, ${colors.kinpaku} 24%, transparent)`,
      background: `color-mix(in srgb, ${colors.kinpaku} 8%, transparent)`,
      text: colors.kinpaku,
    };
  }
  if (tone === "error") {
    return {
      border: `color-mix(in srgb, ${colors.bengara} 24%, transparent)`,
      background: `color-mix(in srgb, ${colors.bengara} 8%, transparent)`,
      text: colors.bengara,
    };
  }
  return {
    border: `color-mix(in srgb, ${colors.sumi[600]} 20%, transparent)`,
    background: `color-mix(in srgb, ${colors.sumi[600]} 8%, transparent)`,
    text: colors.sumi[600],
  };
}

export function ControlPlanePageSummary({
  routeId,
  snapshot,
  surfaces,
}: ControlPlanePageSummaryProps) {
  const items = buildControlPlanePageSummary({ routeId, snapshot, surfaces });

  return (
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => {
        const tone = toneStyles(item.tone);
        return (
          <article
            key={item.label}
            className="rounded-2xl border bg-sumi-900/55 px-4 py-3"
            style={{ borderColor: tone.border }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-sumi-500">
              {item.label}
            </div>
            <div
              className="mt-2 text-sm font-medium"
              style={{
                color: tone.text,
                backgroundColor: tone.background,
              }}
            >
              {item.value}
            </div>
            <p className="mt-2 text-xs text-sumi-400">{item.detail}</p>
            {item.commands?.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {item.commands.map((command) => (
                  <code
                    key={command}
                    className="rounded bg-sumi-950/75 px-2 py-1 text-[10px] text-sumi-300"
                  >
                    {command}
                  </code>
                ))}
              </div>
            ) : null}
            {item.href && item.actionLabel ? (
              <Link
                href={item.href}
                className="mt-3 inline-flex items-center gap-1 text-xs font-medium transition-colors hover:text-torinoko"
                style={{ color: tone.text }}
              >
                {item.actionLabel}
                <ArrowUpRight size={12} />
              </Link>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
