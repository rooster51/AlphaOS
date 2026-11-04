import test from "node:test";
import assert from "node:assert/strict";
import { GET } from "../src/app/api/current-quote/route.ts";
import { authBindings, cookie } from "./auth-fixture.mjs";

const origin = "https://preview.test";
const request = (symbol, authenticated = true) => new Request(`${origin}/api/current-quote?symbol=${symbol}`, {
  headers: authenticated ? { Cookie: `__Host-alphaos_session=${cookie(origin)}` } : {},
});

test("quote bridge authenticates, classifies slow requests and keeps symbols separate", async t => {
  for (const [key, value] of Object.entries({
    ...authBindings, ALPHAOS_API_URL: "https://backend.test", ALPHAOS_API_TOKEN: "fixture-token",
  })) process.env[key] = value;
  const timeout = new AbortController();
  t.mock.method(AbortSignal, "timeout", ms => {
    assert.equal(ms, 5000);
    return timeout.signal;
  });
  let markSpyStarted;
  const spyStarted = new Promise(resolve => { markSpyStarted = resolve; });
  const upstream = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(options.cache, "no-store");
    assert.equal(url.searchParams.get("refresh"), "true");
    assert.match(options.headers["X-AlphaOS-Request-ID"], /^[a-f0-9]{32}$/);
    if (url.pathname.endsWith("/SPY")) {
      const signal = options.signal;
      markSpyStarted();
      return new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(signal.reason), { once: true }));
    }
    const stamp = new Date(Date.now() - 1000).toISOString();
    return Response.json({ evidence: { cache: { hit: false }, quote: {
      symbol: "QQQ", last: 699, bid: 698, ask: 700, provider_outcome: "SUCCESS",
      updated_at: stamp, bid_timestamp: stamp, ask_timestamp: stamp, provider_retrieved_at: stamp,
    } } });
  });
  assert.equal((await GET(request("QQQ", false))).status, 401);
  assert.equal(upstream.mock.callCount(), 0);
  const spy = GET(request("SPY"));
  await spyStarted;
  const qqq = await GET(request("QQQ"));
  assert.equal((await qqq.json()).status, "fresh");
  assert.equal(qqq.headers.get("Cache-Control"), "private, no-store");
  timeout.abort(new DOMException("private text", "TimeoutError"));
  const failed = await (await spy).json();
  assert.equal(failed.code, "request_timeout");
  assert.doesNotMatch(JSON.stringify(failed), /private text|fixture-token/);
});
