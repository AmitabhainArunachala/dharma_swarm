export type VerificationEntry = {
  name: string;
  ok: boolean;
};

export type VerificationSummaryRows = {
  status: string;
  passing: string;
  failing: string;
  bundle: string;
};

export type VerificationFields = {
  checksText?: string;
  summaryText?: string;
  bundleText?: string;
  passingText?: string;
  failingText?: string;
};

function uniqueEntries(entries: VerificationEntry[]): VerificationEntry[] {
  const seen = new Set<string>();
  return entries.filter((entry) => {
    const key = `${entry.name}:${entry.ok ? "ok" : "fail"}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function parseVerificationBundle(checksText: string, summaryText = ""): VerificationEntry[] {
  const fromChecks = checksText
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && part.toLowerCase() !== "none")
    .map((part) => {
      const match = part.match(/^(.*?)\s+(ok|fail)$/i);
      if (!match) {
        return null;
      }
      return {
        name: match[1]!.trim(),
        ok: match[2]!.toLowerCase() === "ok",
      };
    })
    .filter((entry): entry is VerificationEntry => entry !== null && entry.name.length > 0);

  if (fromChecks.length > 0) {
    return uniqueEntries(fromChecks);
  }

  const fromSummary = summaryText
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && part.toLowerCase() !== "none")
    .map((part) => {
      const match = part.match(/^(.*?)=(ok|fail)$/i);
      if (!match) {
        return null;
      }
      return {
        name: match[1]!.trim(),
        ok: match[2]!.toLowerCase() === "ok",
      };
    })
    .filter((entry): entry is VerificationEntry => entry !== null && entry.name.length > 0);

  return uniqueEntries(fromSummary);
}

function parseVerificationNames(value = ""): string[] {
  return value
    .split(/[;,]/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && part.toLowerCase() !== "none" && !isGenericVerificationLabel(part));
}

export function resolveVerificationEntries(fields: VerificationFields): VerificationEntry[] {
  const fromChecks = parseVerificationBundle(fields.checksText ?? "", "");
  if (fromChecks.length > 0) {
    return fromChecks;
  }

  const fromBundle = parseVerificationBundle("none", fields.bundleText ?? "");
  if (fromBundle.length > 0) {
    return fromBundle;
  }

  const fromSummary = parseVerificationBundle("none", fields.summaryText ?? "");
  if (fromSummary.length > 0) {
    return fromSummary;
  }

  const fromDetailRows = uniqueEntries([
    ...parseVerificationNames(fields.passingText).map((name) => ({name, ok: true})),
    ...parseVerificationNames(fields.failingText).map((name) => ({name, ok: false})),
  ]);
  return fromDetailRows;
}

export function verificationBundleLabel(bundle: VerificationEntry[]): string {
  if (bundle.length === 0) {
    return "none";
  }
  return bundle.map((entry) => `${entry.name}=${entry.ok ? "ok" : "fail"}`).join(" | ");
}

export function isGenericVerificationLabel(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return (
    normalized.length === 0 ||
    normalized === "ok" ||
    normalized === "pass" ||
    normalized === "passing" ||
    normalized === "fail" ||
    normalized === "failing" ||
    normalized === "failed" ||
    normalized === "error" ||
    normalized === "none" ||
    normalized === "unknown" ||
    normalized === "n/a"
  );
}

export function buildVerificationSummaryRows(bundle: VerificationEntry[]): VerificationSummaryRows {
  if (bundle.length === 0) {
    return {
      status: "unknown",
      passing: "unknown",
      failing: "unknown",
      bundle: "none",
    };
  }

  const passing = bundle.filter((entry) => entry.ok).map((entry) => entry.name);
  const failing = bundle.filter((entry) => !entry.ok).map((entry) => entry.name);

  return {
    status:
      failing.length > 0
        ? `${failing.length} failing, ${passing.length}/${bundle.length} passing`
        : `all ${bundle.length} checks passing`,
    passing: passing.length > 0 ? passing.join(", ") : "none",
    failing: failing.length > 0 ? failing.join(", ") : "none",
    bundle: verificationBundleLabel(bundle),
  };
}
