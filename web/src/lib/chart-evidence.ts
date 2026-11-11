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
import { readRuntimeBindings } from "#alphaos-runtime";
import { fetchResearchEnvelope, object, ResearchUnavailableError } from "./research-evidence.ts";
import { getServerConfig } from "./server-config.ts";
import type {
  ChartEvidence,
  ChartEvidenceCode,
  ChartEvidenceFailure,
  ChartEvidenceResult,
  ChartSymbol,
  CompletedSession,
  EvidenceLevel,
  MarketStateSummary,
  ObservationContext,
  QuoteObservation,
  QuoteSession,
} from "./chart-types.ts";

const DEFAULT_TIMEOUT_MS = 9_000;
// Netlify's synchronous function limit defaults to 10s and this site sets no
// override, so both legs share one budget below that limit: the route returns
// its own bounded error instead of being killed mid-response. Measured warm
// legs are ~0.2-0.3s; a sleeping Render instance needs ~40s to boot, which no
// in-function timeout can cover (see DEPLOYMENT.md).
const DEFAULT_BUDGET_MS = 8_500;
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
function dateOnly(value: unknown): string | null {
  const raw = text(value, 40);
  if (!raw) return null;
  const date = raw.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : null;
}
function samePrice(left: number, right: number): boolean {
  return Math.abs(left - right) <= 0.005;
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
const QUOTE_SESSIONS = new Set<QuoteSession>([
  "regular_session", "extended_hours", "overnight", "off_hours", "closed", "unknown",
]);
const OBSERVATION_CONTEXTS = new Set<ObservationContext>([
  "regular_session_observation", "extended_hours_observation",
  "completed_session_close_observation", "overnight_observation",
  "off_hours_observation", "dated_closed_market_observation", "unknown",
]);

function quoteSession(value: unknown): QuoteSession {
  return typeof value === "string" && QUOTE_SESSIONS.has(value as QuoteSession)
    ? value as QuoteSession : "unknown";
}
function observationContext(value: unknown): ObservationContext {
  return typeof value === "string" && OBSERVATION_CONTEXTS.has(value as ObservationContext)
    ? value as ObservationContext : "unknown";
}

/** Recompute the documented completed-session EMA ordering from the same row. */
function emaOrderingMatches(
  structure: MarketStateSummary["ema_structure"],
  close: number | null,
  ema9: number | null,
  ema21: number | null,
  ema50: number | null,
): boolean | null {
  if (structure === null || close === null || ema9 === null || ema21 === null || ema50 === null) {
    return null;
  }
  const computed = close > ema9 && ema9 > ema21 && ema21 > ema50 ? "bullish"
    : close < ema9 && ema9 < ema21 && ema21 < ema50 ? "bearish" : "mixed";
  return computed === structure;
}

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
    as_of: dateOnly(state.date),
    close: finitePositive(state.close) ? state.close : null,
    ema_9: finitePositive(state.ema_9) ? state.ema_9 : null,
    ema_21: finitePositive(state.ema_21) ? state.ema_21 : null,
    ema_50: finitePositive(state.ema_50) ? state.ema_50 : null,
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

export type EvidenceTimeoutPhase = "market" | "structure";

/**
 * Bounded retrieval timing. Durations and the phase that ran out of time only:
 * never a credential, backend URL, provider body or market value.
 */
export type EvidenceTiming = {
  symbol: string;
  budget_ms: number;
  market_ms: number | null;
  structure_ms: number | null;
  total_ms: number;
  timeout_phase: EvidenceTimeoutPhase | null;
};

export type LoadChartEvidenceOptions = {
  request?: typeof fetch;
  token?: string;
  baseUrl?: string;
  now?: () => number;
  timeoutMs?: number;
  /** Wall-clock budget shared by both legs; defaults below the function limit. */
  budgetMs?: number;
  clock?: () => number;
  onTiming?: (timing: EvidenceTiming) => void;
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
  const clock = options.clock ?? Date.now;
  const startedAt = clock();
  const timing: EvidenceTiming = {
    symbol: symbol.trim().toUpperCase().slice(0, 8) || "unknown",
    budget_ms: options.budgetMs ?? DEFAULT_BUDGET_MS,
    market_ms: null,
    structure_ms: null,
    total_ms: 0,
    timeout_phase: null,
  };
  try {
    return await retrieveChartEvidence(symbol, options, timing, startedAt, clock);
  } finally {
    timing.total_ms = Math.max(0, Math.round(clock() - startedAt));
    options.onTiming?.(timing);
  }
}

async function retrieveChartEvidence(
  symbol: string,
  options: LoadChartEvidenceOptions,
  timing: EvidenceTiming,
  startedAt: number,
  clock: () => number,
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

  // Each leg gets its own timeout and at most what remains of the shared
  // budget. Structure depends on the market snapshot id, so the two legs cannot
  // run in parallel without breaking snapshot consistency.
  const remaining = () => Math.max(0, timing.budget_ms - (clock() - startedAt));
  const legTimeout = () => Math.min(timeoutMs, remaining());

  let market: Awaited<ReturnType<typeof fetchResearchEnvelope>>;
  let structure: Awaited<ReturnType<typeof fetchResearchEnvelope>>;
  let phase: EvidenceTimeoutPhase = "market";
  try {
    if (remaining() <= 0) {
      throw new ResearchUnavailableError("Research API request timed out");
    }
    let legStarted = clock();
    try {
      market = await fetchResearchEnvelope(
        `${origin.origin}/v1/market/${normalized}?horizon=3`, token, request, legTimeout());
    } finally {
      timing.market_ms = Math.max(0, Math.round(clock() - legStarted));
    }
    const marketMeta = object(market.meta);
    const snapshotId = text(marketMeta?.snapshot_id, 128);
    if (!snapshotId) {
      return failure("market_evidence_mismatch",
        "The AlphaOS research backend did not return a verifiable snapshot identifier.");
    }
    phase = "structure";
    legStarted = clock();
    try {
      structure = await fetchResearchEnvelope(
        `${origin.origin}/v1/structure/${normalized}?horizon=3&levels=5&snapshot_id=${encodeURIComponent(snapshotId)}`,
        token, request, legTimeout());
    } finally {
      timing.structure_ms = Math.max(0, Math.round(clock() - legStarted));
    }
  } catch (error) {
    const result = evidenceFailure(error);
    if (result.code === "market_evidence_timeout") timing.timeout_phase = phase;
    return result;
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
  const currentSpot = finitePositive(meta.current_spot) ? meta.current_spot : null;
  const quoteLast = finitePositive(underlying?.last) ? underlying.last : null;
  // A non-live quote may still be displayed, but only as an observed quote.
  // `current` below requires verified `meta.current_spot`, so the fallback is
  // never promoted to a current-market price.
  const spot = currentSpot ?? quoteLast;
  const atr = structureEvidence.atr;
  const asOf = meta.quote_as_of;
  if (spot === null || !finitePositive(atr) || !isTimestamp(asOf)) {
    return failure("market_evidence_mismatch",
      "AlphaOS evidence is missing a verified price, volatility measure or observation timestamp.");
  }

  const state = marketStateFrom(marketEvidence.market_state);
  const metaClose = finitePositive(meta.research_close) ? meta.research_close : null;
  const metaSession = dateOnly(meta.research_session);
  const completedClose = metaClose ?? state.close;
  const completedSession = metaSession ?? state.as_of;
  if (metaClose !== null && state.close !== null && !samePrice(metaClose, state.close)) {
    return failure("market_evidence_mismatch",
      "AlphaOS completed-session close and market-state close disagree.");
  }
  if (metaSession && state.as_of && metaSession !== state.as_of) {
    return failure("market_evidence_mismatch",
      "AlphaOS completed-session date and market-state date disagree.");
  }
  const emaMatch = emaOrderingMatches(state.ema_structure, state.close,
    state.ema_9, state.ema_21, state.ema_50);
  if (emaMatch === false) {
    return failure("market_evidence_mismatch",
      "AlphaOS completed-session EMA values do not match the reported EMA structure.");
  }

  const structureAnchor = finitePositive(structureEvidence.anchor_spot) ? structureEvidence.anchor_spot : null;
  const structureClose = finitePositive(structureEvidence.research_close) ? structureEvidence.research_close : null;
  const structureAsOf = dateOnly(structureEvidence.structure_as_of);
  if (structureAnchor !== null && !samePrice(structureAnchor, spot)) {
    return failure("market_evidence_mismatch",
      "AlphaOS structure evidence was anchored to a different observed price.");
  }
  if (structureClose !== null && completedClose !== null && !samePrice(structureClose, completedClose)) {
    return failure("market_evidence_mismatch",
      "AlphaOS structure and market evidence used different completed-session closes.");
  }
  if (structureAsOf && completedSession && structureAsOf !== completedSession) {
    return failure("market_evidence_mismatch",
      "AlphaOS structure and market evidence used different completed sessions.");
  }

  const quality = object(meta.quote_freshness) ?? {};
  const dataStatus = text(quality.data_status) ?? "unknown";
  const freshness = text(quality.freshness) ?? "unknown";
  const marketSession = text(quality.market_state) ?? "unknown";
  const observedSession = quoteSession(quality.quote_session);
  const observedContext = observationContext(quality.observation_context);
  const liveSession = marketSession === "regular_open" || marketSession === "extended_hours";
  const current = currentSpot !== null && quality.usable_for_live_research === true &&
    dataStatus === "fresh" && freshness === "fresh" && liveSession &&
    observedSession !== "overnight" && observedSession !== "off_hours" && observedSession !== "closed";
  const mode = current ? "current" : "point_in_time";
  const retrievedAt = now();
  const ageSeconds = Math.max(0, Math.round((retrievedAt - Date.parse(asOf)) / 1000));

  const quoteObservation: QuoteObservation = {
    price: spot,
    as_of: asOf,
    session: observedSession,
    context: observedContext,
    current,
    executable: false,
    ats_verified: quality.overnight_ats_verified === true,
    data_status: dataStatus,
    freshness,
    reason: text(quality.freshness_reason, 80),
    market_state_source: text(quality.market_state_source, 240),
  };
  const completed: CompletedSession = {
    session: completedSession,
    close: completedClose,
    as_of: completedSession,
    ema_structure: state.ema_structure,
    ema_9: state.ema_9,
    ema_21: state.ema_21,
    ema_50: state.ema_50,
  };

  const caveats = caveatsFrom(object(market)?.caveats, object(structure)?.caveats)
    .slice(0, CAVEAT_LIMIT - 2);
  if (observedSession === "overnight" || observedContext === "overnight_observation") {
    caveats.unshift("Observed price is an overnight/off-hours print; overnight ATS status is unverified and it is not a current-market or executable quote.");
  } else if (observedSession === "extended_hours" || observedSession === "off_hours" ||
      observedContext === "extended_hours_observation" || observedContext === "off_hours_observation") {
    caveats.unshift("Observed price is an extended/off-hours print; it is not a regular-session close or an executable quote.");
  }
  if (completedSession && caveats.length < CAVEAT_LIMIT) {
    caveats.push(`Completed-session EMA, ATR and levels are dated ${completedSession} and were not computed from the observed quote.`);
  }

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
    quote: quoteObservation,
    completed_session: completed,
    technical_as_of: completedSession,
    levels_as_of: structureAsOf ?? completedSession,
    market_state: state,
    data_status: dataStatus,
    freshness,
    market_session: marketSession,
    // AlphaOS 2.0's ResearchEnvelope type omits caveats even though the runtime
    // envelope must carry them; read them without widening the shared type.
    caveats: caveats.slice(0, CAVEAT_LIMIT),
  };
  return { status: "ok", evidence };
}

/**
 * Structured, preview-gated timing diagnostics. Enabled by the deploy-preview
 * environment (`ALPHAOS_PREVIEW_DIAGNOSTICS`), so production logs stay quiet.
 * Durations, outcome and phase only: no credential, backend URL or market data.
 */
export function logEvidenceTiming(
  event: string,
  timing: EvidenceTiming | undefined,
  outcome?: string,
): void {
  if (!timing) return;
  const values = readRuntimeBindings().bindings as Record<string, unknown>;
  if (values.ALPHAOS_PREVIEW_DIAGNOSTICS !== "true") return;
  console.log(JSON.stringify({ event, outcome: outcome ?? null, ...timing }));
}

/** Timestamp/host label used in UI copy, never a fabricated observation. */
export function evidenceSourceLabel(evidence: ChartEvidence): string {
  return `${evidence.source} via AlphaOS research API`;
}

export const CHART_EVIDENCE_STATE_KEYS = STATE_KEYS;
