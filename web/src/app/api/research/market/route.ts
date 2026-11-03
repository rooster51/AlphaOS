import { validateArchiveObservation } from "../../../../lib/archive-observation.ts";
import { getServerConfig } from "../../../../lib/server-config.ts";
import { readRuntimeBindings } from "#alphaos-runtime";
import { validSessionCookie } from "../../../../lib/website-auth.ts";

type MarketPayload = {
  view?: "observation";
  symbol: "SPY" | "QQQ";
  research_mode?: "current" | "historical";
  expiration?: string;
  available_capital?: number;
  objective?: string;
  width?: number | null;
};

function parseMarketPayload(value: unknown): MarketPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  const allowed = new Set(["symbol", "research_mode", "expiration", "available_capital", "objective", "width", "view"]);
  if (Object.keys(input).some((key) => !allowed.has(key))) return null;

  if (typeof input.symbol !== "string") return null;
  const symbol = input.symbol.toUpperCase();
  if (symbol !== "SPY" && symbol !== "QQQ") return null;

  const payload: MarketPayload = { symbol };
  if (input.view !== undefined) {
    if (input.view !== "observation" || ["available_capital","objective","width"].some(k => k in input)) return null;
    payload.view = "observation";
  }
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
    if (input.width !== null && (typeof input.width !== "number" || !Number.isFinite(input.width) ||
        input.width <= 0 || input.width > 100)) return null;
    payload.width = input.width;
  }
  return payload;
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

// JSON.parse can produce Infinity from otherwise valid JSON such as 1e999.
// Reject that input rather than letting raw forwarding change the old JSON
// serializer's normalization. This visits parsed data without rebuilding it.
const SAFE_NUMERIC_FIELDS = new Set([
  "spot", "age_seconds", "max_age_seconds", "contract_count", "total_contract_count",
  "valid_contracts", "questionable_contracts", "rejected_contracts",
]);

function jsonNumberEncoding(value: unknown): {encoding: "raw" | "normalize" | "invalid"; fields: string[]} {
  const pending: {value: unknown; path: string[]}[] = [{value,path:[]}];
  let encoding: "raw" | "normalize" = "raw";
  const fields = new Set<string>();
  while (pending.length) {
    const {value:item,path} = pending.pop()!;
    if (typeof item === "number") {
      if (!Number.isFinite(item)) {
        const known = path.filter(part=>SAFE_NUMERIC_FIELDS.has(part));
        fields.add(known.length ? known.join(".") : "response.numeric_value");
        continue;
      }
      // JSON.stringify historically normalizes negative zero to zero. Keep
      // that decoded response contract, including underflow such as -1e-999.
      if (Object.is(item, -0)) encoding = "normalize";
    }
    if (item && typeof item === "object") {
      const entries = Object.entries(item);
      for (const [key,child] of entries) {
        pending.push({value:child,path:Array.isArray(item) ? path : [...path,key]});
      }
    }
  }
  return {encoding:fields.size ? "invalid" : encoding,fields:[...fields].slice(0,8)};
}

