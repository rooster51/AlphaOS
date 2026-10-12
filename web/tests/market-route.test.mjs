import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { POST } from "../src/app/api/research/market/route.ts";

const originalToken = process.env.ALPHAOS_API_TOKEN;
const originalUrl = process.env.ALPHAOS_API_URL;
const originalFetch = globalThis.fetch;

function setBackendConfig(config = {}) {
  const token = Object.hasOwn(config, "token") ? config.token : "test-token";
  const url = Object.hasOwn(config, "url") ? config.url : "https://api.example.test";
  if (token === null) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = token;
  if (url === null) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = url;
}

function request(body) {
  return new Request("http://localhost/api/research/market", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function envelope(symbol = "QQQ") {
  return {
    schema_version: "alphaos-interface-v2",
    request: { symbol },
    read_only: true,
    research: { status: "complete" },
    provenance: { source: "test" },
    caveats: [],
  };
}

afterEach(() => {
  if (originalToken === undefined) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = originalToken;
  if (originalUrl === undefined) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = originalUrl;
  globalThis.fetch = originalFetch;
});

test("forwards a valid authenticated JSON POST and preserves read-only response envelope", async () => {
  setBackendConfig();
  let upstreamRequest;
  globalThis.fetch = async (url, options) => {
    upstreamRequest = { url: new URL(url), options };
    return Response.json(envelope());
  };

  const response = await POST(request({
    symbol: "qqq", expiration: "2026-10-16", available_capital: 250,
    objective: "research context", width: 7.5,
  }));
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(upstreamRequest.url.toString(), "https://api.example.test/v1/research/market");
  assert.equal(upstreamRequest.options.method, "POST");
  assert.equal(upstreamRequest.options.headers.Authorization, "Bearer test-token");
  assert.equal(upstreamRequest.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(upstreamRequest.options.body), {
    symbol: "QQQ", expiration: "2026-10-16", available_capital: 250,
    objective: "research context", width: 7.5,
  });
  assert.equal(body.research.schema_version, "alphaos-interface-v2");
  assert.equal(body.verified_for_trading, false);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("upstream authentication failures do not leak response details", async () => {
  setBackendConfig();
  for (const status of [401, 403]) {
    globalThis.fetch = async () => new Response("Bearer secret backend detail", { status });
    const response = await POST(request({ symbol: "SPY" }));
    const body = await response.json();
    assert.equal(response.status, 502);
    assert.deepEqual(body, { error: "Research backend unavailable" });
    assert.equal(JSON.stringify(body).includes("secret"), false);
  }
});

test("invalid or malformed request bodies fail before contacting the backend", async () => {
  setBackendConfig();
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(envelope()); };

  for (const body of [
    "not-json",
    {},
    { symbol: "DIA" },
    { symbol: "QQQ", unexpected: true },
    { symbol: "SPY", expiration: "2026-02-30" },
    { symbol: "SPY", available_capital: Number.NaN },
    { symbol: "SPY", width: 101 },
  ]) {
    const response = await POST(request(body));
    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { error: "Invalid research request" });
  }
  assert.equal(calls, 0);
});

test("malformed upstream research envelopes fail closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json({ schema_version: "wrong", research: [] });

  const response = await POST(request({ symbol: "QQQ" }));
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { error: "Invalid research response" });
});

test("upstream errors and invalid JSON fail closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => new Response("private backend failure", { status: 503 });
  const unavailable = await POST(request({ symbol: "QQQ" }));
  assert.equal(unavailable.status, 502);
  assert.deepEqual(await unavailable.json(), { error: "Research backend unavailable" });

  globalThis.fetch = async () => new Response("{", {
    status: 200, headers: { "Content-Type": "application/json" },
  });
  const malformed = await POST(request({ symbol: "QQQ" }));
  assert.equal(malformed.status, 502);
  assert.deepEqual(await malformed.json(), { error: "Research request failed" });
});

test("missing or invalid backend configuration is unavailable without fetching", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(envelope()); };

  setBackendConfig({ token: null });
  const missing = await POST(request({ symbol: "SPY" }));
  assert.equal(missing.status, 503);

  setBackendConfig({ url: "http://api.example.test" });
  const invalid = await POST(request({ symbol: "SPY" }));
  assert.equal(invalid.status, 503);
  assert.equal(calls, 0);
});
