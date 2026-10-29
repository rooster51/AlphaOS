/**
 * Server-side bridge for explicit structure research.
 *
 * Credentials stay on the server. The browser never receives the API token,
 * backend URL, upstream body or exception text. Response envelopes are only
 * forwarded when they pass the same contract the renderer uses.
 */
import { STRUCTURE_SOURCE } from "./structure-contract.ts";
import { getServerConfig } from "./server-config.ts";

export const SOURCE = STRUCTURE_SOURCE;
export const STRUCTURE_PATH = "/v1/research/structure";
export const COMPARE_PATH = "/v1/research/structures/compare";

/**
 * Explicit scenario research performs its own archive and history work, so it
 * has its own budget. The market research bridge keeps its 12,000 ms deadline.
 */
const UPSTREAM_TIMEOUT_MS = 20_000;

type Outcome = { status: number; code: string };

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function upstreamCode(value: unknown): string | null {
  const error = object(object(value)?.error);
  const code = error?.code;
  return typeof code === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(code) ? code : null;
}

function failure(status: number, code: string | null): Outcome {
  if (status === 401) return { status: 502, code: "backend_authentication_required" };
  if (status === 403) return { status: 502, code: "backend_authentication_rejected" };
  if (code === "invalid_structure") return { status: 502, code: "invalid_structure" };
  if (code && ["archive_snapshot_mismatch", "archive_expiration_unavailable", "archive_stale", "archive_missing",
    "archive_unavailable", "market_data_integrity_error", "market_data_date_mismatch", "market_data_spot_mismatch",
    "market_data_cashflow_mismatch", "market_contract_mismatch", "market_quote_invalid", "market_quote_stale",
    "market_data_unavailable"].includes(code)) return {status:502, code};
  if (status === 422) return { status: 502, code: "backend_rejected_request" };
  if (code === "api_not_configured") return { status: 502, code: "backend_api_not_configured" };
  if (code === "internal_error") return { status: 502, code: "backend_internal_error" };
  if (status === 404) return { status: 502, code: "backend_endpoint_unavailable" };
  if (status === 429) return { status: 502, code: "backend_rate_limited" };
  if (status >= 500) return { status: 502, code: "backend_service_unavailable" };
  return { status: 502, code: "backend_http_error" };
}

function json(body: unknown, status: number, requestId: string): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store", "X-AlphaOS-Request-ID": requestId },
  });
}

export async function postStructure(
  path: typeof STRUCTURE_PATH | typeof COMPARE_PATH,
  payload: unknown,
  request: Request,
  isValidEnvelope: (envelope: unknown) => boolean,
): Promise<Response> {
  const requestId = crypto.randomUUID().replaceAll("-", "");
  const started = performance.now();
  const trace: Record<string, unknown> = {
    event: "structure_bridge",
    request_id: requestId,
    path,
    stage: "request_validation",
  };

  const { token, base, diagnostics } = getServerConfig();
  trace.configuration = diagnostics;
  if (!token || !base) {
    console.warn(JSON.stringify({ ...trace, outcome: "backend_not_configured" }));
    return json({ status: "unavailable", code: "backend_not_configured" }, 503, requestId);
  }

  let origin: URL;
  try {
    origin = new URL(base);
    if (origin.protocol !== "https:" || origin.username || origin.password ||
        origin.search || origin.hash) {
      throw new Error("Invalid backend URL");
    }
  } catch {
    return json({ status: "unavailable", code: "invalid_backend_configuration" }, 503, requestId);
  }

  trace.stage = "fetch";
  // Kept separate from the combined signal so a timeout that fires while the
  // response body is being consumed is still recognisable as a timeout.
  const timeout = AbortSignal.timeout(UPSTREAM_TIMEOUT_MS);
  const signals = AbortSignal.any([timeout, request.signal]);

  /** Classify a transport failure without trusting the exception's message. */
  function transportOutcome(error: unknown): Outcome | null {
    if (request.signal.aborted) return { status: 499, code: "request_cancelled" };
    if (timeout.aborted || (error instanceof DOMException && error.name === "TimeoutError")) {
      return { status: 502, code: "backend_timeout" };
    }
    if (error instanceof DOMException || error instanceof TypeError) {
      return { status: 502, code: "backend_unreachable" };
    }
    return null;
  }

  function unavailable(outcome: Outcome): Response {
    trace.outcome = outcome.code;
    trace.elapsed_ms = Math.round(performance.now() - started);
    console.warn(JSON.stringify(trace));
    return json({ status: "unavailable", code: outcome.code }, outcome.status, requestId);
  }

  let response: Response;
  try {
    response = await fetch(new URL(path, origin), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-AlphaOS-Request-ID": requestId,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: signals,
    });
  } catch (error) {
    const outcome = transportOutcome(error);
    if (!outcome) {
      trace.outcome = "unexpected_error";
      trace.elapsed_ms = Math.round(performance.now() - started);
      console.warn(JSON.stringify(trace));
      throw error;
    }
    return unavailable(outcome);
  }

  trace.upstream_status = response.status;
  trace.correlated = response.headers.get("X-AlphaOS-Request-ID") === requestId;

  if (!response.ok) {
    let code: string | null = null;
    try {
      code = upstreamCode(await response.json());
    } catch (error) {
      // A timeout or cancellation while reading the error body is that outcome,
      // not a generic backend failure.
      const transport = transportOutcome(error);
      if (transport) return unavailable(transport);
      code = null;
    }
    return unavailable(failure(response.status, code));
  }

  trace.stage = "response_body";
  let envelope: unknown;
  try {
    envelope = await response.json();
  } catch (error) {
    // Headers already arrived, so malformed JSON and a body that timed out or
    // was cancelled must stay distinguishable.
    return unavailable(transportOutcome(error) ??
      { status: 502, code: "response_schema_mismatch" });
  }

  trace.stage = "schema_validation";
  if (!isValidEnvelope(envelope)) {
    return unavailable({ status: 502, code: "response_schema_mismatch" });
  }

  trace.outcome = "ok";
  trace.elapsed_ms = Math.round(performance.now() - started);
  trace.timeout_ms = UPSTREAM_TIMEOUT_MS;
  console.warn(JSON.stringify(trace));
  return json({ research: envelope, verified_for_trading: false, source: SOURCE }, 200, requestId);
}

export const BRIDGE_TIMEOUT_MS = UPSTREAM_TIMEOUT_MS;
