/**
 * Presentation model for explicit structure research.
 *
 * The backend is the sole source of economics. This module only validates the
 * envelope, labels what the backend returned, and marks anything missing as
 * unavailable instead of filling it in.
 */
import type { CompareRequestInput, StructureRequestInput } from "./structure-contract.ts";

export type Scalar =
  | { kind: "value"; value: number }
  | { kind: "unlimited" }
  | { kind: "unavailable"; reason: string };

export interface LegView {
  type: string;
  strike: number;
  qty: number;
  action: "Buy" | "Sell";
  quantity: number;
}

export interface PayoffExtreme {
  price: number;
  pnl: number;
  movePct: number | null;
}

export interface HistoricalView {
  evidenceStatus: "descriptive_only" | "unavailable" | "missing";
  missing: string[];
  provenance: string | null;
  sampleSize: number | null;
  capitalStatus: string | null;
  temporalBasis: string | null;
  deterministicBreakevens: number[];
  deterministicMaxProfit: Scalar | null;
  deterministicMaxLoss: Scalar | null;
}

export interface StructureView {
  symbol: string;
  expiration: string;
  asOf: string;
  spot: number;
  family: string | null;
  direction: string | null;
  dte: number | null;
  maxProfit: Scalar;
  maxLoss: Scalar;
  capitalRequired: Scalar;
  breakevens: number[];
  entryDebit: number | null;
  entryCredit: number | null;
  /** The backend's signed package cashflow; zero is a real value, not missing. */
  packageCashflow: number;
  fees: number | null;
  width: number | null;
  creditWidth: number | null;
  legs: LegView[];
  extremes: PayoffExtreme[];
  historical: HistoricalView;
  pricingAssumption: string | null;
  caveats: string[];
  /** Present only when the backend's own numbers disagree with each other. */
  integrity: string[];
}

export interface CompareCandidateView {
  index: number;
  family: string;
  capital: Scalar;
  maxProfit: Scalar;
  maxLoss: Scalar;
  breakevens: number[];
  dte: number | null;
  observedEvidence: string[];
  pricingAssumption: string | null;
  historicalStatus: string | null;
}

export interface CompareGroupView {
  groupId: number;
  indices: number[];
  directlyComparable: boolean;
  evidenceAvailable: boolean;
  missing: string[];
}

export interface ComparePairView {
  indices: number[];
  comparable: boolean;
  reason: string | null;
}

export interface CompareView {
  thesis: string | null;
  order: string;
  noCandidate: boolean;
  candidates: CompareCandidateView[];
  excluded: { index: number; reason: string }[];
  groups: CompareGroupView[];
  pairs: ComparePairView[];
  caveats: string[];
}

export interface ObservationSeed {
  symbol: "SPY" | "QQQ";
  spot: number;
  expiration: string;
  asOf: string;
  provider: string;
  observedAt: string;
  ageSeconds: number;
}

