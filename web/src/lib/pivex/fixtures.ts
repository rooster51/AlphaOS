import type { Candle, Evidence } from "./evidence.ts";
/** Explicitly synthetic, opt-in fixtures. Never used for account or performance records. */
export function fixture(
  direction: "long" | "short" | "chop" = "long",
): Evidence {
  const candle = (
    at: string,
    minutes: number,
    open: number,
    close: number,
    low = Math.min(open, close) - 1,
    high = Math.max(open, close) + 1,
  ): Candle => ({
    openTime: at,
    closeTime: new Date(Date.parse(at) + minutes * 60000).toISOString(),
    open,
    close,
    low,
    high,
    complete: true,
  });
  const h1 = Array.from({ length: 24 }, (_, i) =>
    candle(
      new Date(Date.parse("2026-11-08T00:00:00Z") + i * 3600000).toISOString(),
      60,
      100 + i * 2,
      101 + i * 2,
    ),
  );
  Object.assign(h1.at(-1)!, { close: 150, low: 144, high: 152 });
  const m15 = [
    candle("2026-11-08T23:15:00Z", 15, 147, 148, 146, 149),
    candle("2026-11-08T23:30:00Z", 15, 148, 146, 144, 149),
    candle("2026-11-08T23:45:00Z", 15, 146, 150, 145, 151),
  ];
  const m5 = [
    candle("2026-11-09T00:00:00Z", 5, 150, 149, 147, 151),
    candle("2026-11-09T00:05:00Z", 5, 149, 151, 148, 152),
  ];
  const e: Evidence = {
    instrument: "NAS100",
    mode: "fixture",
    source: "SYNTHETIC v1 — arbitrary prices, not NAS100 market history",
    asOf: "2026-11-09T00:10:00Z",
    candles: { h1, m15, m5 },
    target: {
      price: 180,
      observedAt: "2026-11-08T23:00:00Z",
      reason: "Synthetic pre-existing resistance",
    },
    tickSize: 0.5,
    bufferTicks: 2,
  };
  if (direction === "short") {
    for (const rows of [h1, m15, m5])
      for (const c of rows) {
        const low = c.low;
        c.open = 300 - c.open;
        c.close = 300 - c.close;
        c.low = 300 - c.high;
        c.high = 300 - low;
      }
    e.target.price = 120;
    e.target.reason = "Synthetic pre-existing support";
  }
  if (direction === "chop")
    for (const c of h1.slice(0, -1)) {
      c.open = 140;
      c.close = 140;
      c.low = 139;
      c.high = 141;
    }
  return e;
}
