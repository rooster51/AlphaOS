import { loadChartEvidence, logEvidenceTiming } from "../../../../lib/chart-evidence.ts";
import type { EvidenceTiming } from "../../../../lib/chart-evidence.ts";
import type { ChartEvidenceCode } from "../../../../lib/chart-types.ts";

const STATUS: Record<ChartEvidenceCode, number> = {
  unsupported_chart_symbol: 400,
  market_evidence_not_configured: 503,
  market_evidence_unreachable: 502,
  market_evidence_timeout: 504,
  market_evidence_backend_error: 502,
  market_evidence_schema_mismatch: 502,
  market_evidence_mismatch: 502,
};

/** Read-only evidence endpoint; credentials stay server-side. */
export async function GET(request: Request) {
  const symbol = new URL(request.url).searchParams.get("symbol") ?? "";
  const captured: { timing?: EvidenceTiming } = {};
  const result = await loadChartEvidence(symbol, {
    onTiming: (value) => { captured.timing = value; },
  });
  logEvidenceTiming("charts_evidence_timing", captured.timing,
    result.status === "ok" ? "ok" : result.code);
  if (result.status === "unavailable") {
    return Response.json(
      { status: "unavailable", code: result.code, message: result.message },
      { status: STATUS[result.code], headers: { "Cache-Control": "private, no-store", Vary: "Cookie" } },
    );
  }
  return Response.json(result, {
    headers: { "Cache-Control": "private, no-store", Vary: "Cookie" },
  });
}
