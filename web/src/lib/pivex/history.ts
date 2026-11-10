import { finite, positive, timestamp, instruments } from "./evidence.ts";
import type { Candle, Evidence, MarketDataAdapter } from "./evidence.ts";
export type HistoricalDataset = {
  schema: 1;
  instrument: string;
  source: string;
  mode: "fixture" | "manual_historical";
  mapping: {
    providerSymbol: string;
    brokerSymbol: string;
    instrument: string;
    instrumentType: "pivex_cfd" | "synthetic";
    contractReference: string;
    attested: boolean;
    rightsReference: string;
    priceBasis: "bid" | "ask" | "mid" | "unspecified";
  };
  candles: Evidence["candles"];
  targets: Evidence["target"][];
  tickSize: number;
  bufferTicks: number;
  closedPeriods: { from: string; to: string; source: string }[];
};
export function validateDataset(value: unknown): HistoricalDataset {
  const d = value as HistoricalDataset;
  if (
    !d ||
    d.schema !== 1 ||
    !instruments.some((i) => i.id === d.instrument) ||
    !["fixture", "manual_historical"].includes(d.mode) ||
    typeof d.source !== "string" ||
    !d.source.trim() ||
    !d.mapping ||
    d.mapping.instrument !== d.instrument ||
    d.mapping.instrumentType !==
      (d.mode === "fixture" ? "synthetic" : "pivex_cfd") ||
    /^(QQQ|NQ|NQ=F|GC|GC=F)$/i.test(d.mapping.providerSymbol) ||
    d.mapping.attested !== true ||
    ![
      d.mapping.providerSymbol,
      d.mapping.brokerSymbol,
      d.mapping.contractReference,
      d.mapping.rightsReference,
    ].every((v) => typeof v === "string" && v.trim()) ||
    !["bid", "ask", "mid", "unspecified"].includes(d.mapping.priceBasis) ||
    !positive(d.tickSize) ||
    !Number.isSafeInteger(d.bufferTicks) ||
    d.bufferTicks < 1 ||
    !d.candles ||
    !Array.isArray(d.targets) ||
    d.targets.length > 10000 ||
    !Array.isArray(d.closedPeriods) ||
    d.closedPeriods.length > 10000
  )
    throw Error(
      "Historical import needs explicit instrument mapping, contract and usage-rights provenance",
    );
  for (const [key, minutes] of [
    ["h1", 60],
    ["m15", 15],
    ["m5", 5],
  ] as const) {
    const rows = d.candles[key];
    if (!Array.isArray(rows) || rows.length > 10000)
      throw Error(
        "Missing or excessive historical bars (10,000/timeframe maximum)",
      );
    let previous = -Infinity;
    for (const c of rows) {
      const start = Date.parse(c.openTime),
        end = Date.parse(c.closeTime);
      if (
        !timestamp(c.openTime) ||
        !timestamp(c.closeTime) ||
        c.complete !== true ||
        end - start !== minutes * 60000 ||
        start % (minutes * 60000) !== 0 ||
        start < previous ||
        ![c.open, c.high, c.low, c.close].every(positive) ||
        c.low > Math.min(c.open, c.close) ||
        c.high < Math.max(c.open, c.close) ||
        ![c.open, c.high, c.low, c.close].every(
          (p) => Math.abs(p / d.tickSize - Math.round(p / d.tickSize)) < 1e-6,
        )
      )
        throw Error(`Invalid, incomplete, unordered or off-tick ${key} bar`);
      previous = end;
    }
  }
  let previous = -Infinity;
  for (const t of d.targets) {
    if (
      !positive(t.price) ||
      !timestamp(t.observedAt) ||
      !t.reason?.trim() ||
      Date.parse(t.observedAt) < previous
    )
      throw Error(
        "Targets need chronological, pre-existing structure evidence",
      );
    previous = Date.parse(t.observedAt);
  }
  for (const p of d.closedPeriods)
    if (
      !timestamp(p.from) ||
      !timestamp(p.to) ||
      Date.parse(p.to) <= Date.parse(p.from) ||
      !p.source?.trim()
    )
      throw Error("Invalid sourced non-trading period");
  // A closure declaration cannot hide observed trading bars.
  for (const p of d.closedPeriods)
    if (
      d.candles.m5.some(
        (c) =>
          Date.parse(c.openTime) < Date.parse(p.to) &&
          Date.parse(c.closeTime) > Date.parse(p.from),
      )
    )
      throw Error("Non-trading period conflicts with observed bars");
  return d;
}
export function contiguousSuffix(rows: Candle[], cutoff: number): Candle[] {
  const selected = rows.filter((c) => Date.parse(c.closeTime) <= cutoff);
  let start = selected.length - 1;
  while (
    start > 0 &&
    Date.parse(selected[start].openTime) ===
      Date.parse(selected[start - 1].closeTime)
  )
    start--;
  return selected.slice(Math.max(0, start));
}
/** Authorized export adapter. No remote transport is enabled without credentials/rights. */
export class HistoricalExportAdapter implements MarketDataAdapter {
  readonly id = "authorized-historical-export-v1";
  private dataset: HistoricalDataset;
  constructor(value: unknown) {
    this.dataset = structuredClone(validateDataset(value));
  }
  evidenceAt(instrument: string, asOf: string): Evidence {
    const d = this.dataset;
    if (instrument !== d.instrument || !timestamp(asOf))
      throw Error("Historical adapter instrument/as-of mismatch");
    const asOfMs = Date.parse(asOf),
      m5 = contiguousSuffix(d.candles.m5, asOfMs),
      confirmation = m5.at(-1);
    if (!confirmation) throw Error("No completed entry candles");
    const cutoff = Date.parse(confirmation.openTime),
      target = d.targets
        .filter((t) => Date.parse(t.observedAt) <= cutoff)
        .at(-1);
    if (!target) throw Error("No pre-existing target evidence");
    return {
      instrument,
      mode: d.mode,
      source: d.source,
      asOf,
      candles: {
        h1: contiguousSuffix(d.candles.h1, cutoff),
        m15: contiguousSuffix(d.candles.m15, cutoff),
        m5,
      },
      target,
      tickSize: d.tickSize,
      bufferTicks: d.bufferTicks,
    };
  }
  async load(instrument: string, asOf: string): Promise<Evidence> {
    return this.evidenceAt(instrument, asOf);
  }
}
export function gapKind(d: HistoricalDataset, from: string, to: string) {
  return d.closedPeriods.some(
    (p) =>
      Date.parse(p.from) <= Date.parse(from) &&
      Date.parse(p.to) >= Date.parse(to),
  )
    ? "declared non-trading period"
    : "missing bars";
}
