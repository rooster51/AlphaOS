import assert from "node:assert/strict";
import { test } from "node:test";
import {
  answerWorkspaceQuestion,
  buildWorkspaceAssessment,
  formatDistancePct,
  normalizeMarketResponse,
} from "../src/lib/workspace-evidence.ts";
import { tradingViewEmbedUrl, tradingViewSymbol } from "../src/lib/tradingview.ts";

function setup(overrides = {}) {
  return {
    id: "opening_range_breakout",
    name: "Opening-range breakout",
    state: "WAIT",
    direction: "unknown",
    evidence: ["Opening range high 504.75, low 498.20."],
    missing_conditions: ["A confirmed five-minute close above the opening-range high."],
    entry_trigger: {
      price: 504.75,
      condition: "Confirmed five-minute close above the opening-range high.",
    },
    invalidation: {
      price: 504.75,
      condition: "Five-minute close back below the opening-range high.",
    },
    stop_reference: { price: 498.2, basis: "Opening-range low" },
    target_reference: { price: 510.2, basis: "R2" },
    risk: {
      underlying_risk_distance: 6.55,
      risk_pct: 1.31,
      target_distance: 5.45,
      reward_to_risk: 0.83,
    },
    wait_reason: "No confirmed five-minute close has left the opening range.",
    timestamp: "2026-11-13T15:45:00+00:00",
    freshness: "verified",
    options: { strategy_families: [] },
    ...overrides,
  };
}

function tradeIntelligence(overrides = {}) {
  return {
    schema_version: "alphaos-trade-intelligence-v1",
    symbol: "QQQ",
    generated_at: "2026-11-13T15:45:00+00:00",
    source: "Public",
    session: {
      state: "open",
      date: "2026-11-13",
      open: "2026-11-13T14:30:00+00:00",
      close: "2026-11-13T21:00:00+00:00",
      as_of: "2026-11-13T15:45:00+00:00",
    },
    data: {
      status: "verified",
      freshness: "fresh",
      latest_confirmed_candle_at: "2026-11-13T15:45:00+00:00",
      confirmed_bars: 15,
      warnings: [],
      reasons: [],
    },
    levels: {
      previous_session: {
        date: "2026-11-12",
        open: 496.0,
        high: 505.0,
        low: 495.0,
        close: 503.0,
      },
      current_session: { high: 503.8, low: 497.4 },
      pivots: { pivot: 501.0, r1: 507.0, r2: 511.0, s1: 497.0, s2: 493.0 },
      opening_range: { high: 504.75, low: 498.2, status: "complete" },
      vwap: { price: 501.4, status: "available" },
      ema9: { price: 500.9, status: "available" },
      references: [
        { id: "prior_high", label: "Previous session high", price: 505.0, kind: "resistance", source: "previous_session_ohlc" },
        { id: "prior_low", label: "Previous session low", price: 495.0, kind: "support", source: "previous_session_ohlc" },
        { id: "pivot", label: "Pivot", price: 501.0, kind: "mid", source: "previous_session_ohlc" },
        { id: "r1", label: "R1", price: 507.0, kind: "resistance", source: "previous_session_ohlc" },
        { id: "s1", label: "S1", price: 497.0, kind: "support", source: "previous_session_ohlc" },
        { id: "or_high", label: "Opening range high", price: 504.75, kind: "resistance", source: "confirmed_opening_range" },
        { id: "or_low", label: "Opening range low", price: 498.2, kind: "support", source: "confirmed_opening_range" },
      ],
    },
    bias: { direction: "bullish", basis: "Descriptive alignment." },
    state: "WAIT",
    reason: "No setup has met its confirmed entry conditions.",
    active_setup_id: null,
    closest_setup_id: "opening_range_breakout",
    setups: [
      setup(),
      setup({
        id: "vwap_ema9_continuation",
        name: "VWAP + EMA 9 continuation",
        wait_reason: "The VWAP/EMA 9 alignment is mixed or contradictory.",
        entry_trigger: null,
        invalidation: null,
        stop_reference: null,
        target_reference: null,
        risk: null,
      }),
      setup({
        id: "support_resistance_reversal",
        name: "Support/resistance reversal",
        direction: "bullish",
        wait_reason: "Only one close has reclaimed support; follow-through is missing.",
        entry_trigger: { price: 498.2, condition: "Two consecutive confirmed closes above support." },
        invalidation: { price: 498.2, condition: "Five-minute close below support." },
        stop_reference: { price: 497.0, basis: "Test low with ATR buffer" },
        target_reference: { price: 505.0, basis: "Previous session high" },
      }),
    ],
    last_change: {
      previous_at: "2026-11-13T15:40:00+00:00",
      current_at: "2026-11-13T15:45:00+00:00",
      previous_close: 503.1,
      current_close: 503.8,
      change: 0.7,
      change_pct: 0.14,
    },
    exit_early: {
      state: "UNAVAILABLE",
      reason: "No modeled position was supplied.",
    },
    warnings: [],
    disclaimer: "Research state only.",
    ...overrides,
  };
}

