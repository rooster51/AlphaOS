/**
 * Deterministic workspace evidence and assistant answers.
 *
 * This module never creates prices, levels, confidence scores, option quotes,
 * or trade recommendations. It only normalizes the existing `/api/market`
 * response and answers questions from fields that are actually present.
 */

export type WorkspaceSymbol = "SPY" | "QQQ";
export type WorkspaceDirection = "bullish" | "bearish" | "neutral" | "unknown";
export type WorkspaceLevelKind = "support" | "resistance" | "mid" | "atr";

export type WorkspaceLevel = {
  label: string;
  price: number;
  distance: number | null;
  distancePct: number | null;
  kind: WorkspaceLevelKind;
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
};

export type WorkspaceAssessment = {
  stance: "WAIT" | "UNAVAILABLE";
  bias: WorkspaceDirection;
  biasLabel: string;
  reason: string;
  evidenceGaps: string[];
  support: WorkspaceLevel[];
  resistance: WorkspaceLevel[];
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

function symbolValue(value: unknown): WorkspaceSymbol | null {
  return value === "SPY" || value === "QQQ" ? value : null;
}

function directionValue(value: unknown): WorkspaceDirection {
  return value === "bullish" || value === "bearish" || value === "neutral"
    ? value
    : "unknown";
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
  };
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
        "Pivot points",
        "Previous-day high and low",
        "Opening range",
        "Entry and invalidation model",
        "Stop-loss and target model",
        "Early-exit model",
      ],
      support: [],
      resistance: [],
    };
  }

  const labels = snapshot.levels.map((level) => level.label.toLowerCase());
  const evidenceGaps = [
    ...(labels.some((label) => label.includes("pivot")) ? [] : ["Pivot points"]),
    ...(labels.some((label) =>
      /previous[- ]day|prior[- ]day|\bpdh\b|\bpdl\b|previous.*(?:high|low)|prior.*(?:high|low)/.test(label),
    )
      ? []
      : ["Previous-day high and low"]),
    "Opening range",
    "Entry and invalidation model",
    "Stop-loss and target model",
    "Early-exit model",
  ];

  const near = (level: WorkspaceLevel) =>
    level.distancePct === null ? Number.POSITIVE_INFINITY : Math.abs(level.distancePct);
  const support = snapshot.levels
    .filter((level) => level.kind === "support")
    .sort((a, b) => near(a) - near(b));
  const resistance = snapshot.levels
    .filter((level) => level.kind === "resistance")
    .sort((a, b) => near(a) - near(b));

  return {
    stance: "WAIT",
    bias: snapshot.direction,
    biasLabel: directionLabel(snapshot.direction),
    reason: `The verified snapshot provides a ${directionLabel(snapshot.direction)} descriptive bias. No verified entry/invalidation, stop/target, or early-exit model is connected, so the workspace stays WAIT.`,
    evidenceGaps,
    support,
    resistance,
  };
}

function dataLine(snapshot: WorkspaceSnapshot): string {
  const observation = snapshot.isLive
    ? "marked live by the AlphaOS bridge"
    : "a verified archive observation, not a live executable quote";
  return `${snapshot.symbol} is ${price(snapshot.spot)} as of ${snapshot.asOf} (${snapshot.source}; ${observation}).`;
}

