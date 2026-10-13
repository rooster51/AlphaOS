import assert from "node:assert/strict";
import { test } from "node:test";
import {
  fetchResearchEnvelope,
  supportedMarketSymbol,
  verifiedMarketPair,
  validEnvelope,
} from "../src/lib/research-evidence.ts";

const market = () => ({
  meta: {
    schema_version: "alphaos-research-v1",
    symbol: "QQQ", source: "Public", snapshot_id: "verified-1",
    quote_as_of: "2026-10-09T14:00:00Z", current_spot: 600,
    quote_freshness: {
      quote_as_of: "2026-10-09T14:00:00+00:00",
      data_status: "fresh", freshness: "fresh", market_state: "regular_open",
      usable_for_live_research: true,
    },
  },
  evidence: { market_state: { direction: "unknown" } },
  caveats: [],
});
const structure = () => ({
  meta: { schema_version: "alphaos-research-v1", symbol: "QQQ", snapshot_id: "verified-1" },
  evidence: { atr: 5 },
  caveats: [],
});
test("valid paired market/structure observations may display", () => {
  assert.equal(verifiedMarketPair(market(), structure(), "QQQ"), true);
});
test("missing or malformed API envelope fails closed", () => {
  assert.equal(validEnvelope({ meta: {}, evidence: {} }), false);
  assert.equal(validEnvelope({ meta: { schema_version: "unknown" }, evidence: {}, caveats: [] }), false);
  assert.equal(verifiedMarketPair({ error: { code: "provider_unavailable" } }, structure(), "QQQ"), false);
});
test("stale or untrusted provider observations fail closed", () => {
  const a = market();
  a.meta.quote_freshness.usable_for_live_research = false;
  assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
  for (const stale of ["stale", "latest_available", "unknown"]) {
    const b = market();
    b.meta.quote_freshness.data_status = stale;
    b.meta.quote_freshness.freshness = stale;
    assert.equal(verifiedMarketPair(b, structure(), "QQQ"), false);
  }
});
test("snapshot mismatch and wrong symbol fail closed", () => {
  const b = structure(); b.meta.snapshot_id = "different";
  assert.equal(verifiedMarketPair(market(), b, "QQQ"), false);
  assert.equal(verifiedMarketPair(market(), structure(), "SPY"), false);
});
test("unsupported or malformed symbols are rejected", () => {
  assert.equal(supportedMarketSymbol("spy"), "SPY");
  assert.throws(() => supportedMarketSymbol("QQQ/../SPY"), /Unsupported market symbol/);
  assert.equal(verifiedMarketPair(market(), structure(), "QQQ/../SPY"), false);
});
test("non-finite and missing prices fail closed", () => {
  const a = market(); a.meta.current_spot = Number.NaN;
  assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
  const b = structure(); b.evidence.atr = 0;
  assert.equal(verifiedMarketPair(market(), b, "QQQ"), false);
});
test("missing observation timestamp and market evidence fail closed", () => {
  for (const invalid of [null, "not-an-observation", "2026-10-09", "2026-10-09T14:00:00"]) {
    const a = market(); a.meta.quote_as_of = invalid;
    assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
  }
  const b = market(); b.evidence.market_state = null;
  assert.equal(verifiedMarketPair(b, structure(), "QQQ"), false);
});
test("timestamp provenance must match the freshness evaluator", () => {
  const a = market();
  a.meta.quote_freshness.quote_as_of = "2026-10-09T14:01:00Z";
  assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
});
test("valid backend responses use an authenticated, uncached server request", async () => {
  const url = "https://api.example.test/v1/market/QQQ";
  const result = await fetchResearchEnvelope(url, "test-token", async (requestUrl, options) => {
    assert.equal(requestUrl, url);
    assert.equal(options.headers.Authorization, "Bearer test-token");
    assert.equal(options.headers.Accept, "application/json");
    assert.equal(options.cache, "no-store");
    assert.equal(options.method, undefined);
    return Response.json(market());
  });
  assert.equal(validEnvelope(result), true);
});
test("backend authentication and upstream failures are surfaced without accepting error bodies", async () => {
  for (const status of [401, 403, 502, 503]) {
    await assert.rejects(
      fetchResearchEnvelope("https://api.example.test/v1/market/QQQ", "test-token",
        async () => new Response(JSON.stringify({ error: { code: "unavailable" } }), { status })),
      new RegExp(`HTTP ${status}`),
    );
  }
});
test("malformed, invalid JSON and unavailable backend responses fail closed", async () => {
  const url = "https://api.example.test/v1/market/QQQ";
  await assert.rejects(fetchResearchEnvelope(url, "test-token",
    async () => new Response("{", { status: 200 })), /schema is unavailable/);
  await assert.rejects(fetchResearchEnvelope(url, "test-token",
    async () => Response.json({ error: { code: "provider_unavailable" } })), /schema is unavailable/);
  await assert.rejects(fetchResearchEnvelope(url, "",
    async () => Response.json(market())), /not configured/);
});
test("backend request timeout and network failure are reported", async () => {
  const url = "https://api.example.test/v1/market/QQQ";
  const hangsUntilAborted = async (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
  await assert.rejects(fetchResearchEnvelope(url, "test-token", hangsUntilAborted, 5), /timed out/);
  await assert.rejects(fetchResearchEnvelope(url, "test-token",
    async () => { throw new TypeError("connection failed"); }), /network request failed/);
});
