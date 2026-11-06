/**
 * Server-side retrieval of independently timestamped AlphaOS market evidence
 * for the Charting & AI page.
 *
 * Only the existing authenticated AlphaOS research endpoints are used
 * (`/v1/market/{symbol}` and `/v1/structure/{symbol}`). TradingView is never
 * queried, scraped or read here, and no value is synthesised: when the two
 * envelopes cannot be verified against each other the caller gets an explicit
 * unavailable result.
 */
import { fetchResearchEnvelope, object, ResearchUnavailableError } from "./research-evidence.ts";
import { getServerConfig } from "./server-config.ts";
import type {
  ChartEvidence,
  ChartEvidenceCode,
  ChartEvidenceFailure,
  ChartEvidenceResult,
  ChartSymbol,
  EvidenceLevel,
  MarketStateSummary,
} from "./chart-types.ts";

const DEFAULT_TIMEOUT_MS = 9_000;
const CAVEAT_LIMIT = 8;

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value));
}
function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
function text(value: unknown, limit = 64): string | null {
  return typeof value === "string" && value.trim() && value.length <= limit ? value : null;
}
function failure(code: ChartEvidenceCode, message: string): ChartEvidenceFailure {
  return { status: "unavailable", code, message };
}
function evidenceFailure(error: unknown): ChartEvidenceFailure {
  if (error instanceof ResearchUnavailableError) {
    if (/not configured/i.test(error.message)) {
      return failure("market_evidence_not_configured",
        "The AlphaOS research backend is not configured for this deployment.");
    }
    if (/timed out/i.test(error.message)) {
      return failure("market_evidence_timeout",
        "The AlphaOS research backend did not answer in time.");
    }
    if (/network/i.test(error.message)) {
      return failure("market_evidence_unreachable",
        "The AlphaOS research backend could not be reached.");
    }
    if (/HTTP \d{3}/.test(error.message)) {
      return failure("market_evidence_backend_error",
        "The AlphaOS research backend returned an unsuccessful response.");
    }
    return failure("market_evidence_schema_mismatch",
      "The AlphaOS research backend response could not be verified.");
  }
  return failure("market_evidence_unreachable",
    "The AlphaOS research backend could not be reached.");
}

const KINDS = new Set(["support", "resistance", "mid", "atr"]);

/**
 * Label a backend level from the observations that formed its cluster.
 * `/v1/structure` returns `sources` such as "swing_high, 20d_high", not a
 * display label, so the previous adapter dropped every level.
 */
function levelLabel(level: Record<string, unknown>, kind: string): string {
  const sources = text(level.sources, 80);
  if (sources) return sources.replace(/_/g, " ");
  return text(level.label, 80) ?? `${kind} level`;
}

function levelsFrom(value: unknown, spot: number): EvidenceLevel[] {
  if (!Array.isArray(value)) return [];
  const levels: EvidenceLevel[] = [];
  for (const row of value.slice(0, 10)) {
    const level = object(row);
    if (!level) continue;
    // `/v1/structure` emits `side`, `level` (the price), cluster bounds and the
    // source observations; an older adapter shape used `kind` + `price`.
    const backendPrice = finitePositive(level.level) ? level.level : null;
    const legacyPrice = finitePositive(level.price) ? level.price : null;
    const price = backendPrice ?? legacyPrice;
    const rawKind = String(level.side ?? level.kind ?? "").toLowerCase();
    if (price === null || !KINDS.has(rawKind)) continue;
    // The backend's distance_pct is a decimal fraction of spot and the legacy
    // shape used percentages; derive it from the two verified prices instead
    // of guessing units.
    const distance = (price - spot) / spot * 100;
    const zoneLow = finitePositive(level.zone_low) ? level.zone_low : null;
    const zoneHigh = finitePositive(level.zone_high) ? level.zone_high : null;
    levels.push({
      label: levelLabel(level, rawKind),
      price,
      kind: rawKind as EvidenceLevel["kind"],
      distance_pct: Number.isFinite(distance) ? Math.round(distance * 100) / 100 : null,
      ...(zoneLow !== null && zoneHigh !== null && zoneLow <= zoneHigh
        ? { zone_low: zoneLow, zone_high: zoneHigh }
        : {}),
    });
  }
  return levels;
}

