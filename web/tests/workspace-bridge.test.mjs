import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { getMarketSnapshotServer } from "../src/lib/alphaos-server.ts";
import { formatDistancePct, normalizeMarketResponse } from "../src/lib/workspace-evidence.ts";

const originalFetch = globalThis.fetch;
const originalUrl = process.env.ALPHAOS_API_URL;
const originalToken = process.env.ALPHAOS_API_TOKEN;

function envelope(symbol, evidence, meta = {}) {
  return {
    meta: { schema_version: "alphaos-research-v1", symbol, ...meta },
    evidence,
    caveats: [],
  };
}

function tradeEvidence(symbol = "SPY") {
  const setup = (id, name) => ({
    id, name, state: "WAIT", direction: "unknown",
    evidence: [], missing_conditions: ["A confirmed setup trigger."],
    entry_trigger: null, invalidation: null, stop_reference: null,
    target_reference: null, risk: null, wait_reason: "Waiting.",
    timestamp: "2026-11-13T15:45:00+00:00", freshness: "verified",
    options: { strategy_families: [] },
  });
  return {
    schema_version: "alphaos-trade-intelligence-v1",
    symbol,
    session: { state: "open", date: "2026-11-13" },
    data: {
      status: "verified", freshness: "fresh", confirmed_bars: 10,
      latest_confirmed_candle_at: "2026-11-13T15:45:00+00:00",
    },
    levels: {
      previous_session: { date: "2026-11-12", open: 496, high: 505, low: 495, close: 503 },
      pivots: { pivot: 501, r1: 507, r2: 511, s1: 497, s2: 493 },
      opening_range: { high: 504.75, low: 498.2, status: "complete" },
      vwap: { price: 501.4 }, ema9: { price: 500.9 },
      references: [{ id: "prior_high", label: "Previous session high", price: 505, kind: "resistance" }],
    },
    bias: { direction: "bullish" },
    state: "WAIT",
    reason: "No setup has met its confirmed entry conditions.",
    active_setup_id: null,
    closest_setup_id: "opening_range_breakout",
    setups: [
      setup("opening_range_breakout", "Opening-range breakout"),
      setup("vwap_ema9_continuation", "VWAP + EMA 9 continuation"),
      setup("support_resistance_reversal", "Support/resistance reversal"),
    ],
    last_change: null,
    exit_early: { state: "UNAVAILABLE", reason: "No modeled position was supplied." },
    warnings: [],
  };
}

function mockBackend({
  symbol = "SPY",
  spot = 505.1,
  level = 498.2,
  distancePct = -0.0137,
  tradeFailure = null,
  closed = false,
} = {}) {
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname === `/v1/market/${symbol}`) {
      return Response.json(envelope(symbol, {
        market_state: { direction: "bullish" },
        timing: {},
      }, {
        snapshot_id: "snapshot-1", source: "Public", current_spot: spot,
        quote_as_of: "2026-11-13T15:45:00+00:00",
        quote_freshness: {
          freshness: closed ? "latest_available" : "fresh",
          data_status: closed ? "latest_available" : "fresh",
          market_state: closed ? "closed" : "regular_open",
          usable_for_live_research: !closed,
          usable_for_contextual_research: true,
          quote_as_of: "2026-11-13T15:45:00+00:00",
        },
      }));
    }
    if (url.pathname === `/v1/structure/${symbol}`) {
      return Response.json(envelope(symbol, {
        atr: 4.5,
        levels: [{ side: "support", level, distance_pct: distancePct, sources: "20d_low" }],
      }, { snapshot_id: "snapshot-1", source: "Public" }));
    }
    if (url.pathname === `/v1/research/trade-intelligence/${symbol}`) {
      if (tradeFailure === "network") throw new TypeError("network down");
      if (tradeFailure === "throws") throw new Error("unexpected trade failure");
      if (tradeFailure === "not_deployed") {
        return Response.json({ error: { code: "not_found" } }, { status: 404 });
      }
      if (tradeFailure === "server_error") {
        return Response.json({ error: { code: "internal_error" } }, { status: 500 });
      }
      if (tradeFailure === "invalid_contract") {
        return Response.json(envelope(symbol, {
          schema_version: "alphaos-trade-intelligence-v0",
          symbol,
        }));
      }
      return Response.json(envelope(symbol, tradeEvidence(symbol)));
    }
    throw new Error(`Unexpected URL ${url}`);
  };
}

