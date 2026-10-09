import { NextRequest, NextResponse } from "next/server";
import { getMarketSnapshotServer } from "@/lib/alphaos-server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const symbol = searchParams.get("symbol") || "QQQ";

  const result = await getMarketSnapshotServer(symbol);
  return NextResponse.json(result);
}
