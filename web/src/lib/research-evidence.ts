export type ResearchEnvelope = { meta: Record<string, unknown>; evidence: Record<string, unknown> };
export function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}
export function validEnvelope(value: unknown): value is ResearchEnvelope {
  const body = object(value);
  return Boolean(body && !body.error && object(body.meta) && object(body.evidence)
    && typeof object(body.meta)?.schema_version === "string");
}
export function verifiedMarketPair(market: unknown, structure: unknown, symbol: string): boolean {
  if (!validEnvelope(market) || !validEnvelope(structure)) return false;
  const a = market.meta, b = structure.meta;
  const quality = object(a.quote_freshness);
  const spot = a.current_spot, atr = structure.evidence.atr;
  const observedAt = a.quote_as_of;
  return a.symbol === symbol && b.symbol === symbol && a.source === "Public"
    && a.snapshot_id !== null && typeof a.snapshot_id === "string"
    && a.snapshot_id.length > 0 && a.snapshot_id === b.snapshot_id
    && a.schema_version === b.schema_version
    && quality?.usable_for_live_research === true
    && typeof spot === "number" && Number.isFinite(spot) && spot > 0
    && typeof atr === "number" && Number.isFinite(atr) && atr > 0
    && typeof observedAt === "string" && Number.isFinite(Date.parse(observedAt))
    && object(market.evidence.market_state) !== null;
}
