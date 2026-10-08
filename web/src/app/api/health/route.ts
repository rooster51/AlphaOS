import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    service: "alphaos-web-bff",
    timestamp: new Date().toISOString(),
    api_connected: Boolean(process.env.ALPHAOS_API_URL),
    mode: "read_only",
  });
}