function validResearchEnvelope(value: unknown, symbol: MarketPayload["symbol"], mode: MarketPayload["research_mode"], expiration?: string, width?: number | null): value is Record<string, unknown> {
  const envelope = object(value);
  const request = object(envelope?.request);
  const research = object(envelope?.research);
  const archive = object(research?.archive);
  const session = object(research?.research_session);
  if ((request?.width ?? null) !== (width ?? null)) return false;
  if (expiration !== undefined && (request?.expiration !== expiration || research?.expiration !== expiration || session?.expiration !== expiration)) return false;
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
  configuration?: ReturnType<typeof getServerConfig>["diagnostics"];
  request_id: string;
  stage: string;
  symbol?: MarketPayload["symbol"];
  research_mode?: "current" | "historical";
  fetch_headers_ms?: number;
  response_body_ms?: number;
  schema_validation_ms?: number;
  validation_category?: string;
  validation_categories?: string[];
  validation_fields?: string[];
  upstream_status?: number;
  upstream_json?: boolean;
  backend_correlated?: boolean;
  upstream_code?: string;
  outcome?: "backend_timeout" | "backend_unreachable" | "request_cancelled";
  timeout_phase?: "response_headers" | "response_body" | "schema_validation";
  fetch_wait_ms?: number;
};
const KNOWN_UPSTREAM_CODES = new Set([
  "archive_stale", "archive_missing", "archive_not_configured", "archive_unavailable",
  "archive_research_unavailable", "archive_expiration_unavailable", "api_not_configured",
  "internal_error", "authentication_required", "forbidden", "invalid_request",
]);
const PREVIEW_DIAGNOSTIC_HOST = "deploy-preview-82--alphaostrading.netlify.app";
const SAFE_VALIDATION_CATEGORIES = new Set([
  "invalid_json", "invalid_numeric_encoding", "observation_schema_mismatch",
  "timestamp_freshness_mismatch", "archive_metadata_quality_mismatch",
  "multiple_validation_failures", "research_schema_mismatch",
]);
const SAFE_VALIDATION_FIELDS = new Set([
  "response.numeric_value", "spot", "schema_version", "read_only", "verified_for_trading",
  "research_performed", "evidence_scope", "research_session", "candidates", "symbol",
  "research_mode", "expiration", "caveats", "as_of", "requested_as_of", "as_of_order",
  "session.open", "session.close", "archive.observation.observed_at", "archive.storage.observed_at",
  "archive.freshness.as_of", "archive.freshness.age_seconds", "archive.freshness.max_age_seconds",
  "archive.session_date", "archive.storage.symbol", "archive.provider", "archive.storage.quality_status",
  "archive.observation.options_status", "archive.storage.contract_count",
  "archive.diagnostics.total_contract_count", "archive.diagnostics.bucket_counts.valid_contracts",
  "archive.diagnostics.bucket_counts.questionable_contracts", "archive.diagnostics.bucket_counts.rejected_contracts",
  "archive.storage.archive_sha256", "archive.storage.archive_path",
]);

async function previewDiagnostic(request: Request, trace: BridgeTrace) {
  const {runtime, bindings} = readRuntimeBindings();
  const sessionBindings = {
    ALPHAOS_PASSWORD_HASH: bindings.ALPHAOS_PASSWORD_HASH,
    ALPHAOS_SESSION_KEY: bindings.ALPHAOS_SESSION_KEY,
  };
  if (runtime !== "node" || process.env.ALPHAOS_PREVIEW_DIAGNOSTICS !== "true" ||
      new URL(request.url).hostname.toLowerCase() !== PREVIEW_DIAGNOSTIC_HOST ||
      !trace.validation_category || !await validSessionCookie(request, sessionBindings)) return null;
  const categories = [...new Set(trace.validation_categories?.length
    ? trace.validation_categories : [trace.validation_category])]
    .filter((category): category is string => typeof category === "string" &&
      SAFE_VALIDATION_CATEGORIES.has(category));
  if (!categories.length) return null;
  return {
    request_id: trace.request_id,
    upstream_status: trace.upstream_status ?? null,
    validation_categories: categories,
    rejected_fields: [...new Set((trace.validation_fields ?? [])
      .filter(field => SAFE_VALIDATION_FIELDS.has(field)))].slice(0, 16),
  };
}

