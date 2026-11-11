import { finite, positive, timestamp } from "./evidence.ts";
import type { Candle, Evidence } from "./evidence.ts";
import type { gapKind, HistoricalDataset } from "./history.ts";
import { replayWindow } from "./backtest.ts";
import { analyze } from "./strategy.ts";

const minute = 60_000;
const five = 5 * minute;
const hour = 60 * minute;
const iso = (at: number) => new Date(at).toISOString();
const onGrid = (value: number, step: number) =>
  Math.abs(value / step - Math.round(value / step)) < 1e-6;
const hasText = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

const symbols = {
  "XAU/USD": { instrument: "XAUUSD", instrumentType: "rolling_spot_metal" },
  "USATECH.IDX/USD": { instrument: "NAS100", instrumentType: "index_cfd" },
} as const;

type Manifest = {
  providerSymbol: keyof typeof symbols;
  sourceReference: string;
  rightsReference: string;
  exportReference: string;
  exportedAt: string;
  from: string;
  to: string;
  quoteDecimals: number;
  closedPeriods: HistoricalDataset["closedPeriods"];
};

type Tick = { at: string; bid: number; ask: number };
type PriceBasis = "bid" | "ask" | "mid";
const sides = ["bid", "ask", "mid"] as const;
type PriceBars = Record<PriceBasis, Candle>;
type Timeframes = Evidence["candles"];
type Gap = {
  from: string;
  to: string;
  kind: ReturnType<typeof gapKind>;
  slots: number;
};

function candle(start: number, duration: number, price: number): Candle {
  return {
    openTime: iso(start),
    closeTime: iso(start + duration),
    open: price,
    high: price,
    low: price,
    close: price,
    complete: true,
  };
}

