/**
 * Deterministic workspace evidence and assistant answers.
 *
 * This module never creates prices, levels, confidence scores, option quotes,
 * or trade recommendations. It only normalizes the authenticated AlphaOS
 * market bridge and the versioned trade-intelligence contract.
 */

export type WorkspaceSymbol = "SPY" | "QQQ";
export type WorkspaceDirection = "bullish" | "bearish" | "neutral" | "unknown";
export type WorkspaceLevelKind = "support" | "resistance" | "mid" | "atr";
export type WorkspaceTradeState = "BUY" | "SELL" | "WAIT";
export type WorkspaceSessionState = "open" | "closed" | "preopen" | "unknown";
export type WorkspaceDataStatus = "verified" | "incomplete" | "stale" | "unavailable";

export type WorkspaceLevel = {
  label: string;
  price: number;
  distance: number | null;
  distancePct: number | null;
  kind: WorkspaceLevelKind;
  source?: string;
};

export type WorkspacePriceReference = {
  price: number;
  condition?: string;
  basis?: string;
};

export type WorkspaceRisk = {
  underlyingRiskDistance: number;
  riskPct: number | null;
  targetDistance: number | null;
  rewardToRisk: number | null;
};

export type WorkspaceSetup = {
  id: string;
  name: string;
  state: WorkspaceTradeState;
  direction: WorkspaceDirection;
  evidence: string[];
  missingConditions: string[];
  entry: WorkspacePriceReference | null;
  invalidation: WorkspacePriceReference | null;
  stop: WorkspacePriceReference | null;
  target: WorkspacePriceReference | null;
  risk: WorkspaceRisk | null;
  waitReason: string | null;
  timestamp: string | null;
  freshness: string;
  strategyFamilies: string[];
};

export type WorkspaceTradeIntelligence = {
  schemaVersion: string;
  symbol: WorkspaceSymbol;
  sessionState: WorkspaceSessionState;
  sessionDate: string | null;
  dataStatus: WorkspaceDataStatus;
  freshness: string;
  latestConfirmedAt: string | null;
  confirmedBars: number;
  previousSession: {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
  };
  pivots: { pivot: number; r1: number; r2: number; s1: number; s2: number };
  openingRange: { high: number; low: number; status: string } | null;
  currentSession: { high: number | null; low: number | null };
  vwap: number | null;
  ema9: number | null;
  references: WorkspaceLevel[];
  bias: WorkspaceDirection;
  state: WorkspaceTradeState;
  reason: string;
  activeSetupId: string | null;
  closestSetupId: string | null;
  setups: WorkspaceSetup[];
  lastChange: {
    previousAt: string;
    currentAt: string;
    previousClose: number;
    currentClose: number;
    change: number;
    changePct: number | null;
  } | null;
  exitEarly: { state: string; reason: string };
  warnings: string[];
};

export type WorkspaceSnapshot = {
  symbol: WorkspaceSymbol;
  spot: number;
  asOf: string;
  source: "verified_archive" | "live_public";
  isLive: boolean;
  direction: WorkspaceDirection;
  atr: number;
  expectedMove: number | null;
  levels: WorkspaceLevel[];
  caveats: string[];
  warning: string | null;
  tradeIntelligence: WorkspaceTradeIntelligence | null;
  tradeIntelligenceWarning: string | null;
};

export type WorkspaceAssessment = {
  stance: WorkspaceTradeState | "UNAVAILABLE";
  bias: WorkspaceDirection;
  biasLabel: string;
  reason: string;
  evidenceGaps: string[];
  support: WorkspaceLevel[];
  resistance: WorkspaceLevel[];
  setups: WorkspaceSetup[];
  closestSetup: WorkspaceSetup | null;
  exitEarly: { state: string; reason: string } | null;
  sessionState: WorkspaceSessionState;
};

type JsonObject = Record<string, unknown>;

function record(value: unknown): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function stringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const values = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  return values.length === value.length ? values : null;
}

function symbolValue(value: unknown): WorkspaceSymbol | null {
  return value === "SPY" || value === "QQQ" ? value : null;
}

function directionValue(value: unknown): WorkspaceDirection {
  return value === "bullish" || value === "bearish" || value === "neutral"
    ? value
    : "unknown";
}

