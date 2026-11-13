import assert from "node:assert/strict";
import { test } from "node:test";
import {
  answerWorkspaceQuestion,
  buildWorkspaceAssessment,
  normalizeMarketResponse,
} from "../src/lib/workspace-evidence.ts";
import { tradingViewEmbedUrl, tradingViewSymbol } from "../src/lib/tradingview.ts";

function response(overrides = {}) {
  return {
    isLive: true,
    warning: "Live underlying observation only.",
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

test("workspace assessment stays WAIT and reports the missing trade models", () => {
  const snapshot = normalizeMarketResponse(response());
  assert.ok(snapshot);
  const assessment = buildWorkspaceAssessment(snapshot);
  assert.equal(assessment.stance, "WAIT");
  assert.equal(assessment.biasLabel, "UP / bullish");
  assert.match(assessment.reason, /WAIT/);
  assert.deepEqual(assessment.support.map((level) => level.price), [498.2]);
  assert.deepEqual(assessment.resistance.map((level) => level.price), [503.1]);
  for (const gap of [
    "Pivot points",
    "Previous-day high and low",
    "Opening range",
    "Entry and invalidation model",
    "Stop-loss and target model",
    "Early-exit model",
  ]) {
    assert.ok(assessment.evidenceGaps.includes(gap), `expected gap ${gap}`);
  }

  const unavailable = buildWorkspaceAssessment(null);
  assert.equal(unavailable.stance, "UNAVAILABLE");
  assert.equal(unavailable.bias, "unknown");
  assert.match(unavailable.reason, /No BUY, SELL/);
});

test("assistant answers only from verified fields and refuses missing levels", () => {
  const snapshot = normalizeMarketResponse(response());
  assert.ok(snapshot);

  const buy = answerWorkspaceQuestion(snapshot, "Is this a BUY?");
  assert.match(buy, /^WAIT\./);
  assert.match(buy, /No verified entry, invalidation, stop-loss, target, or early-exit model/);
  assert.match(buy, /UP \/ bullish descriptive bias/);

  const support = answerWorkspaceQuestion(snapshot, "Where is support?");
  assert.match(support, /498\.20/);
  assert.match(support, /EMA 9 support/);
  assert.match(support, /backend structure levels/);

  const resistance = answerWorkspaceQuestion(snapshot, "Where is resistance?");
  assert.match(resistance, /503\.10/);

  const pivot = answerWorkspaceQuestion(snapshot, "Where is the pivot?");
  assert.match(pivot, /does not include a pivot-point series/);
  assert.match(pivot, /will not infer/);

  const concept = answerWorkspaceQuestion(snapshot, "What is a pivot?");
  assert.match(concept, /^A pivot point is/);

  const price = answerWorkspaceQuestion(snapshot, "What is the price?");
  assert.match(price, /\$500\.25/);
  assert.match(price, /live_public/);
  assert.match(price, /not an executable options quote/);

  const missing = answerWorkspaceQuestion(null, "What is the price?");
  assert.match(missing, /verified price is unavailable/i);

  const unknown = answerWorkspaceQuestion(snapshot, "Will it go up tomorrow?");
  assert.match(unknown, /cannot verify that question/);
  assert.match(unknown, /will not invent/);
});
