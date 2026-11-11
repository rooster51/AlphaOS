import { finite, positive, timestamp } from "./evidence.ts";
import type { Candle, Evidence } from "./evidence.ts";
import type { gapKind, HistoricalDataset } from "./history.ts";
import { replayWindow } from "./backtest.ts";
import { analyze } from "./strategy.ts";

const five = 300_000;
const iso = (at: number) => new Date(at).toISOString();
const hasText = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

type Gap = {
  from: string;
  to: string;
  kind: ReturnType<typeof gapKind>;
  slots: number;
};

export function aggregate(
  rows: Candle[],
  duration: number,
  childDuration = five,
): Candle[] {
  const result: Candle[] = [];
  const count = duration / childDuration;
  for (let i = 0; i + count <= rows.length; i++) {
    const first = rows[i];
    const start = Date.parse(first.openTime);
    if (start % duration !== 0) continue;
    const last = rows[i + count - 1];
    if (Date.parse(last.closeTime) !== start + duration) continue;
    const children = rows.slice(i, i + count);
    result.push({
      ...first,
      closeTime: last.closeTime,
      close: last.close,
      high: Math.max(...children.map((row) => row.high)),
      low: Math.min(...children.map((row) => row.low)),
    });
  }
  return result;
}

export function candleGaps(
  bars: Candle[],
  from: number,
  to: number,
  closedPeriods: HistoricalDataset["closedPeriods"],
): Gap[] {
  const gaps: Gap[] = [];
  let gapClosureIndex = 0;
  function addGap(start: number, end: number) {
    for (let at = start; at < end; at += five) {
      while (
        gapClosureIndex < closedPeriods.length &&
        Date.parse(closedPeriods[gapClosureIndex].to) <= at
      )
        gapClosureIndex++;
      const closure = closedPeriods[gapClosureIndex];
      const closed =
        closure &&
        Date.parse(closure.from) <= at &&
        Date.parse(closure.to) >= at + five;
      const kind = closed ? "declared non-trading period" : "missing bars";
      const previous = gaps.at(-1);
      if (previous?.kind === kind && Date.parse(previous.to) === at) {
        previous.to = iso(at + five);
        previous.slots++;
      } else {
        gaps.push({ from: iso(at), to: iso(at + five), kind, slots: 1 });
      }
    }
  }
  let next = from;
  for (const bar of bars) {
    addGap(next, Date.parse(bar.openTime));
    next = Date.parse(bar.closeTime);
  }
  addGap(next, to);

  return gaps;
}

type ProxyDataset = {
  schema: 2 | 3;
  mode: "external_proxy";
  provider: string;
  instrument: string;
  instrumentType: string;
  providerSymbol: string;
  sourceReference: string;
  exportReference: string;
  rightsReference: string;
  exportedAt: string;
  inputSha256: string;
  from: string;
  to: string;
  closedPeriods: HistoricalDataset["closedPeriods"];
  candles: Evidence["candles"];
  tickSize: number;
  quality: { gaps: Gap[] };
} & (
  | { schema: 2; quoteBars: Record<"bid" | "ask", Evidence["candles"]> }
  | {
      schema: 3;
      sourceTimeframe: "M1";
      sourceTimezone: string;
      quoteBasis: "bid";
    }
);
export type ProxyReplayConfig = {
  from: string;
  splitAt: string;
  to: string;
  startingEquity: number;
  units: number;
  riskBudget: number;
  spreadFloor: number;
  roundTripSlippage: number;
  roundTripFees: number;
  costsReference: string;
};

function upperBound(
  length: number,
  cutoff: number,
  timeAt: (index: number) => number,
) {
  let low = 0,
    high = length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (timeAt(mid) <= cutoff) low = mid + 1;
    else high = mid;
  }
  return low;
}
const endIndex = (rows: Candle[], cutoff: number) =>
  upperBound(rows.length, cutoff, (i) => Date.parse(rows[i].closeTime));

const gapAt = (gaps: Gap[], start: number) =>
  gaps[upperBound(gaps.length, start, (i) => Date.parse(gaps[i].to))];

