import assert from "node:assert/strict";
import { test } from "node:test";
import { verifiedMarketPair, validEnvelope } from "../src/lib/research-evidence.ts";

const market = () => ({
  meta: {
    schema_version: "alphaos-research-v1",
    symbol: "QQQ", source: "Public", snapshot_id: "verified-1",
    quote_as_of: "2026-10-09T14:00:00Z", current_spot: 600,
    quote_freshness: { usable_for_live_research: true },
  },
  evidence: { market_state: { direction: "unknown" } },
});
const structure = () => ({
  meta: { schema_version: "alphaos-research-v1", symbol: "QQQ", snapshot_id: "verified-1" },
  evidence: { atr: 5 },
});
test("valid paired market/structure observations may display", () => {
  assert.equal(verifiedMarketPair(market(), structure(), "QQQ"), true);
});
test("missing or malformed API envelope fails closed", () => {
  assert.equal(validEnvelope({ meta: {}, evidence: {} }), false);
  assert.equal(verifiedMarketPair({ error: { code: "provider_unavailable" } }, structure(), "QQQ"), false);
});
test("stale or untrusted provider observations fail closed", () => {
  const a = market();
  a.meta.quote_freshness.usable_for_live_research = false;
  assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
});
test("snapshot mismatch and wrong symbol fail closed", () => {
  const b = structure(); b.meta.snapshot_id = "different";
  assert.equal(verifiedMarketPair(market(), b, "QQQ"), false);
  assert.equal(verifiedMarketPair(market(), structure(), "SPY"), false);
});
test("non-finite and missing prices fail closed", () => {
  const a = market(); a.meta.current_spot = Number.NaN;
  assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
  const b = structure(); b.evidence.atr = 0;
  assert.equal(verifiedMarketPair(market(), b, "QQQ"), false);
});
test("missing observation timestamp and market evidence fail closed", () => {
  const a = market(); a.meta.quote_as_of = "not-an-observation";
  assert.equal(verifiedMarketPair(a, structure(), "QQQ"), false);
  const b = market(); b.evidence.market_state = null;
  assert.equal(verifiedMarketPair(b, structure(), "QQQ"), false);
});
