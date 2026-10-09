import { validEnvelope, verifiedMarketPair } from "./research-evidence";
import { MarketSnapshot, ResearchCandidate } from "@/types/research";
import { MOCK_MARKET_SNAPSHOTS, MOCK_CANDIDATES } from "./mock-data";

const API_BASE = process.env.ALPHAOS_API_URL || "https://alphaos.onrender.com";
const API_TOKEN = process.env.ALPHAOS_API_TOKEN || "";
const DEMO = process.env.ALPHAOS_DEMO_MODE === "true";
type JsonObject = Record<string, unknown>;

function record(value: unknown): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject) : {};
}
function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
function symbolValue(symbol: string): "QQQ" | "SPY" {
  const norm = symbol.toUpperCase();
  if (norm !== "QQQ" && norm !== "SPY") throw new Error("Unsupported market symbol");
  return norm;
}
async function research(path: string): Promise<JsonObject> {
  if (!API_TOKEN) throw new Error("Research backend not configured");
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${API_TOKEN}`, Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Research API unavailable (HTTP ${response.status})`);
  const body = record(await response.json());
  if (
    body.error ||
    Object.keys(record(body.meta)).length === 0 ||
    Object.keys(record(body.evidence)).length === 0
  ) {
    throw new Error("Research response schema is unavailable");
  }
  return body;
}

/** Only actual, explicitly verified provider observations can be displayed as live. */
export async function getMarketSnapshotServer(symbol: string): Promise<{
  data: MarketSnapshot;
  isLive: boolean;
  warning?: string;
}> {
  const normSymbol = symbolValue(symbol);
  if (DEMO) {
    return {
      data: { ...MOCK_MARKET_SNAPSHOTS[normSymbol], source: "mock_fixture" },
      isLive: false,
      warning: "DEMO MODE: these are synthetic example prices and signals, never market observations.",
    };
  }
  // The original frontend expected context/structure fields that are not part
  // of the real API. Query both documented endpoints and validate the envelope.
  const [market, structure] = await Promise.all([
    research(`/v1/market/${normSymbol}?horizon=3`),
    research(`/v1/structure/${normSymbol}?horizon=3`),
  ]);
  const meta = record(market.meta);
  const marketEvidence = record(market.evidence);
  const structureEvidence = record(structure.evidence);
  const quotedSpot = meta.current_spot;
  const atr = structureEvidence.atr;
  const observedAt = meta.quote_as_of;
  if (!verifiedMarketPair(market, structure, normSymbol) ||
      !finitePositive(quotedSpot) || !finitePositive(atr) ||
      typeof observedAt !== "string") {
    throw new Error("No verified, fresh, matching market/structure evidence available");
  }
  const state = record(marketEvidence.market_state);
  const allowedDirection = ["bullish", "bearish", "neutral"];
  const direction = allowedDirection.includes(String(state.direction))
    ? state.direction as "bullish" | "bearish" | "neutral" : "unknown";
  const rawLevels = structureEvidence.levels;
  const levels = Array.isArray(rawLevels) ? rawLevels.flatMap((row) => {
    const value = record(row);
    if (typeof value.label !== "string" || !finitePositive(value.price)) return [];
    const kind = ["support", "resistance", "mid", "atr"].includes(String(value.kind))
      ? value.kind as "support" | "resistance" | "mid" | "atr" : "mid";
    return [{
      label: value.label, price: value.price,
      distance: typeof value.distance === "number" && Number.isFinite(value.distance) ? value.distance : value.price - quotedSpot,
      distance_pct: typeof value.distance_pct === "number" && Number.isFinite(value.distance_pct)
        ? value.distance_pct : (value.price - quotedSpot) / quotedSpot * 100,
      kind,
    }];
  }) : [];
  return {
    data: {
      symbol: normSymbol, current_spot: quotedSpot, as_of: observedAt,
      source: "live_public", atr_14: atr, levels,
      opportunity_state: {
        direction, premium_state: "unknown", movement_state: "unknown",
        time_state: "unknown", volatility_state: "unknown",
        evidence: {}, caveats: [
          "Direction/volatility/premium classifications are unavailable unless independently validated.",
          "A fresh underlying quote is not an executable options quote.",
        ],
        classified_at: observedAt,
      },
    },
    isLive: true,
    warning: "Live underlying observation only. Unverified regime dimensions remain unknown.",
  };
}

/** No fixture candidate ever enters the normal research pathway. */
export async function getStrategyCandidatesServer(symbol: string): Promise<{
  candidates: ResearchCandidate[];
  isLive: boolean;
}> {
  const normalized = symbol.toUpperCase();
  if (normalized !== "ALL") symbolValue(normalized);
  if (DEMO) {
    return {
      candidates: MOCK_CANDIDATES.filter(c => normalized === "ALL" || c.symbol === normalized),
      isLive: false,
    };
  }
  // The actual /v1/research/market contract is not interchangeable with the
  // fixture ResearchCandidate schema. Show no candidates until an audited adapter exists.
  return { candidates: [], isLive: false };
}
