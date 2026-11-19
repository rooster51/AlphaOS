import type { CandleSymbol } from "./candles.ts";

export type Provenance = { provider: string; snapshot_id: string; retrieved_at: string; freshness: string };
export type Level = {
  low: number;
  high: number;
  types: string[];
  rank: number;
  observations: number;
  reactions: number;
  last_observed_at: string;
  evidence: { price: number; kind: string; source: string; observed_at: string; available_at: string }[];
  provenance: Provenance;
};
export type Scenario = {
  thesis: {
    id: string;
    session: string;
    direction: "bullish" | "bearish";
    family: string;
    thesis: string;
    confirmation: string;
    invalidation_condition: string;
    target_condition: string;
    expires_at: string;
    supporting: Level[];
    conflicting: string[];
    provenance: Provenance;
    quality: "Strong" | "Mixed";
    bias: string;
    structure: string;
  };
  updated_at: string;
  state: string;
  events: { state: string; bar_at: string | null; recorded_at: string; reason?: string }[];
};
export type Playbook = {
  version: "market-playbook-v1";
  symbol: CandleSymbol;
  session: string | null;
  provider: string;
  as_of: string | null;
  levels: Level[];
  vwap: { value: number; status: string } | null;
  provenance?: Provenance;
  status: string;
  reason: string;
  bias: string;
  structure: string;
  provisional_range: { low: number; high: number } | null;
  quality: string;
  history: Scenario[];
};

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

function strings(value: unknown): boolean {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function hasStrings(value: Record<string, unknown>, ...keys: string[]): boolean {
  return keys.every((key) => typeof value[key] === "string");
}

function provenance(input: unknown): boolean {
  return hasStrings(record(input), "provider", "snapshot_id", "retrieved_at", "freshness");
}

function level(input: unknown): boolean {
  const value = record(input);
  return [value.low, value.high, value.rank, value.observations, value.reactions].every(Number.isFinite)
    && strings(value.types) && hasStrings(value, "last_observed_at") && provenance(value.provenance)
    && Array.isArray(value.evidence) && value.evidence.every((item) => {
      const proof = record(item);
      return Number.isFinite(proof.price) && hasStrings(proof, "kind", "source", "observed_at", "available_at");
    });
}

function scenario(input: unknown): boolean {
  const value = record(input);
  const thesis = record(value.thesis);
  return hasStrings(value, "state", "updated_at")
    && hasStrings(thesis, "id", "session", "family", "thesis", "confirmation", "invalidation_condition",
      "target_condition", "expires_at", "quality", "bias", "structure")
    && (thesis.direction === "bullish" || thesis.direction === "bearish")
    && strings(thesis.conflicting) && provenance(thesis.provenance)
    && Array.isArray(thesis.supporting) && thesis.supporting.every(level)
    && Array.isArray(value.events) && value.events.every((item) => {
      const event = record(item);
      return hasStrings(event, "state", "recorded_at")
        && (event.bar_at === null || typeof event.bar_at === "string")
        && (event.reason === undefined || typeof event.reason === "string");
    });
}

export function parsePlaybook(input: unknown, symbol: CandleSymbol): Playbook | null {
  const value = record(input);
  const vwap = record(value.vwap);
  const opening = record(value.provisional_range);
  if (value.version !== "market-playbook-v1" || value.symbol !== symbol
    || !hasStrings(value, "provider", "status", "reason", "bias", "quality", "structure")
    || !(value.session === null || typeof value.session === "string")
    || !(value.as_of === null || typeof value.as_of === "string")
    || !(value.provenance === undefined || provenance(value.provenance))
    || !(value.vwap === null || (Number.isFinite(vwap.value) && hasStrings(vwap, "status")))
    || !(value.provisional_range === null || [opening.low, opening.high].every(Number.isFinite))
    || !Array.isArray(value.levels) || !value.levels.every(level)
    || !Array.isArray(value.history) || !value.history.every(scenario)) return null;
  return value as unknown as Playbook;
}
