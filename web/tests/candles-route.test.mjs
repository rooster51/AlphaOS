import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { GET } from "../src/app/api/candles/[symbol]/route.ts";
import { authBindings, cookie } from "./auth-fixture.mjs";
import { candleSnapshot } from "./candles-fixture.mjs";

const origin = "https://preview.test";
const originalFetch = globalThis.fetch;
const originalWarn = console.warn;
const saved = Object.fromEntries(
  ["ALPHAOS_PASSWORD_HASH", "ALPHAOS_SESSION_KEY", "ALPHAOS_API_URL", "ALPHAOS_API_TOKEN", "ALPHAOS_CANDLE_CHART_ENABLED"]
    .map((name) => [name, process.env[name]]),
);

function configure(token = "fixture-token", url = "https://backend.test") {
  for (const [name, value] of Object.entries({
    ...authBindings,
    ALPHAOS_API_URL: url,
    ALPHAOS_API_TOKEN: token,
    ALPHAOS_CANDLE_CHART_ENABLED: "true",
  })) process.env[name] = value;
}

function request(query = "", { authenticated = true, role = "owner" } = {}) {
  return new Request(`${origin}/api/candles/SPY${query}`, {
    headers: authenticated ? { Cookie: `__Host-alphaos_session=${cookie(origin, Date.now(), role)}` } : {},
  });
}

const context = (symbol = "SPY") => ({ params: Promise.resolve({ symbol }) });

beforeEach(() => {
  configure();
  console.warn = () => {};
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  console.warn = originalWarn;
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
});

test("anonymous and shared-link requests are rejected before contacting the backend", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json({ status: "ok" }); };
  for (const target of [request("", { authenticated: false }), new Request(`${origin}/api/candles/SPY`)]) {
    const response = await GET(target, context());
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), { status: "unavailable", code: "authentication_required" });
    assert.match(response.headers.get("cache-control"), /private, no-store/);
    assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
  }
  assert.equal(calls, 0);
});

test("a valid non-owner account is denied the owner-only chart before the backend", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(candleSnapshot()); };
  const response = await GET(request("", { role: "viewer" }), context());
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "owner_only" });
  assert.match(response.headers.get("cache-control"), /private, no-store/);
  assert.equal(calls, 0);
});

test("a session without a recognized role is not an authenticated owner session", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(candleSnapshot()); };
  const response = await GET(request("", { role: null }), context());
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "authentication_required" });
  assert.equal(calls, 0);
});

test("owner access still fails closed while the deployment switch is off", async () => {
  process.env.ALPHAOS_CANDLE_CHART_ENABLED = "false";
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(candleSnapshot()); };
  const response = await GET(request(), context());
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "feature_disabled" });
  assert.match(response.headers.get("cache-control"), /private, no-store/);
  assert.equal(calls, 0);
});

test("the owner bridge forwards the exact native request with server-side auth and owner-private use", async () => {
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url: new URL(url), options };
    return Response.json(candleSnapshot({ interval: "5m" }));
  };
  const response = await GET(request("?interval=5m&session=regular&limit=390"), context());
  assert.equal(response.status, 200);
  assert.equal(captured.url.toString(), "https://backend.test/v1/candles/SPY?interval=5m&session=regular&limit=390");
  assert.equal(captured.options.headers.Authorization, "Bearer fixture-token");
  assert.equal(captured.options.headers["X-AlphaOS-Data-Use"], "owner_private_display");
  assert.equal(captured.options.cache, "no-store");
  assert.match(captured.options.headers["X-AlphaOS-Request-ID"], /^[a-f0-9]{32}$/);
  const body = await response.json();
  assert.equal(body.status, "ok");
  assert.equal(body.snapshot.snapshot_id, "a".repeat(64));
  assert.equal(body.snapshot.entitlement.use_context, "owner_private_display");
  assert.equal(body.snapshot.returned_bars, 2);
  assert.equal(response.headers.get("Vary"), "Cookie");
  assert.match(response.headers.get("cache-control"), /private, no-store/);
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
});

test("private-research entitlement is not owner-private display authorization", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    const snapshot = candleSnapshot();
    return Response.json({
      ...snapshot,
      entitlement: {
        ...snapshot.entitlement,
        use_context: "private_research",
        authorization_reference_present: false,
      },
    });
  };
  const response = await GET(request(), context());
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "data_use_denied" });
  assert.equal(calls, 1);
});

