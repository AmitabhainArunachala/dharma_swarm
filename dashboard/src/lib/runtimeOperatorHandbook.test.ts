import assert from "node:assert/strict";
import test from "node:test";

import { buildRuntimeOperatorHandbook } from "./runtimeOperatorHandbook.ts";

test("buildRuntimeOperatorHandbook keeps runtime truth on the canonical shell and overnight watch", () => {
  const handbook = buildRuntimeOperatorHandbook();

  assert.deepEqual(handbook.stableRoutes, [
    "/dashboard",
    "/dashboard/command-post",
    "/dashboard/qwen35",
    "/dashboard/observatory",
    "/dashboard/runtime",
  ]);

  const productShell = handbook.sections.find((section) => section.id === "product-shell");
  assert.ok(productShell);
  assert.deepEqual(productShell?.entries, [
    "bash scripts/dashboard_ctl.sh status",
    "bash scripts/dashboard_ctl.sh start",
    "bash scripts/dashboard_ctl.sh restart",
    "bash scripts/dashboard_ctl.sh logs 80",
  ]);
  assert.match(productShell?.detail ?? "", /launchd/i);
  assert.match(productShell?.detail ?? "", /3420/);
  assert.match(productShell?.detail ?? "", /8420/);

  const nightWatch = handbook.sections.find((section) => section.id === "night-watch");
  assert.ok(nightWatch);
  assert.deepEqual(nightWatch?.entries, [
    "bash scripts/start_build_conclave.sh 8",
    "bash scripts/status_build_conclave.sh",
  ]);
  assert.match(nightWatch?.detail ?? "", /worker swarm/i);
  assert.doesNotMatch(nightWatch?.detail ?? "", /product shell/i);

  const artifacts = handbook.sections.find((section) => section.id === "morning-artifacts");
  assert.ok(artifacts);
  assert.deepEqual(artifacts?.entries, [
    "~/.dharma/logs/codex_overnight/<run-id>/outputs/cycle_<n>_semantic_packet.md",
    "~/.dharma/logs/codex_overnight/<run-id>/outputs/cycle_<n>_xray_packet.md",
    "~/.dharma/logs/codex_overnight/<run-id>/morning_handoff.md",
    "~/.dharma/shared/codex_overnight_handoff.md",
  ]);

  assert.match(handbook.wrapperDetail, /desktop-shell\//i);
  assert.match(handbook.wrapperDetail, /wrapper/i);
  assert.match(handbook.wrapperDetail, /not the runtime authority/i);
  assert.equal(handbook.nextStep.href, "/dashboard/command-post");
  assert.equal(handbook.nextStep.label, "Command Post");
});

test("buildRuntimeOperatorHandbook lets the night entrypoint reflect the requested target window", () => {
  const handbook = buildRuntimeOperatorHandbook({ targetHours: 6 });
  const nightWatch = handbook.sections.find((section) => section.id === "night-watch");

  assert.ok(nightWatch);
  assert.equal(nightWatch?.entries[0], "bash scripts/start_build_conclave.sh 6");
});
