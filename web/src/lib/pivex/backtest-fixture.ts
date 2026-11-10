import { fixture } from "./fixtures.ts";
import type { Candle } from "./evidence.ts";
import type { HistoricalDataset } from "./history.ts";
import type { BacktestConfig } from "./backtest.ts";
export function backtestFixture(direction: "long" | "short" = "long"): {
  dataset: HistoricalDataset;
  config: BacktestConfig;
} {
  const first = fixture(direction),
    second = fixture(direction),
    shift = (at: string) => new Date(Date.parse(at) + 86400000).toISOString();
  for (const rows of Object.values(second.candles))
    for (const bar of rows) {
      bar.openTime = shift(bar.openTime);
      bar.closeTime = shift(bar.closeTime);
    }
  second.target.observedAt = shift(second.target.observedAt);
  const entryBar = (day: string, win: boolean): Candle => ({
    openTime: `2026-11-${day}T00:10:00Z`,
    closeTime: `2026-11-${day}T00:15:00Z`,
    complete: true,
    ...(direction === "long"
      ? {
          open: 149,
          high: win ? 168 : 150,
          low: win ? 148 : 142,
          close: win ? 167 : 143,
        }
      : {
          open: 151,
          low: win ? 132 : 150,
          high: win ? 152 : 158,
          close: win ? 133 : 157,
        }),
  });
  const dataset: HistoricalDataset = {
    schema: 1,
    instrument: "NAS100",
    source:
      "SYNTHETIC replay fixture v1 — sparse arbitrary bars, no actual market history",
    mode: "fixture",
    mapping: {
      instrument: "NAS100",
      instrumentType: "synthetic",
      providerSymbol: "SYNTHETIC",
      brokerSymbol: "SYNTHETIC",
      contractReference: "Synthetic test contract only",
      attested: true,
      rightsReference: "Generated test fixture; no vendor data",
      priceBasis: "mid",
    },
    candles: {
      h1: [...first.candles.h1, ...second.candles.h1],
      m15: [...first.candles.m15, ...second.candles.m15],
      m5: [
        ...first.candles.m5,
        entryBar("09", true),
        ...second.candles.m5,
        entryBar("10", false),
      ],
    },
    targets: [first.target, second.target],
    tickSize: 0.5,
    bufferTicks: 2,
    closedPeriods: [],
  };
  return {
    dataset,
    config: {
      from: "2026-11-09T00:00:00Z",
      splitAt: "2026-11-09T12:00:00Z",
      to: "2026-11-10T00:15:00Z",
      startingEquity: 10000,
      lots: 1,
      riskBudget: 25,
      spec: {
        instrument: "NAS100",
        brokerSymbol: "SYNTHETIC",
        source: "Synthetic test assumptions",
        verifiedAt: "2026-11-08T00:00:00Z",
        attested: true,
        tickSize: 0.5,
        tickValue: 1,
        quoteToAccount: 1,
        minLot: 0.1,
        maxLot: 100,
        lotStep: 0.1,
        spreadTicks: 1,
        slippageTicks: 1,
        commissionPerLot: 1,
        fixedFees: 0,
        costsSource: "SYNTHETIC round-trip costs",
        marketHours: "Synthetic sparse test windows",
        permitted: true,
      },
    },
  };
}
