const FRESH_WINDOW_MS = 6 * 60 * 60 * 1000;

export function freshnessToken(updated: string, now: Date = new Date()): string {
  const normalized = updated.trim().toLowerCase();
  if (normalized.length === 0 || normalized === "n/a" || normalized === "unknown" || normalized === "none") {
    return "unknown";
  }

  const updatedAt = Date.parse(updated);
  if (Number.isNaN(updatedAt)) {
    return "unknown";
  }

  return now.getTime() - updatedAt <= FRESH_WINDOW_MS ? "fresh" : "stale";
}
