import {describe, expect, test} from "bun:test";

import {
  defaultRoutePolicy,
  nonSelectableRouteTargets,
  routeLabel,
  routePolicyFromValue,
  routeSummary,
  selectableRouteTargets,
} from "../src/routePolicy";

describe("routePolicyFromValue", () => {
  test("normalizes a ready codex route with a truthful fallback chain", () => {
    const policy = routePolicyFromValue({
      version: "v1",
      domain: "routing_decision",
      decision: {
        route_id: "codex:gpt-5.4",
        provider_id: "codex",
        model_id: "gpt-5.4",
        strategy: "responsive",
        route_state: "ready",
        metadata: {
          default_route: "codex:gpt-5.4",
          active_label: "Codex 5.4",
        },
      },
      targets: [
        {
          alias: "codex:gpt-5.4",
          label: "Codex 5.4",
          provider: "codex",
          model: "gpt-5.4",
          route_id: "codex:gpt-5.4",
          route_state: "ready",
          picker_visible: true,
        },
      ],
      fallback_targets: [
        {provider: "claude", model: "sonnet-4.5", route_id: "claude:sonnet-4.5"},
        {provider: "openrouter", model: "anthropic/claude-sonnet-4.5", route_id: "openrouter:anthropic/claude-sonnet-4.5"},
      ],
    });

    expect(policy.provider).toBe("codex");
    expect(policy.model).toBe("gpt-5.4");
    expect(policy.routeState).toBe("ready");
    expect(policy.selectable).toBe(true);
    expect(policy.defaultRouteId).toBe("codex:gpt-5.4");
    expect(policy.fallbackChain).toEqual(["claude:sonnet-4.5", "openrouter:anthropic/claude-sonnet-4.5"]);
    expect(routeLabel(policy)).toBe("codex:gpt-5.4");
  });

  test("accepts a claude route selected through payload.policy", () => {
    const policy = routePolicyFromValue({
      payload: {
        domain: "routing_decision",
        policy: {
          route_id: "claude:sonnet-4.5",
          provider_id: "claude",
          model_id: "sonnet-4.5",
          strategy: "deliberate",
          route_state: "ready",
          selectable: true,
          active_label: "Claude Sonnet 4.5",
        },
        targets: [
          {
            alias: "claude:sonnet-4.5",
            label: "Claude Sonnet 4.5",
            provider: "claude",
            model: "sonnet-4.5",
            route_state: "ready",
            picker_visible: true,
          },
        ],
      },
    });

    expect(policy.routeId).toBe("claude:sonnet-4.5");
    expect(policy.provider).toBe("claude");
    expect(policy.model).toBe("sonnet-4.5");
    expect(policy.strategy).toBe("deliberate");
    expect(policy.activeLabel).toBe("Claude Sonnet 4.5");
  });

  test("keeps degraded ollama routes visible and selectable", () => {
    const policy = routePolicyFromValue({
      version: "v1",
      domain: "routing_decision",
      decision: {
        route_id: "ollama:qwen2.5-coder:14b",
        provider_id: "ollama",
        model_id: "qwen2.5-coder:14b",
        strategy: "responsive",
        route_state: "degraded",
      },
      targets: [
        {
          alias: "ollama:qwen2.5-coder:14b",
          label: "Ollama Qwen 14B",
          provider: "ollama",
          model: "qwen2.5-coder:14b",
          route_state: "degraded",
          availability_reason: "warming local runtime",
          picker_visible: true,
        },
      ],
    });

    expect(policy.routeState).toBe("degraded");
    expect(policy.selectable).toBe(true);
    expect(selectableRouteTargets(policy)).toHaveLength(1);
    expect(routeSummary(policy)).toContain("warming local runtime");
  });

  test("keeps invalid openrouter targets clearly non-selectable", () => {
    const policy = routePolicyFromValue({
      version: "v1",
      domain: "routing_decision",
      decision: {
        route_id: "codex:gpt-5.4",
        provider_id: "codex",
        model_id: "gpt-5.4",
        strategy: "responsive",
        route_state: "ready",
      },
      targets: [
        {
          alias: "codex:gpt-5.4",
          label: "Codex 5.4",
          provider: "codex",
          model: "gpt-5.4",
          route_state: "ready",
          picker_visible: true,
        },
        {
          alias: "openrouter:anthropic/claude-sonnet-4.5",
          label: "OpenRouter Claude Sonnet 4.5",
          provider: "openrouter",
          model: "anthropic/claude-sonnet-4.5",
          route_state: "invalid",
          availability_reason: "missing credential",
          picker_visible: false,
        },
      ],
      fallback_targets: [{provider: "codex", model: "gpt-5.4", route_id: "codex:gpt-5.4"}],
    });

    expect(selectableRouteTargets(policy).map((target) => target.routeId)).toEqual(["codex:gpt-5.4"]);
    expect(nonSelectableRouteTargets(policy).map((target) => target.routeId)).toEqual([
      "openrouter:anthropic/claude-sonnet-4.5",
    ]);
    expect(nonSelectableRouteTargets(policy)[0]?.routeState).toBe("invalid");
    expect(nonSelectableRouteTargets(policy)[0]?.availabilityReason).toBe("missing credential");
    expect(policy.fallbackChain).toEqual(["codex:gpt-5.4"]);
  });

  test("preserves a sane default policy baseline", () => {
    const policy = defaultRoutePolicy();

    expect(policy.routeId).toBe("codex:gpt-5.4");
    expect(policy.provider).toBe("codex");
    expect(policy.model).toBe("gpt-5.4");
    expect(policy.targets).toEqual([]);
  });
});