function aggregate(rows: Candle[], duration: number): Candle[] {
  const result: Candle[] = [];
  const count = duration / five;
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

function validateManifest(m: Manifest) {
  if (
    !m ||
    !Object.hasOwn(symbols, m.providerSymbol) ||
    ![m.sourceReference, m.rightsReference, m.exportReference].every(hasText) ||
    ![m.from, m.to, m.exportedAt].every(timestamp) ||
    Date.parse(m.from) >= Date.parse(m.to) ||
    Date.parse(m.to) > Date.parse(m.exportedAt) ||
    Date.parse(m.to) - Date.parse(m.from) > 366 * 24 * hour ||
    [m.from, m.to].some((at) => Date.parse(at) % five !== 0) ||
    !Number.isInteger(m.quoteDecimals) ||
    m.quoteDecimals < 0 ||
    m.quoteDecimals > 6 ||
    !Array.isArray(m.closedPeriods)
  )
    throw Error(
      "Expected a supported Dukascopy export, UTC bounds, quote precision and source/rights references",
    );
  let previous = -Infinity;
  for (const p of m.closedPeriods) {
    if (
      !p ||
      !timestamp(p.from) ||
      !timestamp(p.to) ||
      !hasText(p.source) ||
      Date.parse(p.from) < previous ||
      Date.parse(p.from) >= Date.parse(p.to)
    )
      throw Error("Closures must be sourced, chronological and nonoverlapping");
    previous = Date.parse(p.to);
  }
}

export async function prepareDukascopyHistory(
  manifest: Manifest,
  ticks: AsyncIterable<Tick> | Iterable<Tick>,
  inputSha256: () => string,
) {
  const m = structuredClone(manifest);
  validateManifest(m);
  const from = Date.parse(m.from),
    to = Date.parse(m.to);
  const quoteStep = 10 ** -m.quoteDecimals;
  const tickSize = quoteStep / 2;
  const quoteBars: Record<PriceBasis, Timeframes> = {
    bid: { m5: [], m15: [], h1: [] },
    ask: { m5: [], m15: [], h1: [] },
    mid: { m5: [], m15: [], h1: [] },
  };
  let lastAt = -Infinity;
  let bucketStart = -Infinity;
  let bucket: PriceBars | undefined;
  let observedTicks = 0,
    duplicateQuoteUpdates = 0;
  let largestSpread = 0;
  let previousQuote: Tick | undefined;
  let closureIndex = 0;
  for await (const tick of ticks) {
    const at = Date.parse(tick.at);
    if (
      !timestamp(tick.at) ||
      at < from ||
      at >= to ||
      at < lastAt ||
      ![tick.bid, tick.ask].every(
        (price) => positive(price) && onGrid(price, quoteStep),
      ) ||
      tick.ask < tick.bid
    )
      throw Error(
        `Invalid or unordered tick at input observation ${observedTicks + duplicateQuoteUpdates + 1}`,
      );
    const duplicate =
      at === lastAt &&
      tick.bid === previousQuote?.bid &&
      tick.ask === previousQuote?.ask;
    lastAt = at;
    previousQuote = { ...tick };
    if (duplicate) {
      duplicateQuoteUpdates++;
      continue;
    }
    observedTicks++;
    largestSpread = Math.max(largestSpread, tick.ask - tick.bid);

    const start = Math.floor(at / five) * five;
    while (
      closureIndex < m.closedPeriods.length &&
      Date.parse(m.closedPeriods[closureIndex].to) <= start
    )
      closureIndex++;
    const closure = m.closedPeriods[closureIndex];
    if (closure && Date.parse(closure.from) < start + five)
      throw Error("Declared closure overlaps an observed five-minute bar");

    const prices = {
      bid: tick.bid,
      ask: tick.ask,
      mid: (tick.bid + tick.ask) / 2,
    };
    if (start !== bucketStart) {
      bucketStart = start;
      bucket = {
        bid: candle(start, five, prices.bid),
        ask: candle(start, five, prices.ask),
        mid: candle(start, five, prices.mid),
      };
      for (const side of sides) quoteBars[side].m5.push(bucket[side]);
    } else {
      for (const side of sides) {
        const bar = bucket![side],
          price = prices[side];
        bar.high = Math.max(bar.high, price);
        bar.low = Math.min(bar.low, price);
        bar.close = price;
      }
    }
  }
  if (!observedTicks) throw Error("The export contains no price observations");
  const sha256 = inputSha256();
  if (!/^[a-f0-9]{64}$/.test(sha256)) throw Error("Missing export SHA-256");
  for (const side of sides) {
    quoteBars[side].m15 = aggregate(quoteBars[side].m5, 15 * minute);
    quoteBars[side].h1 = aggregate(quoteBars[side].m5, hour);
  }
  const candles = quoteBars.mid;
  const gaps: Gap[] = [];
  let gapClosureIndex = 0;
  function addGap(start: number, end: number) {
    for (let at = start; at < end; at += five) {
      while (
        gapClosureIndex < m.closedPeriods.length &&
        Date.parse(m.closedPeriods[gapClosureIndex].to) <= at
      )
        gapClosureIndex++;
      const closure = m.closedPeriods[gapClosureIndex];
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
  for (const bar of candles.m5) {
    addGap(next, Date.parse(bar.openTime));
    next = Date.parse(bar.closeTime);
  }
  addGap(next, to);

  return {
    schema: 2 as const,
    mode: "external_proxy" as const,
    provider: "Dukascopy Bank SA",
    ...symbols[m.providerSymbol],
    providerSymbol: m.providerSymbol,
    sourceReference: m.sourceReference,
    exportReference: m.exportReference,
    rightsReference: m.rightsReference,
    exportedAt: m.exportedAt,
    from: m.from,
    to: m.to,
    quoteDecimals: m.quoteDecimals,
    closedPeriods: m.closedPeriods.map(({ from, to, source }) => ({
      from,
      to,
      source,
    })),
    inputSha256: sha256,
    candles,
    quoteBars,
    tickSize,
    quality: {
      observedTicks,
      duplicateQuoteUpdates,
      largestSpread,
      gaps,
      counts: {
        m5: candles.m5.length,
        m15: candles.m15.length,
        h1: candles.h1.length,
      },
    },
  };
}

type ProxyDataset = Awaited<ReturnType<typeof prepareDukascopyHistory>>;
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

export function runProxyBacktest(d: ProxyDataset, c: ProxyReplayConfig) {
  if (
    d.schema !== 2 ||
    d.mode !== "external_proxy" ||
    ![c.from, c.splitAt, c.to].every(
      (at) => timestamp(at) && Date.parse(at) % five === 0,
    ) ||
    Date.parse(c.from) < Date.parse(d.from) ||
    Date.parse(c.to) > Date.parse(d.to) ||
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
  const entrySpreads = new Map(
    m5.map((bar, i) => [
      bar.openTime,
      (d.quoteBars.ask.m5[i].open - d.quoteBars.bid.m5[i].open) / d.tickSize,
    ]),
  );
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
    entrySpreadTicks: (at: string) => entrySpreads.get(at)!,
    classifyGap(from: string, to: string): Gap["kind"] {
      const gap = gapAt(d.quality.gaps, Date.parse(from));
      return gap &&
        Date.parse(gap.from) <= Date.parse(from) &&
        Date.parse(gap.to) >= Date.parse(to)
        ? gap.kind
        : "missing bars";
    },
  };
  return {
    model: "pivex-replay-v1",
    kind: "hypothetical_backtest" as const,
    dataMode: d.mode,
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
      "Mid OHLC with next observed contiguous open. USD proxy units, larger of entry quote spread and configured spread floor, plus round-trip slippage and fees. Net 2R minimum, $25 planned cap, stop first on ambiguous bars, adverse reopen for stops, unresolved exposure on missing open-market bars. Reported trade lots are modeled units. Closed-trade equity excludes floating P&L.",
    development: replayWindow(
      d,
      execution,
      c.from,
      c.splitAt,
      "In-sample development",
      evaluate,
      proxy,
    ),
    validation: replayWindow(
      d,
      execution,
      c.splitAt,
      c.to,
      "Out-of-sample validation",
      evaluate,
      proxy,
    ),
  };
}
