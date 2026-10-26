import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, test } from "node:test";
import {
  requestComparison,
  requestObservation,
  requestStructure,
} from "../src/lib/structure-client.ts";

const single = JSON.parse(readFileSync(new URL("./fixtures/structure-parity.json", import.meta.url), "utf8"));
const compared = JSON.parse(readFileSync(new URL("./fixtures/structure-compare-parity.json", import.meta.url), "utf8"));

const originalWarn = console.warn;
afterEach(() => {
  console.warn = originalWarn;
});

function ok(body) {
  return Response.json(body);
}

function wrapped(envelope) {
  return { research: envelope, verified_for_trading: false, source: "alphaos_research_structure_api" };
}

test("structure results are requested from the same-origin bridge only", async () => {
  const calls = [];
  const outcome = await requestStructure(single.request, async (url, options) => {
    calls.push({ url, options });
    return ok(wrapped(single));
  });
  assert.equal(outcome.ok, true);
  assert.equal(outcome.view.family, "call_debit_spread");
  assert.deepEqual(calls.map((call) => call.url), ["/api/research/structure"]);
  assert.deepEqual(JSON.parse(calls[0].options.body), single.request);
  assert.equal(calls[0].options.headers.Authorization, undefined);
  assert.equal(JSON.stringify(calls[0]).includes("test-token"), false);
});

test("comparison results keep the supplied order from the bridge", async () => {
  const outcome = await requestComparison(compared.request, async (url) => {
    assert.equal(url, "/api/research/structures/compare");
    return ok(wrapped(compared));
  });
  assert.equal(outcome.ok, true);
  assert.deepEqual(outcome.view.candidates.map((row) => row.index), [0, 1]);
});

test("bridge error codes reach the caller unchanged", async () => {
  for (const [code, expected] of [
    ["invalid_structure", "invalid_structure"],
    ["backend_timeout", "backend_timeout"],
    ["response_schema_mismatch", "response_schema_mismatch"],
  ]) {
    const outcome = await requestStructure(single.request, async () =>
      Response.json({ status: "unavailable", code }, { status: 502 }));
    assert.deepEqual(outcome, { ok: false, code: expected });
  }
  const malformed = await requestStructure(single.request, async () => new Response("not json", { status: 400 }));
  assert.deepEqual(malformed, { ok: false, code: "invalid_structure_request" });
});

test("a bridge response without the read-only marker or a valid envelope is refused", async () => {
  for (const body of [
    { research: single, verified_for_trading: true, source: "alphaos_research_structure_api" },
    { research: single, verified_for_trading: false, source: "unknown" },
    { research: null, verified_for_trading: false, source: "alphaos_research_structure_api" },
    {},
  ]) {
    const outcome = await requestStructure(single.request, async () => ok(body));
    assert.equal(outcome.ok, false, JSON.stringify(body).slice(0, 80));
    assert.equal(outcome.code, "response_schema_mismatch");
  }
});

test("network and timeout failures are classified, not retried", async () => {
  let calls = 0;
  const unreachable = await requestStructure(single.request, async () => {
    calls += 1;
    throw new TypeError("fetch failed");
  });
  assert.deepEqual(unreachable, { ok: false, code: "backend_unreachable" });

  const timeout = await requestComparison(compared.request, async () => {
    calls += 1;
    throw new DOMException("timed out", "TimeoutError");
  });
  assert.deepEqual(timeout, { ok: false, code: "backend_timeout" });
  assert.equal(calls, 2);
});

test("archive prefill uses the observation view and rejects research payloads", async () => {
  const observation = {
    schema_version: "alphaos-observation-v1",
    read_only: true,
    verified_for_trading: false,
    research_performed: false,
    evidence_scope: "archive_observation_only",
    symbol: "SPY",
    research_mode: "current",
    as_of: "2026-10-26T15:30:00+00:00",
    requested_as_of: "2026-10-26T15:30:01+00:00",
    expiration: "2026-10-30",
    spot: 612.5,
    session: {},
    archive: {
      session_date: "2026-10-26",
      provider: "Public",
      freshness: { age_seconds: 90, max_age_seconds: 600 },
    },
    request: { symbol: "SPY", research_mode: "current" },
    caveats: [],
  };
  const calls = [];
  const outcome = await requestObservation("SPY", async (url, options) => {
    calls.push({ url, options });
    return ok({ research: observation, verified_for_trading: false, source: "alphaos_research_api" });
  });
  assert.equal(outcome.ok, true);
  assert.deepEqual(JSON.parse(calls[0].options.body), { symbol: "SPY", view: "observation" });
  assert.equal(outcome.seed.asOf, "2026-10-26");
  assert.equal(outcome.seed.spot, 612.5);

  const mismatched = await requestObservation("QQQ", async () => ok({ research: observation, verified_for_trading: false }));
  assert.deepEqual(mismatched, { ok: false, code: "response_schema_mismatch" });
});