export function answerWorkspaceQuestion(
  snapshot: WorkspaceSnapshot | null,
  question: string,
): string {
  const text = question.trim().toLowerCase();
  if (!text) return "Ask a question about the selected symbol or a market concept.";

  // Concept questions win over keyword intents (for example "what is a pivot").
  if (/\bwhat is (a )?pivot|explain pivot/.test(text)) {
    return "A pivot point is a reference level calculated from a prior session's high, low, and close. This workspace does not have prior-session OHLC in its verified payload, so it will not display a calculated pivot.";
  }
  if (/\bwhat is (a )?(atr|average true range)|explain atr/.test(text)) {
    return "ATR is the average true range: a volatility measure based on recent high-low ranges. A larger ATR means wider recent movement. AlphaOS displays the backend ATR(14); it does not convert it into a trade signal.";
  }
  if (/\bwhat is (a )?(credit|debit) spread|explain (a )?spread/.test(text)) {
    return "A vertical spread combines a long and short option at different strikes of the same type and expiration. A debit spread is paid for up front; a credit spread receives premium and carries defined assignment/expiration risk. Availability, quotes, and risk must come from the verified research surfaces, not this chat.";
  }

  const pivotQuestion = /\bpivot|\bprevious[- ]day|\bprior[- ]day|\bpdh\b|\bpdl\b|opening range|\bor high\b|\bor low\b/.test(text);
  const tradeQuestion = /\bbuy\b|\bsell\b|\bwait\b|signal|recommend|entry|invalidation|\bstop\b|target|early exit|\btrade\b|should i/.test(text);
  const supportQuestion = /support/.test(text);
  const resistanceQuestion = /resistance/.test(text);
  const trendQuestion = /trend|direction|bias|bull|bear|chop/.test(text);
  const priceQuestion = /price|quote|spot|where.*trading|current/.test(text);
  const volatilityQuestion = /\batr\b|volatil|expected move|range/.test(text);
  const freshnessQuestion = /fresh|stale|delay|timestamp|as of|\blive\b|session|source/.test(text);
  const optionsQuestion = /option|spread|strategy|contract|\biv\b|premium/.test(text);
  const helpQuestion = /help|what can|ask|capabilit/.test(text);

  if (pivotQuestion) {
    const available = snapshot && snapshot.levels.length
      ? ` Available backend reference levels: ${levelsSummary(snapshot.levels)}.`
      : "";
    return `The verified snapshot does not include a pivot-point series, previous-day high/low, or an opening-range calculation. I will not infer those levels.${available}`;
  }

  if (tradeQuestion) {
    if (!snapshot) {
      return "WAIT — verified market evidence is unavailable. No BUY, SELL, entry, stop, target, or confidence value is generated.";
    }
    return `WAIT. No verified entry, invalidation, stop-loss, target, or early-exit model is connected to this workspace. The evidence shows a ${directionLabel(snapshot.direction)} descriptive bias, but bias alone is not a trade signal. Use Strategy Explorer for evidence-gated option structures; it is research only, not a recommendation.`;
  }

  if (supportQuestion || resistanceQuestion) {
    if (!snapshot) {
      return "Verified market evidence is unavailable, so no support or resistance levels are displayed. No levels are inferred.";
    }
    const wanted = supportQuestion
      ? snapshot.levels.filter((level) => level.kind === "support")
      : snapshot.levels.filter((level) => level.kind === "resistance");
    const label = supportQuestion ? "support" : "resistance";
    if (!wanted.length) return `No verified ${label} level is present in the current ${snapshot.symbol} snapshot.`;
    return `Verified ${label} levels: ${levelsSummary(wanted)}. These are backend structure levels; the browser does not add or recalculate them.`;
  }

  if (trendQuestion) {
    if (!snapshot) {
      return "Trend classification is unavailable because no verified snapshot is loaded. No direction is inferred.";
    }
    return `AlphaOS classifies the current ${snapshot.symbol} direction as ${directionLabel(snapshot.direction)}. That is a descriptive classifier output, not a BUY signal, confidence score, or forecast.`;
  }

  if (priceQuestion) {
    if (!snapshot) {
      return "A verified price is unavailable. No quote or substitute price is displayed.";
    }
    return `${dataLine(snapshot)} This is an underlying observation only, not an executable options quote.`;
  }

  if (volatilityQuestion) {
    if (!snapshot) {
      return "ATR and expected-move evidence are unavailable because no verified snapshot is loaded.";
    }
    const expected = snapshot.expectedMove === null
      ? "No verified expected-move value is supplied."
      : `The backend expected move is ${price(snapshot.expectedMove)}.`;
    return `ATR(14) is ${price(snapshot.atr)}. ${expected} These are risk-context measurements, not forecasts.`;
  }

  if (freshnessQuestion) {
    if (!snapshot) {
      return "Data freshness is unavailable because no verified snapshot is loaded.";
    }
    return `The snapshot is ${snapshot.source}, observed at ${snapshot.asOf}. It is ${snapshot.isLive ? "marked live by the AlphaOS bridge" : "a verified archive observation"}. Session open/close status is not supplied by this endpoint, so it is not inferred.`;
  }

  if (optionsQuestion) {
    return `This workspace does not load option quotes, implied volatility, or contract prices. Open Strategy Explorer (/strategies?symbol=${snapshot?.symbol ?? "SPY"}) or Options Chain (/options?symbol=${snapshot?.symbol ?? "SPY"}) for the existing evidence-gated research surfaces. No option price or recommendation is substituted.`;
  }

  if (helpQuestion) {
    return "Ask about the selected symbol's verified price, trend, support/resistance, ATR, or data freshness. I can explain pivots, opening ranges, and option spreads generally. I only use the verified AlphaOS snapshot and will say when a field is missing.";
  }

  return "I can only answer from the verified AlphaOS snapshot: price, direction, support/resistance, ATR, and freshness. I cannot verify that question, so I will not invent levels, confidence, quotes, or recommendations. Try asking about price, trend, support, resistance, volatility, or data freshness.";
}
