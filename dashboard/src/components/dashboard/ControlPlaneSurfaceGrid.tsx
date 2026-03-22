"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import {
  buildControlPlaneSurfaceSections,
  controlPlaneRouteShortcut,
  controlPlaneSurfaceToneLabel,
} from "@/lib/controlPlaneShell";
import type { ControlPlaneSurface } from "@/lib/controlPlaneSurfaces";
import { colors } from "@/lib/theme";

interface ControlPlaneSurfaceGridProps {
  surfaces: ControlPlaneSurface[];
  title?: string;
  detail?: string;
}

function toneClasses(tone: ControlPlaneSurface["tone"]): {
  border: string;
  background: string;
  text: string;
} {
  if (tone === "ok") {
    return {
      border: `color-mix(in srgb, ${colors.rokusho} 28%, transparent)`,
      background: `color-mix(in srgb, ${colors.rokusho} 8%, transparent)`,
      text: colors.rokusho,
    };
  }
  if (tone === "warn") {
    return {
      border: `color-mix(in srgb, ${colors.kinpaku} 28%, transparent)`,
      background: `color-mix(in srgb, ${colors.kinpaku} 8%, transparent)`,
      text: colors.kinpaku,
    };
  }
  if (tone === "error") {
    return {
      border: `color-mix(in srgb, ${colors.bengara} 28%, transparent)`,
      background: `color-mix(in srgb, ${colors.bengara} 8%, transparent)`,
      text: colors.bengara,
    };
  }
  return {
    border: `color-mix(in srgb, ${colors.sumi[600]} 24%, transparent)`,
    background: `color-mix(in srgb, ${colors.sumi[600]} 8%, transparent)`,
    text: colors.sumi[600],
  };
}

export function ControlPlaneSurfaceGrid({
  surfaces,
  title = "Operator Surfaces",
  detail = "These are the canonical dashboard routes for steering the command post, surgical lane, runtime shell, and fleet health.",
}: ControlPlaneSurfaceGridProps) {
  const sections = buildControlPlaneSurfaceSections(surfaces);

  return (
    <section className="rounded-2xl border border-sumi-700/40 bg-sumi-900/55 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sumi-500">
            {title}
          </div>
          <p className="mt-1 max-w-3xl text-sm text-sumi-400">{detail}</p>
        </div>
      </div>

      <div className="mt-4 space-y-4">
        {sections.map((section) => (
          <div key={section.id}>
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-sumi-500">
                  {section.title}
                </div>
                <p className="mt-1 text-xs text-sumi-500">{section.detail}</p>
              </div>
            </div>

            <div
              className={
                section.id === "current"
                  ? "grid gap-3"
                  : section.id === "peers"
                    ? "grid gap-3 md:grid-cols-2 xl:grid-cols-3"
                    : "grid gap-3 md:grid-cols-2 xl:grid-cols-4"
              }
            >
              {section.surfaces.map((surface) => {
                const tone = toneClasses(surface.tone);
                const postureLabel = controlPlaneSurfaceToneLabel(surface.tone);
                const shortcut = controlPlaneRouteShortcut(surface.id);
                return (
                  <article
                    key={surface.id}
                    className="rounded-2xl border bg-sumi-950/60 p-4"
                    style={{ borderColor: tone.border }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.14em] text-sumi-500">
                          Canonical route
                        </div>
                        <h3
                          className="mt-2 font-heading text-lg font-semibold"
                          style={{ color: colors[surface.accent] }}
                        >
                          {surface.label}
                        </h3>
                        {surface.current ? (
                          <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-sumi-500">
                            Route active
                          </div>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <span
                          className="rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]"
                          style={{
                            borderColor: tone.border,
                            backgroundColor: tone.background,
                            color: tone.text,
                          }}
                        >
                          {postureLabel}
                        </span>
                        <code className="rounded bg-sumi-900/85 px-2 py-1 text-[10px] text-sumi-400">
                          {shortcut}
                        </code>
                      </div>
                    </div>

                    <div className="mt-3 text-sm font-medium" style={{ color: tone.text }}>
                      {surface.metric}
                    </div>
                    <p className="mt-3 text-sm text-sumi-300">{surface.summary}</p>
                    <p className="mt-3 text-xs text-sumi-500">{surface.detail}</p>

                    <div className="mt-4 flex items-center justify-between gap-3">
                      <code className="rounded bg-sumi-900/80 px-2 py-1 text-[10px] text-sumi-400">
                        {surface.href}
                      </code>
                      {surface.current ? (
                        <span className="text-xs font-medium text-sumi-400">Route active</span>
                      ) : (
                        <Link
                          href={surface.href}
                          className="inline-flex items-center gap-1 text-xs font-medium transition-colors hover:text-torinoko"
                          style={{ color: colors[surface.accent] }}
                        >
                          Open surface
                          <ArrowUpRight size={13} />
                        </Link>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
