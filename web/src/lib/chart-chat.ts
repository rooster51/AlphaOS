/**
 * Pure request/response policy for the Charting & AI assistant.
 *
 * The model is grounded only on the server-supplied AlphaOS evidence record.
 * Nothing in this module reads TradingView; the guard below rejects replies
 * that claim chart, candle, indicator or drawing visibility.
 */
import type {
  ChartEvidence,
  ChatEvidenceSummary,
  ChatTurn,
  EvidenceMode,
} from "./chart-types.ts";

export const MAX_HISTORY_MESSAGES = 12;
export const MAX_MESSAGE_CHARS = 2_000;
export const MAX_TOTAL_CHARS = 12_000;
export const MAX_REPLY_CHARS = 8_000;

export type ParsedChatRequest = { symbol: "SPY" | "QQQ"; messages: ChatTurn[] };

export function parseChatRequest(value: unknown): ParsedChatRequest | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  if (Object.keys(input).some((key) => key !== "symbol" && key !== "messages")) return null;

  if (typeof input.symbol !== "string") return null;
  const symbol = input.symbol.toUpperCase();
  if (symbol !== "SPY" && symbol !== "QQQ") return null;

  if (!Array.isArray(input.messages) || input.messages.length === 0 ||
      input.messages.length > MAX_HISTORY_MESSAGES) return null;

  const messages: ChatTurn[] = [];
  let total = 0;
  for (const item of input.messages) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return null;
    const turn = item as Record<string, unknown>;
    if (Object.keys(turn).some((key) => key !== "role" && key !== "content")) return null;
    if (turn.role !== "user" && turn.role !== "assistant") return null;
    if (typeof turn.content !== "string") return null;
    const content = turn.content.trim();
    if (!content || content.length > MAX_MESSAGE_CHARS) return null;
    total += content.length;
    if (total > MAX_TOTAL_CHARS) return null;
    messages.push({ role: turn.role, content });
  }
  if (messages[messages.length - 1]?.role !== "user") return null;
  return { symbol, messages };
}

const MODE_LABEL: Record<EvidenceMode, string> = {
  current: "CURRENT-MARKET EVIDENCE (fresh at retrieval)",
  point_in_time: "POINT-IN-TIME EVIDENCE (not current market conditions)",
};

export function evidenceSummary(evidence: ChartEvidence): ChatEvidenceSummary {
  return {
    symbol: evidence.symbol,
    mode: evidence.mode,
    source: evidence.source,
    as_of: evidence.as_of,
    age_seconds: evidence.age_seconds,
    spot: evidence.spot,
    atr_14: evidence.atr_14,
    levels: evidence.levels,
    quote: evidence.quote,
    completed_session: evidence.completed_session,
    technical_as_of: evidence.technical_as_of,
    levels_as_of: evidence.levels_as_of,
    market_state: evidence.market_state,
    data_status: evidence.data_status,
    freshness: evidence.freshness,
    market_session: evidence.market_session,
    caveats: evidence.caveats,
  };
}

/** Marker used in the prompt for a dimension the backend never reported. */
const UNREPORTED = "not reported by the AlphaOS backend";

/**
 * The evidence block is generated only from the verified AlphaOS record.
 * TradingView appears here solely as an explicit prohibition.
 */
