import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { loadChartEvidence, logEvidenceTiming } from "../src/lib/chart-evidence.ts";
import {
  MAX_HISTORY_MESSAGES,
  SAFE_CHART_CLAIM_REPLY,
  buildChatRequestBody,
  buildSystemPrompt,
  chatConfiguration,
  classifyProviderFailure,
  detectChartAccessClaim,
  detectUnsupportedTradeClaim,
  parseChatCompletion,
  parseChatRequest,
  SAFE_UNSUPPORTED_TRADE_REPLY,
} from "../src/lib/chart-chat.ts";
import { POST as chatPost } from "../src/app/api/charts/chat/route.ts";

const AS_OF = "2026-11-04T15:30:00+00:00";
const NOW = Date.parse("2026-11-04T15:31:00Z");
const ENV_KEYS = [
  "ALPHAOS_API_TOKEN",
  "ALPHAOS_API_URL",
  "ALPHAOS_CHAT_API_KEY",
  "ALPHAOS_CHAT_MODEL",
  "ALPHAOS_CHAT_API_URL",
];
const envBackup = Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const key of ENV_KEYS) {
    if (envBackup[key] === undefined) delete process.env[key];
    else process.env[key] = envBackup[key];
  }
});

function marketEnvelope(symbol, options = {}) {
  return {
    meta: {
      schema_version: "alphaos-research-v1",
      symbol,
      source: "Public",
      snapshot_id: options.snapshotId ?? "snap-test",
      quote_as_of: AS_OF,
      research_session: "2026-11-03",
      research_close: options.researchClose === undefined ? 500 : options.researchClose,
      current_spot: options.currentSpot === undefined ? 500 : options.currentSpot,
      quote_freshness: {
        data_status: options.dataStatus ?? "fresh",
        freshness: options.freshness ?? "fresh",
        market_state: options.marketState ?? "regular_open",
        quote_session: options.quoteSession ?? "regular_session",
        observation_context: options.observationContext ?? "regular_session_observation",
        freshness_reason: options.freshnessReason ?? "within_active_age_limit",
        market_state_source: "NYSE calendar; 04:00-20:00 ET extended policy; overnight ATS status unverified",
        overnight_ats_verified: false,
        usable_for_live_research: options.usable ?? true,
      },
      quote_retrieved_at: "2026-11-04T15:30:01+00:00",
    },
    evidence: {
      market_state: {
        date: "2026-11-03T00:00:00",
        close: options.researchClose === undefined ? 500 : options.researchClose,
        ema_structure: "bullish",
        ema_9: 499,
        ema_21: 498,
        ema_50: 497,
        direction: "bullish",
        movement_state: "directional",
        volatility_state: "normal",
      },
      underlying_quote: { quote: { last: 500 }, retrieved_at: "2026-11-04T15:30:01+00:00" },
    },
    caveats: ["Underlying observations are not executable option quotes."],
  };
}

function structureEnvelope(symbol, options = {}) {
  return {
    meta: {
      schema_version: "alphaos-research-v1",
      symbol,
      source: "Public",
      snapshot_id: options.snapshotId ?? "snap-test",
      quote_as_of: AS_OF,
      current_spot: options.currentSpot === undefined ? 500 : options.currentSpot,
    },
    evidence: {
      atr: options.atr === undefined ? 6.5 : options.atr,
      anchor_spot: options.currentSpot === undefined ? 500 : options.currentSpot,
      research_close: options.researchClose === undefined ? 500 : options.researchClose,
      structure_as_of: "2026-11-03",
      levels: options.levels ?? [
        { label: "PIVOT_HIGH_20", price: 505.5, kind: "resistance", distance_pct: 1.1 },
        { label: "PIVOT_LOW_20", price: 494.2, side: "support", distance_pct: -1.16 },
      ],
    },
    caveats: ["Levels are generated from completed history."],
  };
}

function fakeFetch(handler) {
  return async (url, options) => handler(String(url), options);
}

function jsonFetch(market, structure) {
  return fakeFetch((url) => {
    if (url.includes("/v1/market/")) return Response.json(market);
    if (url.includes("/v1/structure/")) return Response.json(structure);
    throw new Error(`unexpected url ${url}`);
  });
}

const options = {
  token: "test-token",
  baseUrl: "https://research.example",
  now: () => NOW,
};

test("loadChartEvidence verifies a fresh market/structure pair", async () => {
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("SPY"), structureEnvelope("SPY")),
  });

  assert.equal(result.status, "ok");
  const { evidence } = result;
  assert.equal(evidence.symbol, "SPY");
  assert.equal(evidence.mode, "current");
  assert.equal(evidence.source, "Public");
  assert.equal(evidence.as_of, AS_OF);
  assert.equal(evidence.age_seconds, 60);
  assert.equal(evidence.spot, 500);
  assert.equal(evidence.atr_14, 6.5);
  assert.equal(evidence.levels.length, 2);
  assert.equal(evidence.levels[0].kind, "resistance");
  assert.equal(evidence.levels[1].kind, "support");
  assert.equal(evidence.market_state.direction, "bullish");
  assert.equal(evidence.data_status, "fresh");
});

