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

function compactSegments(value: string): string[] {
  return value
    .split("|")
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0);
}

export function parseRuntimeFreshness(value: string): {
  loopState?: string;
  updated?: string;
  verificationBundle?: string;
} {
  if (value === "n/a" || value === "none" || value.trim().length === 0) {
    return {};
  }

  const updatedMarker = " | updated ";
  const verifyMarker = " | verify ";
  const updatedIndex = value.indexOf(updatedMarker);
  const verifyIndex = value.indexOf(verifyMarker);
  if (updatedIndex === -1 || verifyIndex === -1 || verifyIndex <= updatedIndex) {
    const segments = compactSegments(value);
    if (segments.length === 0) {
      return {};
    }
    return {
      ...(segments[0] ? {loopState: segments[0]} : {}),
    };
  }

  const loopState = value.slice(0, updatedIndex).trim();
  const updated = value.slice(updatedIndex + updatedMarker.length, verifyIndex).trim();
  const verificationBundle = value.slice(verifyIndex + verifyMarker.length).trim();
  if (!loopState && !updated && !verificationBundle) {
    return {};
  }

  return {
    ...(loopState ? {loopState} : {}),
    ...(updated ? {updated} : {}),
    ...(verificationBundle ? {verificationBundle} : {}),
  };
}

export function parseControlPulsePreview(value: string): {
  freshness?: string;
  lastResult?: string;
  runtimeFreshness?: string;
} {
  if (value === "n/a" || value === "none" || value.trim().length === 0) {
    return {};
  }

  const segments = compactSegments(value);
  if (segments.length < 2) {
    return {};
  }

  const hasFreshnessPrefix = /^(fresh|stale|unknown)$/i.test(segments[0] ?? "");
  const freshness = hasFreshnessPrefix ? segments[0] : undefined;
  const lastResult = hasFreshnessPrefix ? segments[1] : segments[0];
  const runtimeFreshness = hasFreshnessPrefix ? segments.slice(2).join(" | ") : segments.slice(1).join(" | ");
  return {
    ...(freshness ? {freshness} : {}),
    ...(lastResult ? {lastResult} : {}),
    ...(runtimeFreshness ? {runtimeFreshness} : {}),
  };
}
