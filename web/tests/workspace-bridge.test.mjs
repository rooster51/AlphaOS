import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { getMarketSnapshotServer } from "../src/lib/alphaos-server.ts";

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

function tradeEvidence() {
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
    symbol: "SPY",
    session: { state: "open", date: "2026-11-13" },
    data: { status: "verified", freshness: "fresh", confirmed_bars: 10 },
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

function mockBackend({ failTrade = false } = {}) {
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname === "/v1/market/SPY") {
      return Response.json(envelope("SPY", {
        market_state: { direction: "bullish" },
        timing: {},
      }, {
        snapshot_id: "snapshot-1", source: "Public", current_spot: 505.1,
        quote_as_of: "2026-11-13T15:45:00+00:00",
        quote_freshness: {
          freshness: "fresh", data_status: "fresh", market_state: "regular_open",
          usable_for_live_research: true, quote_as_of: "2026-11-13T15:45:00+00:00",
        },
      }));
    }
    if (url.pathname === "/v1/structure/SPY") {
      return Response.json(envelope("SPY", {
        atr: 4.5,
        levels: [{ side: "support", level: 498.2, distance_pct: -1.37, sources: "20d_low" }],
      }, { snapshot_id: "snapshot-1", source: "Public" }));
    }
    if (url.pathname === "/v1/research/trade-intelligence/SPY") {
      if (failTrade) throw new TypeError("network down");
      return Response.json(envelope("SPY", tradeEvidence()));
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
  assert.equal(result.trade_intelligence.schema_version, "alphaos-trade-intelligence-v1");
  assert.equal(result.trade_intelligence.setups.length, 3);
  assert.equal(result.trade_intelligence_warning, undefined);
});

test("a failed trade-intelligence request does not discard a valid market/structure snapshot", async () => {
  configure();
  mockBackend({ failTrade: true });
  const result = await getMarketSnapshotServer("SPY");
  assert.equal(result.data.current_spot, 505.1);
  assert.equal(result.trade_intelligence, null);
  assert.match(result.trade_intelligence_warning, /Verified setup evidence is unavailable/);
});