test("overnight evidence is point-in-time and keeps quote and completed-session provenance separate", async () => {
  const result = await loadChartEvidence("QQQ", {
    ...options,
    request: jsonFetch(
      marketEnvelope("QQQ", {
        currentSpot: null,
        dataStatus: "latest_available",
        freshness: "stale",
        marketState: "closed",
        quoteSession: "overnight",
        observationContext: "overnight_observation",
        freshnessReason: "overnight_observation",
        usable: false,
      }),
      structureEnvelope("QQQ", { currentSpot: null }),
    ),
  });

  assert.equal(result.status, "ok");
  assert.equal(result.evidence.mode, "point_in_time");
  assert.equal(result.evidence.as_of, AS_OF);
  assert.equal(result.evidence.spot, 500);
  assert.equal(result.evidence.data_status, "latest_available");
  assert.equal(result.evidence.quote.session, "overnight");
  assert.equal(result.evidence.quote.context, "overnight_observation");
  assert.equal(result.evidence.quote.current, false);
  assert.equal(result.evidence.quote.executable, false);
  assert.equal(result.evidence.quote.ats_verified, false);
  assert.equal(result.evidence.completed_session.session, "2026-11-03");
  assert.equal(result.evidence.completed_session.close, 500);
  assert.equal(result.evidence.technical_as_of, "2026-11-03");
  assert.equal(result.evidence.levels_as_of, "2026-11-03");
  assert.match(result.evidence.caveats[0], /overnight\/off-hours print/);

  const prompt = buildSystemPrompt(result.evidence);
  assert.match(prompt, /POINT-IN-TIME OVERNIGHT OBSERVATION/);
  assert.match(prompt, /"market_session": "overnight"/);
  assert.match(prompt, /"is_current_market": false/);
  assert.match(prompt, /"completed_session_technical_structure"/);
  assert.match(prompt, /"session": "2026-11-03"/);
  assert.match(prompt, /overnight ATS status is unverified/);
});

test("missing current_spot never promotes underlying.last to a current quote", async () => {
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(
      marketEnvelope("SPY", { currentSpot: null, usable: true }),
      structureEnvelope("SPY", { currentSpot: null }),
    ),
  });
  assert.equal(result.status, "ok");
  assert.equal(result.evidence.spot, 500);
  assert.equal(result.evidence.mode, "point_in_time");
  assert.equal(result.evidence.quote.current, false);
  assert.equal(result.evidence.quote.session, "regular_session");
});

// Shapes copied from a live serialization of the backend engine: /v1/market
// returns the completed-session feature row, /v1/structure returns clustered
// level records with `side`, `level`, zone bounds and `sources`.
function backendMarketEnvelope(symbol, state = {}, options = {}) {
  const currentSpot = options.currentSpot === undefined ? 660.48 : options.currentSpot;
  const envelope = marketEnvelope(symbol, { currentSpot, researchClose: currentSpot, ...options });
  envelope.evidence.market_state = {
    date: "2026-11-03T00:00:00",
    symbol,
    close: currentSpot,
    return_5d: 0.0123,
    rsi_14: 54.2,
    distance_ema_21_atr: 0.81,
    realized_vol_20d: 0.043,
    range_position_20: 0.72,
    ema_structure: "mixed",
    ...state,
  };
  return envelope;
}

function backendStructureEnvelope(symbol, options = {}) {
  const currentSpot = options.currentSpot === undefined ? 660.48 : options.currentSpot;
  const envelope = structureEnvelope(symbol, { currentSpot, researchClose: currentSpot });
  envelope.evidence.levels = [
    { side: "support", level: 650.1, zone_low: 649.2, zone_high: 651,
      distance_pct: -0.0157, distance_atr: -0.63, observations: 3,
      last_observed_sessions_ago: 12, sources: "swing_low, 20d_low", abs_distance_atr: 0.63 },
    { side: "resistance", level: 672.4, zone_low: 671, zone_high: 673.8,
      distance_pct: 0.018, distance_atr: 0.73, observations: 2,
      last_observed_sessions_ago: 4, sources: "swing_high", abs_distance_atr: 0.73 },
  ];
  return envelope;
}

