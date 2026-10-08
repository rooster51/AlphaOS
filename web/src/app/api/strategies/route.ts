import { NextRequest, NextResponse } from "next/server";
import { getStrategyCandidatesServer } from "@/lib/alphaos-server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const symbol = searchParams.get("symbol") || "ALL";

  const result = await getStrategyCandidatesServer(symbol);
  return NextResponse.json(result);
}
