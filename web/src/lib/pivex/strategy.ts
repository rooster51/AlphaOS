import { completedCandles, validateEvidence } from "./evidence.ts";
import type { Evidence } from "./evidence.ts";
export type Setup = {
  status: "CONFIRMED" | "NO SETUP" | "CHOP" | "UNAVAILABLE";
  reason: string;
  direction?: "long" | "short";
  entryReference?: number;
  stop?: number;
  target?: number;
  rewardRisk?: number;
  confirmationTime?: string;
  evidence?: Evidence;
  structuralTarget?: Evidence["target"];
  ema?: number;
};
/** v1: strict three-bar HT structure, two-bar pullback/reclaim, close-through breakout.
 * Seed EMA20 with the first 20 closes. As-of excludes future observations; HT/setup
 * evidence is frozen before the confirmation bar opens. No next-open fill is invented.
 */
export function analyze(
  input: unknown,
  historical?: {
    allowHourlyGap: (from: number, to: number) => boolean;
    hourlyEma: number;
    support: Evidence["target"];
  },
): Setup {
  try {
    const e = validateEvidence(input, Boolean(historical)),
      asOf = Date.parse(e.asOf);
    const m5 = completedCandles(e.candles.m5, 5, asOf, 2),
      confirm = m5.at(-1)!,
      prior = m5.at(-2)!;
    const cutoff = Date.parse(confirm.openTime);
    const h1 = completedCandles(
      e.candles.h1,
      60,
      cutoff,
      23,
      historical?.allowHourlyGap,
    );
    const m15 = completedCandles(e.candles.m15, 15, cutoff, 3);
    const closes = new Map<number, number>();
    for (const candle of [...h1, ...m15, ...m5]) {
      const at = Date.parse(candle.closeTime),
        other = closes.get(at);
      if (
        other !== undefined &&
        Math.abs(other - candle.close) > e.tickSize / 1000
      )
        throw Error("Conflicting cross-timeframe closing prices");
      closes.set(at, candle.close);
    }
    let ema = historical?.hourlyEma;
    if (ema === undefined) {
      ema = h1.slice(0, 20).reduce((s, c) => s + c.close, 0) / 20;
      for (const c of h1.slice(20)) ema = (c.close * 2) / 21 + (ema * 19) / 21;
    }
    const [a, b, c] = h1.slice(-3);
    const long =
      c.close > ema &&
      b.high > a.high &&
      c.high > b.high &&
      b.low > a.low &&
      c.low > b.low;
    const short =
      c.close < ema &&
      b.high < a.high &&
      c.high < b.high &&
      b.low < a.low &&
      c.low < b.low;
    if (!long && !short)
      return {
        status: "CHOP",
        reason: "EMA20 and completed hourly swing structure do not agree",
        ema,
      };
    const [structure, pullback, reclaim] = m15.slice(-3);
    const swingHigh = pullback.high,
      swingLow = pullback.low;
    const valid = long
      ? pullback.close < pullback.open &&
        pullback.low < structure.low &&
        reclaim.close > pullback.high &&
        reclaim.close > reclaim.open
      : pullback.close > pullback.open &&
        pullback.high > structure.high &&
        reclaim.close < pullback.low &&
        reclaim.close < reclaim.open;
    if (!valid)
      return {
        status: "NO SETUP",
        reason: "No confirmed 15-minute pullback reclaim/rejection",
        ema,
      };
    const broken = long
      ? prior.close <= swingHigh && confirm.close > swingHigh
      : prior.close >= swingLow && confirm.close < swingLow;
    if (!broken)
      return {
        status: "NO SETUP",
        reason: "No fresh completed 5-minute close through the pullback swing",
        ema,
      };
    const buffer = e.tickSize * e.bufferTicks;
    const stop = long
      ? Math.min(pullback.low, reclaim.low) - buffer
      : Math.max(pullback.high, reclaim.high) + buffer;
    const target = !long && historical ? historical.support : e.target;
    const entry = confirm.close,
      risk = Math.abs(entry - stop);
    const room = long ? target.price - entry : entry - target.price;
    if (room < 2 * risk || Date.parse(target.observedAt) > cutoff)
      return {
        status: "NO SETUP",
        reason: "No pre-existing defensible target with at least 2R of room",
        ema,
      };
    return {
      status: "CONFIRMED",
      direction: long ? "long" : "short",
      entryReference: entry,
      stop,
      target: entry + (long ? 1 : -1) * 2 * risk,
      rewardRisk: 2,
      confirmationTime: confirm.closeTime,
      ema,
      evidence: { ...e, target },
      reason: `Hypothetical next-candle entry only after ${confirm.closeTime}. Confirmation close is a sizing reference, not a fill. Stop buffer: ${e.bufferTicks} ticks × ${e.tickSize}. Recheck costs and 2R at the actual hypothetical entry.`,
    };
  } catch (err) {
    return {
      status: "UNAVAILABLE",
      reason: err instanceof Error ? err.message : "Invalid evidence",
    };
  }
}
