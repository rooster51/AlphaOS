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

function envelope(symbol = "QQQ", status = "complete") {
  return {
    schema_version: "alphaos-interface-v2",
    request: { symbol },
    read_only: true,
    research: {
      version: "alphaos-run-market-v1",
      symbol,
      as_of: "2030-01-02T15:00:00+00:00",
      expiration: "2030-01-02",
      archive: {
        session_date: "2030-01-02",
        observation: { observed_at: "2030-01-02T15:00:00+00:00" },
        freshness: { age_seconds: 120, max_age_seconds: 600 },
      },
      research_session: {
        version: "opportunity-session-v1",
        symbol,
        status,
        candidates: status === "complete" ? [{ strategy_family: "call_debit_spread" }] : [],
        unavailable_routes: [],
      },
    },
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
  assert.equal(body.research.research.symbol, "QQQ");
  assert.equal(body.research.research.research_session.status, "complete");
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
    assert.equal(body.status, "unavailable");
    assert.equal(body.code, status === 401
      ? "backend_authentication_required"
      : "backend_authentication_rejected");
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
    { symbol: "SPY", expiration: "0000-01-01" },
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
  assert.deepEqual(await response.json(), {
    status: "unavailable", code: "response_schema_mismatch",
  });
});

test("upstream symbol mismatch fails closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json(envelope("SPY"));

  const response = await POST(request({ symbol: "QQQ" }));
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), {
    status: "unavailable", code: "response_schema_mismatch",
  });
});

test("unavailable and no-candidate research states remain explicit and non-tradable", async () => {
  setBackendConfig();
  for (const status of [
    "no_candidate",
  ]) {
    const payload = envelope("QQQ", status);
    globalThis.fetch = async () => Response.json(payload);
    const response = await POST(request({ symbol: "QQQ" }));
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.research.research.research_session.status, status);
    assert.deepEqual(body.research.research.research_session.candidates, []);
    assert.equal(body.verified_for_trading, false);
  }
});

test("upstream errors and invalid JSON fail closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json(
    { error: { code: "archive_unavailable" } },
    { status: 503 },
  );
  const unavailable = await POST(request({ symbol: "QQQ" }));
  assert.equal(unavailable.status, 502);
  assert.deepEqual(await unavailable.json(), {
    status: "unavailable", code: "archive_unavailable",
  });

  globalThis.fetch = async () => new Response("{", {
    status: 200, headers: { "Content-Type": "application/json" },
  });
  const malformed = await POST(request({ symbol: "QQQ" }));
  assert.equal(malformed.status, 502);
  assert.deepEqual(await malformed.json(), {
    status: "unavailable", code: "response_schema_mismatch",
  });
});

test("missing or invalid backend configuration is unavailable without fetching", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(envelope()); };

  setBackendConfig({ token: null });
  const missing = await POST(request({ symbol: "SPY" }));
  assert.equal(missing.status, 503);
  assert.deepEqual(await missing.json(), {
    status: "unavailable", code: "backend_not_configured",
  });

  setBackendConfig({ url: "http://api.example.test" });
  const invalid = await POST(request({ symbol: "SPY" }));
  assert.equal(invalid.status, 503);
  assert.deepEqual(await invalid.json(), {
    status: "unavailable", code: "invalid_backend_configuration",
  });
  assert.equal(calls, 0);
});

test("SPY archive research uses the same authenticated v2 response contract", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json(envelope("SPY"));
  const response = await POST(request({ symbol: "SPY" }));
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.research.request.symbol, "SPY");
  assert.equal(body.research.research.research_session.symbol, "SPY");
  assert.equal(body.research.research.research_session.candidates[0].strategy_family, "call_debit_spread");
  assert.equal(body.verified_for_trading, false);
});

test("archive freshness, backend rejection, timeout, and network errors stay distinguishable", async () => {
  setBackendConfig();
  for (const [upstreamCode, upstreamStatus, expected] of [
    ["archive_stale", 503, "archive_stale"],
    ["archive_missing", 503, "archive_missing"],
    ["archive_not_configured", 503, "archive_not_configured"],
    ["archive_research_unavailable", 422, "archive_research_unavailable"],
    ["archive_expiration_unavailable", 422, "archive_expiration_unavailable"],
  ]) {
    globalThis.fetch = async () => Response.json(
      { error: { code: upstreamCode } },
      { status: upstreamStatus },
    );
    const response = await POST(request({ symbol: "QQQ" }));
    assert.deepEqual(await response.json(), { status: "unavailable", code: expected });
  }

  globalThis.fetch = async () => { throw new DOMException("timeout", "TimeoutError"); };
  const timedOut = await POST(request({ symbol: "QQQ" }));
  assert.deepEqual(await timedOut.json(), {
    status: "unavailable", code: "backend_timeout",
  });

  globalThis.fetch = async () => { throw new TypeError("network unreachable"); };
  const unreachable = await POST(request({ symbol: "QQQ" }));
  assert.deepEqual(await unreachable.json(), {
    status: "unavailable", code: "backend_unreachable",
  });
});


test("consolidated historical economics and history diagnostics survive the website bridge", async () => {
  setBackendConfig();
  const data = envelope();
  const session = data.research.research_session;
  session.diagnostics = { history_loading: { status: "loaded", reason: null } };
  session.historical_comparison = { winner: null, groups: [] };
  session.holding_policy = { preference: "avoid_overnight_exposure" };
  session.candidates[0].research = {
    historical_economics: {
      eligible_for_consideration: false,
      intraday_economics: { expected_value_dollars: null },
      missing_reasons: ["intraday_entry_not_completed_session"],
    },
  };
  globalThis.fetch = async () => Response.json(data);
  const response = await POST(request({ symbol: "QQQ" }));
  const body = await response.json();
  assert.deepEqual(body.research, data);
  assert.equal(body.verified_for_trading, false);
});