afterEach(() => {
  if (originalUrl === undefined) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = originalUrl;
  if (originalToken === undefined) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = originalToken;
  globalThis.fetch = originalFetch;
});

function configure() {
  process.env.ALPHAOS_API_URL = "https://api.example.test";
  process.env.ALPHAOS_API_TOKEN = "test-token";
}

test("the market bridge validates the trade contract and maps existing level/side structure rows", async () => {
  configure();
  mockBackend();
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.isLive, true);
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.data.levels[0].label, "support (20d_low)");
  assert.equal(result.data.levels[0].kind, "support");
  assert.equal(result.data.levels[0].price, 498.2);
  assert.ok(Math.abs(result.data.levels[0].distance_pct - -1.37) < 0.0001);
  assert.equal(result.trade_intelligence.schema_version, "alphaos-trade-intelligence-v1");
  assert.equal(result.trade_intelligence.setups.length, 3);
  assert.equal(result.trade_intelligence_status, "available");
  assert.equal(result.trade_intelligence_warning, undefined);
});

test("QQQ fraction distance is normalized once and formats as -1.97%, not -0.02%", async () => {
  configure();
  const spot = 674.46;
  const level = 661.14;
  mockBackend({
    symbol: "QQQ",
    spot,
    level,
    distancePct: (level - spot) / spot,
  });
  const result = await getMarketSnapshotServer("QQQ");
  assert.equal(result.data.symbol, "QQQ");
  assert.ok(Math.abs(result.data.levels[0].distance_pct - -1.97) < 0.01);

  const snapshot = normalizeMarketResponse({
    isLive: true,
    trade_intelligence: result.trade_intelligence,
    data: {
      ...result.data,
      opportunity_state: { direction: "bullish" },
    },
  });
  assert.ok(snapshot);
  assert.equal(formatDistancePct(snapshot.levels[0].distancePct), "-1.97% from spot");
});

test("a 404/405 trade route is diagnosed as a backend-version mismatch, not provider failure", async () => {
  configure();
  mockBackend({ tradeFailure: "not_deployed" });
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.trade_intelligence, null);
  assert.equal(result.trade_intelligence_status, "endpoint_not_deployed");
  assert.match(result.trade_intelligence_warning, /backend-version mismatch/);
  assert.match(result.trade_intelligence_warning, /not a market-data failure/);
});

test("a backend failure is distinguished from a missing deployment and preserves market evidence", async () => {
  configure();
  mockBackend({ tradeFailure: "server_error" });
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.trade_intelligence, null);
  assert.equal(result.trade_intelligence_status, "provider_unavailable");
  assert.match(result.trade_intelligence_warning, /HTTP 500/);
  assert.doesNotMatch(result.trade_intelligence_warning, /backend-version mismatch/);
});

test("an invalid contract is reported as a contract mismatch without discarding market evidence", async () => {
  configure();
  mockBackend({ tradeFailure: "invalid_contract" });
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.trade_intelligence, null);
  assert.equal(result.trade_intelligence_status, "contract_invalid");
  assert.match(result.trade_intelligence_warning, /contract\/version mismatch/);
});

test("a network failure is reported as provider unavailability", async () => {
  configure();
  mockBackend({ tradeFailure: "network" });
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.trade_intelligence, null);
  assert.equal(result.trade_intelligence_status, "provider_unavailable");
  assert.match(result.trade_intelligence_warning, /request failed/);
});

test("an unexpected optional trade exception cannot discard a valid market snapshot", async () => {
  configure();
  mockBackend({ tradeFailure: "throws" });
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.isLive, true);
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.data.levels.length, 1);
  assert.equal(result.trade_intelligence, null);
  assert.equal(result.trade_intelligence_status, "provider_unavailable");
  assert.match(result.trade_intelligence_warning, /failed unexpectedly/);
});

test("a closed market is diagnosed explicitly and fails independently of trade intelligence", async () => {
  configure();
  mockBackend({ closed: true });
  await assert.rejects(
    () => getMarketSnapshotServer("SPY"),
    (error) => {
      assert.equal(error.name, "ResearchUnavailableError");
      assert.equal(error.status, 503);
      assert.equal(error.code, "market_closed");
      return true;
    },
  );
});
