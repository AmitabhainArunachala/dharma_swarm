"use client";

/**
 * DHARMA COMMAND -- 20 CSS-animated vertical drift particles.
 * No canvas -- pure CSS. Pointer-events disabled.
 */

import { useMemo } from "react";

const PARTICLE_COUNT = 20;

interface ParticleStyle {
  left: string;
  animationDuration: string;
  animationDelay: string;
  height: string;
  opacity: number;
}

export function AmbientParticles() {
  const particles = useMemo<ParticleStyle[]>(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => {
      // Deterministic pseudo-random distribution so SSR matches client.
      const seed = ((i * 7 + 13) % PARTICLE_COUNT) / PARTICLE_COUNT;
      const seed2 = ((i * 11 + 3) % PARTICLE_COUNT) / PARTICLE_COUNT;

      return {
        left: `${(seed * 100).toFixed(1)}%`,
        animationDuration: `${14 + seed2 * 12}s`,
        animationDelay: `${-seed * 18}s`,
        height: `${30 + seed2 * 40}px`,
        opacity: 0.2 + seed2 * 0.3,
      };
    });
  }, []);

  return (
    <div
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
      aria-hidden="true"
    >
      {particles.map((style, i) => (
        <div
          key={i}
          className="particle"
          style={{
            ["--x" as string]: style.left,
            ["--duration" as string]: style.animationDuration,
            ["--delay" as string]: style.animationDelay,
            height: style.height,
            opacity: style.opacity,
            animationDelay: style.animationDelay,
            animationDuration: style.animationDuration,
            left: style.left,
          }}
        />
      ))}
    </div>
  );
}
