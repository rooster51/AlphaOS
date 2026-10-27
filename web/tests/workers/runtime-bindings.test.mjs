import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, readdirSync } from "node:fs";
import { resolve, join } from "node:path";
import { Miniflare, convertV4MiniflareOptions, Log, LogLevel } from "miniflare";

const fixture = name => JSON.parse(readFileSync(`tests/fixtures/${name}.json`, "utf8"));
const markets = fixture("market-parity");
const single = fixture("structure-parity");
const compared = fixture("structure-compare-parity");
const root = resolve(".cloudflare/output/v0/workers/default/bundle");
const names = readdirSync(root, { recursive: true }).filter(name => name.endsWith(".js"));
names.sort((a, b) => a === "index.js" ? -1 : b === "index.js" ? 1 : 0);
const modules = names.map(name => ({ type: "ESModule", path: join(root, name), contents: readFileSync(join(root, name), "utf8") }));
const runtimeBindings = { ALPHAOS_API_URL: "https://runtime-backend.example.test", ALPHAOS_API_TOKEN: "worker-runtime-only-secret", ALPHAOS_DEMO_MODE: "false" };

async function worker(bindings = runtimeBindings, upstream = () => { throw new Error("Unexpected outbound request"); }) {
  return new Miniflare(convertV4MiniflareOptions({
    modules, modulesRoot: root,
    compatibilityDate: "2026-10-26",
    // Native bindings must work even when process.env population is disabled.
    compatibilityFlags: ["nodejs_compat", "nodejs_compat_do_not_populate_process_env"],
    bindings,
    serviceBindings: { ASSETS: () => new Response(null, { status: 404 }) },
    outboundService: upstream,
    log: new Log(LogLevel.NONE),
  }));
}
const post = (mf, path, data) => mf.dispatchFetch(`https://website.test/api/research/${path}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

test("real Worker receives runtime-only bindings; QQQ/SPY and structure proxies forward server credentials", async () => {
  let calls = 0;
  const mf = await worker(runtimeBindings, async request => {
    calls++;
    assert.equal(request.headers.get("authorization"), `Bearer ${runtimeBindings.ALPHAOS_API_TOKEN}`);
    assert.equal(new URL(request.url).origin, runtimeBindings.ALPHAOS_API_URL);
    const payload = await request.json();
    const pathname = new URL(request.url).pathname;
    if (pathname === "/v1/research/market") return Response.json(markets.find(item => item.request.symbol === payload.symbol).response);
    if (pathname === "/v1/research/structure") return Response.json(single);
    if (pathname === "/v1/research/structures/compare") return Response.json(compared);
    throw new Error("Unexpected research endpoint");
  });
  try {
    const health = await (await mf.dispatchFetch("https://website.test/api/health")).json();
    assert.equal(health.research_configuration.runtime, "cloudflare");
    assert.equal(health.research_configuration.configuration, "ready");
    assert.deepEqual(health.research_configuration.bindings_present, { ALPHAOS_API_URL: true, ALPHAOS_API_TOKEN: true, ALPHAOS_DEMO_MODE: true });
    assert(!JSON.stringify(health).includes(runtimeBindings.ALPHAOS_API_TOKEN));
    assert(!JSON.stringify(health).includes(runtimeBindings.ALPHAOS_API_URL));
    for (const [path, data] of [
      ["market", { symbol: "QQQ" }], ["market", { symbol: "SPY" }],
      ["structure", single.request], ["structures/compare", compared.request],
    ]) {
      const response = await post(mf, path, data);
      const body = await response.text();
      assert.equal(response.status, 200, body);
      assert.equal(response.headers.get("cache-control"), "no-store");
      assert(!body.includes(runtimeBindings.ALPHAOS_API_TOKEN));
    }
    assert.equal(calls, 4);
  } finally { await mf.dispose(); }
});

test("missing Worker bindings fail closed and demo mode cannot fabricate market data", async () => {
  const mf = await worker({ ALPHAOS_DEMO_MODE: "true" });
  try {
    const health = await (await mf.dispatchFetch("https://website.test/api/health")).json();
    assert.equal(health.research_configuration.configuration, "missing");
    assert.equal(health.research_configuration.demo_enabled, false);
    for (const [path, data] of [["market", { symbol: "QQQ" }], ["market", { symbol: "SPY" }], ["structure", single.request], ["structures/compare", compared.request]]) {
      const response = await post(mf, path, data);
      assert.equal(response.status, 503);
      assert.equal((await response.json()).code, "backend_not_configured");
    }
    const legacy = await mf.dispatchFetch("https://website.test/api/market?symbol=QQQ");
    assert.equal(legacy.status, 503);
    assert(!(await legacy.text()).includes("mock_fixture"));
  } finally { await mf.dispose(); }
});

test("configured Worker distinguishes authentication, backend failure, and bad data from missing bindings", async () => {
  let scenario = 401;
  const mf = await worker(runtimeBindings, () => scenario === 200 ? Response.json({ bad: true })
    : Response.json({ error: { code: scenario === 409 ? "archive_stale" : "internal_error" } }, { status: scenario }));
  try {
    for (const [status, code] of [[401, "backend_authentication_required"], [403, "backend_authentication_rejected"], [409, "archive_stale"], [503, "backend_internal_error"], [200, "response_schema_mismatch"]]) {
      scenario = status;
      const response = await post(mf, "market", { symbol: "QQQ" });
      assert.equal(response.status, 502);
      assert.equal((await response.json()).code, code);
    }
  } finally { await mf.dispose(); }
});

test("invalid runtime URL and either missing binding are configuration failures without outbound calls", async () => {
  for (const [overrides, code] of [
    [{ ALPHAOS_API_URL: "http://backend.example.test" }, "invalid_backend_configuration"],
    [{ ALPHAOS_API_URL: "" }, "backend_not_configured"],
    [{ ALPHAOS_API_TOKEN: "" }, "backend_not_configured"],
  ]) {
    const mf = await worker({ ...runtimeBindings, ...overrides });
    try {
      for (const [path, data] of [["market", { symbol: "QQQ" }], ["structure", single.request]]) {
        const response = await post(mf, path, data);
        assert.equal(response.status, 503);
        assert.equal((await response.json()).code, code);
      }
    } finally { await mf.dispose(); }
  }
});
