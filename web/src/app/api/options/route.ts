import { record } from "../../../lib/market-candidates.ts";
import { readRuntimeBindings } from "#alphaos-runtime";
import { getServerConfig } from "../../../lib/server-config.ts";
import { validSessionCookie } from "../../../lib/website-auth.ts";
import { validResearchRequest, validResearchResults, stableJSON, type ResearchRequest } from "../../../lib/options-research.ts";

async function optionsResponse(request: Request, research?: ResearchRequest) {
  const requestId = crypto.randomUUID().replaceAll("-", "");
  const reply = (body: unknown, status = 200) => Response.json(body, {
    status, headers: { "Cache-Control": "private, no-store", Vary: "Cookie", "X-AlphaOS-Request-ID": requestId },
  });
  const { bindings } = readRuntimeBindings();
  if (!await validSessionCookie(request, {
    ALPHAOS_PASSWORD_HASH: bindings.ALPHAOS_PASSWORD_HASH,
    ALPHAOS_SESSION_KEY: bindings.ALPHAOS_SESSION_KEY,
  })) return reply({ code: "authentication_failure" }, 401);

  const query = new URL(request.url).searchParams;
  const symbol = query.get("symbol");
  const expiration = query.get("expiration");
  const buy = query.get("buy");
  const sell = query.get("sell");
  const contract = /^[A-Z]+ *\d{6}[CP]\d{8}$/;
  if ((symbol !== "SPY" && symbol !== "QQQ")
      || (expiration !== null && !/^\d{4}-\d{2}-\d{2}$/.test(expiration))
      || (buy !== null && (!expiration || buy.length > 32 || !contract.test(buy)))
      || (sell !== null && (!buy || sell.length > 32 || !contract.test(sell)))
      || (request.method === "POST" && (!research || !expiration || buy || sell))) {
    return reply({ code: "invalid_options_request" }, 400);
  }

  const { base, token, diagnostics } = getServerConfig();
  if (!base || !token || diagnostics.configuration !== "ready") {
    return reply({ code: "backend_not_configured" }, 503);
  }
  const url = new URL(expiration ? `/v1/options/${symbol}/chain/${expiration}` :
    `/v1/options/${symbol}/expirations`, base);
  if (expiration && !research) {
    url.searchParams.set("explicit", "true");
    url.searchParams.set("refresh", buy ? "false" : "true");
  }
  if (buy) url.searchParams.set("buy", buy);
  if (sell) url.searchParams.set("sell", sell);
  const deadline = AbortSignal.timeout(8000);
  const started = performance.now();
  let status: number | undefined;
  let correlated: boolean | undefined;
  try {
    const response = await fetch(url, {
      method: research ? "POST" : "GET",
      body: research ? JSON.stringify(research) : undefined,
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json", "Content-Type": "application/json", "X-AlphaOS-Request-ID": requestId },
      cache: "no-store", redirect: "error", signal: AbortSignal.any([deadline, request.signal]),
    });
    status = response.status;
    correlated = response.headers.get("X-AlphaOS-Request-ID") === requestId;
    const payload = record(await response.json());
    const evidence = record(payload.evidence);
    const chain = record(evidence.chain);
    if (!response.ok) {
      const code = record(payload.error).code;
      return reply({ code: typeof code === "string" && /^[a-z_]{1,64}$/.test(code) ? code : "backend_rejected_request" }, status);
    }
    if (record(payload.meta).symbol !== symbol || (research
      ? evidence.symbol !== symbol || evidence.expiration !== expiration || evidence.source !== "Public"
        || stableJSON(evidence.request) !== stableJSON(research)
        || !validResearchResults(evidence.scenarios, research)
        || (evidence.scenarios as Record<string, unknown>[]).some(result =>
          result.legs && (result.expiration !== expiration || result.symbol !== symbol))
      : expiration
      ? chain.symbol !== symbol || chain.expiration !== expiration || evidence.source !== "Public"
        || !Array.isArray(chain.calls) || !Array.isArray(chain.puts)
      : !Array.isArray(evidence.expirations) || evidence.expirations.some(date =>
        typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)))) {
      return reply({ code: "response_schema_mismatch" }, 502);
    }
    return reply(evidence);
  } catch {
    return reply({ code: deadline.aborted ? "request_timeout" : "backend_unreachable" }, deadline.aborted ? 504 : 502);
  } finally {
    console.info(JSON.stringify({ event: "option_chain_bridge", symbol, request_id: requestId,
      elapsed_ms: Math.round(performance.now() - started), upstream_status: status, backend_correlated: correlated }));
  }
}

export async function GET(request: Request) {
  return optionsResponse(request);
}

export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  if (request.headers.get("origin") !== origin || request.headers.get("sec-fetch-site") === "cross-site") {
    return Response.json({ code: "csrf_rejected" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  // Bound the streamed body as well as requests with Content-Length.
  const reader = request.body?.getReader();
  let text = "";
  let size = 0;
  const decoder = new TextDecoder();
  try {
    if (!reader) throw new Error();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 20000) {
        await reader.cancel();
        throw new Error();
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    const payload: unknown = JSON.parse(text);
    if (!validResearchRequest(payload)) throw new Error();
    return optionsResponse(request, payload);
  } catch {
    return Response.json({ code: "invalid_options_request" }, { status: 400, headers: { "Cache-Control": "no-store" } });
  } finally {
    reader?.releaseLock();
  }
}
