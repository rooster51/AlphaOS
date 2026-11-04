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

export type UnavailableCode = "request_timeout" | "backend_unreachable" | "provider_unavailable" |
  "authentication_failure" | "invalid_quote" | "missing_timestamp" | "stale_quote";

export function unavailable(code: UnavailableCode, reason: string, ageSeconds?: number) {
  return { status: "unavailable" as const, code, reason, ageSeconds };
}

export function quoteHttpFailure(status: number, payload: unknown) {
  if (status === 401 || status === 403) return unavailable("authentication_failure", "Preview backend authorization failed.");
  switch (record(record(payload).error).code) {
    case "public_not_configured": return unavailable("authentication_failure", "Public credentials are not configured on the backend.");
    case "public_authentication_failure": return unavailable("authentication_failure", "Public authorization failed.");
    case "public_rate_limit": return unavailable("provider_unavailable", "Public rate limit reached.");
    case "missing_quote": return unavailable("invalid_quote", "Public did not return a matching quote with a valid last price.");
    case "provider_schema_error": return unavailable("invalid_quote", "Public returned an invalid response.");
    case "provider_unavailable": return unavailable("provider_unavailable", "Public quote request failed.");
  }
  return unavailable(status === 429 ? "provider_unavailable" : "backend_unreachable", status === 429 ? "Quote request rate limited." : "Quote backend request failed.");
}

export function currentQuote(payload: unknown, symbol: Symbol, now: number, limit: number) {
  const evidence = record(record(payload).evidence);
  const q = record(evidence.quote);
  if (q.symbol !== symbol) return unavailable("invalid_quote", "Matching Public quote missing.");
  if (q.provider_outcome !== "SUCCESS") return unavailable("provider_unavailable", "Public quote outcome missing or unsuccessful.");
  if (q.last == null || q.bid == null || q.ask == null) return unavailable("invalid_quote", "Last, bid or ask price missing.");
  if (!positive(q.last) || !positive(q.bid) || !positive(q.ask) || q.bid > q.ask) {
    return unavailable("invalid_quote", "Last, bid or ask price invalid, or bid exceeds ask.");
  }
  if (record(evidence.cache).hit !== false) return unavailable("invalid_quote", "Uncached provider retrieval could not be verified.");
  const rawTimes = [q.updated_at, q.bid_timestamp, q.ask_timestamp];
  if (q.provider_retrieved_at == null || rawTimes.some(value => value == null)) {
    return unavailable("missing_timestamp", "Provider or retrieval timestamp missing.");
  }
  const retrieved = timestamp(q.provider_retrieved_at);
  const times = rawTimes.map(timestamp);
  if (!Number.isFinite(retrieved) || retrieved > now ||
      times.some(value => !Number.isFinite(value) || value > retrieved)) {
    return unavailable("invalid_quote", "Provider or retrieval timestamp invalid or out of order.");
  }
  const oldest = Math.min(...times);
  const expiresAt = oldest + limit * 1000;
  const ageSeconds = (now - oldest) / 1000;
  if (now >= expiresAt) return unavailable("stale_quote", "Provider quote exceeded the freshness limit.", ageSeconds);
  return {
    status: "fresh" as const, symbol, last: q.last, bid: q.bid, ask: q.ask,
    lastAt: new Date(times[0]).toISOString(), bidAt: new Date(times[1]).toISOString(),
    askAt: new Date(times[2]).toISOString(), retrievedAt: new Date(retrieved).toISOString(),
    ageSeconds, expiresAt,
  };
}

export type CurrentQuote = ReturnType<typeof currentQuote>;


export function retainVerifiedQuote(previous: CurrentQuote | null, response: CurrentQuote) {
  return response.status === "fresh" ? response : previous;
}