test("backend level records and the completed-session trend structure are mapped", async () => {
  const result = await loadChartEvidence("QQQ", {
    ...options,
    request: jsonFetch(backendMarketEnvelope("QQQ"), backendStructureEnvelope("QQQ")),
  });

  assert.equal(result.status, "ok");
  const { evidence } = result;
  assert.equal(evidence.spot, 660.48);
  assert.deepEqual(evidence.levels, [
    { label: "swing low, 20d low", price: 650.1, kind: "support", distance_pct: -1.57,
      zone_low: 649.2, zone_high: 651 },
    { label: "swing high", price: 672.4, kind: "resistance", distance_pct: 1.8,
      zone_low: 671, zone_high: 673.8 },
  ]);
  assert.equal(evidence.market_state.ema_structure, "mixed");
  assert.equal(evidence.market_state.direction, "unknown");
  assert.equal(evidence.market_state.direction_reported, false);
  assert.equal(evidence.completed_session.close, 660.48);
  assert.equal(evidence.completed_session.session, "2026-11-03");
  assert.equal(evidence.levels_as_of, "2026-11-03");

  const prompt = buildSystemPrompt(evidence);
  assert.match(prompt, /"backend_ema_trend_structure": "mixed"/);
  assert.match(prompt, /"direction": "not reported by the AlphaOS backend"/);
  assert.match(prompt, /"market direction"/);
  assert.match(prompt, /swing low, 20d low/);
  assert.ok(!/"direction": "neutral"/.test(prompt));

  const bearish = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(
      backendMarketEnvelope("SPY", {
        close: 100, ema_9: 101, ema_21: 102, ema_50: 103, ema_structure: "bearish",
      }, { currentSpot: 100 }),
      backendStructureEnvelope("SPY", { currentSpot: 100 }),
    ),
  });
  assert.equal(bearish.status, "ok");
  assert.equal(bearish.evidence.market_state.ema_9, 101);
  assert.equal(bearish.evidence.market_state.ema_21, 102);
  assert.equal(bearish.evidence.market_state.ema_50, 103);
  const bearishPrompt = buildSystemPrompt(bearish.evidence);
  assert.match(bearishPrompt, /"ema_9": 101/);
  assert.match(bearishPrompt, /"ema_21": 102/);
  assert.match(bearishPrompt, /"ema_50": 103/);

  const inconsistent = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(
      backendMarketEnvelope("SPY", {
        close: 100, ema_9: 101, ema_21: 102, ema_50: 103, ema_structure: "bullish",
      }, { currentSpot: 100 }),
      backendStructureEnvelope("SPY", { currentSpot: 100 }),
    ),
  });
  assert.equal(inconsistent.status, "unavailable");
  assert.equal(inconsistent.code, "market_evidence_mismatch");
});

test("missing classifications are disclosed, never reported as neutral", async () => {
  const market = marketEnvelope("SPY");
  market.evidence.market_state = {};
  const structure = structureEnvelope("SPY");
  structure.evidence.levels = [];

  const result = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(market, structure),
  });

  assert.equal(result.status, "ok");
  assert.deepEqual(result.evidence.levels, []);
  assert.equal(result.evidence.market_state.direction_reported, false);
  assert.equal(result.evidence.market_state.ema_structure, null);

  const prompt = buildSystemPrompt(result.evidence);
  for (const dimension of ["market direction", "EMA trend structure",
    "movement state", "volatility state", "premium state"]) {
    assert.match(prompt, new RegExp(dimension), dimension);
  }
  assert.match(prompt, /"backend_price_levels": \[\]/);
  assert.ok(!/"direction": "neutral"/.test(prompt));
  assert.ok(!/"backend_ema_trend_structure": "mixed"/.test(prompt));
});

test("an explicit backend neutral direction and conflicting EMA structure are both preserved", async () => {
  const market = marketEnvelope("SPY");
  market.evidence.market_state = {
    direction: "neutral",
    ema_structure: "bullish",
    movement_state: "range_bound",
    volatility_state: null,
    premium_state: "fair",
  };

  const result = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(market, structureEnvelope("SPY")),
  });

  assert.equal(result.status, "ok");
  assert.equal(result.evidence.market_state.direction, "neutral");
  assert.equal(result.evidence.market_state.direction_reported, true);
  assert.equal(result.evidence.market_state.ema_structure, "bullish");
  assert.equal(result.evidence.market_state.movement_state, "range_bound");
  assert.equal(result.evidence.market_state.volatility_state, null);

  const prompt = buildSystemPrompt(result.evidence);
  assert.match(prompt, /"direction": "neutral"/);
  assert.match(prompt, /"backend_ema_trend_structure": "bullish"/);
  assert.match(prompt, /"volatility state"/);
  assert.ok(!/"market direction"/.test(prompt));
});

test("evidence is unavailable rather than substituted when pairs disagree", async () => {
  const mismatch = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("SPY"), structureEnvelope("SPY", { snapshotId: "other" })),
  });
  assert.equal(mismatch.status, "unavailable");
  assert.equal(mismatch.code, "market_evidence_mismatch");

  const wrongSymbol = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("QQQ"), structureEnvelope("SPY")),
  });
  assert.equal(wrongSymbol.status, "unavailable");
  assert.equal(wrongSymbol.code, "market_evidence_mismatch");

  const missingAtr = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("SPY"), structureEnvelope("SPY", { atr: null })),
  });
  assert.equal(missingAtr.code, "market_evidence_mismatch");
});

