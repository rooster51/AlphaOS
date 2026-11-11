/** Validate server evidence, never certify client-supplied quote values. */
import { record, type StructureRequestInput } from './structure-contract.ts';

export interface MarketDataView {
  kind: 'hypothetical' | 'verified_archive';
  snapshotId: string | null;
  sha256: string | null;
  evaluatedAt: string | null;
  provider: string | null;
  observedAt: string | null;
  archiveAge: number | null;
  legs: { contract: string; bid: number; ask: number; bidAt: string; askAt: string; age: number }[];
}

const finite = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const samePrice = (a: unknown, b: number) => finite(a) && Math.abs(a-b) <= 1e-8;
const instant = (x: unknown): x is string => typeof x === 'string' &&
  /(Z|[+-]\d{2}:\d{2})$/.test(x) && Number.isFinite(Date.parse(x));

export function marketDataView(value: unknown, submitted: StructureRequestInput): MarketDataView | null {
  const research = record(value);
  const data = record(record(research?.evidence)?.market_data);
  const reference = submitted.market_data;
  if (!reference) {
    if (data && (data.kind !== 'hypothetical' || data.verified !== false || data.verified_for_trading !== false)) return null;
    return { kind: 'hypothetical', snapshotId: null, sha256: null, evaluatedAt: null,
      provider:null, observedAt:null, archiveAge:null, legs: [] };
  }
  const snapshot = record(data?.snapshot);
  const freshness = record(data?.archive_freshness);
  const underlying = record(data?.underlying);
  if (!data || data.version !== 'structure-market-data-v1' || data.kind !== 'verified_archive' ||
      data.verified !== true || data.verified_for_trading !== false || data.pricing !== 'natural_bid_ask' ||
      snapshot?.id !== reference.snapshot_id || snapshot?.archive_sha256 !== reference.archive_sha256 ||
      snapshot?.symbol !== submitted.symbol || snapshot?.session_date !== submitted.as_of ||
      typeof snapshot?.provider !== 'string' || !instant(snapshot?.observed_at) ||
      !samePrice(data.signed_package_cashflow, submitted.credit) || data.fees !== submitted.fees ||
      !samePrice(underlying?.spot, submitted.spot) || !instant(data.evaluated_at) ||
      !instant(underlying?.timestamp) || !freshness || !finite(freshness.age_seconds) ||
      !finite(freshness.max_age_seconds) || freshness.age_seconds < 0 || freshness.age_seconds > freshness.max_age_seconds ||
      !Array.isArray(data.legs) || data.legs.length !== submitted.legs.length) return null;
  const evaluated = Date.parse(data.evaluated_at);
  const underlyingAge = (evaluated-Date.parse(underlying.timestamp))/1000;
  if (underlyingAge < 0 || underlyingAge > 900) return null;
  const legs: MarketDataView['legs'] = [];
  for (let i=0; i<submitted.legs.length; i++) {
    const expected = submitted.legs[i], row = record(data.legs[i]);
    const timing = record(row?.freshness);
    if (!row || row.contract !== expected.contract || row.type !== expected.type || row.strike !== expected.strike ||
        row.qty !== expected.qty || row.symbol !== submitted.symbol || row.expiration !== submitted.expiration ||
        row.snapshot_id !== reference.snapshot_id || !finite(row.bid) || !finite(row.ask) ||
        row.bid < 0 || row.ask <= 0 || row.bid > row.ask || !instant(row.bid_timestamp) || !instant(row.ask_timestamp) ||
        timing?.max_age_seconds !== 900 || timing.evaluated_at !== data.evaluated_at ||
        row.entry_side !== (expected.qty > 0 ? 'ask' : 'bid') ||
        row.entry_price !== (expected.qty > 0 ? row.ask : row.bid)) return null;
    const bidAge = (evaluated-Date.parse(row.bid_timestamp))/1000;
    const askAge = (evaluated-Date.parse(row.ask_timestamp))/1000;
    if (bidAge < 0 || askAge < 0 || bidAge > 900 || askAge > 900 ||
        !finite(timing.bid_age_seconds) || Math.abs(timing.bid_age_seconds-bidAge)>0.002 ||
        !finite(timing.ask_age_seconds) || Math.abs(timing.ask_age_seconds-askAge)>0.002) return null;
    // Canonical provenance and normalized payoff legs must describe the same quotes.
    for (const source of [record(research?.trade), record(research?.position)]) {
      const leg = record(Array.isArray(source?.legs) ? source.legs[i] : null);
      if (!leg || leg.contract !== row.contract || leg.strike !== row.strike || leg.type !== row.type || leg.qty !== row.qty ||
          leg.bid !== row.bid || leg.ask !== row.ask || leg.bid_timestamp !== row.bid_timestamp || leg.ask_timestamp !== row.ask_timestamp) return null;
    }
    legs.push({contract: row.contract as string, bid: row.bid, ask: row.ask,
      bidAt: row.bid_timestamp, askAt: row.ask_timestamp, age: Math.max(bidAge,askAge)});
  }
  return {kind:'verified_archive', snapshotId: reference.snapshot_id, sha256: reference.archive_sha256,
    evaluatedAt: data.evaluated_at, provider:snapshot.provider as string,
    observedAt:snapshot.observed_at as string, archiveAge:freshness.age_seconds, legs};
}
