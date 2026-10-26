/**
 * Server-side bridge for explicit structure research.
 *
 * Credentials stay on the server. The browser never receives the API token,
 * backend URL, upstream body or exception text. Response envelopes are only
 * forwarded when they pass the same contract the renderer uses.
 */
import { STRUCTURE_SOURCE } from "./structure-contract.ts";

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

  const token = process.env.ALPHAOS_API_TOKEN;
  const base = process.env.ALPHAOS_API_URL;
  if (!token || !base) {
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
  const signals = AbortSignal.any([AbortSignal.timeout(UPSTREAM_TIMEOUT_MS), request.signal]);
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
    const cancelled = request.signal.aborted;
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    if (!cancelled && !timedOut && !(error instanceof TypeError)) {
      trace.outcome = "unexpected_error";
      trace.elapsed_ms = Math.round(performance.now() - started);
      console.warn(JSON.stringify(trace));
      throw error;
    }
    const outcome: Outcome = cancelled
      ? { status: 499, code: "request_cancelled" }
      : timedOut
        ? { status: 502, code: "backend_timeout" }
        : { status: 502, code: "backend_unreachable" };
    trace.outcome = outcome.code;
    trace.elapsed_ms = Math.round(performance.now() - started);
    console.warn(JSON.stringify(trace));
    return json({ status: "unavailable", code: outcome.code }, outcome.status, requestId);
  }

  trace.upstream_status = response.status;
  trace.correlated = response.headers.get("X-AlphaOS-Request-ID") === requestId;

  if (!response.ok) {
    let code: string | null = null;
    try {
      code = upstreamCode(await response.json());
    } catch {
      code = null;
    }
    const outcome = failure(response.status, code);
    trace.outcome = outcome.code;
    trace.elapsed_ms = Math.round(performance.now() - started);
    console.warn(JSON.stringify(trace));
    return json({ status: "unavailable", code: outcome.code }, outcome.status, requestId);
  }

  trace.stage = "response_body";
  let envelope: unknown;
  try {
    envelope = await response.json();
  } catch {
    trace.outcome = "response_schema_mismatch";
    trace.elapsed_ms = Math.round(performance.now() - started);
    console.warn(JSON.stringify(trace));
    return json({ status: "unavailable", code: "response_schema_mismatch" }, 502, requestId);
  }

  trace.stage = "schema_validation";
  if (!isValidEnvelope(envelope)) {
    trace.outcome = "response_schema_mismatch";
    trace.elapsed_ms = Math.round(performance.now() - started);
    console.warn(JSON.stringify(trace));
    return json({ status: "unavailable", code: "response_schema_mismatch" }, 502, requestId);
  }

  trace.outcome = "ok";
  trace.elapsed_ms = Math.round(performance.now() - started);
  trace.timeout_ms = UPSTREAM_TIMEOUT_MS;
  console.warn(JSON.stringify(trace));
  return json({ research: envelope, verified_for_trading: false, source: SOURCE }, 200, requestId);
}

export const BRIDGE_TIMEOUT_MS = UPSTREAM_TIMEOUT_MS;
