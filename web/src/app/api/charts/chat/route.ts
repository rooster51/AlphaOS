import { readRuntimeBindings } from "#alphaos-runtime";
import { loadChartEvidence } from "../../../../lib/chart-evidence.ts";
import {
  buildChatRequestBody,
  chatConfiguration,
  detectChartAccessClaim,
  evidenceSummary,
  parseChatCompletion,
  parseChatRequest,
  SAFE_CHART_CLAIM_REPLY,
  disclosuresFor,
} from "../../../../lib/chart-chat.ts";

const CHAT_TIMEOUT_MS = 25_000;
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 30;
const attempts = new Map<string, { count: number; resetAt: number }>();

/** Runtime bindings: process.env on Node/Netlify, the Worker env on Cloudflare. */
function chatEnv(): Record<string, string | undefined> {
  const values = readRuntimeBindings().bindings as Record<string, unknown>;
  const pick = (name: string) =>
    typeof values[name] === "string" ? values[name] as string : undefined;
  return {
    ALPHAOS_CHAT_API_KEY: pick("ALPHAOS_CHAT_API_KEY"),
    ALPHAOS_CHAT_MODEL: pick("ALPHAOS_CHAT_MODEL"),
    ALPHAOS_CHAT_API_URL: pick("ALPHAOS_CHAT_API_URL"),
  };
}

function clientKey(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  return forwarded?.split(",")[0]?.trim() || request.headers.get("x-real-ip") || "unknown";
}

/** Bounded in-process protection for the cost-bearing model endpoint. */
function rateLimited(request: Request, now = Date.now()): boolean {
  const key = clientKey(request);
  const entry = attempts.get(key);
  if (!entry || entry.resetAt <= now) {
    attempts.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }
  entry.count += 1;
  if (attempts.size > 500) {
    for (const [candidate, value] of attempts) {
      if (value.resetAt <= now) attempts.delete(candidate);
    }
  }
  return entry.count > RATE_LIMIT_MAX;
}

/** Reject browser cross-origin calls; requests without Origin are non-browser. */
function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  try {
    const parsed = new URL(origin).host.toLowerCase();
    // Proxies may rewrite Host; accept either forwarded or direct host.
    const hosts = [request.headers.get("host"), request.headers.get("x-forwarded-host")]
      .filter((value): value is string => Boolean(value))
      .flatMap((value) => value.split(","))
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean);
    return hosts.includes(parsed);
  } catch {
    return false;
  }
}

function unavailable(status: number, code: string, message: string) {
  return Response.json(
    { status: "unavailable", code, message },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: Request) {
  if (!sameOrigin(request)) {
    return unavailable(403, "cross_origin_rejected",
      "Cross-origin chat requests are rejected.");
  }
  if (rateLimited(request)) {
    return unavailable(429, "chat_rate_limited",
      "Too many assistant requests from this client. Wait briefly and try again.");
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return unavailable(400, "invalid_request", "The chat request could not be parsed.");
  }
  const parsed = parseChatRequest(payload);
  if (!parsed) {
    return unavailable(400, "invalid_request",
      "The chat request is invalid: a supported symbol and a bounded user/assistant message history are required.");
  }

  const configuration = chatConfiguration(chatEnv());
  if (!configuration.configured) {
    return unavailable(503, "chat_not_configured", configuration.message);
  }

  // Grounding evidence is fetched independently on every request.
  const evidenceResult = await loadChartEvidence(parsed.symbol);
  if (evidenceResult.status === "unavailable") {
    return unavailable(503, evidenceResult.code, evidenceResult.message);
  }
  const evidence = evidenceResult.evidence;

  let upstream: Response;
  try {
    upstream = await fetch(configuration.endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${configuration.key}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(buildChatRequestBody(configuration, evidence, parsed.messages)),
      cache: "no-store",
      signal: AbortSignal.any([AbortSignal.timeout(CHAT_TIMEOUT_MS), request.signal]),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError");
    return unavailable(
      timedOut ? 504 : 502,
      timedOut ? "chat_timeout" : "chat_provider_error",
      timedOut
        ? "The AI assistant did not answer in time. No answer was generated; try again."
        : "The AI assistant provider could not be reached. No answer was generated.",
    );
  }

  if (!upstream.ok) {
    // Provider error bodies are never forwarded: they can contain request metadata.
    return unavailable(502, "chat_provider_error",
      "The AI assistant provider rejected the request. No answer was generated.");
  }

  let body: unknown;
  try {
    body = await upstream.json();
  } catch {
    return unavailable(502, "chat_response_invalid",
      "The AI assistant provider returned an unreadable response.");
  }
  const reply = parseChatCompletion(body);
  if (!reply) {
    return unavailable(502, "chat_response_invalid",
      "The AI assistant provider returned an empty or malformed answer.");
  }

  const chartClaimBlocked = detectChartAccessClaim(reply);
  if (chartClaimBlocked) {
    console.warn(JSON.stringify({
      event: "charts_chat_guardrail",
      symbol: evidence.symbol,
      outcome: "chart_access_claim_blocked",
    }));
  }

  return Response.json(
    {
      status: "ok",
      reply: chartClaimBlocked ? SAFE_CHART_CLAIM_REPLY : reply,
      chart_access: "none",
      chart_claim_blocked: chartClaimBlocked,
      model: configuration.model,
      evidence: evidenceSummary(evidence),
      disclosures: disclosuresFor(evidence),
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
