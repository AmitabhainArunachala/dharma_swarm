/**
 * DHARMA COMMAND -- Color constants and theme helpers.
 * All values mirror the CSS custom properties in globals.css.
 */

// ---------------------------------------------------------------------------
// Base palette
// ---------------------------------------------------------------------------

export const colors = {
  sumi: {
    950: "#0D0E13",
    900: "#181A20",
    850: "#1E2028",
    800: "#252730",
    700: "#383A44",
    600: "#4E5060",
  },
  aozora: "#4FD1D9",
  botan: "#D47DB5",
  kinpaku: "#D4A855",
  rokusho: "#8FA89B",
  bengara: "#C19392",
  fuji: "#A89DB9",
  torinoko: "#D8DCE6",
  kitsurubami: "#C5B198",
} as const;

// ---------------------------------------------------------------------------
// Status mapping
// ---------------------------------------------------------------------------

export type StatusKey = "ok" | "warn" | "error" | "info" | "idle" | "running" | "done" | "failed";

const statusColorMap: Record<StatusKey, string> = {
  ok: colors.rokusho,
  warn: colors.kinpaku,
  error: colors.bengara,
  info: colors.aozora,
  idle: colors.sumi[600],
  running: colors.aozora,
  done: colors.rokusho,
  failed: colors.bengara,
};

export function statusColor(status: string): string {
  const key = status.toLowerCase() as StatusKey;
  return statusColorMap[key] ?? colors.sumi[600];
}

/** Tailwind-compatible class suffix for a given status. */
export function statusTwColor(status: string): string {
  const map: Record<string, string> = {
    ok: "rokusho",
    warn: "kinpaku",
    error: "bengara",
    info: "aozora",
    idle: "sumi-600",
    running: "aozora",
    done: "rokusho",
    failed: "bengara",
  };
  return map[status.toLowerCase()] ?? "sumi-600";
}

// ---------------------------------------------------------------------------
// Glow shadow generators
// ---------------------------------------------------------------------------

/**
 * Returns a CSS `text-shadow` string that produces a neon glow effect.
 * @param hex -- hex color string (e.g. "#4FD1D9")
 * @param intensity -- multiplier 0..1 (default 0.6)
 */
export function glowText(hex: string, intensity = 0.6): string {
  const inner = Math.round(intensity * 100);
  const outer = Math.round(intensity * 50);
  return `0 0 6px color-mix(in srgb, ${hex} ${inner}%, transparent), 0 0 20px color-mix(in srgb, ${hex} ${outer}%, transparent)`;
}

/**
 * Returns a CSS `box-shadow` string for glowing panels / cards.
 * @param hex -- hex color string
 * @param intensity -- multiplier 0..1 (default 0.4)
 */
export function glowBox(hex: string, intensity = 0.4): string {
  const inner = Math.round(intensity * 100);
  const outer = Math.round(intensity * 40);
  return `0 0 8px color-mix(in srgb, ${hex} ${inner}%, transparent), 0 0 24px color-mix(in srgb, ${hex} ${outer}%, transparent)`;
}

/**
 * Returns a CSS `box-shadow` for a subtle border glow (used on cards).
 */
export function glowBorder(hex: string, intensity = 0.25): string {
  const alpha = Math.round(intensity * 100);
  return `inset 0 0 0 1px color-mix(in srgb, ${hex} ${alpha}%, transparent)`;
}

// ---------------------------------------------------------------------------
// Accent color cycle (for sequential items like agent cards)
// ---------------------------------------------------------------------------

export const accentCycle = [
  colors.aozora,
  colors.botan,
  colors.kinpaku,
  colors.rokusho,
  colors.bengara,
  colors.fuji,
] as const;

export function accentAt(index: number): string {
  return accentCycle[index % accentCycle.length];
}

/** Tailwind class name for the accent at a given index. */
export function accentTwAt(index: number): string {
  const names = ["aozora", "botan", "kinpaku", "rokusho", "bengara", "fuji"] as const;
  return names[index % names.length];
}