test("evidence failures map to explicit codes without fabricating data", async () => {
  let calls = 0;
  const unconfigured = await loadChartEvidence("SPY", {
    token: "",
    request: async () => {
      calls += 1;
      return Response.json({});
    },
  });
  assert.equal(unconfigured.code, "market_evidence_not_configured");
  assert.equal(calls, 0);

  const upstream = await loadChartEvidence("SPY", {
    ...options,
    request: async () => Response.json({ error: "down" }, { status: 503 }),
  });
  assert.equal(upstream.code, "market_evidence_backend_error");

  const schema = await loadChartEvidence("SPY", {
    ...options,
    request: async () => Response.json({ meta: {} }),
  });
  assert.equal(schema.code, "market_evidence_schema_mismatch");

  const unsupported = await loadChartEvidence("IWM", options);
  assert.equal(unsupported.code, "unsupported_chart_symbol");
});

test("a hanging research backend produces a timeout, not a stall", async () => {
  const hanging = (url, init) => new Promise((resolve, reject) => {
    init.signal.addEventListener("abort", () =>
      reject(new DOMException("The operation was aborted.", "AbortError")));
  });
  const result = await loadChartEvidence("SPY", {
    ...options,
    timeoutMs: 5,
    request: hanging,
  });
  assert.equal(result.status, "unavailable");
  assert.equal(result.code, "market_evidence_timeout");
});

test("system prompt carries evidence and forbids TradingView access claims", async () => {
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("SPY"), structureEnvelope("SPY")),
  });
  const prompt = buildSystemPrompt(result.evidence);
  assert.match(prompt, /cannot see the embedded TradingView chart/);
  assert.match(prompt, /never describe candles you were not given/i);
  assert.match(prompt, new RegExp(AS_OF.replace(/[.+]/g, "\\$&")));
  assert.match(prompt, /PIVOT_HIGH_20/);
  assert.match(prompt, /CURRENT-MARKET EVIDENCE/);
});

test("unsupported trade claims are detected without blocking unavailable-value statements", () => {
  const claims = [
    "There is a 65% probability of profit on this spread.",
    "The option premium is $1.25 and the bid is 1.20.",
    "Buy 3 contracts of the 505 call.",
    "Size the position at 2 contracts.",
    "You should sell a put spread here.",
    "Expected value is $42 per contract.",
  ];
  for (const claim of claims) assert.equal(detectUnsupportedTradeClaim(claim), true, claim);

  const safe = [
    "I can't provide a probability of profit from this evidence.",
    "Option quotes, expected values and position sizing are unavailable.",
    "The evidence does not contain an executable option price or a recommendation.",
    "There is no probability estimate or position size in the AlphaOS record.",
  ];
  for (const reply of safe) assert.equal(detectUnsupportedTradeClaim(reply), false, reply);
  assert.match(SAFE_UNSUPPORTED_TRADE_REPLY, /no option quotes/);
});

