// Legacy URL now delegates to the same authenticated Release 1 bridge.
// Explicit symbol/capital/expiration use the same validation and response contract.
export { POST } from "../research/market/route";
import { POST } from "../research/market/route";
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const payload: Record<string, unknown> = {symbol: params.get("symbol")};
  for (const key of ["available_capital", "width"]) {
    if (params.has(key)) payload[key] = params.get(key)?.trim() ? Number(params.get(key)) : null;
  }
  if (params.has("expiration")) payload.expiration = params.get("expiration");
  if (params.has("research_mode")) payload.research_mode = params.get("research_mode");
  return POST(new Request(request.url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}));
}
