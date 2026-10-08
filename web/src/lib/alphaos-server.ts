import { MarketSnapshot, ResearchCandidate } from "@/types/research";
import { MOCK_MARKET_SNAPSHOTS, MOCK_CANDIDATES } from "./mock-data";

const API_BASE = process.env.ALPHAOS_API_URL || "https://alphaos.onrender.com";
const API_TOKEN = process.env.ALPHAOS_API_TOKEN || "";

/**
 * Server-only client for querying the AlphaOS FastAPI backend.
 * Falls back safely to labeled mock data when the backend is unreachable or in development.
 */
export async function getMarketSnapshotServer(symbol: string): Promise<{
  data: MarketSnapshot;
  isLive: boolean;
  warning?: string;
}> {
  const normSymbol = symbol.toUpperCase();

  if (!API_TOKEN) {
    const mock = MOCK_MARKET_SNAPSHOTS[normSymbol] || MOCK_MARKET_SNAPSHOTS["QQQ"];
    return {
      data: mock,
      isLive: false,
      warning: "ALPHAOS_API_TOKEN not configured on server; displaying labeled research fixture.",
    };
  }

  try {
    const res = await fetch(`${API_BASE}/v1/market/${normSymbol}?horizon=3`, {
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        Accept: "application/json",
      },
      next: { revalidate: 60 },
    });

    if (!res.ok) {
      throw new Error(`API returned HTTP ${res.status}`);
    }

    const json = await res.json();
    return {
      data: {
        symbol: normSymbol,
        current_spot: json.context?.spot || 0,
        as_of: json.context?.as_of || new Date().toISOString(),
        source: "verified_archive",
        atr_14: json.structure?.atr || 5.0,
        opportunity_state: {
          direction: json.market_state?.direction || "unknown",
          premium_state: json.market_state?.premium_state || "unknown",
          movement_state: json.market_state?.movement_state || "unknown",
          time_state: json.market_state?.time_state || "unknown",
          volatility_state: json.market_state?.volatility_state || "unknown",
          evidence: json.market_state?.evidence || {},
          caveats: json.market_state?.caveats || [],
          classified_at: json.timing?.classified_at || new Date().toISOString(),
        },
        levels: json.structure?.levels || [],
      },
      isLive: true,
    };
  } catch (err: any) {
    const mock = MOCK_MARKET_SNAPSHOTS[normSymbol] || MOCK_MARKET_SNAPSHOTS["QQQ"];
    return {
      data: mock,
      isLive: false,
      warning: `Backend connection unavailable (${err?.message || "error"}); displaying labeled research fixture.`,
    };
  }
}

export async function getStrategyCandidatesServer(symbol: string): Promise<{
  candidates: ResearchCandidate[];
  isLive: boolean;
}> {
  return {
    candidates: MOCK_CANDIDATES.filter((c) => c.symbol === symbol.toUpperCase() || symbol === "ALL"),
    isLive: false,
  };
}