function response(overrides = {}) {
  return {
    isLive: true,
    warning: "Live underlying observation only.",
    trade_intelligence: tradeIntelligence(),
    data: {
      symbol: "QQQ",
      current_spot: 500.25,
      as_of: "2026-11-13T15:45:00-05:00",
      source: "live_public",
      atr_14: 4.5,
      expected_move: 3.25,
      levels: [
        { label: "R1 (Upper 1-ATR)", price: 504.75, distance: 4.5, distance_pct: 0.9, kind: "atr" },
        { label: "R2 (Prior swing)", price: 503.1, distance: 2.85, distance_pct: 0.57, kind: "resistance" },
        { label: "S1 (EMA 9 support)", price: 498.2, distance: -2.05, distance_pct: -0.41, kind: "support" },
        { label: "S2 (Lower 1-ATR)", price: 495.75, distance: -4.5, distance_pct: -0.9, kind: "atr" },
      ],
      opportunity_state: {
        direction: "bullish",
        caveats: ["Direction is descriptive.", "No executable options quote is present."],
      },
      ...overrides,
    },
  };
}

test("distance percentages are formatted once with the correct sign and precision", () => {
  assert.equal(formatDistancePct(1.97), "+1.97% from spot");
  assert.equal(formatDistancePct(-1.97), "-1.97% from spot");
  assert.equal(formatDistancePct(0), "0.00% from spot");
  assert.equal(formatDistancePct(null), "Distance unavailable");
});

test("TradingView maps SPY and QQQ to their real listing exchanges", () => {
  assert.equal(tradingViewSymbol("SPY"), "AMEX:SPY");
  assert.equal(tradingViewSymbol("QQQ"), "NASDAQ:QQQ");
  assert.match(tradingViewEmbedUrl("QQQ"), /symbol=NASDAQ%3AQQQ/);
  assert.match(tradingViewEmbedUrl("SPY"), /symbol=AMEX%3ASPY/);
  assert.doesNotMatch(tradingViewEmbedUrl("QQQ"), /AMEX%3AQQQ/);
});

test("verified live and archive snapshots normalize without inventing fields", () => {
  const live = normalizeMarketResponse(response());
  assert.ok(live);
  assert.equal(live.symbol, "QQQ");
  assert.equal(live.spot, 500.25);
  assert.equal(live.isLive, true);
  assert.equal(live.source, "live_public");
  assert.equal(live.direction, "bullish");
  assert.equal(live.atr, 4.5);
  assert.equal(live.expectedMove, 3.25);
  assert.equal(live.levels.length, 4);
  assert.equal(live.levels[0].distancePct, 0.9);
  assert.equal(live.levels[2].kind, "support");
  assert.equal(live.tradeIntelligence?.state, "WAIT");
  assert.equal(live.tradeIntelligence?.setups.length, 3);
  assert.equal(live.tradeIntelligence?.pivots.pivot, 501);
  assert.equal(live.tradeIntelligence?.openingRange?.high, 504.75);
  assert.deepEqual(live.caveats, ["Direction is descriptive.", "No executable options quote is present."]);

  const archive = normalizeMarketResponse({
    ...response(),
    isLive: false,
    data: { ...response().data, source: "verified_archive", expected_move: null },
  });
  assert.ok(archive);
  assert.equal(archive.isLive, false);
  assert.equal(archive.source, "verified_archive");
  assert.equal(archive.expectedMove, null);
});

test("synthetic, inconsistent, or malformed responses fail closed", () => {
  assert.equal(normalizeMarketResponse({ ...response(), isLive: false }), null);
  assert.equal(normalizeMarketResponse({
    ...response(),
    data: { ...response().data, source: "mock_fixture" },
  }), null);
  assert.equal(normalizeMarketResponse(response({ current_spot: 0 })), null);
  assert.equal(normalizeMarketResponse(response({ atr_14: -1 })), null);
  assert.equal(normalizeMarketResponse(response({ as_of: "not-a-date" })), null);
  assert.equal(normalizeMarketResponse(response({ symbol: "IWM" })), null);
  assert.equal(normalizeMarketResponse(null), null);
});

test("invalid trade intelligence fails closed without discarding the verified market snapshot", () => {
  const malformed = response();
  malformed.trade_intelligence = {
    ...tradeIntelligence(),
    setups: [{ id: "only-one" }],
  };
  const snapshot = normalizeMarketResponse(malformed);
  assert.ok(snapshot);
  assert.equal(snapshot.tradeIntelligence, null);
  const assessment = buildWorkspaceAssessment(snapshot);
  assert.equal(assessment.stance, "WAIT");
  assert.match(assessment.reason, /versioned setup contract is unavailable/);
});

