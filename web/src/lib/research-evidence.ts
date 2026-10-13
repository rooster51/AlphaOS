export type ResearchEnvelope = { meta: Record<string, unknown>; evidence: Record<string, unknown> };

const RESEARCH_SCHEMA = "alphaos-research-v1";

export class ResearchUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ResearchUnavailableError";
  }
}

export function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

export function validEnvelope(value: unknown): value is ResearchEnvelope {
  const body = object(value);
  const meta = object(body?.meta);
  return Boolean(body && !("error" in body) && meta && object(body.evidence)
    && Array.isArray(body.caveats) && meta.schema_version === RESEARCH_SCHEMA);
}

function validTimestamp(value: unknown): value is string {
  return typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

export function supportedMarketSymbol(symbol: string): "QQQ" | "SPY" {
  const normalized = symbol.toUpperCase();
  if (normalized !== "QQQ" && normalized !== "SPY") {
    throw new Error("Unsupported market symbol");
  }
  return normalized;
}

export async function fetchResearchEnvelope(
  url: string,
  token: string,
  request: typeof fetch = fetch,
  timeoutMs = 10_000,
): Promise<ResearchEnvelope> {
  if (!token) throw new ResearchUnavailableError("Research backend not configured");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await request(url, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ResearchUnavailableError(`Research API unavailable (HTTP ${response.status})`);
    }

    const text = await response.text();
    let body: unknown;
    try {
      body = JSON.parse(text);
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new ResearchUnavailableError("Research response schema is unavailable");
      }
      throw error;
    }
    if (!validEnvelope(body)) {
      throw new ResearchUnavailableError("Research response schema is unavailable");
    }
    return body;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ResearchUnavailableError("Research API request timed out");
    }
    if (error instanceof TypeError) {
      throw new ResearchUnavailableError("Research API network request failed");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export function verifiedMarketPair(market: unknown, structure: unknown, symbol: string): boolean {
  if (!validEnvelope(market) || !validEnvelope(structure)) return false;
  let expectedSymbol: string;
  try {
    expectedSymbol = supportedMarketSymbol(symbol);
  } catch {
    return false;
  }
  const a = market.meta, b = structure.meta;
  const quality = object(a.quote_freshness);
  const qualityTimestamp = quality?.quote_as_of;
  const spot = a.current_spot, atr = structure.evidence.atr;
  const observedAt = a.quote_as_of;
  return a.symbol === expectedSymbol && b.symbol === expectedSymbol && a.source === "Public"
    && a.snapshot_id !== null && typeof a.snapshot_id === "string"
    && a.snapshot_id.length > 0 && a.snapshot_id === b.snapshot_id
    && a.schema_version === b.schema_version
    && quality?.usable_for_live_research === true
    && quality.data_status === "fresh" && quality.freshness === "fresh"
    && (quality.market_state === "regular_open" || quality.market_state === "extended_hours")
    && typeof spot === "number" && Number.isFinite(spot) && spot > 0
    && typeof atr === "number" && Number.isFinite(atr) && atr > 0
    && validTimestamp(observedAt) && validTimestamp(qualityTimestamp)
    && Date.parse(observedAt) === Date.parse(qualityTimestamp)
    && object(market.evidence.market_state) !== null;
}