export function buildSystemPrompt(evidence: ChartEvidence): string {
  const state = evidence.market_state;
  const unreported: string[] = [];
  if (!state.direction_reported) unreported.push("market direction");
  if (state.ema_structure === null) unreported.push("EMA trend structure");
  if (state.close === null) unreported.push("completed-session close");
  if (state.as_of === null) unreported.push("completed-session date");
  if (state.ema_9 === null || state.ema_21 === null || state.ema_50 === null) {
    unreported.push("completed-session EMA values");
  }
  if (state.movement_state === null) unreported.push("movement state");
  if (state.volatility_state === null) unreported.push("volatility state");
  if (state.premium_state === null) unreported.push("premium state");
  const modeLabel = evidence.mode === "current" ? MODE_LABEL.current
    : evidence.quote.session === "overnight"
      ? "POINT-IN-TIME OVERNIGHT OBSERVATION (not current market conditions)"
      : evidence.quote.session === "extended_hours" || evidence.quote.session === "off_hours"
        ? "POINT-IN-TIME EXTENDED/OFF-HOURS OBSERVATION (not current market conditions)"
        : MODE_LABEL.point_in_time;
  const facts = {
    symbol: evidence.symbol,
    evidence_mode: modeLabel,
    data_source: "AlphaOS research API (Public provider observations)",
    quote_observation: {
      observed_quote_price: evidence.quote.price,
      quote_as_of_utc: evidence.quote.as_of,
      market_session: evidence.quote.session,
      observation_context: evidence.quote.context,
      is_current_market: evidence.quote.current,
      executable: false,
      overnight_ats_verified: evidence.quote.ats_verified,
      data_status: evidence.quote.data_status,
      freshness: evidence.quote.freshness,
      freshness_reason: evidence.quote.reason ?? UNREPORTED,
      market_state_source: evidence.quote.market_state_source ?? UNREPORTED,
    },
    completed_session_technical_structure: {
      session: evidence.completed_session.session ?? UNREPORTED,
      close: evidence.completed_session.close ?? UNREPORTED,
      as_of: evidence.completed_session.as_of ?? UNREPORTED,
      ema_structure: state.ema_structure ?? UNREPORTED,
      ema_9: state.ema_9 ?? UNREPORTED,
      ema_21: state.ema_21 ?? UNREPORTED,
      ema_50: state.ema_50 ?? UNREPORTED,
    },
    evidence_age_seconds_at_retrieval: evidence.age_seconds,
    observed_quote_price: evidence.spot,
    atr_14: evidence.atr_14,
    market_state: {
      direction: state.direction_reported ? state.direction : UNREPORTED,
      backend_ema_trend_structure: state.ema_structure ?? UNREPORTED,
      completed_session_close: state.close ?? UNREPORTED,
      completed_session_date: state.as_of ?? UNREPORTED,
      ema_9: state.ema_9 ?? UNREPORTED,
      ema_21: state.ema_21 ?? UNREPORTED,
      ema_50: state.ema_50 ?? UNREPORTED,
      movement_state: state.movement_state ?? UNREPORTED,
      volatility_state: state.volatility_state ?? UNREPORTED,
      premium_state: state.premium_state ?? UNREPORTED,
    },
    backend_price_levels: evidence.levels,
    backend_levels_as_of: evidence.levels_as_of ?? UNREPORTED,
    backend_levels_anchor_quote_price: evidence.spot,
    backend_unreported_dimensions: unreported,
    backend_data_status: evidence.data_status,
    backend_freshness: evidence.freshness,
    market_session_at_retrieval: evidence.market_session,
    backend_caveats: evidence.caveats,
  };

  return [
    "You are the AlphaOS Charting & AI research assistant for a read-only options research terminal.",
    "You explain only the AlphaOS evidence record supplied below. You have no other market data.",
    "",
    `## AlphaOS evidence (${evidence.symbol})`,
    JSON.stringify(facts, null, 2),
    "",
    "## Hard rules",
    "1. You cannot see the embedded TradingView chart, its candles, indicators, studies, drawings, trendlines, overlays, watchlists or widget state. AlphaOS does not receive them. Never claim, imply or guess what the chart displays, and never describe candles you were not given.",
    "2. Do not invent quotes, candles, volumes, indicators, moving averages, support/resistance prices, signals, probabilities, expected values or trade recommendations. If a value is not in the evidence above, say it is unavailable.",
    "3. Always state both timestamps when you describe conditions: quote_observation.quote_as_of_utc for the observed quote and completed_session_technical_structure.as_of for the EMA/levels. Label the evidence as current-market or point-in-time exactly as given. If it is point-in-time, say it is historical and not current market conditions.",
    "4. Levels above are backend-generated from completed history. Describe them as AlphaOS levels with the recorded timestamp; do not present them as exact levels visible on TradingView. Their distance is from backend_levels_anchor_quote_price, not from the completed-session close.",
    "5. Answers are educational research, not advice, not a signal, not an executable quote, and not a prediction of future prices.",
    "6. Options ideas may only be framed as areas the user could research (structure, risk, expiration). Never recommend placing an order, never size a position, and never claim an edge.",
    "7. If the user asks for anything the evidence cannot support (intraday trend, volume, indicator values, current bid/ask, news), state clearly what is missing and offer what the evidence does support.",
    "8. Keep answers concise, conversational and evidence-based. Do not use headings unless the answer needs structure.",
    "9. Distinguish missing evidence from neutral conditions. Any dimension listed in backend_unreported_dimensions, and any value reading 'not reported by the AlphaOS backend', was not supplied by AlphaOS. Say the backend does not provide it. Never restate a missing classification as neutral, balanced, mixed, range-bound, calm or consolidating.",
    "10. backend_ema_trend_structure is the backend's EMA ordering for the completed session (bullish, bearish or mixed); 'mixed' means no clean EMA ordering, not a neutral forecast. The numeric ema_9, ema_21 and ema_50 values are from the same completed-session row. An empty backend_price_levels list means the backend returned no levels for this snapshot, not that price has no structure.",
    "11. quote_observation and completed_session_technical_structure are separate dated observations. Never call the observed quote a completed-session close or imply the EMA/levels were computed from it.",
    "12. If quote_observation.is_current_market is false, do not present the quote as a current market price. If its market_session is overnight, extended_hours or off_hours, say it is an overnight/after-hours observation, that overnight ATS status is unverified, and that it is not an executable quote.",
    "13. NO TRADE: when evidence is insufficient, stale, overnight-only or missing, do not recommend a trade, an option price, a probability or a position size. State what is unavailable and what the evidence can support.",
    "14. Do not estimate or invent probabilities, expected values, option premiums, bid/ask spreads or position sizes. Those values are not in the evidence and must be described as unavailable.",
  ].join("\n");
}

