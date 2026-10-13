export async function GET() {
  // Process health only; do not imply verified API credentials or market freshness.
  return Response.json({
    status: "ok",
    service: "alphaos-web-bff",
    mode: "read_only",
    backend_verification: "not_assessed",
    market_freshness: "not_assessed",
    account_access: "disabled",
  }, { headers: { "Cache-Control": "no-store" } });
}