// Headers, URLs, bodies, objective text and exception strings never enter diagnostics.
export async function POST(request: Request) {
  const trace: BridgeTrace = {request_id: crypto.randomUUID().replaceAll("-", ""), stage: "request_validation"};
  const started = performance.now();
  let result: Response;
  let timeoutSignal: AbortSignal | undefined;
  try {
    result = await marketRequest(request, trace, () => timeoutSignal = AbortSignal.timeout(12000));
  } catch (error) {
    const clientCancelled = request.signal.aborted;
    const timeout = error instanceof DOMException && (error.name === "TimeoutError" ||
      (error.name === "AbortError" && timeoutSignal?.reason instanceof DOMException &&
        timeoutSignal.reason.name === "TimeoutError"));
    if (!clientCancelled && !timeout && !(error instanceof TypeError)) {
      console.warn(JSON.stringify({event: "research_bridge", ...trace, outcome: "unexpected_error",
        elapsed_ms: Math.round(performance.now() - started)}));
      throw error;
    }
    trace.outcome = clientCancelled ? "request_cancelled" : timeout ? "backend_timeout" : "backend_unreachable";
    result = Response.json({status: "unavailable", code: trace.outcome},
      {status: clientCancelled ? 499 : 502, headers: {"Cache-Control": "no-store"}});
  }
  if (trace.outcome === "backend_timeout") {
    // A timeout before headers cannot establish whether the origin is asleep,
    // authenticating, or computing. Correlate with Render logs; never guess.
    trace.timeout_phase = trace.stage === "fetch" ? "response_headers"
      : trace.stage === "schema_validation" ? "schema_validation" : "response_body";
  }
  if (result.status === 502) {
    const diagnostic = await previewDiagnostic(request, trace);
    if (diagnostic) {
      result = Response.json(
        {status: "unavailable", code: "response_schema_mismatch", diagnostic},
        {status: 502, headers: result.headers},
      );
    }
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

  const { token, base, diagnostics } = getServerConfig();
  trace.configuration = diagnostics;
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
    const {view,...backendPayload} = payload;
    response = await fetch(new URL(view === "observation" ? "/v1/research/observation" : "/v1/research/market", origin), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "X-AlphaOS-Request-ID": trace.request_id,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(backendPayload),
      cache: "no-store",
      signal: AbortSignal.any([timeout(), request.signal]),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    if (!timedOut && !(error instanceof TypeError)) throw error;
    trace.fetch_wait_ms = Math.round(performance.now() - fetchStarted);
    trace.outcome = timedOut ? "backend_timeout" : "backend_unreachable";
    return Response.json(
      { status: "unavailable", code: trace.outcome },
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
  let responseText: string;
  const bodyStarted = performance.now();
  try {
    responseText = await response.text();
    responsePayload = JSON.parse(responseText);
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError) {
      trace.validation_category = "invalid_json";
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
  const numberEncoding = jsonNumberEncoding(responsePayload);
  let valid = false;
  if (numberEncoding.encoding === "invalid") {
    trace.validation_category = "invalid_numeric_encoding";
    trace.validation_fields = numberEncoding.fields;
  } else if (payload.view === "observation") {
    const validation = validateArchiveObservation(responsePayload,payload.symbol,payload.research_mode ?? "current",payload.expiration);
    valid = validation.valid;
    if (!valid) {
      trace.validation_categories = validation.categories;
      trace.validation_category = validation.categories.length === 1
        ? validation.categories[0] : "multiple_validation_failures";
      trace.validation_fields = validation.fields;
    }
  } else {
    valid = validResearchEnvelope(responsePayload, payload.symbol, payload.research_mode, payload.expiration, payload.width);
    if (!valid) trace.validation_category = "research_schema_mismatch";
  }
  trace.schema_validation_ms = Math.round(performance.now() - validationStarted);
  if (!valid) {
    return Response.json(
      { status: "unavailable", code: "response_schema_mismatch" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (numberEncoding.encoding === "normalize") {
    return Response.json(
      { research: responsePayload, verified_for_trading: false, source: "alphaos_research_api" },
      { headers: { "Cache-Control": "no-store" } }
    );
  }
  // Only after the entire body parses and passes the existing schema checks.
  // Preserve every research field without serializing a multi-MB tree again.
  return new Response(
    `{"research":${responseText},"verified_for_trading":false,"source":"alphaos_research_api"}`,
    { headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } }
  );
}
