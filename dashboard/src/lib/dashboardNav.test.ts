import assert from "node:assert/strict";
import test from "node:test";

import { buildDashboardNavSections, isDashboardPathActive } from "./dashboardNav.ts";
import { CONTROL_PLANE_ROUTE_DECK } from "./controlPlaneSurfaces.ts";

function commandSection() {
  const section = buildDashboardNavSections().find((entry) => entry.label === "COMMAND");
  assert.ok(section, "expected COMMAND section");
  return section;
}

test("buildDashboardNavSections keeps the canonical operator deck contiguous near the top of COMMAND", () => {
  const items = commandSection().items;

  assert.deepEqual(
    items.slice(0, 6).map((item) => item.label),
    ["Overview", ...CONTROL_PLANE_ROUTE_DECK.map((route) => route.label), "Conv. Log"],
  );
  assert.deepEqual(
    items.slice(0, 5).map((item) => item.href),
    ["/dashboard", ...CONTROL_PLANE_ROUTE_DECK.map((route) => route.href)],
  );
});

test("buildDashboardNavSections avoids advertising /dashboard/claude as a second control plane", () => {
  const items = commandSection().items;
  const semanticGraph = items.find((item) => item.href === "/dashboard/claude");

  assert.equal(semanticGraph?.label, "Semantic Graph");
  assert.equal(items.some((item) => item.label === "Control Plane"), false);
});

test("isDashboardPathActive keeps nested routes attached to their canonical top-level nav item", () => {
  assert.equal(isDashboardPathActive("/dashboard/agents", "/dashboard/agents/agent-7"), true);
  assert.equal(isDashboardPathActive("/dashboard/qwen35", "/dashboard/qwen35/telemetry"), true);
});

test("isDashboardPathActive does not let /dashboard match every nested route", () => {
  assert.equal(isDashboardPathActive("/dashboard", "/dashboard"), true);
  assert.equal(isDashboardPathActive("/dashboard", "/dashboard/command-post"), false);
  assert.equal(isDashboardPathActive("/dashboard/log", "/dashboard/logbook"), false);
});
