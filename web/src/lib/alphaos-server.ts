import { fetchResearchEnvelope, supportedMarketSymbol, verifiedMarketPair, ResearchUnavailableError } from "./research-evidence.ts";
import type { MarketSnapshot } from "../types/research.ts";
import { MOCK_MARKET_SNAPSHOTS } from "./mock-data.ts";
import { getServerConfig } from "./server-config.ts";

type JsonObject = Record<string, unknown>;
type TradeIntelligenceStatus =
  | "available"
  | "endpoint_not_deployed"
  | "contract_invalid"
  | "backend_rejected_request"
  | "provider_unavailable";
type OptionalTradeIntelligence = {
  data: JsonObject | null;
  status: TradeIntelligenceStatus;
  warning?: string;
};

const MARKET_REQUEST_TIMEOUT_MS = 10_000;
// The optional contract must not consume the bridge's whole response budget.
const TRADE_INTELLIGENCE_TIMEOUT_MS = 3_500;

function record(value: unknown): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject) : {};
}
function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
function symbolValue(symbol: string): "QQQ" | "SPY" {
  return supportedMarketSymbol(symbol);
}

function percentPoints(value: unknown): number | null {
  // /v1/structure reports price_structure.distance_pct as a decimal fraction
  // (for example -0.0197). The browser contract stores percentage points.
  return typeof value === "number" && Number.isFinite(value) ? value * 100 : null;
}

function classifyTradeIntelligenceError(
  error: ResearchUnavailableError,
): { status: TradeIntelligenceStatus; warning: string } {
  if (error.status === 404 || error.status === 405) {
    return {
      status: "endpoint_not_deployed",
      warning:
        `Verified setup evidence is unavailable: the research backend does not expose the ` +
        `Phase 2 trade-intelligence route (HTTP ${error.status}). This is a backend-version ` +
        `mismatch, not a market-data failure. Market and structure evidence remain available; ` +
        `no setup state was inferred.`,
    };
  }
  if (error.status === 401 || error.status === 403) {
    return {
      status: "backend_rejected_request",
      warning:
        `Verified setup evidence is unavailable: the research backend rejected the authenticated ` +
        `request (HTTP ${error.status}). This is a bridge authorization/configuration failure, ` +
        `not missing market evidence; no setup state was inferred.`,
    };
  }
  if (error.status === 400 || error.status === 422) {
    return {
      status: "backend_rejected_request",
      warning:
        `Verified setup evidence is unavailable: the research backend rejected the request ` +
        `parameters (HTTP ${error.status}). This is a frontend/backend contract incompatibility, ` +
        `not a validated market state; no setup state was inferred.`,
    };
  }
  return {
    status: "provider_unavailable",
    warning:
      `Verified setup evidence is unavailable because the research backend request failed` +
      `${error.status ? ` (HTTP ${error.status})` : ""}. No BUY, SELL, entry, or invalidation ` +
      `was inferred; this is not a substitute for verified market evidence.`,
  };
}

function priceReference(value: unknown): boolean {
  if (value === null) return true;
  const row = record(value);
  return finitePositive(row.price) && typeof row.condition === "string";
}

/** Validate only the derived setup contract; raw candles are never accepted. */
function validTradeIntelligence(value: unknown, symbol: string): boolean {
  const envelope = record(value);
  const evidence = record(envelope.evidence);
  if (evidence.schema_version !== "alphaos-trade-intelligence-v1") return false;
  if (evidence.symbol !== symbol || "candles" in evidence || "bars" in evidence) return false;
  const session = record(evidence.session);
  const data = record(evidence.data);
  const levels = record(evidence.levels);
  const previous = record(levels.previous_session);
  const pivots = record(levels.pivots);
  const opening = record(levels.opening_range);
  const vwap = record(levels.vwap);
  const ema9 = record(levels.ema9);
  if (!["open", "closed", "preopen", "unknown"].includes(String(session.state))) return false;
  if (!["verified", "incomplete", "stale", "unavailable"].includes(String(data.status))) return false;
  if (!["high", "low", "close"].every((key) => finitePositive(previous[key]))) return false;
  if (!["pivot", "r1", "r2", "s1", "s2"].every((key) => finitePositive(pivots[key]))) return false;
  const openingAvailable = finitePositive(opening.high) && finitePositive(opening.low);
  const openingNotYet = (opening.high === null || opening.high === undefined)
    && (opening.low === null || opening.low === undefined);
  if (!openingAvailable && !openingNotYet) return false;
  if (!(vwap.price === null || finitePositive(vwap.price))) return false;
  if (!(ema9.price === null || finitePositive(ema9.price))) return false;
  if (!Array.isArray(levels.references) || !levels.references.every((item) => {
    const level = record(item);
    return typeof level.label === "string" && finitePositive(level.price)
      && ["support", "resistance", "mid"].includes(String(level.kind));
  })) return false;
  if (!Array.isArray(evidence.setups) || evidence.setups.length < 3) return false;
  return evidence.setups.every((item) => {
    const setup = record(item);
    return typeof setup.id === "string" && typeof setup.name === "string"
      && ["BUY", "SELL", "WAIT"].includes(String(setup.state))
      && ["bullish", "bearish", "neutral", "unknown"].includes(String(setup.direction))
      && Array.isArray(setup.evidence) && Array.isArray(setup.missing_conditions)
      && (setup.wait_reason === null || typeof setup.wait_reason === "string")
      && priceReference(setup.entry_trigger) && priceReference(setup.invalidation)
      && priceReference(setup.stop_reference) && priceReference(setup.target_reference)
      && (setup.risk === null || (typeof record(setup.risk).underlying_risk_distance === "number"));
  });
}
async function research(
  path: string,
  timeoutMs = MARKET_REQUEST_TIMEOUT_MS,
): Promise<JsonObject> {
  const { base, token, diagnostics } = getServerConfig();
  if (!base || !token || diagnostics.configuration !== "ready") {
    throw new ResearchUnavailableError(
      "Research backend not configured", null, "backend_not_configured",
    );
  }
  return await fetchResearchEnvelope(`${base}${path}`, token, fetch, timeoutMs);
}

