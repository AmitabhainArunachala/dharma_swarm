"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  EconomicSummary,
  RoutingSummary,
  TelemetryAgentIdentity,
  TelemetryEconomicEvent,
  TelemetryIntervention,
  TelemetryOutcome,
  TelemetryOverview,
  TelemetryPolicyDecision,
  TelemetryRouteDecision,
} from "@/lib/telemetry";

export function useTelemetry() {
  const overviewQuery = useQuery<TelemetryOverview>({
    queryKey: ["telemetry", "overview"],
    queryFn: () => apiFetch<TelemetryOverview>("/api/telemetry/overview"),
    refetchInterval: 10_000,
  });

  const routingQuery = useQuery<RoutingSummary>({
    queryKey: ["telemetry", "routing"],
    queryFn: () => apiFetch<RoutingSummary>("/api/telemetry/routing"),
    refetchInterval: 10_000,
  });

  const economicsQuery = useQuery<EconomicSummary>({
    queryKey: ["telemetry", "economics"],
    queryFn: () => apiFetch<EconomicSummary>("/api/telemetry/economics"),
    refetchInterval: 10_000,
  });

  const agentsQuery = useQuery<TelemetryAgentIdentity[]>({
    queryKey: ["telemetry", "agents"],
    queryFn: () => apiFetch<TelemetryAgentIdentity[]>("/api/telemetry/agents?limit=24"),
    refetchInterval: 15_000,
  });

  const routesQuery = useQuery<TelemetryRouteDecision[]>({
    queryKey: ["telemetry", "routes"],
    queryFn: () => apiFetch<TelemetryRouteDecision[]>("/api/telemetry/routes?limit=20"),
    refetchInterval: 15_000,
  });

  const policiesQuery = useQuery<TelemetryPolicyDecision[]>({
    queryKey: ["telemetry", "policies"],
    queryFn: () => apiFetch<TelemetryPolicyDecision[]>("/api/telemetry/policies?limit=20"),
    refetchInterval: 15_000,
  });

  const interventionsQuery = useQuery<TelemetryIntervention[]>({
    queryKey: ["telemetry", "interventions"],
    queryFn: () => apiFetch<TelemetryIntervention[]>("/api/telemetry/interventions?limit=20"),
    refetchInterval: 15_000,
  });

  const economicEventsQuery = useQuery<TelemetryEconomicEvent[]>({
    queryKey: ["telemetry", "economic-events"],
    queryFn: () => apiFetch<TelemetryEconomicEvent[]>("/api/telemetry/events/economic?limit=20"),
    refetchInterval: 15_000,
  });

  const outcomesQuery = useQuery<TelemetryOutcome[]>({
    queryKey: ["telemetry", "outcomes"],
    queryFn: () => apiFetch<TelemetryOutcome[]>("/api/telemetry/outcomes?limit=20"),
    refetchInterval: 15_000,
  });

  const isLoading =
    overviewQuery.isLoading ||
    routingQuery.isLoading ||
    economicsQuery.isLoading;

  return {
    overview: overviewQuery.data ?? null,
    routing: routingQuery.data ?? null,
    economics: economicsQuery.data ?? null,
    agents: agentsQuery.data ?? [],
    routes: routesQuery.data ?? [],
    policies: policiesQuery.data ?? [],
    interventions: interventionsQuery.data ?? [],
    economicEvents: economicEventsQuery.data ?? [],
    outcomes: outcomesQuery.data ?? [],
    isLoading,
    error:
      overviewQuery.error ||
      routingQuery.error ||
      economicsQuery.error ||
      agentsQuery.error ||
      routesQuery.error ||
      policiesQuery.error ||
      interventionsQuery.error ||
      economicEventsQuery.error ||
      outcomesQuery.error ||
      null,
  };
}
