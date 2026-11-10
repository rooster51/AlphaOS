/** Pivex evidence only. No ETF proxies, broker calls, or options-engine imports. */
export type Instrument = {
  id: string;
  name: string;
  assetClass: string;
  liveEnabled: boolean;
  missing: string[];
};
export const instruments: readonly Instrument[] = [
  {
    id: "NAS100",
    name: "Nasdaq 100 index",
    assetClass: "index",
    liveEnabled: false,
    missing: [
      "Broker symbol",
      "Contract specifications",
      "Market hours",
      "Costs",
      "Permission and licensed provider coverage",
    ],
  },
  {
    id: "XAUUSD",
    name: "Gold / US dollar",
    assetClass: "commodity",
    liveEnabled: false,
    missing: [
      "Broker symbol",
      "Contract specifications",
      "Market hours",
      "Costs",
      "Permission and licensed provider coverage",
    ],
  },
];
export type Candle = {
  openTime: string;
  closeTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  complete: boolean;
};
export type Evidence = {
  instrument: string;
  mode: "manual_historical" | "fixture";
  source: string;
  asOf: string;
  candles: { h1: Candle[]; m15: Candle[]; m5: Candle[] };
  target: { price: number; observedAt: string; reason: string };
  tickSize: number;
  bufferTicks: number;
};
/** A future authorized provider must return the same bounded, timestamped contract. */
export interface MarketDataAdapter {
  readonly id: string;
  load(instrument: string, asOf: string): Promise<Evidence>;
}
/** The only implemented adapter: caller-supplied historical research, never live. */
export class ManualHistoricalAdapter implements MarketDataAdapter {
  readonly id = "manual-historical-v1";
  private evidence: Evidence;
  constructor(value: unknown) {
    this.evidence = structuredClone(validateEvidence(value));
  }
  async load(instrument: string, asOf: string): Promise<Evidence> {
    if (
      instrument !== this.evidence.instrument ||
      Date.parse(asOf) !== Date.parse(this.evidence.asOf)
    )
      throw Error("Manual adapter instrument/as-of mismatch");
    return structuredClone(this.evidence);
  }
}
/** Chart integration seam. Freebuff's chart implementation is intentionally independent. */
export interface ChartEvidencePort {
  show(
    evidence: Evidence,
    levels: { stop: number; target: number; confirmationTime: string },
  ): void;
}
export const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);
export const positive = (v: unknown): v is number => finite(v) && v > 0;
export const timestamp = (v: unknown): v is string =>
  typeof v === "string" &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|\+00:00)$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 19) === v.slice(0, 19);
export function completedCandles(
  rows: Candle[],
  minutes: number,
  cutoff: number,
  minimum: number,
): Candle[] {
  if (!Array.isArray(rows) || rows.length > 10000)
    throw Error("Missing or excessive candles");
  if (rows.some((c) => !c || !timestamp(c.closeTime)))
    throw Error("Invalid candle timestamp");
  const selected = rows.filter(
    (c) => timestamp(c.closeTime) && Date.parse(c.closeTime) <= cutoff,
  );
  if (selected.length < minimum) throw Error("Missing completed candles");
  let previous = -Infinity;
  for (const c of selected) {
    const start = Date.parse(c.openTime),
      end = Date.parse(c.closeTime),
      duration = minutes * 60000;
    if (
      !timestamp(c.openTime) ||
      c.complete !== true ||
      end - start !== duration ||
      start % duration !== 0 ||
      ![c.open, c.high, c.low, c.close].every(positive) ||
      c.low > Math.min(c.open, c.close) ||
      c.high < Math.max(c.open, c.close) ||
      start < previous ||
      (previous !== -Infinity && start !== previous)
    )
      throw Error("Invalid, unfinished, unordered or missing candles");
    previous = end;
  }
  if (cutoff - previous >= minutes * 60000)
    throw Error("Stale or misaligned timeframe");
  return selected;
}
export function validateEvidence(value: unknown): Evidence {
  if (!value || typeof value !== "object")
    throw Error("Evidence must be an object");
  const e = value as Evidence;
  if (
    !instruments.some((i) => i.id === e.instrument) ||
    !["manual_historical", "fixture"].includes(e.mode) ||
    typeof e.source !== "string" ||
    !e.source.trim() ||
    !timestamp(e.asOf) ||
    !positive(e.tickSize) ||
    !Number.isSafeInteger(e.bufferTicks) ||
    e.bufferTicks < 1 ||
    !e.candles ||
    !e.target ||
    !positive(e.target.price) ||
    !timestamp(e.target.observedAt) ||
    Date.parse(e.target.observedAt) > Date.parse(e.asOf) ||
    typeof e.target.reason !== "string" ||
    !e.target.reason.trim()
  )
    throw Error("Invalid instrument, provenance, buffer or target evidence");
  return e;
}
