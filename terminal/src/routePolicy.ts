import type {RoutePolicyState, RouteTarget, RouteState} from "./types";

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
    : [];
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value.trim() || fallback : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter((item) => item.length > 0) : [];
}

export function routeIdFor(provider: string, model: string, explicitRouteId?: string): string {
  const normalized = explicitRouteId?.trim();
  if (normalized) {
    return normalized;
  }
  return [provider.trim(), model.trim()].filter(Boolean).join(":") || "unknown";
}

function normalizeRouteState(value: unknown, selectable: boolean): RouteState {
  if (typeof value === "boolean") {
    return value ? "degraded" : (selectable ? "ready" : "unavailable");
  }
  const normalized = asString(value).toLowerCase();
  if (normalized === "ready" || normalized === "degraded" || normalized === "slow" || normalized === "unavailable" || normalized === "invalid") {
    return normalized;
  }
  return selectable ? "ready" : "unavailable";
}

function normalizeRouteTarget(target: Record<string, unknown>): RouteTarget | null {
  const provider = asString(target.provider);
  const model = asString(target.model);
  const alias = asString(target.alias);
  const label = asString(target.label);
  if (!provider || !model || !alias) {
    return null;
  }
  const selectable = asBoolean(target.picker_visible, asBoolean(target.available, true));
  return {
    alias,
    label: label || alias,
    provider,
    model,
    routeId: routeIdFor(provider, model, asString(target.route_id)),
    routeState: normalizeRouteState(target.route_state, selectable),
    availabilityReason: asString(target.availability_reason) || undefined,
    selectable,
  };
}

export function defaultRoutePolicy(): RoutePolicyState {
  return {
    routeId: "codex:gpt-5.4",
    provider: "codex",
    model: "gpt-5.4",
    strategy: "responsive",
    routeState: "ready",
    selectable: true,
    fallbackChain: [],
    lastConfirmedRouteId: "codex:gpt-5.4",
    activeLabel: "Codex 5.4",
    targets: [],
  };
}

export function routePolicyWithConfig(
  current: RoutePolicyState,
  provider: string,
  model: string,
  strategy: string,
): RoutePolicyState {
  const nextRouteId = routeIdFor(provider, model, current.routeId);
  const matchingTarget = current.targets.find((target) => target.provider === provider && target.model === model);
  return {
    ...current,
    routeId: matchingTarget?.routeId ?? nextRouteId,
    provider,
    model,
    strategy,
    routeState: matchingTarget?.routeState ?? current.routeState,
    selectable: matchingTarget?.selectable ?? current.selectable,
    availabilityReason: matchingTarget?.availabilityReason ?? current.availabilityReason,
    lastConfirmedRouteId: nextRouteId,
    activeLabel: matchingTarget?.label ?? current.activeLabel,
  };
}

export function routePolicyFromValue(value: unknown, current: RoutePolicyState = defaultRoutePolicy()): RoutePolicyState {
  const record = asRecord(value);
  const payload =
    asString(record.domain) === "routing_decision" && Object.keys(asRecord(record.decision)).length > 0
      ? record
      : asRecord(record.payload).domain === "routing_decision"
        ? asRecord(record.payload)
        : record;

  const decisionRecord = asRecord(payload.decision);
  const metadata = asRecord(decisionRecord.metadata);
  const payloadPolicy = asRecord(payload.policy);
  const policy = Object.keys(decisionRecord).length > 0 ? decisionRecord : Object.keys(payloadPolicy).length > 0 ? payloadPolicy : payload;

  const provider = asString(policy.provider_id ?? policy.selected_provider, current.provider);
  const model = asString(policy.model_id ?? policy.selected_model, current.model);
  const strategy = asString(policy.strategy, current.strategy);
  const targets = asRecordList(payload.targets ?? policy.targets)
    .map(normalizeRouteTarget)
    .filter((target): target is RouteTarget => Boolean(target));
  const matchingTarget = targets.find((target) => target.provider === provider && target.model === model);
  const selectable = matchingTarget?.selectable ?? asBoolean(policy.selectable, true);
  const routeId = routeIdFor(provider, model, asString(policy.route_id ?? policy.selected_route));
  const fallbackTargets = asRecordList(payload.fallback_targets ?? policy.fallback_chain);
  const fallbackChain = fallbackTargets
    .map((entry) => routeIdFor(asString(entry.provider), asString(entry.model), asString(entry.route_id ?? entry.alias)))
    .filter((entry) => entry !== "unknown");

  return {
    routeId,
    provider,
    model,
    strategy,
    routeState: matchingTarget?.routeState ?? normalizeRouteState(policy.route_state ?? policy.degraded, selectable),
    selectable,
    availabilityReason: matchingTarget?.availabilityReason ?? (asString(policy.availability_reason) || undefined),
    defaultRouteId: asString(metadata.default_route ?? policy.default_route) || undefined,
    fallbackChain,
    lastConfirmedRouteId: routeId || current.lastConfirmedRouteId,
    activeLabel: asString(metadata.active_label ?? policy.active_label) || matchingTarget?.label || undefined,
    targets,
  };
}

export function routeLabel(policy: RoutePolicyState): string {
  return `${policy.provider}:${policy.model.replace(/:cloud$/, "")}`;
}

export function routeSummary(policy: RoutePolicyState): string {
  const parts = [policy.routeState, routeLabel(policy)];
  if (policy.availabilityReason) {
    parts.push(policy.availabilityReason);
  }
  return parts.join(" | ");
}

export function selectableRouteTargets(policy: RoutePolicyState): RouteTarget[] {
  return policy.targets.filter((target) => target.selectable);
}

export function nonSelectableRouteTargets(policy: RoutePolicyState): RouteTarget[] {
  return policy.targets.filter((target) => !target.selectable);
}
