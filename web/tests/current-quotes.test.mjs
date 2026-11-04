import test from "node:test";
import assert from "node:assert/strict";
import { currentQuote, quoteAgeLimit, quoteHttpFailure } from "../src/lib/current-quotes.ts";

const now = Date.parse("2026-11-04T15:00:15Z");
const quote = {
  symbol: "SPY", provider_outcome: "SUCCESS", last: 600, bid: 599, ask: 601,
  updated_at: "2026-11-04T15:00:04Z", bid_timestamp: "2026-11-04T15:00:14Z",
  ask_timestamp: "2026-11-04T15:00:13Z", provider_retrieved_at: "2026-11-04T15:00:14Z",
};
const envelope = (q, hit = false) => ({ evidence: { quote: q, cache: { hit } } });

test("fresh quote uses oldest provider timestamp and preserves retrieval time", () => {
  const result = currentQuote(envelope(quote), "SPY", now, 15);
  assert.equal(result.status, "fresh");
  assert.equal(result.ageSeconds, 11);
  assert.equal(result.expiresAt, now + 4000);
  assert.equal(result.retrievedAt, "2026-11-04T15:00:14.000Z");
  assert.equal(currentQuote(envelope(quote), "SPY", now, 10).status, "unavailable");
});

test("unavailable reasons distinguish stale, missing, inconsistent, failed and crossed quotes", () => {
  for (const [change, reason] of [
    [{ updated_at: "2026-11-04T15:00:00Z" }, /freshness limit/],
    [{ ask_timestamp: undefined }, /timestamp missing/],
    [{ bid_timestamp: "2026-11-04T15:00:15Z" }, /out of order/],
    [{ provider_outcome: "UNKNOWN" }, /outcome/],
    [{ bid: 602 }, /bid exceeds ask/],
    [{ ask: null }, /price missing/],
  ]) {
    const result = currentQuote(envelope({ ...quote, ...change }), "SPY", now, 15);
    assert.equal(result.status, "unavailable");
    assert.match(result.reason, reason);
    assert.equal("bid" in result, false);
  }
  assert.match(currentQuote(envelope(quote, true), "SPY", now, 15).reason, /Uncached/);
  assert.equal(currentQuote(envelope(quote), "SPY", now, 15).status, "fresh");
  assert.match(currentQuote(envelope(quote), "QQQ", now, 15).reason, /Matching/);
});

test("HTTP failures distinguish backend auth from provider auth and redact raw text", () => {
  const payload = { error: { code: "public_authentication_failure", message: "PRIVATE" } };
  assert.match(quoteHttpFailure(503, payload).reason, /Public authorization/);
  assert.match(quoteHttpFailure(403, payload).reason, /backend authorization/);
  assert.doesNotMatch(JSON.stringify(quoteHttpFailure(503, { error: { code: "PRIVATE" } })), /PRIVATE/);
});

test("configuration can tighten the conservative default", () => {
  assert.equal(quoteAgeLimit(), 15);
  assert.equal(quoteAgeLimit("10"), 10);
  assert.equal(quoteAgeLimit("60"), 15);
});
