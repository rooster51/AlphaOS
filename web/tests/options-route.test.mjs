import test from "node:test";
import assert from "node:assert/strict";
import { GET } from "../src/app/api/options/route.ts";
import { authBindings, cookie } from "./auth-fixture.mjs";

const origin = "https://preview.test";
const request = (query, authenticated = true) => new Request(`${origin}/api/options?${query}`, {
  headers: authenticated ? { Cookie: `__Host-alphaos_session=${cookie(origin)}` } : {},
});

test("dated options bridge authenticates, bounds requests and isolates symbols", async t => {
  Object.assign(process.env, authBindings, {
    ALPHAOS_API_URL: "https://backend.test", ALPHAOS_API_TOKEN: "fixture-token",
  });
  const timeout = new AbortController();
  t.mock.method(AbortSignal, "timeout", ms => {
    assert.equal(ms, 8000);
    return timeout.signal;
  });
  let markSpyStarted;
  const spyStarted = new Promise(resolve => { markSpyStarted = resolve; });
  const upstream = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    assert.equal(options.headers.Authorization, "Bearer fixture-token");
    if (url.pathname.includes("/SPY/")) {
      assert.equal(url.pathname, "/v1/options/SPY/chain/2026-11-06");
      assert.equal(url.searchParams.get("explicit"), "true");
      assert.equal(url.searchParams.get("refresh"), "true");
      markSpyStarted();
      return new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true }));
    }
    assert.equal(url.pathname, "/v1/options/QQQ/expirations");
    return Response.json({ meta: { symbol: "QQQ" }, evidence: { expirations: ["2026-11-06"] } });
  });
  assert.equal((await GET(request("symbol=SPY", false))).status, 401);
  assert.equal((await GET(request("symbol=SPY&expiration=../../quote"))).status, 400);
  assert.equal(upstream.mock.callCount(), 0);
  const spy = GET(request("symbol=SPY&expiration=2026-11-06"));
  await spyStarted;
  const qqq = await GET(request("symbol=QQQ"));
  assert.equal(qqq.headers.get("Cache-Control"), "private, no-store");
  assert.deepEqual(await qqq.json(), { expirations: ["2026-11-06"] });
  timeout.abort(new DOMException("private text", "TimeoutError"));
  const timedOut = await spy;
  assert.equal(timedOut.status, 504);
  assert.deepEqual(await timedOut.json(), { code: "request_timeout" });
});
