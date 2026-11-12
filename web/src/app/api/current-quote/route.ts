import { readRuntimeBindings } from "#alphaos-runtime";
import { getServerConfig } from "../../../lib/server-config.ts";
import { sessionRole } from "../../../lib/website-auth.ts";
import { currentQuote, quoteAgeLimit, quoteHttpFailure, unavailable } from "../../../lib/current-quotes.ts";

const timeoutMs = 5000;

export async function GET(request: Request) {
  const symbol = new URL(request.url).searchParams.get("symbol");
  const reply = (result: ReturnType<typeof currentQuote>, status = 200) =>
    Response.json(result, { status, headers: { "Cache-Control": "private, no-store", Vary: "Cookie" } });
  const { bindings } = readRuntimeBindings();
  const role = await sessionRole(request, {
    ALPHAOS_PASSWORD_HASH: bindings.ALPHAOS_PASSWORD_HASH,
    ALPHAOS_SESSION_KEY: bindings.ALPHAOS_SESSION_KEY,
  });
  if (!role) {
    return reply(unavailable("authentication_failure", "Preview session expired."), 401);
  }
  if (role !== "owner") {
    return reply(unavailable("owner_only", "Only the authenticated repository owner may view this quote."), 403);
  }
  if (symbol !== "SPY" && symbol !== "QQQ") {
    return reply(unavailable("invalid_quote", "Invalid quote symbol."), 400);
  }
  const { base, token, diagnostics } = getServerConfig();
  if (!base || !token || diagnostics.configuration !== "ready") {
    return reply(unavailable("backend_unreachable", "Preview quote backend is not configured."), 503);
  }

  const requestId = crypto.randomUUID().replaceAll("-", "");
  const started = performance.now();
  const deadline = AbortSignal.timeout(timeoutMs);
  let headersMs: number | undefined;
  let status: number | undefined;
  let result: ReturnType<typeof currentQuote>;
  try {
    const response = await fetch(new URL(`/v1/quote/${symbol}?refresh=true`, base), {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json", "X-AlphaOS-Request-ID": requestId },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([deadline, request.signal]),
    });
    status = response.status;
    headersMs = Math.round(performance.now() - started);
    const payload: unknown = await response.json().catch(error => {
      if (error instanceof SyntaxError) return null;
      throw error;
    });
    result = response.ok
      ? currentQuote(payload, symbol, Date.now(), quoteAgeLimit(process.env.ALPHAOS_CURRENT_QUOTE_MAX_AGE_SECONDS))
      : quoteHttpFailure(response.status, payload);
  } catch {
    result = deadline.aborted
      ? unavailable("request_timeout", "Quote backend request timed out.")
      : unavailable("backend_unreachable", "Quote backend could not be reached.");
  }
  console.warn(JSON.stringify({ event: "current_quote_bridge", request_id: requestId, symbol,
    timeout_ms: timeoutMs, elapsed_ms: Math.round(performance.now() - started), headers_ms: headersMs,
    upstream_status: status, outcome: result.status === "fresh" ? "fresh" : result.code }));
  return reply(result);
}
