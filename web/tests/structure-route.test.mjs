import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, test } from "node:test";
import { POST as postStructure } from "../src/app/api/research/structure/route.ts";
import { POST as postCompare } from "../src/app/api/research/structures/compare/route.ts";

const single = JSON.parse(readFileSync(new URL("./fixtures/structure-parity.json", import.meta.url), "utf8"));
const compared = JSON.parse(readFileSync(new URL("./fixtures/structure-compare-parity.json", import.meta.url), "utf8"));
const spyPutCredit = JSON.parse(readFileSync(new URL("./fixtures/structure-spy-put-credit-parity.json", import.meta.url), "utf8"));

const originalToken = process.env.ALPHAOS_API_TOKEN;
const originalUrl = process.env.ALPHAOS_API_URL;
const originalFetch = globalThis.fetch;
const originalWarn = console.warn;

function setConfig({ token = "test-token", url = "https://api.example.test" } = {}) {
  if (token === null) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = token;
  if (url === null) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = url;
}

function request(path, body) {
  return new Request(`http://localhost${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function wrapper(envelope) {
  return { research: envelope, verified_for_trading: false, source: "alphaos_research_structure_api" };
}

const structureRoute = () => request("/api/research/structure", single.request);
const compareRoute = () => request("/api/research/structures/compare", compared.request);

beforeEach(() => {
  console.warn = () => {};
});

afterEach(() => {
  console.warn = originalWarn;
  globalThis.fetch = originalFetch;
  if (originalToken === undefined) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = originalToken;
  if (originalUrl === undefined) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = originalUrl;
});

test("single structure research is forwarded exactly with server-side credentials", async () => {
  setConfig();
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return Response.json(single);
  };
  const response = await postStructure(structureRoute());
  assert.equal(response.status, 200);
  assert.equal(captured.url.toString(), "https://api.example.test/v1/research/structure");
  assert.equal(captured.options.method, "POST");
  assert.equal(captured.options.headers.Authorization, "Bearer test-token");
  assert.equal(captured.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(captured.options.body), single.request);
  assert.equal(captured.options.cache, "no-store");

  const body = await response.json();
  assert.deepEqual(body, wrapper(single));
  assert.equal(body.verified_for_trading, false);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const requestId = response.headers.get("X-AlphaOS-Request-ID");
  assert.match(requestId, /^[0-9a-f]{32}$/);
  assert.equal(captured.options.headers["X-AlphaOS-Request-ID"], requestId);
});

test("structure comparison is forwarded in supplied order with its thesis", async () => {
  setConfig();
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return Response.json(compared);
  };
  const response = await postCompare(compareRoute());
  assert.equal(response.status, 200);
  assert.equal(captured.url.toString(), "https://api.example.test/v1/research/structures/compare");
  const forwarded = JSON.parse(captured.options.body);
  assert.deepEqual(forwarded, compared.request);
  assert.deepEqual(forwarded.structures.map((item) => item.credit), [-1.2, -2.2]);
  assert.equal(forwarded.thesis, "Debit spread versus outright call");
  assert.deepEqual(await response.json(), wrapper(compared));
});

test("both bridges preserve the backend envelope byte-for-byte for REST parity", async () => {
  setConfig();
  const cases = [
    [postStructure, single, "/api/research/structure"],
    [postStructure, spyPutCredit, "/api/research/structure"],
    [postCompare, compared, "/api/research/structures/compare"],
  ];
  for (const [handler, fixture, path] of cases) {
    let forwarded;
    globalThis.fetch = async (_, options) => {
      forwarded = JSON.parse(options.body);
      return Response.json(fixture);
    };
    const response = await handler(request(path, fixture.request));
    assert.equal(response.status, 200);
    assert.deepEqual(forwarded, fixture.request);
    const body = await response.json();
    assert.deepEqual(body.research, fixture);
    assert.equal(body.source, "alphaos_research_structure_api");
    assert.equal(body.verified_for_trading, false);
  }
});

test("an unsupported leg combination reaches the backend and surfaces only its rejection", async () => {
  setConfig();
  // Two same-type legs in the same direction have no supported family; the
  // website forwards the scenario and lets the backend reject it.
  const unsupported = {
    ...spyPutCredit.request,
    credit: -3.4,
    legs: [
      { type: "Call", strike: 610, qty: 1 },
      { type: "Call", strike: 615, qty: 2 },
    ],
  };
  let forwarded;
  globalThis.fetch = async (_, options) => {
    forwarded = JSON.parse(options.body);
    return Response.json({ error: { code: "invalid_structure" } }, { status: 422 });
  };
  const response = await postStructure(request("/api/research/structure", unsupported));

  assert.deepEqual(forwarded, unsupported);
  assert.equal(response.status, 502);
  const body = await response.json();
  assert.deepEqual(body, { status: "unavailable", code: "invalid_structure" });
  assert.equal("research" in body, false);
});

test("missing archive evidence is preserved as data, not turned into an error or a number", async () => {
  setConfig();
  const copy = structuredClone(spyPutCredit);
  copy.research.historical_economics.missing_evidence = ["verified_archive_unavailable"];
  copy.research.historical_economics.evidence = null;
  globalThis.fetch = async () => Response.json(copy);
  const response = await postStructure(request("/api/research/structure", copy.request));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.deepEqual(
    body.research.research.historical_economics.missing_evidence,
    ["verified_archive_unavailable"],
  );
  assert.equal(body.research.research.historical_economics.historical_evidence_status, "unavailable");
});

test("out-of-contract request bodies fail before any backend access", async () => {
  setConfig();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return Response.json(single);
  };
  const invalid = [
    "not-json",
    {},
    { ...single.request, extra: true },
    { ...single.request, symbol: "SPX" },
    { ...single.request, expiration: "Friday" },
    { ...single.request, as_of: "2030-01-03" },
    { ...single.request, spot: -1 },
    { ...single.request, spot: Number.NaN },
    { ...single.request, credit: "1.2" },
    { ...single.request, fees: -0.01 },
    { ...single.request, legs: [] },
    { ...single.request, legs: [{ type: "Call", strike: 500, qty: 0 }] },
    { ...single.request, legs: [{ type: "Call", strike: 500, qty: 1.5 }] },
    { ...single.request, legs: [{ type: "Call", strike: 500, qty: 101 }] },
    { ...single.request, legs: Array.from({ length: 5 }, () => ({ type: "Call", strike: 500, qty: 1 })) },
  ];
  for (const body of invalid) {
    const response = await postStructure(request("/api/research/structure", body));
    assert.equal(response.status, 400, JSON.stringify(body).slice(0, 100));
    assert.deepEqual(await response.json(), { error: "Invalid structure request" });
  }
  for (const body of [{}, { structures: [] }, { structures: [single.request], extra: 1 },
    { structures: [{ ...single.request, legs: [] }] }]) {
    const response = await postCompare(request("/api/research/structures/compare", body));
    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { error: "Invalid structure comparison request" });
  }
  assert.equal(calls, 0);
});

for (const [status, code, expected] of [
  [422, "invalid_structure", "invalid_structure"],
  [422, null, "backend_rejected_request"],
  [401, null, "backend_authentication_required"],
  [403, null, "backend_authentication_rejected"],
  [404, null, "backend_endpoint_unavailable"],
  [429, null, "backend_rate_limited"],
  [500, "internal_error", "backend_internal_error"],
  [503, "api_not_configured", "backend_api_not_configured"],
  [503, null, "backend_service_unavailable"],
]) {
  test(`upstream ${status}/${code} maps to one safe website code`, async () => {
    setConfig();
    globalThis.fetch = async () => code
      ? Response.json({ error: { code, message: "sensitive detail" } }, { status })
      : new Response("sensitive gateway page", { status });
    const response = await postStructure(structureRoute());
    assert.equal(response.status, 502);
    const body = await response.json();
    assert.deepEqual(body, { status: "unavailable", code: expected });
    assert.equal(JSON.stringify(body).includes("sensitive"), false);
    assert.match(response.headers.get("X-AlphaOS-Request-ID"), /^[0-9a-f]{32}$/);
  });
}

test("tampered or mismatched upstream envelopes are rejected before rendering", async () => {
  setConfig();
  const defects = [
    (copy) => { copy.schema_version = "alphaos-interface-v1"; },
    (copy) => { copy.read_only = false; },
    (copy) => { copy.request.spot = 501; },
    (copy) => { copy.request.symbol = "SPY"; },
    (copy) => { copy.request.legs[0].qty = -1; },
    (copy) => { delete copy.research.position; },
  ];
  for (const defect of defects) {
    const copy = structuredClone(single);
    defect(copy);
    globalThis.fetch = async () => Response.json(copy);
    const response = await postStructure(structureRoute());
    assert.equal(response.status, 502, defect.toString());
    assert.deepEqual(await response.json(), { status: "unavailable", code: "response_schema_mismatch" });
  }

  const ranked = structuredClone(compared);
  ranked.research.comparison.winner = 0;
  globalThis.fetch = async () => Response.json(ranked);
  const response = await postCompare(compareRoute());
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "response_schema_mismatch" });
});

test("transport failures stay distinguishable and never leak details", async () => {
  setConfig();
  globalThis.fetch = async () => { throw new DOMException("DO_NOT_LOG", "TimeoutError"); };
  const timedOut = await postStructure(structureRoute());
  assert.equal(timedOut.status, 502);
  assert.deepEqual(await timedOut.json(), { status: "unavailable", code: "backend_timeout" });

  globalThis.fetch = async () => { throw new TypeError("DO_NOT_LOG"); };
  const unreachable = await postStructure(structureRoute());
  assert.deepEqual(await unreachable.json(), { status: "unavailable", code: "backend_unreachable" });

  const controller = new AbortController();
  const pending = new Request("http://localhost/api/research/structure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(single.request),
    signal: controller.signal,
  });
  globalThis.fetch = async () => {
    controller.abort();
    throw new DOMException("DO_NOT_LOG", "AbortError");
  };
  const cancelled = await postStructure(pending);
  assert.equal(cancelled.status, 499);
  assert.deepEqual(await cancelled.json(), { status: "unavailable", code: "request_cancelled" });
});

test("missing or invalid backend configuration fails without fetching", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return Response.json(single);
  };
  setConfig({ token: null });
  const missing = await postStructure(structureRoute());
  assert.equal(missing.status, 503);
  assert.deepEqual(await missing.json(), { status: "unavailable", code: "backend_not_configured" });

  setConfig({ url: "http://api.example.test" });
  const invalid = await postStructure(structureRoute());
  assert.equal(invalid.status, 503);
  assert.deepEqual(await invalid.json(), { status: "unavailable", code: "invalid_backend_configuration" });

  setConfig({ url: "https://user:pass@api.example.test" });
  const credentials = await postCompare(compareRoute());
  assert.equal(credentials.status, 503);
  assert.equal(calls, 0);
});

test("bridge diagnostics are sanitized and record correlation and status", async () => {
  setConfig();
  const logs = [];
  console.warn = (value) => logs.push(JSON.parse(value));
  for (const status of [500, 503]) {
    globalThis.fetch = async (_, options) => new Response("DO_NOT_LOG", {
      status,
      headers: { "X-AlphaOS-Request-ID": options.headers["X-AlphaOS-Request-ID"] },
    });
    const response = await postStructure(structureRoute());
    const log = logs.at(-1);
    assert.equal(log.event, "structure_bridge");
    assert.equal(log.path, "/v1/research/structure");
    assert.equal(log.upstream_status, status);
    assert.equal(log.correlated, true);
    assert.equal(log.request_id, response.headers.get("X-AlphaOS-Request-ID"));
    assert.equal(log.outcome, "backend_service_unavailable");
    assert.equal(typeof log.elapsed_ms, "number");
  }
  assert.ok(!JSON.stringify(logs).includes("DO_NOT_LOG"));
  assert.ok(!JSON.stringify(logs).includes("test-token"));
  assert.ok(!JSON.stringify(logs).includes("500.0"));
});