export function buildModelMessages(
  evidence: ChartEvidence,
  messages: ChatTurn[],
): Array<{ role: "system" | "user" | "assistant"; content: string }> {
  return [
    { role: "system", content: buildSystemPrompt(evidence) },
    ...messages.map((message) => ({ role: message.role, content: message.content })),
  ];
}

/**
 * Fail-closed detector for claims of direct chart access. The route replaces
 * any matching reply; model output is never returned with a chart claim.
 */
const CHART_CLAIM_PATTERNS: RegExp[] = [
  /\bi (?:can|could|am able to) (?:see|read|view|access) (?:your|the) (?:tradingview )?(?:chart|candles?|indicators?|drawings?|studies)\b/i,
  /\b(?:looking at|based on) (?:your|the) (?:tradingview |embedded |live )?chart\b/i,
  /\b(?:your|the) (?:tradingview )?(?:chart|candles?) (?:currently )?(?:shows?|displays?|indicates?|tells?)\b/i,
  /\b(?:the|your) (?:current|latest) candle (?:shows?|closed|is|was)\b/i,
  /\bi (?:have|can get) access to (?:your|the) (?:tradingview )?(?:chart|candles?)\b/i,
  /\b(?:drawings?|trendlines?|indicators?|studies) (?:on|in) your chart\b/i,
  /\b(?:i|we) (?:see|read) (?:the|your) (?:tradingview|embedded) chart\b/i,
];

export function detectChartAccessClaim(reply: string): boolean {
  return CHART_CLAIM_PATTERNS.some((pattern) => pattern.test(reply));
}

export const SAFE_CHART_CLAIM_REPLY = [
  "I can't read the TradingView chart. AlphaOS does not receive its candles, indicators, drawings or widget state,",
  "so I can't describe what it currently shows.",
  "",
  "I can only discuss the independently retrieved AlphaOS evidence for this symbol, including its timestamp and",
  "any backend-generated price levels. If you rephrase the question around that evidence, I can help with it.",
].join(" ");

/**
 * Focused post-generation check for claims the evidence cannot support. This is
 * deliberately narrow: it is not a general hallucination detector, and it only
 * replaces replies containing a positive probability, option-quote, sizing or
 * direct recommendation claim. Negated/unavailable statements are allowed.
 */
const UNSUPPORTED_TRADE_PATTERNS: RegExp[] = [
  /\b(?:probability|chance|odds|likelihood)\b[^.\n]{0,50}\b\d{1,3}(?:\.\d+)?\s*%/i,
  /\b\d{1,3}(?:\.\d+)?\s*%\s*(?:probability|chance|odds|likelihood)\b/i,
  /\bexpected value\b[^.\n]{0,50}\$?\d/i,
  /\b(?:option|call|put|contract|spread)\b[^.\n]{0,60}\b(?:bid|ask|premium|price)\b[^.\n]{0,30}\$?\d+(?:\.\d+)?/i,
  /\b(?:bid|ask|premium)\b[^.\n]{0,30}\$?\d+(?:\.\d+)?[^.\n]{0,40}\b(?:option|call|put|contract|spread)\b/i,
  /\b(?:buy|sell|short|long)\s+\d+\s+(?:contracts?|shares?|lots?)\b/i,
  /\b(?:size|position size)\b[^.\n]{0,40}\b\d+\s*(?:contracts?|shares?|lots?)\b/i,
  /\b(?:risk|allocate)\s+\d+(?:\.\d+)?\s*%\b/i,
  /\b(?:i recommend|my recommendation is|you should)\b[^.\n]{0,100}\b(?:buy|sell|enter|short|long|spread|straddle|strangle|condor)\b/i,
];

