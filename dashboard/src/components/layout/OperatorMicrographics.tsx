"use client";

import { useEffect, useId, useMemo, useState, type CSSProperties } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { usePathname } from "next/navigation";
import { colors } from "@/lib/theme";

type LensId = "routing" | "fleet" | "contracts";

interface LensDef {
  id: LensId;
  label: string;
  accent: string;
  summary: string;
}

const LENSES: LensDef[] = [
  {
    id: "routing",
    label: "Routing Flux",
    accent: colors.aozora,
    summary: "Live route pressure, adaptive drift, and handoff bias.",
  },
  {
    id: "fleet",
    label: "Fleet Pulse",
    accent: colors.botan,
    summary: "Operator-visible rhythm across agents, tasks, and active lanes.",
  },
  {
    id: "contracts",
    label: "Contract Tension",
    accent: colors.kinpaku,
    summary: "Surface contract drift before it turns into silent state rot.",
  },
];

function routeLens(pathname: string): LensId {
  if (pathname.includes("/agents") || pathname.includes("/tasks")) return "fleet";
  if (pathname.includes("/doctor") || pathname.includes("/modules")) return "contracts";
  return "routing";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function sparkle(value: number, accent: string): CSSProperties {
  const alpha = clamp(10 + value * 70, 10, 78);
  return {
    background: `color-mix(in srgb, ${accent} ${alpha}%, ${colors.sumi[900]})`,
    boxShadow: `0 0 14px color-mix(in srgb, ${accent} ${Math.round(alpha * 0.55)}%, transparent)`,
  };
}

export function OperatorMicrographics() {
  const pathname = usePathname();
  const prefersReducedMotion = useReducedMotion();
  const fluxGradientId = useId();
  const coreGradientId = useId();
  const defaultLens = useMemo(() => routeLens(pathname), [pathname]);
  const [activeLens, setActiveLens] = useState<LensId>(defaultLens);
  const [tick, setTick] = useState(0);
  const [focusIndex, setFocusIndex] = useState(8);
  const [focusCell, setFocusCell] = useState(19);
  const [orbitalBias, setOrbitalBias] = useState(0.36);

  useEffect(() => {
    setActiveLens(defaultLens);
  }, [defaultLens]);

  useEffect(() => {
    if (prefersReducedMotion) return;
    const handle = window.setInterval(() => {
      setTick((value) => value + 1);
    }, 1400);
    return () => window.clearInterval(handle);
  }, [prefersReducedMotion]);

  const lens = LENSES.find((item) => item.id === activeLens) ?? LENSES[0];

  const sparkline = useMemo(() => {
    const phaseShift = activeLens === "routing" ? 0.2 : activeLens === "fleet" ? 1.1 : 2.4;
    return Array.from({ length: 28 }, (_, index) => {
      const base =
        0.52
        + Math.sin(index * 0.38 + tick * 0.22 + phaseShift) * 0.18
        + Math.cos(index * 0.16 + tick * 0.11) * 0.11;
      return clamp(base, 0.1, 0.92);
    });
  }, [activeLens, tick]);

  const sparklinePath = useMemo(() => {
    return sparkline
      .map((value, index) => {
        const x = 8 + index * 14.2;
        const y = 92 - value * 60;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  }, [sparkline]);

  const lattice = useMemo(() => {
    const lensShift = activeLens === "routing" ? 0 : activeLens === "fleet" ? 0.55 : 1.05;
    return Array.from({ length: 48 }, (_, index) => {
      const row = Math.floor(index / 8);
      const col = index % 8;
      const value =
        0.44
        + Math.sin(col * 0.9 + tick * 0.18 + lensShift) * 0.24
        + Math.cos(row * 0.8 + tick * 0.12 + lensShift) * 0.16;
      return clamp(value, 0.04, 0.98);
    });
  }, [activeLens, tick]);

  const orbitals = useMemo(() => {
    return Array.from({ length: 5 }, (_, index) => {
      const speed = 0.12 + index * 0.035;
      const radius = 30 + index * 18;
      const angle = tick * speed + orbitalBias * (index + 1) * 3.8;
      const x = 104 + Math.cos(angle) * radius;
      const y = 104 + Math.sin(angle) * radius * 0.62;
      const intensity = 0.4 + ((index + tick) % 4) * 0.12;
      return { radius, x, y, intensity };
    });
  }, [orbitalBias, tick]);

  const focusValue = sparkline[focusIndex] ?? sparkline[0];
  const focusLattice = lattice[focusCell] ?? lattice[0];

  return (
    <section className="glass-panel relative overflow-hidden px-5 py-4">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            `radial-gradient(circle at 12% 20%, color-mix(in srgb, ${lens.accent} 18%, transparent), transparent 28%), ` +
            `radial-gradient(circle at 88% 15%, color-mix(in srgb, ${colors.fuji} 12%, transparent), transparent 22%), ` +
            `linear-gradient(135deg, rgba(255,255,255,0.015), transparent 65%)`,
        }}
      />

      <div className="relative flex flex-col gap-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span
                className="rounded-full px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em]"
                style={{
                  color: lens.accent,
                  background: `color-mix(in srgb, ${lens.accent} 12%, transparent)`,
                }}
              >
                Operator Micrographics
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-sumi-600">
                {pathname.replace("/dashboard", "dashboard") || "dashboard"}
              </span>
            </div>
            <h2
              className="font-heading text-lg font-semibold tracking-tight"
              style={{ color: lens.accent }}
            >
              Thin diagnostics, dense texture, no fake dashboards
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-sumi-600">
              {lens.summary}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {LENSES.map((item) => {
              const active = item.id === activeLens;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveLens(item.id)}
                  className="rounded-full border px-3 py-1.5 font-mono text-[11px] tracking-[0.12em] transition-all"
                  style={{
                    color: active ? item.accent : colors.sumi[600],
                    borderColor: active
                      ? `color-mix(in srgb, ${item.accent} 38%, transparent)`
                      : `${colors.sumi[700]}66`,
                    background: active
                      ? `color-mix(in srgb, ${item.accent} 12%, transparent)`
                      : `${colors.sumi[900]}99`,
                    boxShadow: active
                      ? `0 0 18px color-mix(in srgb, ${item.accent} 18%, transparent)`
                      : "none",
                  }}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr_0.92fr]">
          <motion.div
            layout
            className="glass-panel-subtle overflow-hidden p-4"
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 0.999);
              setFocusIndex(Math.floor(ratio * sparkline.length));
            }}
          >
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-600">
                  Flux Ribbon
                </p>
                <p className="font-heading text-sm text-torinoko">Adaptive route pressure</p>
              </div>
              <span
                className="rounded-full px-2 py-1 font-mono text-[10px]"
                style={{
                  color: lens.accent,
                  background: `color-mix(in srgb, ${lens.accent} 10%, transparent)`,
                }}
              >
                {Math.round(focusValue * 100)}%
              </span>
            </div>

            <svg viewBox="0 0 400 120" className="h-32 w-full">
              <defs>
                <linearGradient id={fluxGradientId} x1="0" x2="1">
                  <stop offset="0%" stopColor={lens.accent} stopOpacity="0.15" />
                  <stop offset="100%" stopColor={colors.fuji} stopOpacity="0.28" />
                </linearGradient>
              </defs>
              {sparkline.map((value, index) => {
                const x = 8 + index * 14.2;
                const h = value * 62;
                return (
                  <rect
                    key={index}
                    x={x - 3}
                    y={102 - h}
                    width="6"
                    height={h}
                    rx="3"
                    fill={index === focusIndex ? lens.accent : `${colors.sumi[700]}77`}
                    opacity={index === focusIndex ? 0.95 : 0.34}
                  />
                );
              })}
              <path
                d={`${sparklinePath} L 392 104 L 8 104 Z`}
                fill={`url(#${fluxGradientId})`}
                opacity="0.28"
              />
              <path
                d={sparklinePath}
                fill="none"
                stroke={lens.accent}
                strokeWidth="2.4"
                strokeLinecap="round"
              />
              <circle
                cx={8 + focusIndex * 14.2}
                cy={92 - focusValue * 60}
                r="5.5"
                fill={lens.accent}
                style={{ filter: `drop-shadow(0 0 8px ${lens.accent})` }}
              />
            </svg>

            <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-sumi-600">
              <MiniReadout label="Bias" value={`${(focusValue * 1.34).toFixed(2)}x`} accent={lens.accent} />
              <MiniReadout label="Drift" value={`${(sparkline[focusIndex + 1] ?? focusValue - 0.1).toFixed(2)}`} accent={colors.fuji} />
              <MiniReadout label="Pulse" value={`${42 + focusIndex}`} accent={colors.rokusho} />
            </div>
          </motion.div>

          <motion.div layout className="glass-panel-subtle p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-600">
                  Lattice Mesh
                </p>
                <p className="font-heading text-sm text-torinoko">Hover any cell to isolate tension</p>
              </div>
              <span className="font-mono text-[11px]" style={{ color: lens.accent }}>
                C{focusCell.toString().padStart(2, "0")}
              </span>
            </div>

            <div className="grid grid-cols-8 gap-1.5">
              {lattice.map((value, index) => (
                <button
                  key={index}
                  type="button"
                  aria-label={`mesh cell ${index}`}
                  onMouseEnter={() => setFocusCell(index)}
                  onFocus={() => setFocusCell(index)}
                  className="aspect-square rounded-[7px] border border-transparent transition-transform duration-150 hover:scale-[1.08]"
                  style={{
                    ...sparkle(value, index === focusCell ? lens.accent : colors.fuji),
                    opacity: index === focusCell ? 1 : 0.52 + value * 0.36,
                  }}
                />
              ))}
            </div>

            <div className="mt-4 rounded-2xl border border-sumi-700/40 bg-sumi-900/70 p-3">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-mono uppercase tracking-[0.14em] text-sumi-600">Mesh Readout</span>
                <span style={{ color: lens.accent }}>{Math.round(focusLattice * 100)} / 100</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-sumi-800">
                <motion.div
                  className="h-full rounded-full"
                  animate={{ width: `${Math.round(focusLattice * 100)}%` }}
                  transition={
                    prefersReducedMotion
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 120, damping: 20 }
                  }
                  style={{
                    background: `linear-gradient(90deg, ${lens.accent}, ${colors.fuji})`,
                  }}
                />
              </div>
              <p className="mt-3 text-[11px] leading-5 text-sumi-600">
                {activeLens === "contracts"
                  ? "Contract seams are shimmering at the edges. This is where route/API/schema truth tends to drift first."
                  : activeLens === "fleet"
                    ? "The mesh is reading operator-visible pressure bands across active cells, handoffs, and stalled queues."
                    : "The routing field is showing uneven lift across lanes; hover reveals local pressure rather than page-level averages."}
              </p>
            </div>
          </motion.div>

          <motion.div
            layout
            className="glass-panel-subtle p-4"
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              setOrbitalBias(clamp((event.clientX - rect.left) / rect.width, 0.1, 0.9));
            }}
          >
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-600">
                  Orbital Sweep
                </p>
                <p className="font-heading text-sm text-torinoko">Pointer-reactive diagnostics halo</p>
              </div>
              <span className="font-mono text-[11px]" style={{ color: lens.accent }}>
                {(orbitalBias * 10).toFixed(1)}
              </span>
            </div>

            <div className="flex items-center justify-center">
              <svg viewBox="0 0 208 208" className="h-52 w-52 max-w-full">
                <defs>
                  <radialGradient id={coreGradientId}>
                    <stop offset="0%" stopColor={lens.accent} stopOpacity="0.42" />
                    <stop offset="100%" stopColor={lens.accent} stopOpacity="0" />
                  </radialGradient>
                </defs>

                {[34, 52, 70, 88].map((radius, index) => (
                  <circle
                    key={radius}
                    cx="104"
                    cy="104"
                    r={radius}
                    fill="none"
                    stroke={index % 2 === 0 ? `${colors.sumi[700]}bb` : `${colors.sumi[600]}88`}
                    strokeDasharray={index % 2 === 0 ? "3 8" : "12 9"}
                    strokeWidth="1.2"
                  />
                ))}

                <circle cx="104" cy="104" r="20" fill={`url(#${coreGradientId})`} />
                <circle cx="104" cy="104" r="8" fill={lens.accent} opacity="0.9" />

                {orbitals.map((orbital, index) => (
                  <g key={index}>
                    <circle
                      cx="104"
                      cy="104"
                      r={orbital.radius}
                      fill="none"
                      stroke={`color-mix(in srgb, ${index % 2 === 0 ? lens.accent : colors.fuji} 18%, transparent)`}
                    />
                    <circle
                      cx={orbital.x}
                      cy={orbital.y}
                      r={4 + index * 0.8}
                      fill={index % 2 === 0 ? lens.accent : colors.fuji}
                      opacity={orbital.intensity}
                    />
                  </g>
                ))}
              </svg>
            </div>

            <div className="mt-2 space-y-2">
              {[
                ["Sweep", `${Math.round(orbitalBias * 100)}%`, lens.accent],
                ["Lock", `${76 + tick % 12} ms`, colors.kinpaku],
                ["Focus", activeLens.toUpperCase(), colors.fuji],
              ].map(([label, value, accent]) => (
                <div
                  key={label}
                  className="flex items-center justify-between rounded-xl border border-sumi-700/30 bg-sumi-900/60 px-3 py-2 text-[11px]"
                >
                  <span className="font-mono uppercase tracking-[0.14em] text-sumi-600">{label}</span>
                  <span style={{ color: accent }}>{value}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function MiniReadout({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-sumi-700/35 bg-sumi-900/70 px-3 py-2">
      <p className="font-mono uppercase tracking-[0.12em] text-sumi-600">{label}</p>
      <p className="mt-1 font-heading text-sm" style={{ color: accent }}>
        {value}
      </p>
    </div>
  );
}
