import { NextRequest, NextResponse } from "next/server";

/**
 * Read-only research bridge. Raw upstream evidence is intentionally NOT
 * converted into trade candidates or advertised as executable prices.
 * Credentials remain server-side.
 */
export async function GET(request: NextRequest) {
  const symbol = (request.nextUrl.searchParams.get("symbol") || "").toUpperCase();
  if (symbol !== "SPY" && symbol !== "QQQ") {
    return NextResponse.json({ error: "Unsupported symbol" }, { status: 400 });
  }

  const token = process.env.ALPHAOS_API_TOKEN;
  const base = process.env.ALPHAOS_API_URL;
  if (!token || !base) {
    return NextResponse.json({ error: "Research backend not configured" }, { status: 503 });
  }

  let origin: URL;
  try {
    origin = new URL(base);
    if (origin.protocol !== "https:" || origin.username || origin.password ||
        origin.search || origin.hash) throw new Error("Invalid backend URL");
  } catch {
    return NextResponse.json({ error: "Invalid backend configuration" }, { status: 503 });
  }

  try {
    const endpoint = new URL("/v1/research/market", origin);
    endpoint.searchParams.set("symbol", symbol);
    const response = await fetch(endpoint, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(12000),
    });
    if (!response.ok) {
      return NextResponse.json({ error: "Research backend unavailable" }, { status: 502 });
    }
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return NextResponse.json({ error: "Invalid research response" }, { status: 502 });
    }
    return NextResponse.json(
      { research: payload, verified_for_trading: false, source: "alphaos_research_api" },
      { headers: { "Cache-Control": "no-store" } }
    );
  } catch {
    return NextResponse.json({ error: "Research request failed" }, { status: 502 });
  }
}
