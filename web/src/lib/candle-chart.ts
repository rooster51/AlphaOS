/** Pure adapter from alphaos-candles-v1 to Lightweight Charts data. */
import type { CandlestickData, HistogramData, LineData, UTCTimestamp } from "lightweight-charts";
import type { CandleBar, CandleSnapshot } from "./candles.ts";

export const EMA_PERIODS = [9, 21, 50] as const;
export type EmaPeriod = (typeof EMA_PERIODS)[number];

export type CandleChartSeries = {
  snapshotId: string;
  candles: CandlestickData<UTCTimestamp>[];
  volume: HistogramData<UTCTimestamp>[];
  ema: Record<EmaPeriod, LineData<UTCTimestamp>[]>;
};

function seconds(value: string): UTCTimestamp {
  return Math.floor(Date.parse(value) / 1000) as UTCTimestamp;
}

/**
 * EMA values are derived only from the returned native closes. A value is not
 * emitted until a complete period has been observed; nothing is backfilled.
 */
export function emaValues(closes: number[], period: number): Array<{ timeIndex: number; value: number }> {
  if (!Number.isInteger(period) || period < 1 || closes.length < period) return [];
  if (!closes.every((value) => Number.isFinite(value) && value > 0)) return [];
  const alpha = 2 / (period + 1);
  const seed = closes.slice(0, period).reduce((total, value) => total + value, 0) / period;
  const values = [{ timeIndex: period - 1, value: seed }];
  let previous = seed;
  for (let index = period; index < closes.length; index += 1) {
    previous = closes[index] * alpha + previous * (1 - alpha);
    values.push({ timeIndex: index, value: previous });
  }
  return values;
}

/**
 * Keep the server snapshot ID with the series. Bars stay at their native
 * timestamps: a missing interval is a gap, never a synthesized row.
 */
export function toChartSeries(snapshot: CandleSnapshot): CandleChartSeries {
  const candles: CandlestickData<UTCTimestamp>[] = [];
  const volume: HistogramData<UTCTimestamp>[] = [];
  const bars: CandleBar[] = snapshot.candles;
  for (const bar of bars) {
    const time = seconds(bar.time);
    candles.push({ time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
    volume.push({
      time,
      value: bar.volume,
      color: bar.close >= bar.open ? "rgba(16, 185, 129, 0.55)" : "rgba(239, 68, 68, 0.55)",
    });
  }
  const closes = bars.map((bar) => bar.close);
  const ema = Object.fromEntries(
    EMA_PERIODS.map((period) => [
      period,
      emaValues(closes, period).map(({ timeIndex, value }) => ({ time: seconds(bars[timeIndex].time), value })),
    ]),
  ) as CandleChartSeries["ema"];
  return { snapshotId: snapshot.snapshot_id, candles, volume, ema };
}
