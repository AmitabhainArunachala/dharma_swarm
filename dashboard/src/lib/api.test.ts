import assert from "node:assert/strict";
import test from "node:test";

import { BASE_URL, apiPath } from "./api.ts";

test("apiPath keeps the canonical API transport prefix for slash-prefixed routes", () => {
  assert.equal(apiPath("/api/chat"), `${BASE_URL}/api/chat`);
});

test("apiPath normalizes bare route segments onto the canonical API transport path", () => {
  assert.equal(apiPath("api/health"), `${BASE_URL}/api/health`);
});
