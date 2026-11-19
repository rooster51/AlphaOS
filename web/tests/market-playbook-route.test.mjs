import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { POST } from "../src/app/api/market-playbook/[symbol]/route.ts";
import { authBindings, cookie } from "./auth-fixture.mjs";

const origin = "https://preview.test";
const originalFetch = globalThis.fetch;
const configured = {
  ...authBindings,
  ALPHAOS_API_URL: "https://backend.test",
  ALPHAOS_API_TOKEN: "fixture-token",
  ALPHAOS_MARKET_PLAYBOOK_ENABLED: "true",
};
const saved = Object.fromEntries(Object.keys(configured).map((name) => [name, process.env[name]]));

beforeEach(() => Object.assign(process.env, configured));
afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
});

function request(role, source = origin) {
  const headers = { Origin: source, "X-AlphaOS-Playbook": "observe" };
  if (role) headers.Cookie = `__Host-alphaos_session=${cookie(origin, Date.now(), role)}`;
  return new Request(`${origin}/api/market-playbook/QQQ`, { method: "POST", headers });
}

const context = (symbol = "QQQ") => ({ params: Promise.resolve({ symbol }) });

test("playbook fails closed before Render for anonymous, viewer, cross-origin and disabled requests", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({}); };
  assert.equal((await POST(request(), context())).status, 401);
  assert.equal((await POST(request("viewer"), context())).status, 403);
  assert.equal((await POST(request("owner", "https://other.test"), context())).status, 403);
  assert.equal((await POST(request("owner"), context("IWM"))).status, 400);
  delete process.env.ALPHAOS_MARKET_PLAYBOOK_ENABLED;
  assert.equal((await POST(request("owner"), context())).status, 503);
  assert.equal(calls, 0);
});

test("owner observations reuse server-only auth and reject entitlement denial and symbol mismatch", async () => {
  const evidence = {
    version: "market-playbook-v1", symbol: "QQQ", session: null, as_of: null,
    provider: "Public", levels: [], vwap: null, provisional_range: null, history: [],
    status: "INSUFFICIENT DATA", reason: "Waiting for a final candle.",
    bias: "Undetermined", quality: "Insufficient", structure: "No verified intraday structure.",
  };
  const replies = [
    Response.json(evidence),
    Response.json({ symbol: "SPY" }),
    Response.json({}, { status: 403 }),
  ];
  globalThis.fetch = async (url, init) => {
    assert.equal(url.href, "https://backend.test/v1/market-playbook/QQQ");
    assert.equal(init.method, "POST");
    assert.equal(init.headers.Authorization, "Bearer fixture-token");
    assert.equal(init.headers["X-AlphaOS-Data-Use"], "owner_private_display");
    return replies.shift();
  };
  const response = await POST(request("owner"), context());
  assert.equal(response.status, 200);
  assert.match(response.headers.get("cache-control"), /no-store/);
  assert.deepEqual(await response.json(), evidence);
  assert.equal((await POST(request("owner"), context())).status, 502);
  assert.equal((await POST(request("owner"), context())).status, 403);
});