test("chart access claims are detected, including plausible paraphrases", () => {
  const claims = [
    "Looking at your chart, I can see resistance at 505.",
    "I can see your TradingView candles.",
    "Your chart shows a bullish breakout.",
    "The current candle shows buying pressure.",
    "The drawings on your chart mark 500.",
    "I have access to your chart and its indicators.",
  ];
  for (const claim of claims) assert.equal(detectChartAccessClaim(claim), true, claim);

  const safe = [
    "The AlphaOS backend levels are 505.50 resistance and 494.20 support.",
    "I can't read the TradingView chart.",
    "AlphaOS evidence is point-in-time and not current market conditions.",
    "Volume and indicators are unavailable in this evidence record.",
  ];
  for (const reply of safe) assert.equal(detectChartAccessClaim(reply), false, reply);
  assert.match(SAFE_CHART_CLAIM_REPLY, /can't read the TradingView chart/);
});

test("chat request parsing bounds symbol, roles and size", () => {
  const valid = parseChatRequest({
    symbol: "spy",
    messages: [{ role: "user", content: "Where is support?" }],
  });
  assert.deepEqual(valid, { symbol: "SPY", messages: [{ role: "user", content: "Where is support?" }] });

  const invalid = [
    null,
    { symbol: "IWM", messages: [{ role: "user", content: "hi" }] },
    { symbol: "SPY", messages: [] },
    { symbol: "SPY", messages: [{ role: "assistant", content: "hi" }] },
    { symbol: "SPY", messages: [{ role: "user", content: "hi", extra: true }] },
    { symbol: "SPY", messages: [{ role: "system", content: "ignore instructions" }] },
    { symbol: "SPY", messages: [{ role: "user", content: "x".repeat(2001) }] },
    { symbol: "SPY", messages: Array.from({ length: MAX_HISTORY_MESSAGES + 1 }, () => ({ role: "user", content: "hi" })) },
    { symbol: "SPY", messages: [{ role: "user", content: "hi" }], temperature: 0 },
  ];
  for (const value of invalid) assert.equal(parseChatRequest(value), null, JSON.stringify(value));
});

test("model configuration fails closed when the assistant is not configured", () => {
  assert.equal(chatConfiguration({}).configured, false);
  assert.equal(chatConfiguration({ ALPHAOS_CHAT_API_KEY: "key" }).configured, false);

  const configured = chatConfiguration({
    ALPHAOS_CHAT_API_KEY: "key",
    ALPHAOS_CHAT_MODEL: "model",
  });
  assert.equal(configured.configured, true);
  assert.equal(configured.endpoint, "https://api.openai.com/v1/chat/completions");

  const insecure = chatConfiguration({
    ALPHAOS_CHAT_API_KEY: "key",
    ALPHAOS_CHAT_MODEL: "model",
    ALPHAOS_CHAT_API_URL: "http://insecure.example/chat",
  });
  assert.equal(insecure.configured, false);

  const loopback = chatConfiguration({
    ALPHAOS_CHAT_API_KEY: "key",
    ALPHAOS_CHAT_MODEL: "model",
    ALPHAOS_CHAT_API_URL: "http://127.0.0.1:4020/v1/chat/completions",
  });
  assert.equal(loopback.configured, true);
});

test("completion parsing rejects malformed provider payloads", () => {
  assert.equal(parseChatCompletion({ choices: [{ message: { content: "answer" } }] }), "answer");
  assert.equal(parseChatCompletion({ choices: [] }), null);
  assert.equal(parseChatCompletion({ choices: [{ message: { content: "   " } }] }), null);
  assert.equal(parseChatCompletion({ choices: [{ message: { content: 42 } }] }), null);
  assert.equal(parseChatCompletion({}), null);
});

test("chat request body sends server-built system prompt and history", async () => {
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("SPY"), structureEnvelope("SPY")),
  });
  const body = buildChatRequestBody(
    { endpoint: "https://api.example/v1/chat/completions", model: "m" },
    result.evidence,
    [{ role: "user", content: "Is this a breakout?" }],
  );
  assert.equal(body.model, "m");
  assert.equal(body.stream, false);
  assert.equal(body.messages[0].role, "system");
  assert.equal(body.messages[1].role, "user");
  assert.equal(body.messages.length, 2);
});

test("chat route returns an explicit unavailable state without a model call", async () => {
  delete process.env.ALPHAOS_CHAT_API_KEY;
  delete process.env.ALPHAOS_CHAT_MODEL;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return Response.json({});
  };

  const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "hello" }] }),
  }));
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.code, "chat_not_configured");
  assert.match(body.message, /ALPHAOS_CHAT_API_KEY/);
  assert.equal(calls, 0);
});

test("chat route rejects invalid payloads and foreign origins", async () => {
  const invalid = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol: "IWM", messages: [{ role: "user", content: "hi" }] }),
  }));
  assert.equal(invalid.status, 400);

  const foreign = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin: "https://evil.example",
      host: "localhost:3000",
    },
    body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "hi" }] }),
  }));
  assert.equal(foreign.status, 403);
  assert.equal((await foreign.json()).code, "cross_origin_rejected");
});

test("chat route grounds a reply and never exposes provider credentials", async () => {
  process.env.ALPHAOS_API_TOKEN = "research-secret";
  process.env.ALPHAOS_API_URL = "https://research.example";
  process.env.ALPHAOS_CHAT_API_KEY = "chat-secret";
  process.env.ALPHAOS_CHAT_MODEL = "grounded-model";
  process.env.ALPHAOS_CHAT_API_URL = "https://chat.example/v1/chat/completions";

  const reply = "AlphaOS evidence as of 2026-11-04T15:30:00+00:00 shows a bullish backend direction with resistance at 505.50. This is research, not advice.";
  let providerBody;
  globalThis.fetch = fakeFetch((url, init) => {
    if (url.includes("/v1/market/")) return Response.json(marketEnvelope("SPY"));
    if (url.includes("/v1/structure/")) return Response.json(structureEnvelope("SPY"));
    if (url === "https://chat.example/v1/chat/completions") {
      providerBody = JSON.parse(init.body);
      return Response.json({ choices: [{ message: { content: reply } }] });
    }
    throw new Error(`unexpected url ${url}`);
  });

  const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "Is this a breakout?" }] }),
  }));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.status, "ok");
  assert.equal(body.reply, reply);
  assert.equal(body.chart_access, "none");
  assert.equal(body.chart_claim_blocked, false);
  assert.equal(body.trade_claim_blocked, false);
  assert.equal(body.model, "grounded-model");
  assert.equal(body.evidence.as_of, AS_OF);
  assert.equal(body.evidence.market_state.direction, "bullish");
  assert.equal(body.evidence.market_state.direction_reported, true);
  assert.ok(body.disclosures.some((item) => /no access to TradingView/.test(item)));
  assert.match(providerBody.messages[0].content, /TradingView/);
  assert.equal(providerBody.messages[1].content, "Is this a breakout?");

  const serialized = JSON.stringify(body);
  assert.ok(!serialized.includes("chat-secret"));
  assert.ok(!serialized.includes("research-secret"));
});

