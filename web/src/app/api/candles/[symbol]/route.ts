/**
 * Authenticated same-origin bridge for GET /v1/candles/{symbol}.
 *
 * The browser session is verified here; the backend bearer token stays
 * server-side. The upstream body is validated before any candles are returned.
 */
import { readRuntimeBindings } from "#alphaos-runtime";
import {
  CANDLE_INTERVALS,
  CANDLE_LIMIT,
  CANDLE_SYMBOLS,
  parseCandleSnapshot,
  type CandleInterval,
  type CandleSymbol,
} from "../../../../lib/candles.ts";
import { getServerConfig } from "../../../../lib/server-config.ts";
import { sessionRole } from "../../../../lib/website-auth.ts";

const UPSTREAM_TIMEOUT_MS = 12_000;
const SAFE_UPSTREAM_CODES = new Set([
  "public_not_configured",
  "provider_unavailable",
  "no_candles",
  "invalid_provider_response",
  "market_data_unavailable",
]);

type Failure = { status: number; code: string };

function failure(status: number, code: string): Response {
  return Response.json(
    { status: "unavailable", code },
    {
      status,
      headers: {
        "Cache-Control": "private, no-store",
        Vary: "Cookie",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow",
        "Referrer-Policy": "same-origin",
      },
    },
  );
}

function upstreamCode(value: unknown): string | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const error = (value as Record<string, unknown>).error;
  if (error === null || typeof error !== "object" || Array.isArray(error)) return null;
  const code = (error as Record<string, unknown>).code;
  return typeof code === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(code) ? code : null;
}

function mapUpstream(status: number, code: string | null): Failure {
  if (status === 401) return { status: 502, code: "backend_authentication_failed" };
  if (status === 403) return { status: 403, code: "data_use_denied" };
  if (status === 429) return { status: 429, code: "provider_rate_limited" };
  if (status === 504) return { status: 504, code: "provider_timeout" };
  if (status === 400) return { status: 400, code: "invalid_request" };
  if (status === 422) return { status: 400, code: "invalid_request" };
  if (status === 404) return { status: 502, code: "backend_endpoint_unavailable" };
  if (status === 503 && code && SAFE_UPSTREAM_CODES.has(code)) return { status: 503, code };
  if (status === 503) return { status: 503, code: "provider_unavailable" };
  if (status >= 500) return { status: 502, code: "provider_unavailable" };
  return { status: 502, code: "backend_http_error" };
}

function entitlementDenied(value: unknown): boolean {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const entitlement = (value as Record<string, unknown>).entitlement;
  return entitlement !== null && typeof entitlement === "object" && !Array.isArray(entitlement) &&
    (entitlement as Record<string, unknown>).allowed === false;
}

function isSymbol(value: string): value is CandleSymbol {
  return (CANDLE_SYMBOLS as readonly string[]).includes(value);
}

function isInterval(value: string): value is CandleInterval {
  return (CANDLE_INTERVALS as readonly string[]).includes(value);
}