/** Optional evidence: every failure is contained so market/structure survive. */
async function loadTradeIntelligence(symbol: "QQQ" | "SPY"): Promise<OptionalTradeIntelligence> {
  try {
    const candidate = await research(
      `/v1/research/trade-intelligence/${symbol}?horizon=3`,
      TRADE_INTELLIGENCE_TIMEOUT_MS,
    );
    if (validTradeIntelligence(candidate, symbol)) {
      return { data: record(candidate.evidence), status: "available" };
    }
    return {
      data: null,
      status: "contract_invalid",
      warning:
        "Verified setup evidence is unavailable: the backend responded, but the setup contract " +
        "did not pass validation. This is a contract/version mismatch, not a market-data failure; " +
        "no setup state was inferred.",
    };
  } catch (error) {
    if (error instanceof ResearchUnavailableError) {
      const classified = classifyTradeIntelligenceError(error);
      return { data: null, ...classified };
    }
    return {
      data: null,
      status: "provider_unavailable",
      warning:
        "Verified setup evidence is unavailable because the optional trade-intelligence request " +
        "failed unexpectedly. Market and structure evidence remain available; no setup state was inferred.",
    };
  }
}

/** Only actual, explicitly verified provider observations can be displayed as live. */
export async function getMarketSnapshotServer(symbol: string): Promise<{
  data: MarketSnapshot;
  isLive: boolean;
  warning?: string;
  trade_intelligence?: JsonObject | null;
  trade_intelligence_status?: TradeIntelligenceStatus;
  trade_intelligence_warning?: string;
}> {
  const normSymbol = symbolValue(symbol);
  if (getServerConfig().demo) {
    return {
      data: { ...MOCK_MARKET_SNAPSHOTS[normSymbol], source: "mock_fixture" },
      isLive: false,
      warning: "DEMO MODE: these are synthetic example prices and signals, never market observations.",
    };
  }
  // The original frontend expected context/structure fields that are not part
  // of the real API. Query both documented endpoints and validate the envelope.
  const market = await research(`/v1/market/${normSymbol}?horizon=3`);
  const marketMeta = record(market.meta);
  if (typeof marketMeta.snapshot_id !== "string" || !marketMeta.snapshot_id) {
    throw new ResearchUnavailableError(
      "No verified market snapshot identifier available",
      503,
      "market_snapshot_unavailable",
    );
  }
  // Structure depends on the market snapshot; the optional trade contract does
  // not, so run it alongside structure rather than adding its latency afterward.
  const structurePromise = research(
    `/v1/structure/${normSymbol}?horizon=3&snapshot_id=${encodeURIComponent(marketMeta.snapshot_id)}`
  );
  const tradePromise = loadTradeIntelligence(normSymbol);
  const [structure, trade] = await Promise.all([structurePromise, tradePromise]);
  const {
    data: tradeIntelligence,
    status: tradeIntelligenceStatus,
    warning: tradeIntelligenceWarning,
  } = trade;
  const meta = record(market.meta);
  const marketEvidence = record(market.evidence);
  const structureEvidence = record(structure.evidence);
  const quotedSpot = meta.current_spot;
  const atr = structureEvidence.atr;
  const observedAt = meta.quote_as_of;
  if (!verifiedMarketPair(market, structure, normSymbol)) {
    const quality = record(meta.quote_freshness);
    const code = quality.market_state === "closed" || quality.data_status === "latest_available"
      ? "market_closed" : "market_evidence_unavailable";
    throw new ResearchUnavailableError(
      "No verified, fresh, matching market/structure evidence available",
      503,
      code,
    );
  }
  if (!finitePositive(quotedSpot) || !finitePositive(atr) ||
      typeof observedAt !== "string") {
    throw new ResearchUnavailableError(
      "No verified, fresh, matching market/structure evidence available",
      503,
      "market_evidence_unavailable",
    );
  }
  const state = record(marketEvidence.market_state);
  const allowedDirection = ["bullish", "bearish", "neutral"];
  const direction = allowedDirection.includes(String(state.direction))
    ? state.direction as "bullish" | "bearish" | "neutral" : "unknown";
  const rawLevels = structureEvidence.levels;
  const levels = Array.isArray(rawLevels) ? rawLevels.flatMap((row) => {
    const value = record(row);
    const rawPrice = finitePositive(value.price) ? value.price
      : finitePositive(value.level) ? value.level : null;
    if (rawPrice === null) return [];
    const rawKind = value.kind ?? value.side;
    const kind = ["support", "resistance", "mid", "atr"].includes(String(rawKind))
      ? rawKind as "support" | "resistance" | "mid" | "atr" : "mid";
    const source = typeof value.sources === "string" ? ` (${value.sources})` : "";
    const label = typeof value.label === "string" && value.label.trim()
      ? value.label : `${kind}${source}`;
    const rawDistance = typeof value.distance === "number" && Number.isFinite(value.distance)
      ? value.distance : rawPrice - quotedSpot;
    const rawDistancePct = percentPoints(value.distance_pct)
      ?? (rawPrice - quotedSpot) / quotedSpot * 100;
    return [{ label, price: rawPrice, distance: rawDistance, distance_pct: rawDistancePct, kind }];
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
    trade_intelligence: tradeIntelligence,
    trade_intelligence_status: tradeIntelligenceStatus,
    trade_intelligence_warning: tradeIntelligenceWarning,
  };
}
