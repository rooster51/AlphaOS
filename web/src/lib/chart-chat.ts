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
    data_status: evidence.data_status,
  };
}

/**
 * The evidence block is generated only from the verified AlphaOS record.
 * TradingView appears here solely as an explicit prohibition.
 */
export function buildSystemPrompt(evidence: ChartEvidence): string {
  const facts = {
    symbol: evidence.symbol,
    evidence_mode: MODE_LABEL[evidence.mode],
    data_source: "AlphaOS research API (Public provider observations)",
    quote_as_of_utc: evidence.as_of,
    evidence_age_seconds_at_retrieval: evidence.age_seconds,
    underlying_price: evidence.spot,
    atr_14: evidence.atr_14,
    market_state: evidence.market_state,
    backend_price_levels: evidence.levels,
    backend_data_status: evidence.data_status,
    backend_freshness: evidence.freshness,
    market_session: evidence.market_session,
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
    "3. Always state the evidence timestamp when you describe conditions, and label the evidence as current-market or point-in-time exactly as given. If it is point-in-time, say it is historical and not current market conditions.",
    "4. Levels above are backend-generated from completed history. Describe them as AlphaOS levels with the recorded timestamp; do not present them as exact levels visible on TradingView.",
    "5. Answers are educational research, not advice, not a signal, not an executable quote, and not a prediction of future prices.",
    "6. Options ideas may only be framed as areas the user could research (structure, risk, expiration). Never recommend placing an order, never size a position, and never claim an edge.",
    "7. If the user asks for anything the evidence cannot support (intraday trend, volume, indicator values, current bid/ask, news), state clearly what is missing and offer what the evidence does support.",
    "8. Keep answers concise, conversational and evidence-based. Do not use headings unless the answer needs structure.",
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

/** Disclosures returned with every reply and rendered in the UI. */
export function disclosuresFor(evidence: ChartEvidence): string[] {
  const disclosures = [
    "The assistant receives the selected symbol and AlphaOS research evidence only. It has no access to TradingView candles, indicators, drawings or chart state.",
    `Evidence source: ${evidence.source} via the AlphaOS research API, observed ${evidence.as_of} (${evidence.age_seconds}s old at retrieval).`,
  ];
  if (evidence.mode === "point_in_time") {
    disclosures.push(
      "This evidence is point-in-time and is not current market conditions. The market may have moved since the recorded observation.");
  } else {
    disclosures.push(
      "This evidence was fresh at retrieval. It is a research observation, not an executable quote or a broker price.");
  }
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