test("chat route replaces unsupported probability, option-price and sizing claims", async () => {
  process.env.ALPHAOS_API_TOKEN = "research-secret";
  process.env.ALPHAOS_API_URL = "https://research.example";
  process.env.ALPHAOS_CHAT_API_KEY = "chat-secret";
  process.env.ALPHAOS_CHAT_MODEL = "grounded-model";
  process.env.ALPHAOS_CHAT_API_URL = "https://chat.example/v1/chat/completions";

  globalThis.fetch = fakeFetch((url) => {
    if (url.includes("/v1/market/")) return Response.json(marketEnvelope("SPY"));
    if (url.includes("/v1/structure/")) return Response.json(structureEnvelope("SPY"));
    return Response.json({
      choices: [{ message: { content: "There is a 65% probability of profit. Buy 3 contracts at $1.25 premium." } }],
    });
  });

  const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "What is the trade?" }] }),
  }));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.chart_claim_blocked, false);
  assert.equal(body.trade_claim_blocked, true);
  assert.equal(body.reply, SAFE_UNSUPPORTED_TRADE_REPLY);
  assert.ok(!body.reply.includes("65%"));
  assert.ok(!body.reply.includes("$1.25"));
});

test("chat route replaces replies that claim TradingView chart access", async () => {
  process.env.ALPHAOS_API_TOKEN = "research-secret";
  process.env.ALPHAOS_API_URL = "https://research.example";
  process.env.ALPHAOS_CHAT_API_KEY = "chat-secret";
  process.env.ALPHAOS_CHAT_MODEL = "grounded-model";
  process.env.ALPHAOS_CHAT_API_URL = "https://chat.example/v1/chat/completions";

  globalThis.fetch = fakeFetch((url) => {
    if (url.includes("/v1/market/")) return Response.json(marketEnvelope("QQQ"));
    if (url.includes("/v1/structure/")) return Response.json(structureEnvelope("QQQ"));
    return Response.json({
      choices: [{ message: { content: "Looking at your chart, I can see resistance at 505.50 right now." } }],
    });
  });

  const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol: "QQQ", messages: [{ role: "user", content: "What do you see on my chart?" }] }),
  }));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.chart_claim_blocked, true);
  assert.equal(body.reply, SAFE_CHART_CLAIM_REPLY);
  assert.ok(!body.reply.includes("505.50"));
});

test("evidence configuration comes from deployment bindings, never a hardcoded backend", async () => {
  delete process.env.ALPHAOS_API_URL;
  delete process.env.ALPHAOS_API_TOKEN;
  let calls = 0;
  const result = await loadChartEvidence("SPY", {
    request: async () => {
      calls += 1;
      return Response.json({});
    },
  });
  assert.equal(result.code, "market_evidence_not_configured");
  assert.equal(calls, 0);
});

test("chat configuration never reads ambient process state implicitly", () => {
  process.env.ALPHAOS_CHAT_API_KEY = "ambient-key";
  process.env.ALPHAOS_CHAT_MODEL = "ambient-model";
  // The route must pass runtime bindings explicitly: env is the Worker env on
  // Cloudflare and process.env only on the Node/Netlify runtime.
  assert.equal(chatConfiguration().configured, false);
});

test("chat route refuses when verified evidence is unavailable", async () => {
  process.env.ALPHAOS_CHAT_API_KEY = "chat-secret";
  process.env.ALPHAOS_CHAT_MODEL = "grounded-model";
  process.env.ALPHAOS_CHAT_API_URL = "https://chat.example/v1/chat/completions";
  process.env.ALPHAOS_API_TOKEN = "research-secret";
  process.env.ALPHAOS_API_URL = "https://research.example";

  let modelCalls = 0;
  globalThis.fetch = fakeFetch((url) => {
    if (url.includes("/v1/market/")) {
      return Response.json({ error: { code: "stale_quote" } }, { status: 503 });
    }
    modelCalls += 1;
    return Response.json({ choices: [{ message: { content: "should not happen" } }] });
  });

  const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "hi" }] }),
  }));
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.code, "market_evidence_backend_error");
  assert.equal(modelCalls, 0);
});

function hangingStructure() {
  return (url, init) => {
    if (String(url).includes("/v1/market/")) {
      return Promise.resolve(Response.json(marketEnvelope("SPY")));
    }
    return new Promise((resolve, reject) => {
      init.signal.addEventListener("abort", () =>
        reject(new DOMException("The operation was aborted.", "AbortError")));
    });
  };
}

