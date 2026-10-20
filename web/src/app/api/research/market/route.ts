type MarketPayload = {
  symbol: "SPY" | "QQQ";
  research_mode?: "current" | "historical";
  expiration?: string;
  available_capital?: number;
  objective?: string;
  width?: number;
};

function parseMarketPayload(value: unknown): MarketPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  const allowed = new Set(["symbol", "research_mode", "expiration", "available_capital", "objective", "width"]);
  if (Object.keys(input).some((key) => !allowed.has(key))) return null;

  if (typeof input.symbol !== "string") return null;
  const symbol = input.symbol.toUpperCase();
  if (symbol !== "SPY" && symbol !== "QQQ") return null;

  const payload: MarketPayload = { symbol };
  if (input.research_mode !== undefined) {
    if (input.research_mode !== "current" && input.research_mode !== "historical") return null;
    payload.research_mode = input.research_mode;
  }
  if (input.expiration !== undefined) {
    if (typeof input.expiration !== "string" ||
        !/^\d{4}-\d{2}-\d{2}$/.test(input.expiration) ||
        input.expiration.startsWith("0000-") ||
        new Date(`${input.expiration}T00:00:00Z`).toISOString().slice(0, 10) !== input.expiration) {
      return null;
    }
    payload.expiration = input.expiration;
  }
  if (input.available_capital !== undefined) {
    if (typeof input.available_capital !== "number" ||
        !Number.isFinite(input.available_capital) || input.available_capital <= 0) return null;
    payload.available_capital = input.available_capital;
  }
  if (input.objective !== undefined) {
    if (typeof input.objective !== "string" || input.objective.length > 1000) return null;
    payload.objective = input.objective;
  }
  if (input.width !== undefined) {
    if (typeof input.width !== "number" || !Number.isFinite(input.width) ||
        input.width <= 0 || input.width > 100) return null;
    payload.width = input.width;
  }
  return payload;
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function validResearchEnvelope(value: unknown, symbol: MarketPayload["symbol"], mode: MarketPayload["research_mode"]): value is Record<string, unknown> {
  const envelope = object(value);
  const request = object(envelope?.request);
  const research = object(envelope?.research);
  const archive = object(research?.archive);
  const session = object(research?.research_session);
  if (mode === "historical") {
    const freshness = object(archive?.freshness);
    const observation = object(archive?.observation);
    if (request?.research_mode !== mode || research?.research_mode !== mode ||
        typeof observation?.observed_at !== "string" || !Number.isFinite(Date.parse(observation.observed_at)) ||
        typeof freshness?.age_seconds !== "number" || !Number.isFinite(freshness.age_seconds) || freshness.age_seconds < 0 ||
        freshness.max_age_seconds !== null || typeof archive?.provider !== "string") return false;
  } else if ((research?.research_mode !== undefined && research.research_mode !== "current") ||
      (request?.research_mode !== undefined && request.research_mode !== "current")) return false;
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return envelope?.schema_version === "alphaos-interface-v2" &&
    envelope.read_only === true &&
    request?.symbol === symbol &&
    research?.symbol === symbol &&
    typeof research.as_of === "string" &&
    archive !== null &&
    session?.symbol === symbol &&
    Array.isArray(session.candidates) &&
    Array.isArray(session.unavailable_routes) &&
    (session.status === "complete" || session.status === "no_candidate") &&
    object(envelope.provenance) !== null &&
    Array.isArray(envelope.caveats);
}

function upstreamErrorCode(value: unknown): string | null {
  const envelope = object(value);
  const error = object(envelope?.error);
  const code = error?.code;
  return typeof code === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(code) ? code : null;
}

async function readErrorPayload(response: Response, trace: BridgeTrace): Promise<unknown> {
  const started = performance.now();
  try {
    return await response.json();
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError) return null;
    throw error;
  } finally {
    trace.response_body_ms = Math.round(performance.now() - started);
  }
}

/**
 * Read-only research bridge. Raw upstream evidence is intentionally NOT
 * converted into trade candidates or advertised as executable prices.
 * Credentials remain server-side.
 */
type BridgeTrace = {
  request_id: string;
  stage: string;
  symbol?: MarketPayload["symbol"];
  research_mode?: "current" | "historical";
  fetch_headers_ms?: number;
  response_body_ms?: number;
  schema_validation_ms?: number;
  upstream_status?: number;
  upstream_json?: boolean;
  backend_correlated?: boolean;
  upstream_code?: string;
};
const KNOWN_UPSTREAM_CODES = new Set([
  "archive_stale", "archive_missing", "archive_not_configured", "archive_unavailable",
  "archive_research_unavailable", "archive_expiration_unavailable", "api_not_configured",
  "internal_error", "authentication_required", "forbidden", "invalid_request",
]);