export async function GET(
  request: Request,
  context: { params: Promise<{ symbol: string }> },
): Promise<Response> {
  const { bindings } = readRuntimeBindings();
  const role = await sessionRole(request, {
    ALPHAOS_PASSWORD_HASH: bindings.ALPHAOS_PASSWORD_HASH,
    ALPHAOS_SESSION_KEY: bindings.ALPHAOS_SESSION_KEY,
  });
  if (!role) return failure(401, "authentication_required");
  // The signed session must carry the owner role. A valid viewer session is
  // not enough, and the check happens before any backend request.
  if (role !== "owner") return failure(403, "owner_only");

  // Fail closed: this deployment switch is not the authorization. The owner
  // session above and the provider owner_private_display decision below are.
  if (process.env.ALPHAOS_CANDLE_CHART_ENABLED !== "true") {
    return failure(503, "feature_disabled");
  }

  const { symbol: rawSymbol } = await context.params;
  const symbol = rawSymbol.toUpperCase();
  const query = new URL(request.url).searchParams;
  const interval = query.get("interval") ?? "1m";
  const session = query.get("session") ?? "regular";
  const rawLimit = query.get("limit") ?? String(CANDLE_LIMIT);
  const limit = Number(rawLimit);
  if (!isSymbol(symbol) || !isInterval(interval) || session !== "regular" ||
      !Number.isInteger(limit) || limit < 1 || limit > CANDLE_LIMIT) {
    return failure(400, "invalid_request");
  }

  const { base, token, diagnostics } = getServerConfig();
  if (!base || !token || diagnostics.configuration !== "ready") {
    return failure(503, "backend_not_configured");
  }

  const requestId = crypto.randomUUID().replaceAll("-", "");
  const started = performance.now();
  const deadline = AbortSignal.timeout(UPSTREAM_TIMEOUT_MS);
  const signal = AbortSignal.any([deadline, request.signal]);
  const url = new URL(`/v1/candles/${symbol}`, base);
  url.searchParams.set("interval", interval);
  url.searchParams.set("session", session);
  url.searchParams.set("limit", String(limit));

  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "X-AlphaOS-Data-Use": "owner_private_display",
        "X-AlphaOS-Request-ID": requestId,
      },
      cache: "no-store",
      redirect: "error",
      signal,
    });
  } catch {
    const timedOut = deadline.aborted;
    console.warn(JSON.stringify({
      event: "candles_bridge",
      request_id: requestId,
      symbol,
      interval,
      outcome: timedOut ? "provider_timeout" : "backend_unreachable",
      elapsed_ms: Math.round(performance.now() - started),
    }));
    return failure(timedOut ? 504 : 502, timedOut ? "provider_timeout" : "backend_unreachable");
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    if (!response.ok) {
      const mapped = mapUpstream(response.status, null);
      return failure(mapped.status, mapped.code);
    }
    return failure(502, "provider_schema_error");
  }

  if (!response.ok) {
    const mapped = mapUpstream(response.status, upstreamCode(payload));
    console.warn(JSON.stringify({
      event: "candles_bridge",
      request_id: requestId,
      symbol,
      interval,
      upstream_status: response.status,
      outcome: mapped.code,
      elapsed_ms: Math.round(performance.now() - started),
    }));
    return failure(mapped.status, mapped.code);
  }

  // A denied entitlement is a policy result, not a malformed snapshot. Keep the
  // safe 403 distinct from provider schema failures.
  if (entitlementDenied(payload)) return failure(403, "data_use_denied");

  const snapshot = parseCandleSnapshot(payload, { symbol, interval });
  if (!snapshot) return failure(502, "provider_schema_error");

  // The bridge requested owner-private display, not public display. Both the
  // per-response decision and the provider capability must confirm that exact
  // use. Private research is never relabelled, and public display stays denied.
  const capabilityEntitlement = snapshot.provider_capabilities.entitlement;
  const ownerPrivateCapability = capabilityEntitlement !== null &&
    typeof capabilityEntitlement === "object" && !Array.isArray(capabilityEntitlement) &&
    (capabilityEntitlement as Record<string, unknown>).owner_private_display === true;
  if (snapshot.entitlement.allowed !== true ||
      snapshot.entitlement.use_context !== "owner_private_display" ||
      !ownerPrivateCapability) {
    console.warn(JSON.stringify({
      event: "candles_bridge",
      request_id: requestId,
      symbol,
      interval,
      outcome: "data_use_denied",
      entitlement_context: snapshot.entitlement.use_context,
      elapsed_ms: Math.round(performance.now() - started),
    }));
    return failure(403, "data_use_denied");
  }

  console.warn(JSON.stringify({
    event: "candles_bridge",
    request_id: requestId,
    symbol,
    interval,
    snapshot_id: snapshot.snapshot_id,
    candles: snapshot.returned_bars,
    completeness: snapshot.completeness,
    last_bar_status: snapshot.last_bar_status,
    freshness: snapshot.freshness,
    elapsed_ms: Math.round(performance.now() - started),
  }));
  return Response.json(
    { status: "ok", snapshot },
    {
      headers: {
        "Cache-Control": "private, no-store",
        Vary: "Cookie",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow",
        "Referrer-Policy": "same-origin",
      },
    },
  );
}
