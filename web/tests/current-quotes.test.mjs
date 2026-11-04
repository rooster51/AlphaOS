import test from "node:test";
import assert from "node:assert/strict";
import { currentQuote, quoteAgeLimit } from "../src/lib/current-quotes.ts";

const now = Date.parse("2026-11-04T15:00:15Z");
const quote = {
  symbol: "SPY", provider_outcome: "SUCCESS", last: 600, bid: 599, ask: 601,
  updated_at: "2026-11-04T15:00:04Z", bid_timestamp: "2026-11-04T15:00:14Z",
  ask_timestamp: "2026-11-04T15:00:13Z", provider_retrieved_at: "2026-11-04T15:00:14Z",
};
const envelope = (q, hit = false) => ({ evidence: { quote: q, cache: { hit } } });

test("fresh quote uses oldest provider timestamp and preserves retrieval time", () => {
  const result = currentQuote(envelope(quote), "SPY", now, 15);
  assert.equal(result.ageSeconds, 11);
  assert.equal(result.expiresAt, now + 4000);
  assert.equal(result.retrievedAt, "2026-11-04T15:00:14.000Z");
  assert.equal(currentQuote(envelope(quote), "SPY", now, 10), null);
});

test("stale, missing, inconsistent, failed and crossed quotes are unavailable", () => {
  for (const change of [
    { updated_at: "2026-11-04T15:00:00Z" }, { ask_timestamp: undefined },
    { bid_timestamp: "2026-11-04T15:00:15Z" }, { provider_outcome: "UNKNOWN" },
    { bid: 602 }, { ask: Infinity }, { provider_retrieved_at: undefined },
  ]) assert.equal(currentQuote(envelope({ ...quote, ...change }), "SPY", now, 15), null);
  assert.equal(currentQuote(envelope(quote, true), "SPY", now, 15), null);
  assert.equal(currentQuote({ error: "provider_unavailable" }, "QQQ", now, 15), null);
  assert.ok(currentQuote(envelope(quote), "SPY", now, 15));
  assert.equal(currentQuote(envelope(quote), "QQQ", now, 15), null);
});

test("configuration can tighten the conservative default", () => {
  assert.equal(quoteAgeLimit(), 15);
  assert.equal(quoteAgeLimit("10"), 10);
  assert.equal(quoteAgeLimit("60"), 15);
});