// Headers, URLs, bodies, objective text and exception strings never enter diagnostics.
export async function POST(request: Request) {
  const trace: BridgeTrace = {request_id: crypto.randomUUID().replaceAll("-", ""), stage: "request_validation"};
  const started = performance.now();
  let result: Response;
  let timeoutSignal: AbortSignal | undefined;
  try {
    result = await marketRequest(request, trace, () => timeoutSignal = AbortSignal.timeout(12000));
  } catch (error) {
    const timeout = error instanceof DOMException && (error.name === "TimeoutError" ||
      (error.name === "AbortError" && timeoutSignal?.reason instanceof DOMException &&
        timeoutSignal.reason.name === "TimeoutError"));
    if (!timeout && !(error instanceof TypeError)) {
      console.warn(JSON.stringify({event: "research_bridge", ...trace, outcome: "unexpected_error",
        elapsed_ms: Math.round(performance.now() - started)}));
      throw error;
    }
    result = Response.json({status: "unavailable", code: timeout ? "backend_timeout" : "backend_unreachable"},
      {status: 502, headers: {"Cache-Control": "no-store"}});
  }
  result.headers.set("X-AlphaOS-Request-ID", trace.request_id);
  console.warn(JSON.stringify({event: "research_bridge", ...trace, status: result.status,
    timeout_ms: 12000, elapsed_ms: Math.round(performance.now() - started)}));
  return result;
}

async function marketRequest(request: Request, trace: BridgeTrace, timeout: () => AbortSignal) {
  let payload: MarketPayload | null;
  try {
    payload = parseMarketPayload(await request.json());
  } catch {
    payload = null;
  }
  if (!payload) {
    return Response.json({ error: "Invalid research request" }, { status: 400 });
  }
  trace.symbol = payload.symbol;
  trace.research_mode = payload.research_mode ?? "current";

  const token = process.env.ALPHAOS_API_TOKEN;
  const base = process.env.ALPHAOS_API_URL;
  if (!token || !base) {
    return Response.json(
      { status: "unavailable", code: "backend_not_configured" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  let origin: URL;
  try {
    origin = new URL(base);
    if (origin.protocol !== "https:" || origin.username || origin.password ||
        origin.search || origin.hash) throw new Error("Invalid backend URL");
  } catch {
    return Response.json(
      { status: "unavailable", code: "invalid_backend_configuration" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  trace.stage = "fetch";
  const fetchStarted = performance.now();
  let response: Response;
  try {
    response = await fetch(new URL("/v1/research/market", origin), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "X-AlphaOS-Request-ID": trace.request_id,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: timeout(),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    if (!timedOut && !(error instanceof TypeError)) throw error;
    return Response.json(
      { status: "unavailable", code: timedOut ? "backend_timeout" : "backend_unreachable" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  trace.fetch_headers_ms = Math.round(performance.now() - fetchStarted);
  trace.upstream_status = response.status;
  trace.upstream_json = (response.headers.get("Content-Type") ?? "").toLowerCase().includes("application/json");
  trace.backend_correlated = response.headers.get("X-AlphaOS-Request-ID") === trace.request_id;
  trace.stage = "response_body";
  if (!response.ok) {
    const code = upstreamErrorCode(await readErrorPayload(response, trace));
    trace.upstream_code = KNOWN_UPSTREAM_CODES.has(code ?? "") ? code! : "unrecognized_or_missing";
    const detail = response.status === 401
      ? "backend_authentication_required"
      : response.status === 403
        ? "backend_authentication_rejected"
        : code === "archive_stale"
          ? "archive_stale"
          : code === "archive_missing"
            ? "archive_missing"
            : code === "archive_not_configured"
              ? "archive_not_configured"
              : code === "archive_unavailable"
                ? "archive_unavailable"
                : code === "archive_research_unavailable"
                  ? "archive_research_unavailable"
                : code === "archive_expiration_unavailable"
                  ? "archive_expiration_unavailable"
                : response.status === 422
                  ? "backend_rejected_request"
                  : code === "api_not_configured"
                    ? "backend_api_not_configured"
                    : code === "internal_error"
                      ? "backend_internal_error"
                      : response.status === 404
                        ? "backend_endpoint_unavailable"
                        : response.status === 429
                          ? "backend_rate_limited"
                          : response.status >= 500
                            ? "backend_service_unavailable"
                  : "backend_http_error";
    return Response.json(
      { status: "unavailable", code: detail },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  let responsePayload: unknown;
  const bodyStarted = performance.now();
  try {
    responsePayload = await response.json();
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError) {
      return Response.json(
        { status: "unavailable", code: "response_schema_mismatch" },
        { status: 502, headers: { "Cache-Control": "no-store" } },
      );
    }
    throw error;
  } finally {
    trace.response_body_ms = Math.round(performance.now() - bodyStarted);
  }
  trace.stage = "schema_validation";
  const validationStarted = performance.now();
  const valid = validResearchEnvelope(responsePayload, payload.symbol, payload.research_mode);
  trace.schema_validation_ms = Math.round(performance.now() - validationStarted);
  if (!valid) {
    return Response.json(
      { status: "unavailable", code: "response_schema_mismatch" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
  return Response.json(
    { research: responsePayload, verified_for_trading: false, source: "alphaos_research_api" },
    { headers: { "Cache-Control": "no-store" } }
  );
}