const STATE_KEYS = ["movement_state", "volatility_state", "premium_state"] as const;
const TREND_STRUCTURES = new Set(["bullish", "bearish", "mixed"]);

/**
 * `/v1/market` returns the completed-session feature row as `market_state`: it
 * carries `ema_structure` and price-based measures, but no opportunity
 * classification. Missing dimensions stay explicitly missing (direction is
 * `unknown` with `direction_reported: false`) so neither the prompt nor the UI
 * can mistake an absent classification for a neutral market.
 */
function marketStateFrom(value: unknown): MarketStateSummary {
  const state = object(value) ?? {};
  const direction = state.direction;
  const reported = direction === "bullish" || direction === "bearish" || direction === "neutral";
  const ema = state.ema_structure;
  return {
    direction: reported ? direction : "unknown",
    direction_reported: reported,
    ema_structure: typeof ema === "string" && TREND_STRUCTURES.has(ema)
      ? ema as MarketStateSummary["ema_structure"] : null,
    movement_state: text(state.movement_state),
    volatility_state: text(state.volatility_state),
    premium_state: text(state.premium_state),
  };
}

function caveatsFrom(...values: unknown[]): string[] {
  const messages: string[] = [];
  for (const value of values) {
    if (!Array.isArray(value)) continue;
    for (const item of value) {
      if (typeof item === "string" && item.trim() && item.length <= 300 &&
          !messages.includes(item)) {
        messages.push(item);
      }
      if (messages.length >= CAVEAT_LIMIT) return messages;
    }
  }
  return messages;
}

function normalizeSymbol(value: string): ChartSymbol | null {
  const symbol = value.trim().toUpperCase();
  return symbol === "SPY" || symbol === "QQQ" ? symbol : null;
}

export type LoadChartEvidenceOptions = {
  request?: typeof fetch;
  token?: string;
  baseUrl?: string;
  now?: () => number;
  timeoutMs?: number;
};

/**
 * Verify one market + structure pair for `symbol`.
 *
 * Freshness is reported, not silently upgraded: evidence that is not currently
 * usable for live research is returned as `point_in_time` with its original
 * timestamp so the assistant and the page can disclose that it is not current
 * market conditions.
 */
