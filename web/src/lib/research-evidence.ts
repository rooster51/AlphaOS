export type ResearchEnvelope = { meta: Record<string, unknown>; evidence: Record<string, unknown> };

export type ResearchFailureCode =
  | "backend_not_configured"
  | "backend_auth_failed"
  | "backend_route_unavailable"
  | "backend_timeout"
  | "backend_unreachable"
  | "backend_schema_invalid"
  | "backend_http_error"
  | "backend_service_error"
  | "backend_gateway_timeout"
  | "backend_rejected_request"
  | "market_closed"
  | "market_stale"
  | "market_freshness_unknown"
  | "market_history_unavailable"
  | "market_data_unavailable"
  | "market_snapshot_expired"
  | "market_snapshot_mismatch"
  | "market_snapshot_unavailable"
  | "market_evidence_unavailable"
  | "provider_unavailable"
  | "provider_auth_failed"
  | "provider_not_configured"
  | "provider_timeout"
  | "provider_rate_limited"
  | "provider_contract_invalid";

export type ResearchStage =
  | "market"
  | "structure"
  | "market_validation"
  | "trade_intelligence";

const RESEARCH_SCHEMA = "alphaos-research-v1";

// Render's authenticated error contract uses stable codes. Only allowlisted
// values are retained so an upstream body can never become a free-text field.
const UPSTREAM_FAILURE_CODES: Record<string, ResearchFailureCode> = {
  market_closed_quote: "market_closed",
  stale_quote: "market_stale",
  quote_freshness_unknown: "market_freshness_unknown",
  insufficient_historical_data: "market_history_unavailable",
  market_data_unavailable: "market_data_unavailable",
  stale_snapshot: "market_snapshot_expired",
  snapshot_mismatch: "market_snapshot_mismatch",
  provider_unavailable: "provider_unavailable",
  public_authentication_failure: "provider_auth_failed",
  public_not_configured: "provider_not_configured",
  provider_timeout: "provider_timeout",
  public_rate_limit: "provider_rate_limited",
  provider_schema_error: "provider_contract_invalid",
  provider_symbol_mismatch: "provider_contract_invalid",
  missing_quote: "provider_unavailable",
  authentication_required: "backend_auth_failed",
  forbidden: "backend_auth_failed",
  not_found: "backend_route_unavailable",
  api_not_configured: "backend_not_configured",
  internal_error: "backend_service_error",
};

function fallbackFailureCode(status: number): ResearchFailureCode {
  if (status === 401 || status === 403) return "backend_auth_failed";
  if (status === 404 || status === 405) return "backend_route_unavailable";
  if (status === 408 || status === 504) return "backend_gateway_timeout";
  if (status === 429) return "provider_rate_limited";
  if (status === 409) return "market_snapshot_mismatch";
  if (status === 410) return "market_snapshot_expired";
  if (status >= 400 && status < 500) return "backend_rejected_request";
  if (status >= 500) return "backend_service_error";
  return "backend_http_error";
}

function upstreamFailure(status: number, body: unknown): {
  code: ResearchFailureCode;
  upstreamCode: string | null;
} {
  const error = object(body)?.error;
  const candidate = object(error)?.code;
  if (typeof candidate === "string" && Object.hasOwn(UPSTREAM_FAILURE_CODES, candidate)) {
    return { code: UPSTREAM_FAILURE_CODES[candidate], upstreamCode: candidate };
  }
  return { code: fallbackFailureCode(status), upstreamCode: null };
}

export class ResearchUnavailableError extends Error {
  readonly status: number | null;
  readonly code: ResearchFailureCode | null;
  readonly upstreamCode: string | null;
  readonly stage: ResearchStage | null;

  constructor(
    message: string,
    status: number | null = null,
    code: ResearchFailureCode | null = null,
    upstreamCode: string | null = null,
    stage: ResearchStage | null = null,
  ) {
    super(message);
    this.name = "ResearchUnavailableError";
    this.status = status;
    this.code = code;
    this.upstreamCode = upstreamCode;
    this.stage = stage;
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
  if (!token) {
    throw new ResearchUnavailableError(
      "Research backend not configured", null, "backend_not_configured",
    );
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await request(url, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        // A proxy/HTML error page has no stable code; the status fallback applies.
      }
      const failure = upstreamFailure(response.status, body);
      throw new ResearchUnavailableError(
        `Research API unavailable (HTTP ${response.status})`,
        response.status,
        failure.code,
        failure.upstreamCode,
      );
    }

    const text = await response.text();
    let body: unknown;
    try {
      body = JSON.parse(text);
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new ResearchUnavailableError(
          "Research response schema is unavailable", null, "backend_schema_invalid",
        );
      }
      throw error;
    }
    if (!validEnvelope(body)) {
      throw new ResearchUnavailableError(
        "Research response schema is unavailable", null, "backend_schema_invalid",
      );
    }
    return body;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ResearchUnavailableError(
        "Research API request timed out", null, "backend_timeout",
      );
    }
    if (error instanceof TypeError) {
      throw new ResearchUnavailableError(
        "Research API network request failed", null, "backend_unreachable",
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function latestSessionQuote(market: ResearchEnvelope, symbol: string): Record<string, unknown> | null {
  const underlying = object(market.evidence.underlying_quote);
  const quote = object(underlying?.quote) ?? underlying;
  if (!quote || quote.symbol !== symbol) return null;
  const last = quote.last;
  return typeof last === "number" && Number.isFinite(last) && last > 0 ? quote : null;
}

/**
 * The last verified regular-session observation is valid contextual evidence
 * after close, but it is never live or executable evidence. The backend marks
 * this explicitly as latest_available/closed; the bridge must not substitute it
 * for a fresh quote or promote it to current trading state.
 */
export function verifiedLatestSessionPair(market: unknown, structure: unknown, symbol: string): boolean {
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
  const observedAt = a.quote_as_of;
  const atr = structure.evidence.atr;
  return a.symbol === expectedSymbol && b.symbol === expectedSymbol && a.source === "Public"
    && a.snapshot_id !== null && typeof a.snapshot_id === "string"
    && a.snapshot_id.length > 0 && a.snapshot_id === b.snapshot_id
    && a.schema_version === b.schema_version
    && quality?.usable_for_live_research === false
    && quality.usable_for_contextual_research === true
    && quality.data_status === "latest_available"
    && quality.freshness === "latest_available"
    && quality.market_state === "closed"
    && (a.current_spot === null || a.current_spot === undefined)
    && latestSessionQuote(market, expectedSymbol) !== null
    && typeof atr === "number" && Number.isFinite(atr) && atr > 0
    && validTimestamp(observedAt) && validTimestamp(qualityTimestamp)
    && Date.parse(observedAt) === Date.parse(qualityTimestamp)
    && object(market.evidence.market_state) !== null;
}

/** Read the verified closing observation only after the pair passed validation. */
export function latestSessionSpot(market: unknown, symbol: string): number | null {
  if (!validEnvelope(market)) return null;
  let expectedSymbol: string;
  try {
    expectedSymbol = supportedMarketSymbol(symbol);
  } catch {
    return null;
  }
  const quote = latestSessionQuote(market, expectedSymbol);
  return quote && typeof quote.last === "number" ? quote.last : null;
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
