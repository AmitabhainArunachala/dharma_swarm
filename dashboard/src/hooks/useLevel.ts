"use client";

/**
 * DHARMA COMMAND -- Progressive disclosure level store (1-5).
 *
 * Level meanings:
 *   1 = COMMAND   -- Overview, Agents, Tasks
 *   2 = OBSERVE   -- Health, Anomalies
 *   3 = INTEL     -- Evolution, Gates, Fitness
 *   4 = DEEP      -- Ontology, Lineage, Stigmergy
 *   5 = COMPOSE   -- Workflows, Blocks, Full autonomy
 *
 * Persists to localStorage under key "dharma-level".
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface LevelState {
  /** Current disclosure level (1-5). */
  level: number;
  /** Set the level (clamped to 1-5). */
  setLevel: (n: number) => void;
  /** Increment (capped at 5). */
  levelUp: () => void;
  /** Decrement (floored at 1). */
  levelDown: () => void;
}

function clamp(n: number): number {
  return Math.max(1, Math.min(5, Math.round(n)));
}

export const useLevel = create<LevelState>()(
  persist(
    (set) => ({
      level: 3,
      setLevel: (n: number) => set({ level: clamp(n) }),
      levelUp: () => set((s) => ({ level: clamp(s.level + 1) })),
      levelDown: () => set((s) => ({ level: clamp(s.level - 1) })),
    }),
    {
      name: "dharma-level",
    },
  ),
);
