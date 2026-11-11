import { positive, timestamp } from "./evidence.ts";
import type { Candle, Evidence } from "./evidence.ts";
import type { HistoricalDataset } from "./history.ts";
import { aggregate, candleGaps } from "./proxy-history.ts";
export { runProxyBacktest } from "./proxy-history.ts";
export type { ProxyReplayConfig } from "./proxy-history.ts";

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
  const gaps = candleGaps(candles.m5, from, to, m.closedPeriods);

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