const UNAVAILABLE = "not provided by the backend";

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function date(value: unknown): string | null {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function strings(value: unknown): string[] {
  return list(value).filter((item): item is string => typeof item === "string" && item.length > 0);
}

/** A backend "unlimited" marker is preserved; a missing value is never imputed. */
function scalar(value: unknown): Scalar {
  if (value === "unlimited") return { kind: "unlimited" };
  const parsed = number(value);
  if (parsed !== null) return { kind: "value", value: parsed };
  return { kind: "unavailable", reason: UNAVAILABLE };
}

function optionalScalar(value: unknown): Scalar | null {
  if (value === undefined || value === null) return null;
  return scalar(value);
}

function breakevens(...candidates: unknown[]): number[] {
  for (const candidate of candidates) {
    const values = list(candidate).map(number).filter((item): item is number => item !== null);
    if (values.length) return values;
    const single = number(candidate);
    if (single !== null) return [single];
  }
  return [];
}

function envelopeOf(value: unknown): Record<string, unknown> | null {
  const envelope = object(value);
  if (!envelope) return null;
  if (envelope.schema_version !== "alphaos-interface-v2") return null;
  if (envelope.read_only !== true) return null;
  if (object(envelope.request) === null || object(envelope.research) === null) return null;
  if (!Array.isArray(envelope.caveats)) return null;
  return envelope;
}

function legsOf(value: unknown): LegView[] {
  return list(value).flatMap((item) => {
    const leg = object(item);
    const strike = number(leg?.strike);
    const qty = number(leg?.qty);
    const type = text(leg?.type);
    if (!leg || strike === null || qty === null || type === null || qty === 0) return [];
    return [{
      type,
      strike,
      qty,
      action: qty > 0 ? "Buy" as const : "Sell" as const,
      quantity: Math.abs(qty),
    }];
  });
}

function historicalView(value: unknown): HistoricalView {
  const historical = object(value);
  const deterministic = object(historical?.deterministic_expiration);
  const status = historical?.historical_evidence_status;
  return {
    evidenceStatus: status === "descriptive_only"
      ? "descriptive_only"
      : status === "unavailable" ? "unavailable" : "missing",
    missing: strings(historical?.missing_evidence),
    provenance: text(object(historical?.provenance)?.verification),
    sampleSize: number(historical?.sample_size),
    capitalStatus: text(object(historical?.capital_eligibility)?.status),
    temporalBasis: text(historical?.temporal_basis),
    deterministicBreakevens: breakevens(deterministic?.breakevens),
    deterministicMaxProfit: optionalScalar(deterministic?.max_profit),
    deterministicMaxLoss: optionalScalar(deterministic?.max_loss),
  };
}

function extremesOf(value: unknown): PayoffExtreme[] {
  const payoff = object(value);
  return list(payoff?.extremes).flatMap((item) => {
    const row = object(item);
    const price = number(row?.["Terminal underlying ($)"]);
    const pnl = number(row?.["Expiration P&L ($)"]);
    if (price === null || pnl === null) return [];
    return [{ price, pnl, movePct: number(row?.["Move from spot (%)"]) }];
  });
}

/**
 * Validate and project one explicit-structure envelope.
 *
 * Returns null on any provenance or echo mismatch so the caller can show an
 * explicit failure instead of partially trusted numbers.
 */
export function structureView(value: unknown): StructureView | null {
  const envelope = envelopeOf(value);
  if (!envelope) return null;
  const request = object(envelope.request);
  const research = object(envelope.research);
  if (!request || !research) return null;

  const symbol = text(research.underlying);
  const trade = object(research.trade);
  const position = object(research.position);
  if (symbol === null || !trade || !position) return null;

  // Single-leg long options omit the top-level expiration; the normalized trade
  // carries the same backend value, so read it there instead of inferring one.
  const expiration = date(research.expiration) ?? date(trade.expiration);
  const asOf = date(request.as_of);
  const spot = number(trade.spot);
  const credit = number(trade.credit);
  if (expiration === null || asOf === null || spot === null || credit === null) return null;
  if (request.symbol !== symbol || request.expiration !== expiration) return null;
  if (number(request.spot) !== spot || number(request.credit) !== credit) return null;
  if (position.symbol !== symbol || position.expiration !== expiration) return null;

  const requestLegs = legsOf(request.legs);
  const positionLegs = legsOf(position.legs);
  if (requestLegs.length === 0 || positionLegs.length === 0) return null;
  if (requestLegs.length !== positionLegs.length) return null;
  const legsMatch = requestLegs.every((leg, index) =>
    leg.type === positionLegs[index].type &&
    leg.strike === positionLegs[index].strike &&
    leg.qty === positionLegs[index].qty);
  if (!legsMatch) return null;

  const integrity: string[] = [];
  const historical = historicalView(research.historical_economics);
  const capital = number(research.capital_at_risk);
  const maxLoss = number(research.max_loss);
  if (capital !== null && maxLoss !== null && Math.abs(capital - maxLoss) > 1e-9) {
    integrity.push("capital_at_risk_disagrees_with_max_loss");
  }
  const historicalMaxLoss = historical.deterministicMaxLoss;
  if (historicalMaxLoss?.kind === "value" && maxLoss !== null &&
      Math.abs(historicalMaxLoss.value - maxLoss) > 0.01) {
    integrity.push("historical_max_loss_disagrees_with_position_max_loss");
  }
  const positionBreakevens = breakevens(research.breakevens, research.breakeven);
  if (historical.deterministicBreakevens.length &&
      positionBreakevens.length !== historical.deterministicBreakevens.length) {
    integrity.push("historical_breakevens_disagree_with_position_breakevens");
  }

  const payoff = object(research.payoff);

  return {
    symbol,
    expiration,
    asOf,
    spot,
    family: text(research.strategy_family),
    direction: text(research.direction),
    dte: number(research.dte),
    maxProfit: scalar(research.max_profit),
    maxLoss: scalar(research.max_loss),
    capitalRequired: capital === null
      ? { kind: "unavailable", reason: UNAVAILABLE }
      : { kind: "value", value: capital },
    breakevens: positionBreakevens,
    // entry_debit/entry_credit are absent on single-leg long options; the sign
    // of the backend's own package cashflow labels the same value.
    entryDebit: number(research.entry_debit) ?? (credit < 0 ? -credit : null),
    entryCredit: number(research.entry_credit) ?? (credit > 0 ? credit : null),
    packageCashflow: credit,
    fees: number(trade.fees),
    width: number(payoff?.width),
    creditWidth: number(payoff?.credit_width),
    legs: positionLegs,
    extremes: extremesOf(payoff),
    historical,
    pricingAssumption: text(object(research.evidence)?.pricing_assumption) ??
      text(object(position)?.pricing_assumption),
    caveats: strings(research.caveats),
    integrity,
  };
}

function compareCandidate(
  comparison: Record<string, unknown> | null,
  researched: Record<string, unknown> | null,
): CompareCandidateView | null {
  const index = number(comparison?.input_index);
  const family = text(comparison?.strategy_family);
  if (index === null || family === null) return null;
  const historical = object(researched?.historical_economics);
  return {
    index,
    family,
    capital: scalar(comparison?.capital_at_risk),
    maxProfit: scalar(comparison?.max_profit),
    maxLoss: scalar(comparison?.max_loss),
    breakevens: breakevens(comparison?.breakevens),
    dte: number(comparison?.dte),
    observedEvidence: Object.entries(object(comparison?.market_evidence_available) ?? {})
      .filter(([, available]) => available === true)
      .map(([field]) => field)
      .sort(),
    pricingAssumption: text(comparison?.pricing_assumption),
    historicalStatus: text(historical?.historical_evidence_status),
  };
}

/**
 * Validate and project one comparison envelope. Any ranking, winner or
 * recommendation from the backend is rejected rather than displayed.
 */
export function compareView(value: unknown): CompareView | null {
  const envelope = envelopeOf(value);
  if (!envelope) return null;
  const request = object(envelope.request);
  const research = object(envelope.research);
  const comparison = object(research?.comparison);
  const historical = object(research?.historical_comparison);
  if (!request || !research || !comparison || !historical) return null;
  if (!Array.isArray(request.structures) || !Array.isArray(research.candidates)) return null;
  if (request.structures.length !== research.candidates.length) return null;
  if (comparison.winner !== null || comparison.recommendation !== null) return null;

  const candidates: CompareCandidateView[] = [];
  for (const raw of list(comparison.candidates)) {
    const index = number(object(raw)?.input_index);
    const researched = index === null ? null : object(research.candidates[index]);
    if (index === null || researched === null || index >= research.candidates.length) return null;
    const view = compareCandidate(object(raw), researched);
    if (!view) return null;
    candidates.push(view);
  }

  const excluded = list(comparison.excluded).flatMap((raw) => {
    const item = object(raw);
    const index = number(item?.input_index);
    const reason = text(item?.reason);
    return index === null || reason === null ? [] : [{ index, reason }];
  });

  const groups: CompareGroupView[] = list(historical.groups).flatMap((raw) => {
    const group = object(raw);
    const groupId = number(group?.group_id);
    const indices = list(group?.candidate_indices)
      .map(number)
      .filter((item): item is number => item !== null);
    return groupId === null ? [] : [{
      groupId,
      indices,
      directlyComparable: group?.directly_comparable === true,
      evidenceAvailable: group?.evidence_available === true,
      missing: strings(group?.missing_evidence),
    }];
  });

  const pairs: ComparePairView[] = list(historical.pairwise_comparability).flatMap((raw) => {
    const pair = object(raw);
    const indices = list(pair?.candidate_indices)
      .map(number)
      .filter((item): item is number => item !== null);
    if (indices.length !== 2) return [];
    return [{
      indices,
      comparable: pair?.directly_comparable === true,
      reason: text(pair?.missing_reason),
    }];
  });

  return {
    thesis: text(comparison.thesis),
    order: text(comparison.candidate_order) ?? "supplied input order; not a ranking",
    noCandidate: comparison.no_candidate === true || candidates.length === 0,
    candidates,
    excluded,
    groups,
    pairs,
    caveats: strings(comparison.caveats),
  };
}

/**
 * Bind a validated envelope to the exact normalized request that was sent.
 *
 * A self-consistent envelope can still describe a different scenario than the
 * one submitted. Every echoed field, leg and leg order must match, and for a
 * comparison each researched candidate must match its submitted scenario in
 * supplied order. Anything else is treated as unrenderable.
 */
function echoesLegs(echoed: unknown, submitted: StructureRequestInput["legs"]): boolean {
  const legs = list(echoed);
  if (legs.length !== submitted.length) return false;
  return submitted.every((leg, index) => {
    const row = object(legs[index]);
    return row !== null &&
      row.type === leg.type &&
      number(row.strike) === leg.strike &&
      number(row.qty) === leg.qty;
  });
}

function echoesStructure(echoed: unknown, submitted: StructureRequestInput): boolean {
  const echo = object(echoed);
  if (!echo) return false;
  const fees = echo.fees === undefined ? 0 : number(echo.fees);
  return echo.symbol === submitted.symbol &&
    echo.expiration === submitted.expiration &&
    echo.as_of === submitted.as_of &&
    number(echo.spot) === submitted.spot &&
    number(echo.credit) === submitted.credit &&
    fees === submitted.fees &&
    echoesLegs(echo.legs, submitted.legs);
}

function candidateExpiration(research: Record<string, unknown>): string | null {
  return date(research.expiration) ??
    date(object(research.trade)?.expiration) ??
    date(object(research.position)?.expiration);
}

/** One researched candidate must describe the scenario submitted at its index. */
function candidateMatches(research: unknown, submitted: StructureRequestInput): boolean {
  const row = object(research);
  const trade = object(row?.trade);
  const position = object(row?.position);
  if (!row || !trade || !position) return false;
  return row.underlying === submitted.symbol &&
    candidateExpiration(row) === submitted.expiration &&
    number(trade.spot) === submitted.spot &&
    number(trade.credit) === submitted.credit &&
    echoesLegs(position.legs, submitted.legs);
}

export function structureViewFor(
  value: unknown,
  submitted: StructureRequestInput,
): StructureView | null {
  const envelope = envelopeOf(value);
  if (!envelope) return null;
  const view = structureView(envelope);
  if (!view || !echoesStructure(envelope.request, submitted)) return null;
  return view;
}

export function compareViewFor(
  value: unknown,
  submitted: CompareRequestInput,
): CompareView | null {
  const envelope = envelopeOf(value);
  if (!envelope) return null;
  const view = compareView(envelope);
  if (!view) return null;
  const request = object(envelope.request);
  const researched = list(object(envelope.research)?.candidates);
  const echoed = list(request?.structures);
  if (echoed.length !== submitted.structures.length) return null;
  if (researched.length !== submitted.structures.length) return null;
  if (!submitted.structures.every((item, index) => echoesStructure(echoed[index], item))) {
    return null;
  }
  if (!submitted.structures.every((item, index) => candidateMatches(researched[index], item))) {
    return null;
  }
  // The thesis is echoed context, not a filter; it must still be the one sent.
  return (typeof request?.thesis === "string" ? request.thesis : undefined) === submitted.thesis
    ? view
    : null;
}

/**
 * Prefill spot/expiration/date from a verified archive observation.
 *
 * The observation endpoint performs no research; its spot is an archive read,
 * not a quote, so the caller must label it as such.
 */
export function observationSeed(value: unknown, symbol: "SPY" | "QQQ"): ObservationSeed | null {
  const outer = object(value);
  if (!outer || outer.verified_for_trading !== false) return null;
  const envelope = object(outer.research);
  if (!envelope) return null;
  if (envelope.schema_version !== "alphaos-observation-v1") return null;
  if (envelope.read_only !== true || envelope.research_performed !== false) return null;
  if (envelope.symbol !== symbol) return null;
  const spot = number(envelope.spot);
  const expiration = date(envelope.expiration);
  const archive = object(envelope.archive);
  const asOf = date(archive?.session_date);
  const provider = text(archive?.provider);
  const observedAt = text(envelope.as_of);
  const ageSeconds = number(object(archive?.freshness)?.age_seconds);
  const request = object(envelope.request);
  if (spot === null || spot <= 0 || expiration === null || asOf === null) return null;
  if (!provider || !observedAt || ageSeconds === null || request?.symbol !== symbol) return null;
  return { symbol, spot, expiration, asOf, provider, observedAt, ageSeconds };
}

const MESSAGES: Record<string, string> = {
  invalid_structure_request: "The structure request is incomplete or outside the backend's supported bounds.",
  invalid_structure: "The backend does not support this leg combination. Check strike ordering, leg signs, and cashflow direction.",
  backend_rejected_request: "The backend rejected this structure as invalid.",
  backend_not_configured: "The website backend URL or server-side API token is not configured.",
  invalid_backend_configuration: "The website backend URL configuration is invalid.",
  backend_authentication_required: "The backend requires an API token; the configured token was not accepted as authenticated.",
  backend_authentication_rejected: "The backend rejected the configured API token.",
  backend_endpoint_unavailable: "The configured backend does not provide the structure research endpoint. Check the backend deployment and URL.",
  backend_rate_limited: "The backend is rate limiting requests. Wait briefly and retry.",
  backend_service_unavailable: "The backend service is temporarily unavailable or starting up. Wait briefly and retry.",
  backend_internal_error: "The backend could not complete this structure research.",
  backend_http_error: "The backend returned an unsuccessful response.",
  backend_timeout: "The structure research request timed out. The backend may still be working; no result was accepted.",
  backend_unreachable: "The website could not reach the research backend.",
  response_schema_mismatch: "The backend response did not match the required structure research contract, so it was not displayed.",
  request_cancelled: "The request was cancelled before a result was available.",
  research_unavailable: "Structure research is unavailable. No substitute economics were displayed.",
};

export function structureMessage(code: string): string {
  return MESSAGES[code] ?? MESSAGES.research_unavailable;
}
