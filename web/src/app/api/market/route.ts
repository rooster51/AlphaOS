import { NextRequest, NextResponse } from "next/server";
import { getMarketSnapshotServer } from "@/lib/alphaos-server";
import { ResearchUnavailableError } from "@/lib/research-evidence";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const symbol = searchParams.get("symbol") || "QQQ";

  try {
    const result = await getMarketSnapshotServer(symbol);
    return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
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
        error: "Market research is unavailable; no market data was substituted.",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
