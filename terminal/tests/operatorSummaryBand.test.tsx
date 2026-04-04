import {describe, expect, test} from "bun:test";
import React from "react";

import {OperatorSummaryBand} from "../src/components/OperatorSummaryBand";

function flattenElementText(node: React.ReactNode): string[] {
  if (node === null || node === undefined || typeof node === "boolean") {
    return [];
  }
  if (typeof node === "string" || typeof node === "number") {
    return [String(node)];
  }
  if (Array.isArray(node)) {
    return node.flatMap((child) => flattenElementText(child));
  }
  if (React.isValidElement(node)) {
    return flattenElementText(node.props.children);
  }
  return [];
}

describe("OperatorSummaryBand", () => {
  test("keeps runtime state in the compact band instead of collapsing to the session count", () => {
    const band = OperatorSummaryBand({
      compact: true,
      items: [
        {label: "bridge", value: "connected", tone: "live"},
        {label: "route", value: "chat-first (stable)", tone: "neutral"},
        {label: "strategy", value: "responsive", tone: "neutral"},
        {label: "loop", value: "cycle 12 waiting_for_verification", tone: "warn"},
        {label: "verify", value: "1 failing, 3/4 passing", tone: "critical"},
        {label: "runtime", value: "22 sessions | 3 runs | 1 active", tone: "live"},
        {label: "approvals", value: "1 pending", tone: "warn"},
        {label: "sessions", value: "22", tone: "live"},
      ],
    });
    const visibleText = flattenElementText(band).join("\n");

    expect(visibleText).toContain("loop");
    expect(visibleText).toContain("cycle 12 waiting_for_verification");
    expect(visibleText).toContain("verify");
    expect(visibleText).toContain("1 failing, 3/4 passing");
    expect(visibleText).toContain("runtime");
    expect(visibleText).toContain("22 sessions | 3 runs | 1 active");
    expect(visibleText).toContain("approvals");
    expect(visibleText).toContain("1 pending");
    expect(visibleText).not.toContain("sessions\n22");
  });
});
