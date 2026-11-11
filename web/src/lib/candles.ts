/** Typed client and hard boundary for the alphaos-candles-v1 response. */
export const CANDLE_SYMBOLS = ["SPY", "QQQ"] as const;
export const CANDLE_INTERVALS = ["1m", "5m", "15m"] as const;
export const CANDLE_LIMIT = 390;
export const CANDLE_REFRESH_MS = 20_000;
export const CANDLE_TIMEOUT_MS = 15_000;

export type CandleSymbol = (typeof CANDLE_SYMBOLS)[number];
export type CandleInterval = (typeof CANDLE_INTERVALS)[number];
export type CandleCompleteness = "complete" | "incomplete" | "unknown";
export type LastBarStatus = "complete" | "partial" | "unknown";
export type CandleFreshness = "fresh" | "stale" | "latest_available" | "unknown";

export type CandleBar = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CandleEntitlement = {
  provider: string;
  use_context: string;
  allowed: boolean;
  code: string;
  reason: string;
  basis: string;
  policy_version: string;
  authorization_required: boolean;
  authorization_reference_present: boolean;
};

export type CandleSnapshot = {
  schema_version: "alphaos-candles-v1";
  symbol: CandleSymbol;
  interval: CandleInterval;
  provider: string;
  session: "regular";
  retrieved_at: string;
  latest_candle_at: string;
  snapshot_id: string;
  expected_bars: number | null;
  received_bars: number;
  returned_bars: number;
  completeness: CandleCompleteness;
  last_bar_status: LastBarStatus;
  freshness: CandleFreshness;
  warnings: string[];
  candles: CandleBar[];
  provider_capabilities: Record<string, unknown>;
  entitlement: CandleEntitlement;
};

export type CandleClientCode =
  | "authentication_required"
  | "data_use_denied"
  | "invalid_request"
  | "provider_rate_limited"
  | "provider_unavailable"
  | "provider_timeout"
  | "provider_schema_error"
  | "feature_disabled"
  | "backend_unreachable"
  | "request_timeout"
  | "cancelled"
  | "response_schema_mismatch";

export type CandleClientError = {
  code: CandleClientCode;
  message: string;
  retryAfterSeconds?: number;
};

export type CandleClientResult =
  | { ok: true; snapshot: CandleSnapshot }
  | { ok: false; error: CandleClientError };

export type CandleQuote =
  | {
      status: "fresh";
      symbol: CandleSymbol;
      last: number;
      bid: number;
      ask: number;
      lastAt: string;
      retrievedAt: string;
      ageSeconds: number;
    }
  | {
      status: "unavailable";
      code: string;
      reason: string;
      ageSeconds?: number;
    };

