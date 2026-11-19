import { readRuntimeBindings } from "#alphaos-runtime";
import { sessionRole } from "@/lib/website-auth";
import { NextRequest, NextResponse } from "next/server";
import { getMarketSnapshotServer } from "@/lib/alphaos-server";
import { ResearchUnavailableError } from "@/lib/research-evidence";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const symbol = searchParams.get("symbol") || "QQQ";

  try {
    const result = await getMarketSnapshotServer(symbol);
    const trade = result.trade_intelligence;
    if (trade && Object.hasOwn(trade, "provisional_research")) {
      const { bindings } = readRuntimeBindings();
      const role = await sessionRole(request, {
        ALPHAOS_PASSWORD_HASH: bindings.ALPHAOS_PASSWORD_HASH,
        ALPHAOS_SESSION_KEY: bindings.ALPHAOS_SESSION_KEY,
      });
      const provisional = trade.provisional_research as { owner_private_display_allowed?: boolean } | null;
      if (role !== "owner" || provisional?.owner_private_display_allowed !== true) {
        delete trade.provisional_research;
      }
    }
    return NextResponse.json(result, {
      headers: { "Cache-Control": "private, no-store", Vary: "Cookie" },
    });
  } catch (error) {
    if (error instanceof Error && error.message === "Unsupported market symbol") {
      return NextResponse.json(
        { status: "invalid_request", error: "Unsupported market symbol" },
        { status: 400, headers: { "Cache-Control": "no-store" } },
      );
    }
    if (!(error instanceof ResearchUnavailableError)) throw error;
    return NextResponse.json(
      {
        status: "unavailable",
        code: error.code ?? "market_evidence_unavailable",
        stage: error.stage,
        upstream_code: error.upstreamCode,
        error: "Market research is unavailable; no market data was substituted.",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
