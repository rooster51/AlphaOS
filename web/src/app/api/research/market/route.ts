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

function validResearchEnvelope(value: unknown, symbol: MarketPayload["symbol"]): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const envelope = value as Record<string, unknown>;
  const request = envelope.request;
  return envelope.schema_version === "alphaos-interface-v2" &&
    envelope.read_only === true &&
    !!request && typeof request === "object" && !Array.isArray(request) &&
    (request as Record<string, unknown>).symbol === symbol &&
    !!envelope.research && typeof envelope.research === "object" && !Array.isArray(envelope.research) &&
    !!envelope.provenance && typeof envelope.provenance === "object" && !Array.isArray(envelope.provenance) &&
    Array.isArray(envelope.caveats);
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
    return Response.json({ error: "Research backend not configured" }, { status: 503 });
  }

  let origin: URL;
  try {
    origin = new URL(base);
    if (origin.protocol !== "https:" || origin.username || origin.password ||
        origin.search || origin.hash) throw new Error("Invalid backend URL");
  } catch {
    return Response.json({ error: "Invalid backend configuration" }, { status: 503 });
  }

  try {
    const response = await fetch(new URL("/v1/research/market", origin), {
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
    if (!response.ok) {
      return Response.json({ error: "Research backend unavailable" }, { status: 502 });
    }
    const responsePayload: unknown = await response.json();
    if (!validResearchEnvelope(responsePayload, payload.symbol)) {
      return Response.json({ error: "Invalid research response" }, { status: 502 });
    }
    return Response.json(
      { research: responsePayload, verified_for_trading: false, source: "alphaos_research_api" },
      { headers: { "Cache-Control": "no-store" } }
    );
  } catch {
    return Response.json({ error: "Research request failed" }, { status: 502 });
  }
}
