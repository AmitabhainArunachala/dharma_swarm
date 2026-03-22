import assert from "node:assert/strict";
import test from "node:test";

import { buildControlPlanePageMeta } from "./controlPlanePageMeta.ts";

test("buildControlPlanePageMeta keeps Qwen and Runtime tied to canonical route accents", () => {
  const qwen = buildControlPlanePageMeta("qwen35");
  const runtime = buildControlPlanePageMeta("runtime");

  assert.equal(qwen.pageTitle, "Qwen Surgeon");
  assert.equal(qwen.accent, "rokusho");
  assert.equal(runtime.pageTitle, "Runtime");
  assert.equal(runtime.accent, "kinpaku");
});

test("buildControlPlanePageMeta derives peer route copy in canonical deck order", () => {
  const commandPost = buildControlPlanePageMeta("command-post");
  const observatory = buildControlPlanePageMeta("observatory");

  assert.equal(commandPost.deckTitle, "Canonical Operator Deck");
  assert.deepEqual(commandPost.peerLabels, ["Qwen Surgeon", "Observatory", "Runtime"]);
  assert.match(
    commandPost.deckDetail,
    /Qwen Surgeon, Observatory, and Runtime/,
  );

  assert.equal(observatory.deckTitle, "Canonical Operator Deck");
  assert.deepEqual(observatory.peerLabels, ["Command Post", "Qwen Surgeon", "Runtime"]);
  assert.match(
    observatory.deckDetail,
    /Command Post, Qwen Surgeon, and Runtime/,
  );
});