test("a slow structure leg times out as a structure-phase timeout", async () => {
  const timings = [];
  const startedAt = Date.now();
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: hangingStructure(),
    timeoutMs: 40,
    budgetMs: 2_000,
    onTiming: (timing) => timings.push(timing),
  });

  assert.equal(result.status, "unavailable");
  assert.equal(result.code, "market_evidence_timeout");
  assert.equal("evidence" in result, false, "no partial evidence is returned");
  assert.equal(timings.length, 1, "timing is reported once");
  assert.equal(timings[0].timeout_phase, "structure");
  assert.ok(timings[0].market_ms !== null, "market leg is measured");
  assert.ok(timings[0].structure_ms !== null, "structure leg is measured");
  assert.ok(Date.now() - startedAt < 2_000, "the request stays bounded");
});

test("the shared budget bounds a slow market leg below the platform limit", async () => {
  const timings = [];
  const startedAt = Date.now();
  const hanging = (url, init) => new Promise((resolve, reject) => {
    init.signal.addEventListener("abort", () =>
      reject(new DOMException("The operation was aborted.", "AbortError")));
  });
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: hanging,
    timeoutMs: 30_000,
    budgetMs: 60,
    onTiming: (timing) => timings.push(timing),
  });

  assert.equal(result.code, "market_evidence_timeout");
  assert.equal(timings[0].timeout_phase, "market");
  assert.equal(timings[0].budget_ms, 60);
  assert.equal(timings[0].structure_ms, null, "structure was never attempted");
  assert.ok(Date.now() - startedAt < 2_000, "the budget, not the 30s cap, stopped it");
});

test("a failed market leg never requests structure and reports no timeout phase", async () => {
  const calls = [];
  const timings = [];
  const result = await loadChartEvidence("SPY", {
    ...options,
    budgetMs: 2_000,
    request: async (url) => {
      calls.push(String(url));
      return Response.json({ error: { code: "stale_quote" } }, { status: 503 });
    },
    onTiming: (timing) => timings.push(timing),
  });

  assert.equal(result.code, "market_evidence_backend_error");
  assert.equal(calls.length, 1);
  assert.match(calls[0], /\/v1\/market\/SPY/);
  assert.equal(timings[0].timeout_phase, null);
  assert.equal(timings[0].structure_ms, null);
});

test("structure is requested only after market and carries its verified snapshot id", async () => {
  const order = [];
  const result = await loadChartEvidence("SPY", {
    ...options,
    request: async (url) => {
      order.push(String(url));
      if (String(url).includes("/v1/market/")) {
        return Response.json(marketEnvelope("SPY", { snapshotId: "snap-abc123" }));
      }
      return Response.json(structureEnvelope("SPY", { snapshotId: "snap-abc123" }));
    },
  });

  assert.equal(result.status, "ok");
  assert.equal(order.length, 2);
  assert.match(order[0], /\/v1\/market\/SPY\?horizon=3$/);
  assert.match(order[1], /\/v1\/structure\/SPY\?horizon=3&levels=5&snapshot_id=snap-abc123$/);
});

test("timing diagnostics carry durations only and stay gated off by default", async () => {
  const timings = [];
  await loadChartEvidence("SPY", {
    ...options,
    request: jsonFetch(marketEnvelope("SPY"), structureEnvelope("SPY")),
    onTiming: (timing) => timings.push(timing),
  });
  const [timing] = timings;
  assert.deepEqual(Object.keys(timing).sort(),
    ["budget_ms", "market_ms", "structure_ms", "symbol", "timeout_phase", "total_ms"]);
  assert.equal(timing.timeout_phase, null);
  assert.ok(timing.market_ms >= 0 && timing.structure_ms >= 0 && timing.total_ms >= 0);
  assert.ok(!JSON.stringify(timing).includes("test-token"));

  const lines = [];
  const originalLog = console.log;
  console.log = (...args) => lines.push(args.join(" "));
  try {
    delete process.env.ALPHAOS_PREVIEW_DIAGNOSTICS;
    logEvidenceTiming("charts_evidence_timing", timing, "ok");
    assert.equal(lines.length, 0, "diagnostics are off without the preview flag");

    process.env.ALPHAOS_PREVIEW_DIAGNOSTICS = "true";
    logEvidenceTiming("charts_evidence_timing", timing, "ok");
    assert.equal(lines.length, 1);
    const line = JSON.parse(lines[0]);
    assert.equal(line.event, "charts_evidence_timing");
    assert.equal(line.outcome, "ok");
    assert.equal(line.budget_ms, timing.budget_ms);
    assert.ok(!lines[0].includes("test-token"), "never a credential");
    assert.ok(!lines[0].includes("research.example"), "never the backend host");
  } finally {
    console.log = originalLog;
    delete process.env.ALPHAOS_PREVIEW_DIAGNOSTICS;
  }
});

