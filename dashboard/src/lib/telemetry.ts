export interface TelemetryOverview {
  agent_count: number;
  active_agents: number;
  team_count: number;
  reward_event_count: number;
  workflow_score_count: number;
  routing_decision_count: number;
  policy_decision_count: number;
  intervention_count: number;
  economic_event_count: number;
  external_outcome_count: number;
  total_cost_usd: number;
  total_revenue_usd: number;
}

export interface RoutingSummary {
  total_decisions: number;
  human_required_count: number;
  path_counts: Record<string, number>;
  provider_counts: Record<string, number>;
}

export interface EconomicSummary {
  event_count: number;
  total_cost_usd: number;
  total_revenue_usd: number;
  net_usd: number;
  currency_breakdown: Record<string, number>;
}

export interface TelemetryAgentIdentity {
  agent_id: string;
  codename: string;
  serial: string;
  avatar_id: string;
  department: string;
  squad_id: string;
  specialization: string;
  level: number;
  xp: number;
  status: string;
  last_active: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TelemetryRouteDecision {
  decision_id: string;
  action_name: string;
  route_path: string;
  selected_provider: string;
  selected_model_hint: string;
  confidence: number;
  requires_human: boolean;
  session_id: string;
  task_id: string;
  run_id: string;
  reasons: string[];
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TelemetryPolicyDecision {
  decision_id: string;
  policy_name: string;
  decision: string;
  status_before: string;
  status_after: string;
  confidence: number;
  reason: string;
  session_id: string;
  task_id: string;
  run_id: string;
  evidence: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TelemetryIntervention {
  intervention_id: string;
  intervention_type: string;
  outcome_status: string;
  impact_score: number;
  summary: string;
  operator_id: string;
  session_id: string;
  task_id: string;
  run_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TelemetryEconomicEvent {
  event_id: string;
  event_kind: string;
  amount: number;
  currency: string;
  counterparty: string;
  summary: string;
  session_id: string;
  task_id: string;
  run_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TelemetryOutcome {
  outcome_id: string;
  outcome_kind: string;
  value: number;
  unit: string;
  confidence: number;
  status: string;
  subject_id: string;
  summary: string;
  session_id: string;
  task_id: string;
  run_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