function tradeStateValue(value: unknown): WorkspaceTradeState | null {
  return value === "BUY" || value === "SELL" || value === "WAIT" ? value : null;
}

function levelKind(value: unknown): WorkspaceLevelKind {
  return value === "support" || value === "resistance" || value === "atr"
    ? value
    : "mid";
}

function price(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function percent(value: number | null): string {
  if (value === null) return "distance unavailable";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatDistancePct(value: number | null): string {
  if (value === null) return "Distance unavailable";
  const rounded = Math.abs(value) < 0.005 ? 0 : value;
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded.toFixed(2)}% from spot`;
}

function directionLabel(value: WorkspaceDirection): string {
  if (value === "bullish") return "UP / bullish";
  if (value === "bearish") return "DOWN / bearish";
  if (value === "neutral") return "CHOP / neutral";
  return "UNKNOWN";
}

function levelsSummary(levels: WorkspaceLevel[]): string {
  return levels
    .slice(0, 6)
    .map((level) => `${price(level.price)} (${level.label}, ${percent(level.distancePct)})`)
    .join("; ");
}

function normalizeReference(value: unknown): WorkspacePriceReference | null | undefined {
  if (value === null) return null;
  const row = record(value);
  if (!finitePositive(row.price)) return undefined;
  return {
    price: row.price,
    condition: stringValue(row.condition) ?? undefined,
    basis: stringValue(row.basis) ?? undefined,
  };
}

function normalizeRisk(value: unknown): WorkspaceRisk | null | undefined {
  if (value === null) return null;
  const row = record(value);
  if (!finitePositive(row.underlying_risk_distance)) return undefined;
  return {
    underlyingRiskDistance: row.underlying_risk_distance,
    riskPct: finiteNumber(row.risk_pct),
    targetDistance: finiteNumber(row.target_distance),
    rewardToRisk: finiteNumber(row.reward_to_risk),
  };
}

function normalizeSetup(value: unknown): WorkspaceSetup | null {
  const row = record(value);
  const state = tradeStateValue(row.state);
  const id = stringValue(row.id);
  const name = stringValue(row.name);
  const evidence = stringList(row.evidence);
  const missing = stringList(row.missing_conditions);
  const entry = normalizeReference(row.entry_trigger);
  const invalidation = normalizeReference(row.invalidation);
  const stop = normalizeReference(row.stop_reference);
  const target = normalizeReference(row.target_reference);
  const risk = normalizeRisk(row.risk);
  if (!state || !id || !name || !evidence || !missing) return null;
  if (entry === undefined || invalidation === undefined || stop === undefined ||
      target === undefined || risk === undefined) return null;
  const options = record(row.options);
  return {
    id,
    name,
    state,
    direction: directionValue(row.direction),
    evidence,
    missingConditions: missing,
    entry,
    invalidation,
    stop,
    target,
    risk,
    waitReason: stringValue(row.wait_reason),
    timestamp: stringValue(row.timestamp),
    freshness: stringValue(row.freshness) ?? "unknown",
    strategyFamilies: Array.isArray(options.strategy_families)
      ? options.strategy_families.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function normalizeTradeIntelligence(
  value: unknown,
  symbol: WorkspaceSymbol,
  spot: number,
): WorkspaceTradeIntelligence | null {
  const row = record(value);
  if (row.schema_version !== "alphaos-trade-intelligence-v1" || row.symbol !== symbol) return null;
  if ("candles" in row || "bars" in row) return null;
  const session = record(row.session);
  const data = record(row.data);
  const levels = record(row.levels);
  const previous = record(levels.previous_session);
  const pivots = record(levels.pivots);
  const opening = record(levels.opening_range);
  const currentSession = record(levels.current_session);
  const vwap = record(levels.vwap);
  const ema9 = record(levels.ema9);
  const bias = record(row.bias);
  const exit = record(row.exit_early);
  const sessionState = ["open", "closed", "preopen", "unknown"].includes(String(session.state))
    ? session.state as WorkspaceSessionState : null;
  const dataStatus = ["verified", "incomplete", "stale", "unavailable"].includes(String(data.status))
    ? data.status as WorkspaceDataStatus : null;
  const state = tradeStateValue(row.state);
  const previousSession = {
    date: stringValue(previous.date),
    open: finitePositive(previous.open) ? previous.open : null,
    high: finitePositive(previous.high) ? previous.high : null,
    low: finitePositive(previous.low) ? previous.low : null,
    close: finitePositive(previous.close) ? previous.close : null,
  };
  if (!sessionState || !dataStatus || !state || !previousSession.date ||
      previousSession.open === null || previousSession.high === null ||
      previousSession.low === null || previousSession.close === null) return null;
  const pivotValues = {
    pivot: finitePositive(pivots.pivot) ? pivots.pivot : null,
    r1: finitePositive(pivots.r1) ? pivots.r1 : null,
    r2: finitePositive(pivots.r2) ? pivots.r2 : null,
    s1: finitePositive(pivots.s1) ? pivots.s1 : null,
    s2: finitePositive(pivots.s2) ? pivots.s2 : null,
  };
  if (Object.values(pivotValues).some((item) => item === null)) return null;
  const openingRange = finitePositive(opening.high) && finitePositive(opening.low)
    ? { high: opening.high, low: opening.low, status: stringValue(opening.status) ?? "complete" }
    : null;
  const rawReferences = Array.isArray(levels.references) ? levels.references : [];
  const references = rawReferences.flatMap((item): WorkspaceLevel[] => {
    const level = record(item);
    if (!finitePositive(level.price) || typeof level.label !== "string") return [];
    const distance = level.price - spot;
    return [{
      label: level.label,
      price: level.price,
      distance,
      distancePct: spot > 0 ? (distance / spot) * 100 : null,
      kind: levelKind(level.kind),
      source: stringValue(level.source) ?? undefined,
    }];
  });
  if (references.length !== rawReferences.length) return null;
  const setups = Array.isArray(row.setups) ? row.setups.map(normalizeSetup) : [];
  if (setups.length < 3 || setups.some((setup) => setup === null)) return null;
  const last = record(row.last_change);
  const lastChange = finitePositive(last.previous_close) && finitePositive(last.current_close)
    && stringValue(last.previous_at) && stringValue(last.current_at)
    ? {
        previousAt: String(last.previous_at),
        currentAt: String(last.current_at),
        previousClose: last.previous_close,
        currentClose: last.current_close,
        change: finiteNumber(last.change) ?? last.current_close - last.previous_close,
        changePct: finiteNumber(last.change_pct),
      }
    : null;
  return {
    schemaVersion: String(row.schema_version),
    symbol,
    sessionState,
    sessionDate: stringValue(session.date),
    dataStatus,
    freshness: stringValue(data.freshness) ?? "unknown",
    latestConfirmedAt: stringValue(data.latest_confirmed_candle_at),
    confirmedBars: finiteNumber(data.confirmed_bars) ?? 0,
    previousSession: {
      date: previousSession.date,
      open: previousSession.open,
      high: previousSession.high,
      low: previousSession.low,
      close: previousSession.close,
    },
    pivots: {
      pivot: pivotValues.pivot!,
      r1: pivotValues.r1!,
      r2: pivotValues.r2!,
      s1: pivotValues.s1!,
      s2: pivotValues.s2!,
    },
    openingRange,
    currentSession: {
      high: finitePositive(currentSession.high) ? currentSession.high : null,
      low: finitePositive(currentSession.low) ? currentSession.low : null,
    },
    vwap: finitePositive(vwap.price) ? vwap.price : null,
    ema9: finitePositive(ema9.price) ? ema9.price : null,
    references,
    bias: directionValue(bias.direction),
    state,
    reason: stringValue(row.reason) ?? "No setup reason was supplied.",
    activeSetupId: stringValue(row.active_setup_id),
    closestSetupId: stringValue(row.closest_setup_id),
    setups: setups as WorkspaceSetup[],
    lastChange,
    exitEarly: {
      state: stringValue(exit.state) ?? "UNAVAILABLE",
      reason: stringValue(exit.reason) ?? "No modeled position was supplied.",
    },
    warnings: Array.isArray(row.warnings)
      ? row.warnings.filter((item): item is string => typeof item === "string")
      : [],
  };
}

export function normalizeMarketResponse(value: unknown): WorkspaceSnapshot | null {
  const response = record(value);
  const data = record(response.data);
  const symbol = symbolValue(data.symbol);
  const spot = data.current_spot;
  const asOf = data.as_of;
  const source = data.source;
  const atr = data.atr_14;

  if (
    !symbol ||
    !finitePositive(spot) ||
    typeof asOf !== "string" ||
    !Number.isFinite(Date.parse(asOf)) ||
    (source !== "verified_archive" && source !== "live_public") ||
    !finitePositive(atr)
  ) {
    return null;
  }

  // Synthetic demo fixtures must never enter the trading workspace.
  if (source === "live_public" && response.isLive !== true) return null;
  if (source === "verified_archive" && response.isLive !== false) return null;

  const opportunity = record(data.opportunity_state);
  const rawLevels = Array.isArray(data.levels) ? data.levels : [];
  const levels = rawLevels.flatMap((row): WorkspaceLevel[] => {
    const level = record(row);
    if (typeof level.label !== "string" || !level.label.trim() || !finitePositive(level.price)) {
      return [];
    }
    const rawDistance = finiteNumber(level.distance);
    const rawDistancePct = finiteNumber(level.distance_pct);
    return [{
      label: level.label.trim(),
      price: level.price,
      distance: rawDistance ?? level.price - spot,
      distancePct: rawDistancePct ?? ((level.price - spot) / spot) * 100,
      kind: levelKind(level.kind),
    }];
  });

  const caveats = Array.isArray(opportunity.caveats)
    ? opportunity.caveats.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0,
      )
    : [];
  const warning = typeof response.warning === "string" && response.warning.trim()
    ? response.warning.trim()
    : null;
  const expectedMove = finitePositive(data.expected_move) ? data.expected_move : null;
  const tradeIntelligence = normalizeTradeIntelligence(response.trade_intelligence, symbol, spot);
  const tradeIntelligenceWarning = stringValue(response.trade_intelligence_warning);

  return {
    symbol,
    spot,
    asOf,
    source,
    isLive: source === "live_public",
    direction: directionValue(opportunity.direction),
    atr,
    expectedMove,
    levels,
    caveats,
    warning,
    tradeIntelligence,
    tradeIntelligenceWarning,
  };
}

function nearest(levels: WorkspaceLevel[]): WorkspaceLevel[] {
  return [...levels].sort((a, b) => {
    const aDistance = a.distancePct === null ? Number.POSITIVE_INFINITY : Math.abs(a.distancePct);
    const bDistance = b.distancePct === null ? Number.POSITIVE_INFINITY : Math.abs(b.distancePct);
    return aDistance - bDistance;
  });
}

export function buildWorkspaceAssessment(
  snapshot: WorkspaceSnapshot | null,
): WorkspaceAssessment {
  if (!snapshot) {
    return {
      stance: "UNAVAILABLE",
      bias: "unknown",
      biasLabel: "UNKNOWN",
      reason:
        "No verified market evidence is loaded. No BUY, SELL, entry, stop, target, or confidence value is generated.",
      evidenceGaps: [
        "Verified underlying observation",
        "Verified trade-intelligence contract",
        "Confirmed setup evidence",
      ],
      support: [],
      resistance: [],
      setups: [],
      closestSetup: null,
      exitEarly: null,
      sessionState: "unknown",
    };
  }

  const trade = snapshot.tradeIntelligence;
  const sourceLevels = trade?.references.length ? trade.references : snapshot.levels;
  const support = nearest(sourceLevels.filter((level) => level.kind === "support"));
  const resistance = nearest(sourceLevels.filter((level) => level.kind === "resistance"));

  if (!trade) {
    return {
      stance: "WAIT",
      bias: snapshot.direction,
      biasLabel: directionLabel(snapshot.direction),
      reason:
        "WAIT. The verified market snapshot is present, but the versioned setup contract is unavailable, so no BUY or SELL state is inferred. " +
        (snapshot.tradeIntelligenceWarning ?? "No setup evidence was returned."),
      evidenceGaps: [
        "Verified trade-intelligence contract",
        "Pivot points",
        "Opening range",
        "Confirmed setup trigger",
      ],
      support,
      resistance,
      setups: [],
      closestSetup: null,
      exitEarly: null,
      sessionState: "unknown",
    };
  }

  const closest = trade.setups.find((setup) => setup.id === trade.closestSetupId)
    ?? trade.setups.find((setup) => setup.state !== "WAIT")
    ?? trade.setups[0]
    ?? null;
  const evidenceGaps = [
    ...(closest?.missingConditions ?? []),
    ...(trade.dataStatus === "verified" ? [] : [`Intraday data is ${trade.dataStatus}.`]),
    ...(trade.sessionState === "closed" ? ["The regular session must be open for a new entry."] : []),
    ...(trade.sessionState === "preopen" ? ["The regular session has not opened."] : []),
  ];
  if (!evidenceGaps.length && trade.state === "WAIT") {
    evidenceGaps.push("A confirmed setup trigger.");
  }

  const active = trade.setups.find((setup) => setup.state !== "WAIT") ?? null;
  const setupReason = active
    ? `${active.name} is confirmed as ${active.state}. ${trade.reason}`
    : `${trade.reason}${closest ? ` Closest setup: ${closest.name}. Missing: ${closest.missingConditions.join(" ") || "none listed."}` : ""}`;

  return {
    stance: trade.state,
    bias: trade.bias,
    biasLabel: directionLabel(trade.bias),
    reason: setupReason,
    evidenceGaps,
    support,
    resistance,
    setups: trade.setups,
    closestSetup: closest,
    exitEarly: trade.exitEarly,
    sessionState: trade.sessionState,
  };
}

function dataLine(snapshot: WorkspaceSnapshot): string {
  const observation = snapshot.isLive
    ? "marked live by the AlphaOS bridge"
    : "a verified archive observation, not a live executable quote";
  return `${snapshot.symbol} is ${price(snapshot.spot)} as of ${snapshot.asOf} (${snapshot.source}; ${observation}).`;
}

function referenceLine(reference: WorkspacePriceReference | null): string {
  if (!reference) return "not supplied";
  const condition = reference.condition ? ` — ${reference.condition}` : "";
  const basis = reference.basis ? ` (${reference.basis})` : "";
  return `${price(reference.price)}${condition}${basis}`;
}

function setupLine(setup: WorkspaceSetup): string {
  const missing = setup.missingConditions.length
    ? ` Missing: ${setup.missingConditions.join(" ")}`
    : " No required conditions are listed as missing.";
  const entry = setup.entry ? ` Entry trigger: ${referenceLine(setup.entry)}.` : "";
  const invalidation = setup.invalidation
    ? ` Invalidation: ${referenceLine(setup.invalidation)}.` : "";
  return `${setup.name}: ${setup.state}.${entry}${invalidation}${missing}`;
}

function activeOrClosest(trade: WorkspaceTradeIntelligence): WorkspaceSetup | null {
  return trade.setups.find((setup) => setup.state !== "WAIT")
    ?? trade.setups.find((setup) => setup.id === trade.closestSetupId)
    ?? null;
}

function findSetup(trade: WorkspaceTradeIntelligence, id: string): WorkspaceSetup | null {
  return trade.setups.find((setup) => setup.id === id) ?? null;
}

function waitAnswer(snapshot: WorkspaceSnapshot): string {
  const trade = snapshot.tradeIntelligence;
  if (!trade) {
    return "WAIT because the verified trade-intelligence contract is unavailable. No BUY or SELL state is inferred from price alone.";
  }
  if (trade.state !== "WAIT") return `AlphaOS is not saying WAIT. The current research state is ${trade.state}. ${trade.reason}`;
  const closest = activeOrClosest(trade);
  const missing = closest?.missingConditions.length
    ? closest.missingConditions.join(" ")
    : "No specific condition is listed; review the data status and session warning.";
  const data = trade.dataStatus === "verified"
    ? `Confirmed through ${trade.latestConfirmedAt ?? "the latest confirmed candle"}.`
    : `Data status: ${trade.dataStatus}.`;
  return `WAIT. ${trade.reason} Closest setup: ${closest?.name ?? "none"}. Missing: ${missing} ${data}`;
}

function bullishEntryAnswer(snapshot: WorkspaceSnapshot): string {
  const trade = snapshot.tradeIntelligence;
  if (!trade) {
    return "The verified setup contract is unavailable, so I cannot state the exact bullish confirmation rule. No generic BUY threshold is invented.";
  }
  const confirmed = trade.setups.find((setup) => setup.state === "BUY");
  if (confirmed) {
    return `A bullish setup is confirmed: ${setupLine(confirmed)} This is an underlying research state, not an options order.`;
  }
  const candidates = [
    findSetup(trade, "opening_range_breakout"),
    findSetup(trade, "vwap_ema9_continuation"),
    findSetup(trade, "support_resistance_reversal"),
  ].filter((setup): setup is WorkspaceSetup => setup !== null);
  return candidates.map((setup) => setupLine(setup)).join(" ");
}

function bearishEntryAnswer(snapshot: WorkspaceSnapshot): string {
  const trade = snapshot.tradeIntelligence;
  if (!trade) {
    return "The verified setup contract is unavailable, so I cannot state the exact bearish confirmation rule. No generic SELL threshold is invented.";
  }
  const confirmed = trade.setups.find((setup) => setup.state === "SELL");
  if (confirmed) {
    return `A bearish setup is confirmed: ${setupLine(confirmed)} This is an underlying research state, not an options order.`;
  }
  const candidates = [
    findSetup(trade, "opening_range_breakout"),
    findSetup(trade, "vwap_ema9_continuation"),
    findSetup(trade, "support_resistance_reversal"),
  ].filter((setup): setup is WorkspaceSetup => setup !== null);
  return candidates.map((setup) => setupLine(setup)).join(" ");
}

function breakoutReversalAnswer(snapshot: WorkspaceSnapshot): string {
  const trade = snapshot.tradeIntelligence;
  if (!trade) {
    return "The verified setup contract is unavailable, so I cannot distinguish a breakout from a reversal. No state is inferred.";
  }
  const breakout = findSetup(trade, "opening_range_breakout");
  const reversal = findSetup(trade, "support_resistance_reversal");
  return [
    breakout ? setupLine(breakout) : "Opening-range breakout evidence is unavailable.",
    reversal ? setupLine(reversal) : "Support/resistance reversal evidence is unavailable.",
  ].join(" ");
}

function invalidationAnswer(snapshot: WorkspaceSnapshot): string {
  const trade = snapshot.tradeIntelligence;
  if (trade) {
    const setup = activeOrClosest(trade);
    if (setup?.invalidation) {
      const stop = setup.stop ? ` Stop reference: ${referenceLine(setup.stop)}.` : "";
      return `${setup.name} invalidation: ${referenceLine(setup.invalidation)}.${stop}`;
    }
  }
  const support = nearest(snapshot.levels.filter((level) => level.kind === "support"))[0];
  const resistance = nearest(snapshot.levels.filter((level) => level.kind === "resistance"))[0];
  if (support || resistance) {
    return `No setup-specific invalidation is available. The nearest verified support is ${support ? price(support.price) : "not supplied"}; nearest resistance is ${resistance ? price(resistance.price) : "not supplied"}. These are references, not an inferred stop.`;
  }
  return "No verified invalidation or stop reference is present in the current snapshot. Nothing is inferred.";
}

function changedAnswer(snapshot: WorkspaceSnapshot): string {
  const trade = snapshot.tradeIntelligence;
  if (!trade?.lastChange) {
    return "The contract does not contain two confirmed candles to compare. No change is inferred.";
  }
  const change = trade.lastChange;
  const pct = change.changePct === null ? "percentage unavailable" : `${change.changePct > 0 ? "+" : ""}${change.changePct.toFixed(2)}%`;
  return `The latest confirmed five-minute close changed from ${price(change.previousClose)} at ${change.previousAt} to ${price(change.currentClose)} at ${change.currentAt}: ${change.change > 0 ? "+" : ""}${change.change.toFixed(2)} (${pct}). The unconfirmed tail is excluded.`;
}

export function answerWorkspaceQuestion(
  snapshot: WorkspaceSnapshot | null,
  question: string,
): string {
  const text = question.trim().toLowerCase();
  if (!text) return "Ask a question about the selected symbol or a market concept.";

  // Concept questions win over keyword intents (for example "what is a pivot").
  if (/\bwhat is (a )?pivot|explain pivot/.test(text)) {
    return "A traditional pivot point is (prior high + prior low + prior close) / 3. R1 is 2 × pivot − prior low, S1 is 2 × pivot − prior high, R2 is pivot + (prior high − prior low), and S2 is pivot − (prior high − prior low). The workspace displays them only when completed prior-session OHLC is present.";
  }
  if (/\bwhat is (a )?(atr|average true range)|explain atr/.test(text)) {
    return "ATR is the average true range: a volatility measure based on recent high-low ranges. A larger ATR means wider recent movement. AlphaOS displays the backend ATR(14); it does not convert it into a trade signal.";
  }
  if (/\bwhat is (a )?(credit|debit) spread|explain (a )?spread/.test(text)) {
    return "A vertical spread combines a long and short option at different strikes of the same type and expiration. A debit spread is paid for up front; a credit spread receives premium and carries defined assignment/expiration risk. Availability, quotes, and risk must come from the verified research surfaces, not this chat.";
  }
  if (!snapshot) {
    return "Verified market evidence is unavailable. No BUY, SELL, entry, invalidation, stop, target, quote, or confidence value is generated.";
  }

  const trade = snapshot.tradeIntelligence;
  if (/what changed|previous confirmed|since the last candle|last confirmed candle/.test(text)) {
    return changedAnswer(snapshot);
  }
  if (/why.*wait|why wait|reason.*wait/.test(text)) {
    return waitAnswer(snapshot);
  }
  if (/what would confirm.*(bull|buy|up)|confirm.*bull|bullish entry/.test(text)) {
    return bullishEntryAnswer(snapshot);
  }
  if (/what would confirm.*(bear|sell|down)|confirm.*bear|bearish entry/.test(text)) {
    return bearishEntryAnswer(snapshot);
  }
  if (/break.*out|breakdown|revers/.test(text)) {
    return breakoutReversalAnswer(snapshot);
  }
  if (/invalidation|invalidat|\bstop\b/.test(text)) {
    return invalidationAnswer(snapshot);
  }
  if (/closest|nearest.*confirm|which setup/.test(text)) {
    if (!trade) return "The verified setup contract is unavailable, so no closest setup can be ranked.";
    const setup = activeOrClosest(trade);
    return setup
      ? `${setupLine(setup)}${setup.risk?.rewardToRisk ? ` Reward-to-risk from the supplied references: ${setup.risk.rewardToRisk.toFixed(2)}.` : ""}`
      : "No setup candidate is present in the contract.";
  }
  if (/\bpivot|opening range|\bor high\b|\bor low\b|previous[- ]day|prior[- ]day|\bpdh\b|\bpdl\b/.test(text)) {
    if (!trade) {
      return "The verified snapshot does not include a pivot-point series, previous-session OHLC, or an opening-range calculation. I will not infer those levels.";
    }
    const pivotText = `Pivot ${price(trade.pivots.pivot)}, R1 ${price(trade.pivots.r1)}, R2 ${price(trade.pivots.r2)}, S1 ${price(trade.pivots.s1)}, S2 ${price(trade.pivots.s2)}.`;
    const openingText = trade.openingRange
      ? ` Opening range high ${price(trade.openingRange.high)}, low ${price(trade.openingRange.low)}.`
      : " The opening range is not available.";
    return `Previous session ${trade.previousSession.date}: high ${price(trade.previousSession.high)}, low ${price(trade.previousSession.low)}, close ${price(trade.previousSession.close)}. ${pivotText}${openingText}`;
  }

  const tradeQuestion = /\bbuy\b|\bsell\b|\bwait\b|signal|recommend|entry|invalidation|\bstop\b|target|early exit|\btrade\b|should i/.test(text);
  if (tradeQuestion) {
    if (!trade) {
      return "WAIT — the verified setup contract is unavailable. No BUY, SELL, entry, stop, target, or confidence value is generated from bias alone.";
    }
    const active = trade.setups.find((setup) => setup.state !== "WAIT");
    if (active) {
      const risk = active.risk
        ? ` Underlying risk ${price(active.risk.underlyingRiskDistance)}; target distance ${active.risk.targetDistance === null ? "unavailable" : price(active.risk.targetDistance)}; reward-to-risk ${active.risk.rewardToRisk === null ? "unavailable" : active.risk.rewardToRisk.toFixed(2)}.`
        : "";
      return `${trade.state}. ${setupLine(active)}${risk} This is a research state, not an options order.`;
    }
    return waitAnswer(snapshot);
  }

  if (/support/.test(text) || /resistance/.test(text)) {
    const wanted = /support/.test(text)
      ? snapshot.tradeIntelligence?.references.filter((level) => level.kind === "support") ?? []
      : snapshot.tradeIntelligence?.references.filter((level) => level.kind === "resistance") ?? [];
    const fallback = /support/.test(text)
      ? snapshot.levels.filter((level) => level.kind === "support")
      : snapshot.levels.filter((level) => level.kind === "resistance");
    const levels = wanted.length ? wanted : fallback;
    const label = /support/.test(text) ? "support" : "resistance";
    if (!levels.length) return `No verified ${label} level is present in the current ${snapshot.symbol} snapshot.`;
    return `Verified ${label} levels: ${levelsSummary(levels)}. These are backend structure or calculated session levels; the browser does not add or recalculate them.`;
  }

  if (/trend|direction|bias|bull|bear|chop/.test(text)) {
    const bias = trade?.bias ?? snapshot.direction;
    return `AlphaOS classifies the current ${snapshot.symbol} descriptive bias as ${directionLabel(bias)}. ${trade ? `The research state is ${trade.state}: ${trade.reason}` : "This is a descriptive classifier output, not a BUY signal."}`;
  }

  if (/price|quote|spot|where.*trading|current/.test(text)) {
    return `${dataLine(snapshot)} This is an underlying observation only, not an executable options quote.`;
  }

  if (/\batr\b|volatil|expected move|range/.test(text)) {
    const expected = snapshot.expectedMove === null
      ? "No verified expected-move value is supplied."
      : `The backend expected move is ${price(snapshot.expectedMove)}.`;
    return `ATR(14) is ${price(snapshot.atr)}. ${expected} These are risk-context measurements, not forecasts.`;
  }

  if (/fresh|stale|delay|timestamp|as of|\blive\b|session|source/.test(text)) {
    const session = trade ? `Session state: ${trade.sessionState}.` : "Session status is not supplied by this payload.";
    const data = trade ? `Data status: ${trade.dataStatus}; latest confirmed candle ${trade.latestConfirmedAt ?? "unavailable"}.` : "";
    return `${dataLine(snapshot)} ${session} ${data} The unconfirmed candle tail is excluded from setup calculations.`;
  }

  if (/option|spread|strategy|contract|\biv\b|premium/.test(text)) {
    const families = trade?.setups.flatMap((setup) => setup.strategyFamilies) ?? [];
    const familyText = families.length
      ? ` Directional families that may be researched: ${Array.from(new Set(families)).join(", ")}.`
      : " No directional strategy family is asserted while the state is WAIT.";
    return `This workspace does not load option quotes, implied volatility, or contract prices.${familyText} An underlying BUY/SELL state is not a profitable options trade without exact contract evidence. Open Strategy Explorer (/strategies?symbol=${snapshot.symbol}) or Options Chain (/options?symbol=${snapshot.symbol}) for the existing evidence-gated research surfaces.`;
  }

  if (/help|what can|ask|capabilit/.test(text)) {
    return "Ask about the selected symbol's verified price, session levels, pivots, opening range, setup state, entry trigger, invalidation, closest setup, data freshness, or what changed since the previous confirmed candle. I only use the authenticated AlphaOS contract and will say when a field is missing.";
  }

  return "I can only answer from the verified AlphaOS contract: price, session levels, pivots, opening range, setup states, entry/invalidation references, risk distances, and freshness. I cannot verify that question, so I will not invent levels, confidence, quotes, or recommendations. Try asking why the state is WAIT, what would confirm a bullish entry, or where the nearest invalidation is.";
}