export const CANDLE_WARNING_LABELS: Record<string, string> = {
  missing_bars: "Missing bars",
  incomplete_session: "Incomplete session",
  provider_incomplete_bars_skipped: "Provider skipped incomplete bars",
  session_in_progress: "Session in progress",
  last_bar_completion_unverified: "Last bar completion unverified",
  last_bar_window_open: "Last-bar window open",
  stale_candles: "Stale candles",
  latest_available_session: "Latest available session",
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function integer(value: unknown, minimum = 0): value is number {
  return Number.isInteger(value) && (value as number) >= minimum;
}

function timestamp(value: unknown): value is string {
  return typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function boundedString(value: unknown, max = 128): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max;
}

function validBar(value: unknown): value is CandleBar {
  const bar = record(value);
  if (!bar || !timestamp(bar.time) ||
      !finite(bar.open) || !finite(bar.high) || !finite(bar.low) ||
      !finite(bar.close) || !finite(bar.volume)) return false;
  if (bar.open <= 0 || bar.high <= 0 || bar.low <= 0 || bar.close <= 0 || bar.volume < 0) return false;
  return bar.high >= Math.max(bar.open, bar.close, bar.low)
    && bar.low <= Math.min(bar.open, bar.close, bar.high);
}

/**
 * Validate the exact server contract before any value reaches the renderer.
 * Gaps are retained as timestamp gaps; no bar is inserted or repaired.
 */
export function parseCandleSnapshot(
  value: unknown,
  expected: { symbol: CandleSymbol; interval: CandleInterval },
): CandleSnapshot | null {
  const body = record(value);
  const capabilities = record(body?.provider_capabilities);
  const entitlement = record(body?.entitlement);
  if (!body || !capabilities || !entitlement) return null;
  if (body.schema_version !== "alphaos-candles-v1" ||
      body.symbol !== expected.symbol || body.interval !== expected.interval ||
      !boundedString(body.provider) || body.session !== "regular" ||
      !timestamp(body.retrieved_at) || !timestamp(body.latest_candle_at) ||
      !boundedString(body.snapshot_id) || !/^[A-Za-z0-9_-]{16,128}$/.test(body.snapshot_id) ||
      !(body.expected_bars === null || integer(body.expected_bars)) ||
      !integer(body.received_bars) || !integer(body.returned_bars) ||
      !["complete", "incomplete", "unknown"].includes(String(body.completeness)) ||
      !["complete", "partial", "unknown"].includes(String(body.last_bar_status)) ||
      !["fresh", "stale", "latest_available", "unknown"].includes(String(body.freshness)) ||
      !Array.isArray(body.warnings) || body.warnings.length > 32 ||
      !body.warnings.every((warning) => boundedString(warning, 80)) ||
      !Array.isArray(body.candles) || body.candles.length > CANDLE_LIMIT ||
      body.returned_bars !== body.candles.length ||
      body.received_bars < body.returned_bars) return null;
  if (Date.parse(body.retrieved_at) < Date.parse(body.latest_candle_at)) return null;
  if (!capabilities.native_candles || !Array.isArray(capabilities.symbols) ||
      !capabilities.symbols.includes(expected.symbol) || !Array.isArray(capabilities.intervals) ||
      !capabilities.intervals.includes(expected.interval) || !Array.isArray(capabilities.sessions) ||
      !capabilities.sessions.includes("regular")) return null;
  if (entitlement.allowed !== true || !boundedString(entitlement.provider) ||
      entitlement.provider !== body.provider) return null;
  if (!body.candles.every(validBar)) return null;
  const candles = body.candles as CandleBar[];
  for (let index = 1; index < candles.length; index += 1) {
    if (Date.parse(candles[index].time) <= Date.parse(candles[index - 1].time)) return null;
  }
  if (candles.length > 0 && Date.parse(candles.at(-1)!.time) !== Date.parse(body.latest_candle_at)) return null;
  return {
    schema_version: "alphaos-candles-v1",
    symbol: expected.symbol,
    interval: expected.interval,
    provider: body.provider,
    session: "regular",
    retrieved_at: body.retrieved_at,
    latest_candle_at: body.latest_candle_at,
    snapshot_id: body.snapshot_id,
    expected_bars: body.expected_bars as number | null,
    received_bars: body.received_bars,
    returned_bars: body.returned_bars,
    completeness: body.completeness as CandleCompleteness,
    last_bar_status: body.last_bar_status as LastBarStatus,
    freshness: body.freshness as CandleFreshness,
    warnings: [...body.warnings] as string[],
    candles,
    provider_capabilities: capabilities,
    entitlement: entitlement as CandleEntitlement,
  };
}

function retryAfter(response: Response): number | undefined {
  const value = Number(response.headers.get("Retry-After"));
  return Number.isFinite(value) && value > 0 && value <= 900 ? Math.ceil(value) : undefined;
}

function httpError(status: number, body: Record<string, unknown>, response: Response): CandleClientError {
  const code = typeof body.code === "string" ? body.code : "";
  const retryAfterSeconds = retryAfter(response);
  if (status === 401 || code === "authentication_required") {
    return { code: "authentication_required", message: "Sign in again to view authenticated candles." };
  }
  if (status === 503 && code === "feature_disabled") {
    return { code: "feature_disabled", message: "Candle display is disabled pending provider authorization." };
  }
  if (status === 403 || code === "data_use_denied") {
    return { code: "data_use_denied", message: "This account is not entitled to display this provider's candles." };
  }
  if (status === 429 || code === "provider_rate_limited") {
    return {
      code: "provider_rate_limited",
      message: "The market-data provider is rate limiting requests.",
      ...(retryAfterSeconds ? { retryAfterSeconds } : {}),
    };
  }
  if (status === 504 || code === "provider_timeout") {
    return { code: "provider_timeout", message: "The market-data provider did not respond before the deadline." };
  }
  if (code === "public_not_configured" || code === "provider_unavailable" ||
      code === "no_candles" || code === "invalid_provider_response") {
    return { code: "provider_unavailable", message: "Native candles are unavailable from the provider." };
  }
  if (code === "invalid_request" || code === "unsupported_symbol") {
    return { code: "invalid_request", message: "The candle request is not supported." };
  }
  if (status >= 500) {
    return { code: "provider_unavailable", message: "The candle service is temporarily unavailable." };
  }
  return { code: "backend_unreachable", message: "The candle service returned an unsuccessful response." };
}

function quoteBody(value: unknown): CandleQuote {
  const body = record(value);
  if (body?.status === "fresh" && finite(body.last) && body.last > 0 &&
      finite(body.bid) && body.bid > 0 && finite(body.ask) && body.ask > 0 &&
      body.bid <= body.ask && timestamp(body.lastAt) && timestamp(body.retrievedAt) &&
      finite(body.ageSeconds) && body.ageSeconds >= 0 &&
      (body.symbol === "SPY" || body.symbol === "QQQ")) {
    return {
      status: "fresh",
      symbol: body.symbol,
      last: body.last,
      bid: body.bid,
      ask: body.ask,
      lastAt: body.lastAt,
      retrievedAt: body.retrievedAt,
      ageSeconds: body.ageSeconds,
    };
  }
  return {
    status: "unavailable",
    code: typeof body?.code === "string" ? body.code : "quote_unavailable",
    reason: typeof body?.reason === "string" ? body.reason : "Current quote is unavailable.",
    ...(finite(body?.ageSeconds) && body.ageSeconds >= 0 ? { ageSeconds: body.ageSeconds } : {}),
  };
}

/** Same-origin authenticated client. Tokens never enter browser state. */
export async function fetchCandles(
  symbol: CandleSymbol,
  interval: CandleInterval,
  options: { signal?: AbortSignal; request?: typeof fetch } = {},
): Promise<CandleClientResult> {
  const request = options.request ?? fetch;
  const timeout = AbortSignal.timeout(CANDLE_TIMEOUT_MS);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await request(
      `/api/candles/${symbol}?interval=${interval}&session=regular&limit=${CANDLE_LIMIT}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "same-origin",
        signal,
      },
    );
  } catch (error) {
    if (options.signal?.aborted) return { ok: false, error: { code: "cancelled", message: "Candle request cancelled." } };
    if (timeout.aborted || (error instanceof DOMException && error.name === "TimeoutError")) {
      return { ok: false, error: { code: "request_timeout", message: "The candle request timed out." } };
    }
    return { ok: false, error: { code: "backend_unreachable", message: "The candle service could not be reached." } };
  }

  let body: Record<string, unknown> = {};
  try {
    const parsed: unknown = await response.json();
    body = record(parsed) ?? {};
  } catch {
    if (!response.ok) return { ok: false, error: httpError(response.status, body, response) };
    return {
      ok: false,
      error: { code: "response_schema_mismatch", message: "The candle response was not valid JSON." },
    };
  }
  if (!response.ok) return { ok: false, error: httpError(response.status, body, response) };
  if (body.status !== "ok") {
    return {
      ok: false,
      error: { code: "response_schema_mismatch", message: "The candle response did not use the expected envelope." },
    };
  }
  const snapshot = parseCandleSnapshot(body.snapshot, { symbol, interval });
  return snapshot
    ? { ok: true, snapshot }
    : {
        ok: false,
        error: { code: "response_schema_mismatch", message: "The candle snapshot failed contract validation." },
      };
}

export async function fetchCurrentQuote(
  symbol: CandleSymbol,
  options: { signal?: AbortSignal; request?: typeof fetch } = {},
): Promise<{ ok: true; quote: CandleQuote } | { ok: false; quote: CandleQuote }> {
  const request = options.request ?? fetch;
  try {
    const response = await request(`/api/current-quote?symbol=${symbol}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
      signal: options.signal,
    });
    const body: unknown = await response.json().catch(() => null);
    return { ok: response.ok, quote: quoteBody(body) };
  } catch {
    return {
      ok: false,
      quote: { status: "unavailable", code: "quote_unavailable", reason: "Current quote could not be reached." },
    };
  }
}

export function warningLabel(code: string): string {
  return CANDLE_WARNING_LABELS[code] ??
    code.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function ageSeconds(value: string, now = Date.now()): number | null {
  const at = Date.parse(value);
  return Number.isFinite(at) ? Math.max(0, Math.floor((now - at) / 1000)) : null;
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return "age unavailable";
  if (seconds < 60) return `${seconds}s old`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s old`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m old`;
}

export function completenessLabel(snapshot: CandleSnapshot): string {
  const expected = snapshot.expected_bars === null ? "?" : String(snapshot.expected_bars);
  return `${snapshot.completeness} · ${snapshot.received_bars}/${expected} received · ${snapshot.returned_bars} returned`;
}

export function lastBarLabel(snapshot: CandleSnapshot): string {
  if (snapshot.warnings.includes("last_bar_window_open")) {
    return `${snapshot.last_bar_status} · interval window open`;
  }
  if (snapshot.warnings.includes("last_bar_completion_unverified")) {
    return `${snapshot.last_bar_status} · completion unverified`;
  }
  return snapshot.last_bar_status;
}
