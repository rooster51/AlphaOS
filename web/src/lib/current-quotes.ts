type Symbol = "SPY" | "QQQ";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

function timestamp(value: unknown): number {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
    ? Date.parse(value) : NaN;
}

function positive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

export function quoteAgeLimit(setting?: string): number {
  if (!setting?.trim()) return 15;
  const limit = Number(setting);
  return Number.isFinite(limit) && limit >= 1 && limit <= 15 ? limit : 15;
}

export function currentQuote(payload: unknown, symbol: Symbol, now: number, limit: number) {
  const evidence = record(record(payload).evidence);
  const q = record(evidence.quote);
  if (q.symbol !== symbol || q.provider_outcome !== "SUCCESS" ||
      !positive(q.last) || !positive(q.bid) || !positive(q.ask) || q.bid > q.ask ||
      record(evidence.cache).hit !== false) return null;
  const retrieved = timestamp(q.provider_retrieved_at);
  const times = [q.updated_at, q.bid_timestamp, q.ask_timestamp].map(timestamp);
  if (!Number.isFinite(retrieved) || retrieved > now ||
      times.some(value => !Number.isFinite(value) || value > retrieved)) return null;
  const oldest = Math.min(...times);
  const expiresAt = oldest + limit * 1000;
  if (now >= expiresAt) return null;
  return {
    symbol, last: q.last, bid: q.bid, ask: q.ask,
    lastAt: new Date(times[0]).toISOString(), bidAt: new Date(times[1]).toISOString(),
    askAt: new Date(times[2]).toISOString(), retrievedAt: new Date(retrieved).toISOString(),
    ageSeconds: (now - oldest) / 1000, expiresAt,
  };
}

export type CurrentQuote = NonNullable<ReturnType<typeof currentQuote>>;
