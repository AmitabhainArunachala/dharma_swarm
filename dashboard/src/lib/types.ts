/**
 * DHARMA COMMAND -- TypeScript types matching the FastAPI backend models.
 * These types match the `data` field unwrapped from ApiResponse.
 */

// ---------------------------------------------------------------------------
// Generic API wrapper (raw response before unwrap)
// ---------------------------------------------------------------------------

export interface ApiResponse<T> {
  status: string;
  data: T;
  error: string;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Chat status (GET /api/chat/status)
// ---------------------------------------------------------------------------

export interface ChatStatusOut {
  ready: boolean;
  model: string;
  provider: string;
  tools: number;
  max_tool_rounds: number;
  max_tokens: number;
  timeout_seconds: number;
  tool_result_max_chars: number;
  history_message_limit: number;
  temperature: number;
}

// ---------------------------------------------------------------------------
// Swarm overview (GET /api/overview)
// ---------------------------------------------------------------------------

export interface SwarmOverview {
  agent_count: number;
  task_count: number;
  tasks_pending: number;
  tasks_running: number;
  tasks_completed: number;
  tasks_failed: number;
  mean_fitness: number;
  uptime_seconds: number;
  health_status: string;
  stigmergy_density: number;
  evolution_entries: number;
}

// ---------------------------------------------------------------------------
// Agents (GET /api/agents)
// ---------------------------------------------------------------------------

export interface AgentOut {
  id: string;
  name: string;
  role: string;
  status: string;
  current_task: string | null;
  started_at: string | null;
  last_heartbeat: string | null;
  turns_used: number;
  tasks_completed: number;
  provider: string;
  model: string;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Tasks (GET /api/commands/tasks)
// ---------------------------------------------------------------------------

export interface TaskOut {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  result: string | null;
}

// ---------------------------------------------------------------------------
// Health (GET /api/health)
// ---------------------------------------------------------------------------

export interface AgentHealthOut {
  agent_name: string;
  total_actions: number;
  failures: number;
  success_rate: number;
  last_seen: string | null;
  status: string;
}

export interface AnomalyOut {
  id: string;
  detected_at: string;
  anomaly_type: string;
  severity: string;
  description: string;
  related_traces: string[];
}

export interface HealthOut {
  overall_status: string;
  agent_health: AgentHealthOut[];
  anomalies: AnomalyOut[];
  total_traces: number;
  traces_last_hour: number;
  failure_rate: number;
  mean_fitness: number | null;
}

// ---------------------------------------------------------------------------
// Evolution (GET /api/evolution/*)
// ---------------------------------------------------------------------------

export interface FitnessOut {
  correctness: number;
  dharmic_alignment: number;
  performance: number;
  utilization: number;
  economic_value: number;
  elegance: number;
  efficiency: number;
  safety: number;
  weighted: number;
}

export interface ArchiveEntryOut {
  id: string;
  timestamp: string;
  parent_id: string | null;
  component: string;
  change_type: string;
  description: string;
  fitness: FitnessOut;
  status: string;
  gates_passed: string[];
  gates_failed: string[];
  agent_id: string;
  model: string;
}

export interface FitnessTrendPoint {
  timestamp: string;
  fitness: number;
  correctness: number;
  elegance: number;
  component: string;
  id: string;
}

export interface DagNode {
  id: string;
  type: string;
  data: {
    label: string;
    fitness: number;
    status: string;
    change_type: string;
    timestamp: string;
  };
  position: { x: number; y: number };
}

export interface DagEdge {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
  label?: string;
}

export interface DagData {
  nodes: DagNode[];
  edges: DagEdge[];
}

// ---------------------------------------------------------------------------
// Traces (GET /api/commands/traces)
// ---------------------------------------------------------------------------

export interface TraceOut {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
  state: string;
  parent_id: string | null;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Ontology (GET /api/ontology/*)
// ---------------------------------------------------------------------------

export interface OntologyTypeOut {
  name: string;
  description: string;
  telos_alignment: number;
  shakti: string;
  property_count: number;
  link_count: number;
  action_count: number;
  icon: string;
}

export interface PropertyOut {
  name: string;
  property_type: string;
  required: boolean;
  description: string;
  searchable: boolean;
}

export interface LinkDefOut {
  name: string;
  source_type: string;
  target_type: string;
  cardinality: string;
  description: string;
}

export interface ActionDefOut {
  name: string;
  description: string;
  requires_approval: boolean;
  telos_gates: string[];
  is_deterministic: boolean;
}

export interface OntologyDetailOut {
  name: string;
  description: string;
  properties: PropertyOut[];
  links: LinkDefOut[];
  actions: ActionDefOut[];
  security_level: string;
  telos_alignment: number;
  shakti: string;
}

export interface OntologyGraphData {
  nodes: {
    id: string;
    type: string;
    data: {
      label: string;
      description: string;
      propertyCount: number;
      shakti: string;
      telos: number;
      icon: string;
    };
    position: { x: number; y: number };
  }[];
  edges: {
    id: string;
    source: string;
    target: string;
    label: string;
    data: { cardinality: string };
  }[];
}

// ---------------------------------------------------------------------------
// Lineage (GET /api/lineage/*)
// ---------------------------------------------------------------------------

export interface LineageEdgeOut {
  edge_id: string;
  task_id: string;
  input_artifacts: string[];
  output_artifacts: string[];
  agent: string;
  operation: string;
  timestamp: string;
}

export interface ProvenanceOut {
  artifact_id: string;
  chain: LineageEdgeOut[];
  root_sources: string[];
  depth: number;
}

export interface ImpactOut {
  root_artifact: string;
  affected_artifacts: string[];
  affected_tasks: string[];
  depth: number;
  total_descendants: number;
}

// ---------------------------------------------------------------------------
// Stigmergy (GET /api/stigmergy/*)
// ---------------------------------------------------------------------------

export interface StigmergyMarkOut {
  id: string;
  timestamp: string;
  agent: string;
  file_path: string;
  action: string;
  observation: string;
  salience: number;
  connections: string[];
}

export interface HeatmapCell {
  file_path: string;
  hour: number;
  count: number;
  avg_salience: number;
}

export interface HotPath {
  path: string;
  count: number;
}

// ---------------------------------------------------------------------------
// WebSocket events
// ---------------------------------------------------------------------------

export interface WsEvent<T = unknown> {
  event: string;
  data?: T;
  agents?: AgentOut[];
  agent?: AgentOut;
  agent_id?: string;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

export interface NavSection {
  label: string;
  level: number;
  items: NavItem[];
}

export interface NavItem {
  label: string;
  href: string;
  icon: string;
  level: number;
  badge?: string | number;
}