test("public-display entitlement is not accepted by the owner-private route", async () => {
  globalThis.fetch = async () => {
    const snapshot = candleSnapshot();
    snapshot.entitlement = {
      ...snapshot.entitlement,
      use_context: "public_display",
      authorization_reference_present: true,
    };
    snapshot.provider_capabilities.entitlement = {
      ...snapshot.provider_capabilities.entitlement,
      owner_private_display: false,
      public_display: true,
    };
    return Response.json(snapshot);
  };
  const response = await GET(request(), context());
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "data_use_denied" });
});

test("the provider capability must grant owner-private display", async () => {
  globalThis.fetch = async () => {
    const snapshot = candleSnapshot();
    snapshot.provider_capabilities.entitlement = {
      ...snapshot.provider_capabilities.entitlement,
      owner_private_display: false,
    };
    return Response.json(snapshot);
  };
  const response = await GET(request(), context());
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "data_use_denied" });
});

test("a denied owner-private decision is rejected even with the capability set", async () => {
  globalThis.fetch = async () => {
    const snapshot = candleSnapshot();
    return Response.json({ ...snapshot, entitlement: { ...snapshot.entitlement, allowed: false } });
  };
  const response = await GET(request(), context());
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "data_use_denied" });
});

test("invalid symbol, interval, session or limit fails before any backend call", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(candleSnapshot()); };
  for (const [query, symbol] of [
    ["?interval=30m", "SPY"],
    ["?session=extended", "SPY"],
    ["?limit=391", "SPY"],
    ["?limit=0", "SPY"],
    ["?limit=1.5", "SPY"],
    ["", "DIA"],
  ]) {
    const response = await GET(request(query), context(symbol));
    assert.equal(response.status, 400, `${query} ${symbol}`);
    assert.deepEqual(await response.json(), { status: "unavailable", code: "invalid_request" });
  }
  assert.equal(calls, 0);
});

test("provider throttling is one request/response, never a hidden retry", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return Response.json(
      { error: { code: "public_rate_limit", message: "private detail" } },
      { status: 429 },
    );
  };
  const response = await GET(request(), context());
  assert.equal(response.status, 429);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "provider_rate_limited" });
  assert.equal(calls, 1);
});

test("upstream failures map to distinct safe website states", async () => {
  const cases = [
    [401, { error: { code: "authentication_required" } }, 502, "backend_authentication_failed"],
    [403, { error: { code: "data_use_denied" } }, 403, "data_use_denied"],
    [503, { error: { code: "public_not_configured" } }, 503, "public_not_configured"],
    [503, { error: { code: "no_candles" } }, 503, "no_candles"],
    [504, { error: { code: "provider_timeout" } }, 504, "provider_timeout"],
    [500, { error: { code: "internal_error" } }, 502, "provider_unavailable"],
  ];
  for (const [upstream, body, status, code] of cases) {
    globalThis.fetch = async () => Response.json(body, { status: upstream });
    const response = await GET(request(), context());
    assert.equal(response.status, status, `${upstream}/${code}`);
    assert.deepEqual(await response.json(), { status: "unavailable", code });
  }
});

test("a malformed successful payload fails closed as a provider schema error", async () => {
  globalThis.fetch = async () => Response.json(candleSnapshot({ returned_bars: 1 }));
  const response = await GET(request(), context());
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "provider_schema_error" });
});

test("network failure stays a backend transport state", async () => {
  globalThis.fetch = async () => { throw new TypeError("DO_NOT_LOG"); };
  const response = await GET(request(), context());
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "backend_unreachable" });
});

test("an upstream deadline is classified as provider timeout", async (t) => {
  const controller = new AbortController();
  controller.abort(new DOMException("deadline", "TimeoutError"));
  t.mock.method(AbortSignal, "timeout", () => controller.signal);
  globalThis.fetch = async () => { throw new DOMException("deadline", "TimeoutError"); };
  const response = await GET(request(), context());
  assert.equal(response.status, 504);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "provider_timeout" });
});

test("missing backend configuration returns a safe unavailable state", async () => {
  configure("", "https://backend.test");
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(candleSnapshot()); };
  const response = await GET(request(), context());
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { status: "unavailable", code: "backend_not_configured" });
  assert.equal(calls, 0);
});