test("provider failures are classified from status and envelope, not provider prose", () => {
  const cases = [
    [400, [{ error: { code: 400, message: "Please pass a valid API key", status: "INVALID_ARGUMENT" } }], "invalid_api_key"],
    [400, { error: { type: "invalid_request_error", code: "invalid_api_key" } }, "invalid_api_key"],
    [401, { error: { type: "authentication_error" } }, "authentication"],
    [403, { error: { code: 403, message: "API not enabled", status: "PERMISSION_DENIED" } }, "permission_denied"],
    [404, { error: { code: 404, message: "models/gemini-9.9-nope is not found for API version v1beta" } }, "model_not_found"],
    [404, { error: { code: 404, message: "The requested URL /v1/chat was not found on this server." } }, "endpoint_not_found"],
    [429, [{ error: { status: "RESOURCE_EXHAUSTED", message: "Quota exceeded for quota metric" } }], "quota_exceeded"],
    [429, { error: { code: "rate_limit_exceeded" } }, "rate_limited"],
    [400, { error: { status: "INVALID_ARGUMENT", message: "Invalid JSON payload: unknown field" } }, "invalid_request"],
    [500, { error: { status: "INTERNAL" } }, "provider_unavailable"],
    [418, null, "unknown"],
    [999, null, "unknown"],
  ];
  for (const [status, payload, category] of cases) {
    assert.deepEqual(classifyProviderFailure(status, payload), {
      status: status >= 100 && status <= 599 ? status : 0,
      category,
    }, `${status} ${JSON.stringify(payload)}`);
  }
});

test("chat route reports a sanitised provider rejection and never its body", async () => {
  process.env.ALPHAOS_API_TOKEN = "research-secret";
  process.env.ALPHAOS_API_URL = "https://research.example";
  process.env.ALPHAOS_CHAT_API_KEY = "chat-secret-value";
  process.env.ALPHAOS_CHAT_MODEL = "gemini-2.5-flash";
  process.env.ALPHAOS_CHAT_API_URL =
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";

  const logs = [];
  const originalError = console.error;
  console.error = (...args) => { logs.push(args.map(String).join(" ")); };
  try {
    globalThis.fetch = fakeFetch((url) => {
      if (url.includes("/v1/market/")) return Response.json(marketEnvelope("SPY"));
      if (url.includes("/v1/structure/")) return Response.json(structureEnvelope("SPY"));
      return Response.json([{
        error: {
          code: 400,
          message: "Please pass a valid API key: chat-secret-value",
          status: "INVALID_ARGUMENT",
        },
      }], { status: 400 });
    });

    const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "hello" }] }),
    }));
    assert.equal(response.status, 502);
    const body = await response.json();
    assert.equal(body.code, "chat_provider_error");
    assert.equal(body.provider_status, 400);
    assert.equal(body.provider_error_category, "invalid_api_key");
    assert.equal(body.provider_host, "generativelanguage.googleapis.com");

    const serialized = JSON.stringify(body);
    assert.ok(!serialized.includes("chat-secret-value"));
    assert.ok(!serialized.includes("Please pass a valid API key"));

    const log = logs.join("\n");
    assert.match(log, /charts_chat_provider_error/);
    assert.match(log, /"provider_status":400/);
    assert.match(log, /"provider_error_category":"invalid_api_key"/);
    assert.ok(!log.includes("chat-secret-value"));
    assert.ok(!log.includes("Please pass a valid API key"));
  } finally {
    console.error = originalError;
  }
});

test("chat route records an unreachable provider without leaking credentials", async () => {
  process.env.ALPHAOS_API_TOKEN = "research-secret";
  process.env.ALPHAOS_API_URL = "https://research.example";
  process.env.ALPHAOS_CHAT_API_KEY = "chat-secret-value";
  process.env.ALPHAOS_CHAT_MODEL = "gemini-2.5-flash";
  process.env.ALPHAOS_CHAT_API_URL =
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";

  const logs = [];
  const originalError = console.error;
  console.error = (...args) => { logs.push(args.map(String).join(" ")); };
  try {
    globalThis.fetch = fakeFetch((url) => {
      if (url.includes("/v1/market/")) return Response.json(marketEnvelope("SPY"));
      if (url.includes("/v1/structure/")) return Response.json(structureEnvelope("SPY"));
      throw new TypeError("fetch failed");
    });

    const response = await chatPost(new Request("http://localhost:3000/api/charts/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ symbol: "SPY", messages: [{ role: "user", content: "hello" }] }),
    }));
    assert.equal(response.status, 502);
    const body = await response.json();
    assert.equal(body.code, "chat_provider_error");
    assert.equal(body.provider_status, undefined);
    assert.ok(!JSON.stringify(body).includes("chat-secret-value"));

    const log = logs.join("\n");
    assert.match(log, /charts_chat_provider_unreachable/);
    assert.match(log, /"cause":"network"/);
    assert.ok(!log.includes("chat-secret-value"));
  } finally {
    console.error = originalError;
  }
});
