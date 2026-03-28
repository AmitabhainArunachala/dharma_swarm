import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchHeatmap,
  fetchImpact,
  fetchProvenance,
  fetchHealth,
} from "./api.ts";

type FetchCall = {
  input: RequestInfo | URL;
  init?: RequestInit;
};

function installFetchStub(responseBody: unknown, status = 200): {
  calls: FetchCall[];
  restore: () => void;
} {
  const calls: FetchCall[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input, init });
    return new Response(JSON.stringify(responseBody), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

test("typed dashboard fetch unwraps backend ApiResponse envelopes", async () => {
  const stub = installFetchStub({
    status: "ok",
    data: {
      overall_status: "ok",
      agent_health: [],
      anomalies: [],
      total_traces: 3,
      traces_last_hour: 1,
      failure_rate: 0.0,
      mean_fitness: 0.95,
    },
    error: "",
    timestamp: "2026-03-26T00:00:00.000Z",
  });

  try {
    const result = await fetchHealth();
    assert.equal(result.status, "ok");
    assert.equal(result.error, "");
    assert.equal(result.data.overall_status, "ok");
    assert.equal(result.data.total_traces, 3);
    assert.equal(stub.calls.length, 1);
  } finally {
    stub.restore();
  }
});

test("fetchImpact targets the lineage impact route for one artifact", async () => {
  const stub = installFetchStub({
    status: "ok",
    data: {
      root_artifact: "artifact-1",
      affected_artifacts: [],
      affected_tasks: [],
      depth: 0,
      total_descendants: 0,
    },
    error: "",
    timestamp: "2026-03-26T00:00:00.000Z",
  });

  try {
    const result = await fetchImpact("artifact-1");
    assert.equal(result.data.root_artifact, "artifact-1");
    assert.equal(String(stub.calls[0]?.input), "http://127.0.0.1:8420/api/lineage/artifact-1/impact");
  } finally {
    stub.restore();
  }
});

test("fetchProvenance targets the lineage provenance route", async () => {
  const stub = installFetchStub({
    status: "ok",
    data: {
      artifact_id: "artifact-1",
      chain: [],
      root_sources: [],
      depth: 0,
    },
    error: "",
    timestamp: "2026-03-26T00:00:00.000Z",
  });

  try {
    const result = await fetchProvenance("artifact-1");
    assert.equal(result.data.artifact_id, "artifact-1");
    assert.equal(String(stub.calls[0]?.input), "http://127.0.0.1:8420/api/lineage/artifact-1/provenance");
  } finally {
    stub.restore();
  }
});

test("fetchHeatmap uses the stigmergy heatmap query route", async () => {
  const stub = installFetchStub({
    status: "ok",
    data: [],
    error: "",
    timestamp: "2026-03-26T00:00:00.000Z",
  });

  try {
    const result = await fetchHeatmap(72);
    assert.deepEqual(result.data, []);
    assert.equal(
      String(stub.calls[0]?.input),
      "http://127.0.0.1:8420/api/stigmergy/heatmap?window_hours=72",
    );
  } finally {
    stub.restore();
  }
});
