import { CONTROL_PLANE_ROUTE_DECK } from "./controlPlaneRouteDeck.js";
export { isDashboardPathActive } from "./dashboardPath.js";

export type DashboardNavIcon =
  | "Activity"
  | "Bot"
  | "Brain"
  | "BrainCircuit"
  | "ClipboardCheck"
  | "Dna"
  | "GitBranch"
  | "Globe"
  | "Grid3X3"
  | "HeartPulse"
  | "LayoutDashboard"
  | "ListTodo"
  | "MessageSquare"
  | "Network"
  | "Orbit"
  | "Settings2"
  | "Shield"
  | "Sparkles"
  | "Workflow";

export interface DashboardNavItem {
  label: string;
  href: string;
  icon: DashboardNavIcon;
  level: number;
}

export interface DashboardNavSection {
  label: string;
  level: number;
  items: DashboardNavItem[];
}

function canonicalOperatorDeckItems(): DashboardNavItem[] {
  return CONTROL_PLANE_ROUTE_DECK.map((route) => ({
    label: route.label,
    href: route.href,
    icon: route.navIcon as DashboardNavIcon,
    level: 1,
  }));
}

export function buildDashboardNavSections(): DashboardNavSection[] {
  return [
    {
      label: "COMMAND",
      level: 1,
      items: [
        { label: "Overview", href: "/dashboard", icon: "LayoutDashboard", level: 1 },
        ...canonicalOperatorDeckItems(),
        { label: "Conv. Log", href: "/dashboard/log", icon: "MessageSquare", level: 1 },
        { label: "Truth Map", href: "/dashboard/modules", icon: "Activity", level: 1 },
        { label: "Semantic Graph", href: "/dashboard/claude", icon: "Globe", level: 1 },
        { label: "Models", href: "/dashboard/models", icon: "Sparkles", level: 1 },
        { label: "GLM-5", href: "/dashboard/glm5", icon: "Brain", level: 1 },
        { label: "Telemetry", href: "/dashboard/telemetry", icon: "Activity", level: 1 },
        { label: "Ecosystem Map", href: "/dashboard/ecosystem", icon: "Orbit", level: 1 },
        { label: "Synthesizer", href: "/dashboard/synthesizer", icon: "Sparkles", level: 1 },
        { label: "Agents", href: "/dashboard/agents", icon: "Bot", level: 1 },
        { label: "Tasks", href: "/dashboard/tasks", icon: "ListTodo", level: 1 },
      ],
    },
    {
      label: "INTELLIGENCE",
      level: 3,
      items: [
        { label: "Eval Harness", href: "/dashboard/eval", icon: "ClipboardCheck", level: 3 },
        { label: "System Audit", href: "/dashboard/audit", icon: "HeartPulse", level: 3 },
        { label: "Evolution", href: "/dashboard/evolution", icon: "Dna", level: 3 },
        { label: "Gates", href: "/dashboard/gates", icon: "Shield", level: 3 },
      ],
    },
    {
      label: "DEEP",
      level: 4,
      items: [
        { label: "Ontology", href: "/dashboard/ontology", icon: "Globe", level: 4 },
        { label: "Lineage", href: "/dashboard/lineage", icon: "GitBranch", level: 4 },
        { label: "Stigmergy", href: "/dashboard/stigmergy", icon: "Network", level: 4 },
      ],
    },
    {
      label: "COMPOSE",
      level: 5,
      items: [
        { label: "Workflows", href: "/dashboard/workflows", icon: "Workflow", level: 5 },
        { label: "Blocks", href: "/dashboard/blocks", icon: "Grid3X3", level: 5 },
      ],
    },
  ];
}
