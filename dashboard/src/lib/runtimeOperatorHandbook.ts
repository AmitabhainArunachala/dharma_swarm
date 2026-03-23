import {
  controlPlanePrimaryRoute,
  controlPlaneStableRouteHrefs,
  controlPlaneRuntimeCommands,
} from "./controlPlaneShell";

export interface RuntimeOperatorHandbookSection {
  id: "product-shell" | "night-watch" | "morning-artifacts";
  title: string;
  detail: string;
  entries: string[];
}

export interface RuntimeOperatorHandbook {
  stableRoutes: string[];
  sections: RuntimeOperatorHandbookSection[];
  wrapperDetail: string;
  nextStep: {
    href: string;
    label: string;
  };
}

export function buildRuntimeOperatorHandbook(options?: {
  targetHours?: number;
}): RuntimeOperatorHandbook {
  const targetHours = options?.targetHours ?? 8;
  const primaryRoute = controlPlanePrimaryRoute();

  return {
    stableRoutes: ["/dashboard", ...controlPlaneStableRouteHrefs()],
    sections: [
      {
        id: "product-shell",
        title: "Product shell",
        detail:
          "Launchd owns the canonical dashboard shell on ports 3420 and 8420. Check this first when the operator surface looks stale or dark.",
        entries: [...controlPlaneRuntimeCommands(), "bash scripts/dashboard_ctl.sh logs 80"],
      },
      {
        id: "night-watch",
        title: "Night build watch",
        detail:
          "The overnight worker swarm is a separate tmux lane. Start or inspect it without turning the dashboard truth page into a second operator runtime.",
        entries: [
          `bash scripts/start_build_conclave.sh ${targetHours}`,
          "bash scripts/status_build_conclave.sh",
        ],
      },
      {
        id: "morning-artifacts",
        title: "Morning artifacts",
        detail:
          "Semantic packets, xray packets, and the operator handoff should land in the shared overnight state directory by morning.",
        entries: [
          "~/.dharma/logs/codex_overnight/<run-id>/outputs/cycle_<n>_semantic_packet.md",
          "~/.dharma/logs/codex_overnight/<run-id>/outputs/cycle_<n>_xray_packet.md",
          "~/.dharma/logs/codex_overnight/<run-id>/morning_handoff.md",
          "~/.dharma/shared/codex_overnight_handoff.md",
        ],
      },
    ],
    wrapperDetail:
      "The repo-local desktop-shell/ scaffold is a wrapper around these same dashboard routes. It is not the runtime authority and should not replace the launchd-backed shell.",
    nextStep: {
      href: primaryRoute.href,
      label: primaryRoute.label,
    },
  };
}