export async function loadChartEvidence(
  symbol: string,
  options: LoadChartEvidenceOptions = {},
): Promise<ChartEvidenceResult> {
  const normalized = normalizeSymbol(symbol);
  if (!normalized) {
    return failure("unsupported_chart_symbol", "Only SPY and QQQ are supported on this page.");
  }

  // Credentials come from the deployment's runtime bindings: process.env on the
  // Node/Netlify runtime, the Worker env on Cloudflare. Never a hardcoded host.
  let token = options.token;
  let base = options.baseUrl;
  if (token === undefined || base === undefined) {
    const configuration = getServerConfig();
    token ??= configuration.token;
    base ??= configuration.base;
  }
  if (!token || !base) {
    return failure("market_evidence_not_configured",
      "The website backend URL or server-side API token is not configured.");
  }

  let origin: URL;
  try {
    origin = new URL(base);
    if (origin.protocol !== "https:" || !origin.host || origin.username ||
        origin.password || origin.search || origin.hash) {
      throw new Error("Invalid backend URL");
    }
  } catch {
    return failure("market_evidence_not_configured",
      "The website backend URL configuration is invalid.");
  }
  const request = options.request ?? fetch;
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  let market: Awaited<ReturnType<typeof fetchResearchEnvelope>>;
  let structure: Awaited<ReturnType<typeof fetchResearchEnvelope>>;
  try {
    market = await fetchResearchEnvelope(
      `${origin.origin}/v1/market/${normalized}?horizon=3`, token, request, timeoutMs);
    const marketMeta = object(market.meta);
    const snapshotId = text(marketMeta?.snapshot_id, 128);
    if (!snapshotId) {
      return failure("market_evidence_mismatch",
        "The AlphaOS research backend did not return a verifiable snapshot identifier.");
    }
    structure = await fetchResearchEnvelope(
      `${origin.origin}/v1/structure/${normalized}?horizon=3&levels=5&snapshot_id=${encodeURIComponent(snapshotId)}`,
      token, request, timeoutMs);
  } catch (error) {
    return evidenceFailure(error);
  }

  const meta = object(market.meta);
  const structureMeta = object(structure.meta);
  const structureEvidence = object(structure.evidence);
  const marketEvidence = object(market.evidence);
  if (!meta || !structureMeta || !structureEvidence || !marketEvidence) {
    return failure("market_evidence_schema_mismatch",
      "AlphaOS market evidence did not match the required research schema.");
  }
  if (meta.schema_version !== "alphaos-research-v1" ||
      structureMeta.schema_version !== "alphaos-research-v1" ||
      meta.symbol !== normalized || structureMeta.symbol !== normalized ||
      meta.source !== "Public" || structureMeta.source !== "Public") {
    return failure("market_evidence_mismatch",
      "AlphaOS evidence is not a verified Public observation for the selected symbol.");
  }
  if (typeof meta.snapshot_id !== "string" || !meta.snapshot_id ||
      meta.snapshot_id !== structureMeta.snapshot_id) {
    return failure("market_evidence_mismatch",
      "AlphaOS market and structure evidence describe different snapshots.");
  }

  const quote = object(marketEvidence.underlying_quote);
  const underlying = object(quote?.quote);
  const spot = finitePositive(meta.current_spot) ? meta.current_spot
    : finitePositive(underlying?.last) ? underlying.last : null;
  const atr = structureEvidence.atr;
  const asOf = meta.quote_as_of;
  if (spot === null || !finitePositive(atr) || !isTimestamp(asOf)) {
    return failure("market_evidence_mismatch",
      "AlphaOS evidence is missing a verified price, volatility measure or observation timestamp.");
  }

  const quality = object(meta.quote_freshness) ?? {};
  const dataStatus = text(quality.data_status) ?? "unknown";
  const freshness = text(quality.freshness) ?? "unknown";
  const marketSession = text(quality.market_state) ?? "unknown";
  const mode = quality.usable_for_live_research === true && dataStatus === "fresh" &&
    freshness === "fresh" && (marketSession === "regular_open" || marketSession === "extended_hours")
    ? "current" : "point_in_time";
  const retrievedAt = now();
  const ageSeconds = Math.max(0, Math.round((retrievedAt - Date.parse(asOf)) / 1000));

  const evidence: ChartEvidence = {
    symbol: normalized,
    mode,
    source: "Public",
    as_of: asOf,
    retrieved_at: new Date(retrievedAt).toISOString(),
    age_seconds: ageSeconds,
    spot,
    atr_14: atr,
    levels: levelsFrom(structureEvidence.levels, spot),
    market_state: marketStateFrom(marketEvidence.market_state),
    data_status: dataStatus,
    freshness,
    market_session: marketSession,
    // AlphaOS 2.0's ResearchEnvelope type omits caveats even though the runtime
    // envelope must carry them; read them without widening the shared type.
    caveats: caveatsFrom(object(market)?.caveats, object(structure)?.caveats),
  };
  return { status: "ok", evidence };
}

/** Timestamp/host label used in UI copy, never a fabricated observation. */
export function evidenceSourceLabel(evidence: ChartEvidence): string {
  return `${evidence.source} via AlphaOS research API`;
}

export const CHART_EVIDENCE_STATE_KEYS = STATE_KEYS;
