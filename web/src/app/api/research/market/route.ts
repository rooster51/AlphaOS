type MarketPayload = {
  symbol: "SPY" | "QQQ";
  expiration?: string;
  available_capital?: number;
  objective?: string;
  width?: number;
};

function parseMarketPayload(value: unknown): MarketPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  const allowed = new Set(["symbol", "expiration", "available_capital", "objective", "width"]);
  if (Object.keys(input).some((key) => !allowed.has(key))) return null;

  if (typeof input.symbol !== "string") return null;
  const symbol = input.symbol.toUpperCase();
  if (symbol !== "SPY" && symbol !== "QQQ") return null;

  const payload: MarketPayload = { symbol };
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
        !Number.isFinite(input.available_capital) || input.available_capital < 0) return null;
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

function validResearchEnvelope(value: unknown, symbol: MarketPayload["symbol"]): value is Record<string, unknown> {
  const envelope = object(value);
  const request = object(envelope?.request);
  const research = object(envelope?.research);
  const archive = object(research?.archive);
  const session = object(research?.research_session);
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

async function readErrorPayload(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError) return null;
    throw error;
  }
}

/**
 * Read-only research bridge. Raw upstream evidence is intentionally NOT
 * converted into trade candidates or advertised as executable prices.
 * Credentials remain server-side.
 */
export async function POST(request: Request) {
  let payload: MarketPayload | null;
  try {
    payload = parseMarketPayload(await request.json());
  } catch {
    payload = null;
  }
  if (!payload) {
    return Response.json({ error: "Invalid research request" }, { status: 400 });
  }

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

  let response: Response;
  try {
    response = await fetch(new URL("/v1/research/market", origin), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(12000),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    if (!timedOut && !(error instanceof TypeError)) throw error;
    return Response.json(
      { status: "unavailable", code: timedOut ? "backend_timeout" : "backend_unreachable" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (!response.ok) {
    const code = upstreamErrorCode(await readErrorPayload(response));
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
                : response.status === 422
                  ? "backend_rejected_request"
                  : "backend_http_error";
    return Response.json(
      { status: "unavailable", code: detail },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  let responsePayload: unknown;
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
  }
  if (!validResearchEnvelope(responsePayload, payload.symbol)) {
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