test("workspace assessment reports the validated WAIT and its missing setup condition", () => {
  const snapshot = normalizeMarketResponse(response());
  assert.ok(snapshot);
  const assessment = buildWorkspaceAssessment(snapshot);
  assert.equal(assessment.stance, "WAIT");
  assert.equal(assessment.biasLabel, "UP / bullish");
  assert.match(assessment.reason, /Closest setup/);
  assert.match(assessment.reason, /Opening-range breakout/);
  assert.equal(assessment.setups.length, 3);
  assert.equal(assessment.closestSetup?.id, "opening_range_breakout");
  assert.deepEqual(assessment.support.map((level) => level.price), [498.2, 497, 495]);
  assert.deepEqual(assessment.resistance.map((level) => level.price), [504.75, 505, 507]);
  assert.ok(assessment.evidenceGaps.includes("A confirmed five-minute close above the opening-range high."));
  assert.equal(assessment.exitEarly?.state, "UNAVAILABLE");

  const unavailable = buildWorkspaceAssessment(null);
  assert.equal(unavailable.stance, "UNAVAILABLE");
  assert.equal(unavailable.bias, "unknown");
  assert.match(unavailable.reason, /No BUY, SELL/);
});

test("a confirmed setup produces a BUY research state with entry and invalidation", () => {
  const confirmed = response();
  confirmed.trade_intelligence = tradeIntelligence({
    state: "BUY",
    active_setup_id: "opening_range_breakout",
    closest_setup_id: "opening_range_breakout",
    reason: "1 confirmed setup aligns with a bullish underlying state.",
    setups: [
      setup({
        state: "BUY",
        direction: "bullish",
        missing_conditions: [],
        wait_reason: null,
        evidence: [
          "Opening range high 504.75, low 498.20.",
          "First confirmed close above the range: 505.10.",
        ],
      }),
      setup({ id: "vwap_ema9_continuation", name: "VWAP + EMA 9 continuation" }),
      setup({ id: "support_resistance_reversal", name: "Support/resistance reversal" }),
    ],
  });
  const snapshot = normalizeMarketResponse(confirmed);
  assert.ok(snapshot);
  const assessment = buildWorkspaceAssessment(snapshot);
  assert.equal(assessment.stance, "BUY");
  assert.equal(assessment.bias, "bullish");
  assert.equal(assessment.closestSetup?.state, "BUY");
  assert.match(assessment.reason, /Opening-range breakout is confirmed as BUY/);
});

test("assistant answers setup, invalidation, WAIT, closest, and change questions from the contract", () => {
  const snapshot = normalizeMarketResponse(response());
  assert.ok(snapshot);

  const buy = answerWorkspaceQuestion(snapshot, "Is this a BUY?");
  assert.match(buy, /^WAIT\./);
  assert.match(buy, /Opening-range breakout/);
  assert.match(buy, /A confirmed five-minute close above the opening-range high/);

  const bullish = answerWorkspaceQuestion(snapshot, "What would confirm a bullish SPY entry?");
  assert.match(bullish, /Opening-range breakout/);
  assert.match(bullish, /Entry trigger/);

  const invalidation = answerWorkspaceQuestion(snapshot, "Where is the nearest invalidation?");
  assert.match(invalidation, /504\.75/);
  assert.match(invalidation, /Stop reference/);

  const why = answerWorkspaceQuestion(snapshot, "Why is AlphaOS saying WAIT?");
  assert.match(why, /^WAIT\./);
  assert.match(why, /Missing:/);
  assert.match(why, /Confirmed through/);

  const closest = answerWorkspaceQuestion(snapshot, "Which setup is closest?");
  assert.match(closest, /Opening-range breakout: WAIT/);
  assert.match(closest, /Reward-to-risk/);

  const changed = answerWorkspaceQuestion(snapshot, "What changed since the previous confirmed candle?");
  assert.match(changed, /503\.10/);
  assert.match(changed, /503\.80/);
  assert.match(changed, /\+0\.70/);

  const pivot = answerWorkspaceQuestion(snapshot, "Where is the pivot?");
  assert.match(pivot, /Pivot \$501\.00/);
  assert.match(pivot, /R1 \$507\.00/);

  const concept = answerWorkspaceQuestion(snapshot, "What is a pivot?");
  assert.match(concept, /^A traditional pivot point/);

  const price = answerWorkspaceQuestion(snapshot, "What is the price?");
  assert.match(price, /\$500\.25/);
  assert.match(price, /live_public/);
  assert.match(price, /not an executable options quote/);

  const missing = answerWorkspaceQuestion(null, "What is the price?");
  assert.match(missing, /verified market evidence is unavailable/i);

  const unknown = answerWorkspaceQuestion(snapshot, "Will it go up tomorrow?");
  assert.match(unknown, /cannot verify that question/);
  assert.match(unknown, /will not invent/);
});