function negatedSentence(reply: string, index: number): boolean {
  const start = Math.max(0, reply.lastIndexOf(".", index - 1) + 1);
  const end = reply.indexOf(".", index);
  const sentence = reply.slice(start, end < 0 ? reply.length : end).toLowerCase();
  return /\b(?:not|no|never|without|cannot|can't|don't|doesn't|unavailable|insufficient)\b/.test(sentence);
}

export function detectUnsupportedTradeClaim(reply: string): boolean {
  for (const pattern of UNSUPPORTED_TRADE_PATTERNS) {
    const match = pattern.exec(reply);
    if (match && !negatedSentence(reply, match.index)) return true;
  }
  return false;
}

export const SAFE_UNSUPPORTED_TRADE_REPLY = [
  "I can't support that from the AlphaOS evidence. The record contains no option quotes, probabilities,",
  "expected values, or position-sizing inputs, so I won't provide a specific option price, probability estimate,",
  "or position size. I can discuss the observed quote, the completed-session EMA structure, and the",
  "backend price levels instead. This is research, not advice or an order.",
].join(" ");

/** Disclosures returned with every reply and rendered in the UI. */
export function disclosuresFor(evidence: ChartEvidence): string[] {
  const disclosures = [
    "The assistant receives the selected symbol and AlphaOS research evidence only. It has no access to TradingView candles, indicators, drawings or chart state.",
    `Evidence source: ${evidence.source} via the AlphaOS research API, observed ${evidence.as_of} (${evidence.age_seconds}s old at retrieval).`,
  ];
  disclosures.push(
    `Observed quote: ${evidence.quote.price.toFixed(2)} at ${evidence.quote.as_of}, session ${evidence.quote.session}; this is not an executable quote or a broker price.`);
  if (evidence.quote.session === "overnight" || evidence.quote.context === "overnight_observation") {
    disclosures.push(
      "The observed quote is an overnight/off-hours print. Overnight ATS coverage and entitlement are unverified; it is not a current-market price.");
  } else if (evidence.mode === "point_in_time") {
    disclosures.push(
      "This evidence is point-in-time and is not current market conditions. The market may have moved since the recorded observation.");
  } else {
    disclosures.push(
      "This evidence was fresh at retrieval. It is a research observation, not an executable quote or a broker price.");
  }
  disclosures.push(
    `Completed-session technical structure: ${evidence.completed_session.session ?? "unavailable"} close ${evidence.completed_session.close?.toFixed(2) ?? "unavailable"}; EMA and levels are separate from the observed quote.`);
  disclosures.push(
    "TradingView chart data may be delayed and is not used, read or verified by AlphaOS.");
  return disclosures;
}

export type ChatConfiguration =
  | { configured: true; endpoint: string; model: string; key: string }
  | { configured: false; message: string };

const DEFAULT_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions";

export function chatConfiguration(
  env: Record<string, string | undefined> = {},
): ChatConfiguration {
  const key = env.ALPHAOS_CHAT_API_KEY?.trim();
  const model = env.ALPHAOS_CHAT_MODEL?.trim();
  if (!key || !model) {
    return {
      configured: false,
      message:
        "The AlphaOS AI assistant is not configured on this deployment. " +
        "An operator must set ALPHAOS_CHAT_API_KEY and ALPHAOS_CHAT_MODEL " +
        "(optionally ALPHAOS_CHAT_API_URL) on the web service. No answer was generated.",
    };
  }
  const raw = env.ALPHAOS_CHAT_API_URL?.trim() || DEFAULT_CHAT_ENDPOINT;
  let endpoint: URL;
  try {
    endpoint = new URL(raw);
    const loopback = endpoint.hostname === "127.0.0.1" ||
      endpoint.hostname === "localhost" || endpoint.hostname === "[::1]";
    const secure = endpoint.protocol === "https:" ||
      (endpoint.protocol === "http:" && loopback);
    if (!secure || endpoint.username || endpoint.password) {
      throw new Error("Invalid chat endpoint");
    }
  } catch {
    return {
      configured: false,
      message:
        "The AlphaOS AI assistant endpoint configuration is invalid. " +
        "ALPHAOS_CHAT_API_URL must be an HTTPS chat-completions URL.",
    };
  }
  return { configured: true, endpoint: endpoint.toString(), model, key };
}

export function buildChatRequestBody(
  configuration: { endpoint: string; model: string },
  evidence: ChartEvidence,
  messages: ChatTurn[],
): Record<string, unknown> {
  return {
    model: configuration.model,
    temperature: 0.2,
    max_tokens: 700,
    stream: false,
    messages: buildModelMessages(evidence, messages),
  };
}

export function parseChatCompletion(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const choices = (value as Record<string, unknown>).choices;
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const first = choices[0];
  if (!first || typeof first !== "object" || Array.isArray(first)) return null;
  const message = (first as Record<string, unknown>).message;
  if (!message || typeof message !== "object" || Array.isArray(message)) return null;
  const content = (message as Record<string, unknown>).content;
  if (typeof content !== "string") return null;
  const reply = content.trim();
  if (!reply || reply.length > MAX_REPLY_CHARS) return null;
  return reply;
}

/**
 * Sanitised upstream failure classification.
 *
 * A provider rejection used to be reported as one opaque "provider error",
 * which made an invalid key, an unavailable model, an exhausted quota, a wrong
 * endpoint and a provider outage indistinguishable. Only the HTTP status and a
 * fixed category leave this module: provider error messages and bodies can echo
 * request metadata and are never returned or logged.
 */
export type ProviderFailureCategory =
  | "invalid_api_key"
  | "authentication"
  | "permission_denied"
  | "model_not_found"
  | "endpoint_not_found"
  | "quota_exceeded"
  | "rate_limited"
  | "invalid_request"
  | "provider_unavailable"
  | "unknown";

export type ProviderFailure = { status: number; category: ProviderFailureCategory };

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

/**
 * Providers shape error envelopes differently: OpenAI sends
 * `{ error: { type, code, message } }`, while Gemini's OpenAI compatibility
 * layer wraps the same object in a one-element array and reports a rejected
 * key as HTTP 400 `INVALID_ARGUMENT` rather than 401. Fields are read from
 * either shape and flattened for matching only.
 */
function providerErrorFields(payload: unknown): string {
  const root = Array.isArray(payload) ? record(payload[0]) : record(payload);
  const error = record(root?.error) ?? root;
  if (!error) return "";
  const details = Array.isArray(error.details) ? error.details : [];
  const reasons = details
    .map((detail) => record(detail)?.reason)
    .filter((reason): reason is string => typeof reason === "string");
  return [
    error.status,
    error.type,
    error.code,
    error.reason,
    ...reasons,
    error.message,
  ]
    .filter((item): item is string => typeof item === "string")
    .join(" ")
    .toLowerCase();
}

export function classifyProviderFailure(status: number, payload: unknown): ProviderFailure {
  const code = Number.isInteger(status) && status >= 100 && status <= 599 ? status : 0;
  const fields = providerErrorFields(payload);
  // Gemini reports an invalid or restricted key as HTTP 400 API_KEY_INVALID.
  if (/api[_ -]?key|credential|unauthenticated/.test(fields)) {
    return { status: code, category: "invalid_api_key" };
  }
  if (code === 401) return { status: code, category: "authentication" };
  if (code === 403) return { status: code, category: "permission_denied" };
  if (code === 404) {
    return { status: code, category: /model/.test(fields) ? "model_not_found" : "endpoint_not_found" };
  }
  if (code === 429) {
    return {
      status: code,
      category: /quota|resource_exhausted|billing/.test(fields)
        ? "quota_exceeded" : "rate_limited",
    };
  }
  if (code === 400) {
    if (/model/.test(fields) && /not found|does not exist|not supported|unsupported|invalid/.test(fields)) {
      return { status: code, category: "model_not_found" };
    }
    return { status: code, category: "invalid_request" };
  }
  if (code >= 500) return { status: code, category: "provider_unavailable" };
  return { status: code, category: "unknown" };
}
