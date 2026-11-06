/**
 * Shared Charting & AI types. Safe to import from client components: this
 * module contains no server configuration, credentials or fetching logic.
 */

export type ChartSymbol = "SPY" | "QQQ";
export const CHART_SYMBOLS: readonly ChartSymbol[] = ["SPY", "QQQ"];

export type ChartInterval = "1" | "5" | "15" | "60" | "D" | "W";
export const CHART_INTERVALS: ReadonlyArray<{ value: ChartInterval; label: string }> = [
  { value: "1", label: "1m" },
  { value: "5", label: "5m" },
  { value: "15", label: "15m" },
  { value: "60", label: "1h" },
  { value: "D", label: "1D" },
  { value: "W", label: "1W" },
];
export const DEFAULT_CHART_INTERVAL: ChartInterval = "15";

export type EvidenceMode = "current" | "point_in_time";

export type EvidenceLevel = {
  label: string;
  price: number;
  kind: "support" | "resistance" | "mid" | "atr";
  distance_pct: number | null;
  /** Cluster bounds returned by the backend; absent when it returned none. */
  zone_low?: number;
  zone_high?: number;
};

export type TrendStructure = "bullish" | "bearish" | "mixed";

export type MarketStateSummary = {
  direction: "bullish" | "bearish" | "neutral" | "unknown";
  /**
   * False when the backend reported no direction at all. `unknown` alone must
   * never be read as a neutral market; only an explicit backend `neutral` is.
   */
  direction_reported: boolean;
  /** Completed-session EMA ordering, the only trend classification `/v1/market` returns. */
  ema_structure: TrendStructure | null;
  movement_state: string | null;
  volatility_state: string | null;
  premium_state: string | null;
};

/**
 * Independently retrieved AlphaOS evidence. It never contains TradingView
 * candles, indicators, drawings or widget state.
 */
export type ChartEvidence = {
  symbol: ChartSymbol;
  mode: EvidenceMode;
  source: string;
  as_of: string;
  retrieved_at: string;
  age_seconds: number;
  spot: number;
  atr_14: number;
  levels: EvidenceLevel[];
  market_state: MarketStateSummary;
  data_status: string;
  freshness: string;
  market_session: string;
  caveats: string[];
};

export type ChartEvidenceCode =
  | "unsupported_chart_symbol"
  | "market_evidence_not_configured"
  | "market_evidence_unreachable"
  | "market_evidence_timeout"
  | "market_evidence_backend_error"
  | "market_evidence_schema_mismatch"
  | "market_evidence_mismatch";

export type ChartEvidenceFailure = {
  status: "unavailable";
  code: ChartEvidenceCode;
  message: string;
};

export type ChartEvidenceResult =
  | { status: "ok"; evidence: ChartEvidence }
  | ChartEvidenceFailure;

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatEvidenceSummary = {
  symbol: ChartSymbol;
  mode: EvidenceMode;
  source: string;
  as_of: string;
  age_seconds: number;
  spot: number;
  atr_14: number;
  levels: EvidenceLevel[];
  market_state: MarketStateSummary;
  data_status: string;
};

export type ChatSuccessBody = {
  status: "ok";
  reply: string;
  chart_access: "none";
  chart_claim_blocked: boolean;
  model: string;
  evidence: ChatEvidenceSummary;
  disclosures: string[];
};

export type ChatFailureBody = {
  status: "unavailable";
  code: string;
  message: string;
};