function prepareProxyReplay(
  d: ProxyDataset,
  c: ProxyReplayConfig,
  coverageEnd: string,
) {
  if (
    (d.schema !== 2 && d.schema !== 3) ||
    d.mode !== "external_proxy" ||
    ![c.from, c.splitAt, c.to].every(
      (at) => timestamp(at) && Date.parse(at) % five === 0,
    ) ||
    Date.parse(c.from) < Date.parse(d.from) ||
    Date.parse(coverageEnd) > Date.parse(d.to) ||
    Date.parse(c.from) >= Date.parse(c.splitAt) ||
    Date.parse(c.splitAt) >= Date.parse(c.to) ||
    ![
      c.units,
      c.startingEquity,
      c.riskBudget,
      c.spreadFloor,
      c.roundTripSlippage,
    ].every(positive) ||
    c.riskBudget > 25 ||
    !finite(c.roundTripFees) ||
    c.roundTripFees < 0 ||
    !hasText(c.costsReference)
  )
    throw Error(
      "Proxy replay requires aligned development/validation windows and explicit proxy costs and sizing",
    );

  const { h1, m15, m5 } = d.candles;
  const unknownGaps = d.quality.gaps.filter((g) => g.kind === "missing bars");
  const allowedHourlyGaps = new Map<number, number>();
  const trendStarts: number[] = [];
  const hourlyEma: number[] = [];
  let trendStart = 0,
    gapIndex = 0;
  let seed = 0,
    ema = 0;
  for (let i = 0; i < h1.length; i++) {
    if (i > 0) {
      const from = Date.parse(h1[i - 1].closeTime),
        to = Date.parse(h1[i].openTime);
      while (
        gapIndex < unknownGaps.length &&
        Date.parse(unknownGaps[gapIndex].to) <= from
      )
        gapIndex++;
      const gap = unknownGaps[gapIndex];
      if (gap && Date.parse(gap.from) < to) {
        trendStart = i;
        seed = 0;
      } else if (to > from) allowedHourlyGaps.set(from, to);
    }
    trendStarts.push(trendStart);
    const offset = i - trendStart;
    if (offset < 20) {
      seed += h1[i].close;
      ema = seed / (offset + 1);
    } else {
      ema = (h1[i].close * 2) / 21 + (ema * 19) / 21;
    }
    hourlyEma.push(ema);
  }
  const entrySpreads =
    d.schema === 2
      ? new Map(
          m5.map((bar, i) => [
            bar.openTime,
            (d.quoteBars.ask.m5[i].open - d.quoteBars.bid.m5[i].open) /
              d.tickSize,
          ]),
        )
      : null;
  const evaluate = (bar: Candle) => {
    const cutoff = Date.parse(bar.openTime);
    const end = endIndex(h1, cutoff);
    const trend = h1.slice(Math.max(trendStarts[end - 1] ?? 0, end - 120), end);
    const pullbackEnd = endIndex(m15, cutoff);
    const confirmationEnd = endIndex(m5, Date.parse(bar.closeTime));
    if (trend.length < 23)
      return {
        status: "UNAVAILABLE" as const,
        reason: "Missing completed hourly warm-up",
      };
    const gap = gapAt(unknownGaps, Date.parse(trend.at(-1)!.closeTime));
    if (gap && Date.parse(gap.from) < cutoff)
      return {
        status: "UNAVAILABLE" as const,
        reason: "Missing bars after last completed hourly observation",
      };
    const resistance = trend.reduce((best, row) =>
      row.high > best.high ? row : best,
    );
    const support = trend.reduce((best, row) =>
      row.low < best.low ? row : best,
    );
    return analyze(
      {
        instrument: d.instrument,
        mode: d.mode,
        source: d.provider,
        asOf: bar.closeTime,
        tickSize: d.tickSize,
        bufferTicks: 2,
        candles: {
          h1: trend.slice(-23),
          m15: m15.slice(Math.max(0, pullbackEnd - 3), pullbackEnd),
          m5: m5.slice(Math.max(0, confirmationEnd - 2), confirmationEnd),
        },
        target: {
          price: resistance.high,
          observedAt: resistance.closeTime,
          reason: "Prior completed hourly range high",
        },
      },
      {
        allowHourlyGap: (from, to) => allowedHourlyGaps.get(from) === to,
        hourlyEma: hourlyEma[end - 1],
        support: {
          price: support.low,
          observedAt: support.closeTime,
          reason: "Prior completed hourly range low",
        },
      },
    );
  };
  const execution = {
    startingEquity: c.startingEquity,
    lots: c.units,
    riskBudget: c.riskBudget,
    spec: {
      tickSize: d.tickSize,
      tickValue: d.tickSize,
      quoteToAccount: 1,
      spreadTicks: c.spreadFloor / d.tickSize,
      slippageTicks: c.roundTripSlippage / d.tickSize,
      commissionPerLot: 0,
      fixedFees: c.roundTripFees,
    },
  };
  const proxy = {
    entrySpreadTicks: (at: string) => entrySpreads?.get(at) ?? 0,
    classifyGap(from: string, to: string): Gap["kind"] {
      const gap = gapAt(d.quality.gaps, Date.parse(from));
      return gap &&
        Date.parse(gap.from) <= Date.parse(from) &&
        Date.parse(gap.to) >= Date.parse(to)
        ? gap.kind
        : "missing bars";
    },
  };
  const replay = (from: string, to: string, label: string) =>
    replayWindow(d, execution, from, to, label, evaluate, proxy);
  return {
    replay,
    model: "pivex-replay-v1",
    kind: "hypothetical_backtest" as const,
    dataMode: d.mode,
    observationType: d.schema === 3 ? "bid_candles" : "paired_ticks",
    instrument: d.instrument,
    provider: d.provider,
    providerSymbol: d.providerSymbol,
    instrumentType: d.instrumentType,
    provenance: {
      sourceReference: d.sourceReference,
      exportReference: d.exportReference,
      exportedAt: d.exportedAt,
      rightsReference: d.rightsReference,
      inputSha256: d.inputSha256,
      closedPeriods: d.closedPeriods,
      ...(d.schema === 3
        ? {
            sourceTimeframe: d.sourceTimeframe,
            sourceTimezone: d.sourceTimezone,
            quoteBasis: d.quoteBasis,
          }
        : {}),
    },
    coverage: { from: d.from, to: d.to, ...d.quality },
    config: {
      from: c.from,
      splitAt: c.splitAt,
      to: c.to,
      startingEquity: c.startingEquity,
      units: c.units,
      riskBudget: c.riskBudget,
      spreadFloor: c.spreadFloor,
      roundTripSlippage: c.roundTripSlippage,
      roundTripFees: c.roundTripFees,
      costsReference: c.costsReference,
    },
    executionModel:
      d.schema === 3
        ? "Bid OHLC proxy with next contiguous bid open. Fixed modeled round-trip spread, slippage and fees; net 2R minimum and $25 planned cap. Stops take priority on ambiguous bars, adverse observed opens apply to gap stops, and missing open-market bars leave exposure unresolved. No observed ask, midpoint, or intrabar sequence."
        : "Mid OHLC with next observed contiguous open. USD proxy units, larger of entry quote spread and configured spread floor, plus round-trip slippage and fees. Net 2R minimum, $25 planned cap, stop first on ambiguous bars, adverse reopen for stops, unresolved exposure on missing open-market bars. Reported trade lots are modeled units. Closed-trade equity excludes floating P&L.",
  };
}

export function runProxyDevelopment(d: ProxyDataset, c: ProxyReplayConfig) {
  const { replay, ...report } = prepareProxyReplay(d, c, c.splitAt);
  return {
    ...report,
    development: replay(c.from, c.splitAt, "In-sample development"),
  };
}

export function runProxyBacktest(d: ProxyDataset, c: ProxyReplayConfig) {
  const { replay, ...report } = prepareProxyReplay(d, c, c.to);
  return {
    ...report,
    development: replay(c.from, c.splitAt, "In-sample development"),
    validation: replay(c.splitAt, c.to, "Out-of-sample validation"),
  };
}
