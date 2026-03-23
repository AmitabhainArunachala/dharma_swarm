import { CONTROL_PLANE_ROUTE_DECK as rawControlPlaneRouteDeck } from "./controlPlaneRouteDeck.js";

type ControlPlaneRouteId = "command-post" | "qwen35" | "observatory" | "runtime";
type ControlPlaneSurfaceAccent = "aozora" | "rokusho" | "botan" | "kinpaku";
type ControlPlaneSurfaceIcon = "BrainCircuit" | "Bot" | "HeartPulse" | "Settings2";

interface ControlPlaneRouteMeta {
  id: ControlPlaneRouteId;
  href: string;
  label: string;
  summary: string;
  accent: ControlPlaneSurfaceAccent;
  navIcon: ControlPlaneSurfaceIcon;
}

const CONTROL_PLANE_ROUTE_DECK =
  rawControlPlaneRouteDeck as readonly ControlPlaneRouteMeta[];

interface ControlPlanePageCopy {
  pageTitle: string;
  pageDetail: string;
  deckDetail: (peerList: string) => string;
}

export interface ControlPlanePageMeta {
  route: ControlPlaneRouteMeta;
  accent: ControlPlaneSurfaceAccent;
  pageTitle: string;
  pageDetail: string;
  deckTitle: string;
  deckDetail: string;
  peerLabels: string[];
}

const CONTROL_PLANE_PAGE_COPY: Record<ControlPlaneRouteId, ControlPlanePageCopy> = {
  "command-post": {
    pageTitle: "Live Command Post",
    pageDetail:
      "Resident Claude and resident Codex side by side, with explicit relay controls and a live session telemetry rail beneath them.",
    deckDetail: (peerList) =>
      `Command Post anchors coordination on the same canonical route deck as ${peerList}.`,
  },
  qwen35: {
    pageTitle: "Qwen Surgeon",
    pageDetail:
      "In-house code surgeon for bounded edits, live diagnostics, and operator intervention on the shared control plane.",
    deckDetail: (peerList) =>
      `Qwen Surgeon stays on the same canonical route deck as ${peerList}, so surgical coding pivots across the shared shell instead of a separate control plane.`,
  },
  observatory: {
    pageTitle: "Agent Observatory",
    pageDetail: "Fleet-wide health monitoring, fitness rankings, and activity stream.",
    deckDetail: (peerList) =>
      `Observatory reads the same route contract as ${peerList}, so fleet health stays grounded in the same operator path.`,
  },
  runtime: {
    pageTitle: "Runtime",
    pageDetail:
      "Product-shell runtime state for the shared dashboard. Browser routes stay the same while the macOS shell wraps this surface instead of creating a second UI.",
    deckDetail: (peerList) =>
      `Runtime keeps shell, contract, and transport truth on the same canonical route deck as ${peerList}.`,
  },
};

function joinRouteLabels(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? "";
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(", ")}, and ${labels.at(-1)}`;
}

export function buildControlPlanePageMeta(
  routeId: ControlPlaneRouteId,
): ControlPlanePageMeta {
  const route = CONTROL_PLANE_ROUTE_DECK.find((entry) => entry.id === routeId);
  if (!route) {
    throw new Error(`Unknown control-plane route: ${routeId}`);
  }

  const pageCopy = CONTROL_PLANE_PAGE_COPY[routeId];
  const peerLabels = CONTROL_PLANE_ROUTE_DECK.filter((entry) => entry.id !== routeId).map(
    (entry) => entry.label,
  );

  return {
    route,
    accent: route.accent,
    pageTitle: pageCopy.pageTitle,
    pageDetail: pageCopy.pageDetail,
    deckTitle: "Canonical Operator Deck",
    deckDetail: pageCopy.deckDetail(joinRouteLabels(peerLabels)),
    peerLabels,
  };
}
