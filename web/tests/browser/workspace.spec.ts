import { expect, test } from "@playwright/test";

function setup(state: "BUY" | "WAIT", lastAt: string) {
  return {
    id: "opening_range_breakout",
    name: "Opening-range breakout",
    state,
    direction: "bullish",
    evidence: ["Opening range high 504.75, low 498.20."],
    missing_conditions: state === "BUY" ? [] : ["A confirmed five-minute close above the opening-range high."],
    entry_trigger: { price: 504.75, condition: "Confirmed five-minute close above the opening-range high." },
    invalidation: { price: 504.75, condition: "Five-minute close back below the opening-range high." },
    stop_reference: { price: 498.2, basis: "Opening-range low" },
    target_reference: { price: 510.2, basis: "R2" },
    risk: { underlying_risk_distance: 6.55, risk_pct: 1.31, target_distance: 5.45, reward_to_risk: 0.83 },
    wait_reason: state === "BUY" ? null : "No confirmed five-minute close has left the opening range.",
    timestamp: lastAt,
    freshness: "verified",
    options: { strategy_families: [] },
  };
}

function marketResponse(symbol: "SPY" | "QQQ", closed: boolean) {
  const lastAt = closed ? "2026-11-14T20:00:00+00:00" : "2026-11-13T15:45:00+00:00";
  const state = closed ? "BUY" : "WAIT";
  return {
    isLive: !closed,
    warning: closed
      ? "Market closed. Showing the last verified regular-session observation and historical structure."
      : "Live underlying observation only.",
    trade_intelligence: {
      schema_version: "alphaos-trade-intelligence-v1",
      symbol,
      generated_at: lastAt,
      source: "Public",
      session: {
        state: closed ? "closed" : "open",
        date: closed ? "2026-11-14" : "2026-11-13",
        open: "2026-11-14T14:30:00+00:00",
        close: "2026-11-14T21:00:00+00:00",
        as_of: lastAt,
      },
      data: {
        status: "verified",
        freshness: closed ? "latest_available" : "fresh",
        latest_confirmed_candle_at: lastAt,
        confirmed_bars: 15,
        warnings: closed ? ["Historical session evidence only."] : [],
        reasons: [],
      },
      levels: {
        previous_session: { date: "2026-11-13", open: 496, high: 505, low: 495, close: 503 },
        current_session: { high: 503.8, low: 497.4 },
        pivots: { pivot: 501, r1: 507, r2: 511, s1: 497, s2: 493 },
        opening_range: { high: 504.75, low: 498.2, status: "complete" },
        vwap: { price: 501.4, status: "available" },
        ema9: { price: 500.9, status: "available" },
        references: [
          { id: "prior_high", label: "Previous session high", price: 505, kind: "resistance", source: "previous_session_ohlc" },
          { id: "prior_low", label: "Previous session low", price: 495, kind: "support", source: "previous_session_ohlc" },
          { id: "pivot", label: "Pivot", price: 501, kind: "mid", source: "previous_session_ohlc" },
        ],
      },
      bias: { direction: "bullish", basis: "Descriptive alignment." },
      state,
      reason: closed
        ? "The historical session closed with a confirmed breakout observation."
        : "No setup has met its confirmed entry conditions.",
      active_setup_id: closed ? "opening_range_breakout" : null,
      closest_setup_id: "opening_range_breakout",
      setups: [
        setup(state, lastAt),
        { ...setup("WAIT", lastAt), id: "vwap_ema9_continuation", name: "VWAP + EMA 9 continuation" },
        { ...setup("WAIT", lastAt), id: "support_resistance_reversal", name: "Support/resistance reversal" },
      ],
      last_change: {
        previous_at: "2026-11-13T15:40:00+00:00",
        current_at: lastAt,
        previous_close: 503.1,
        current_close: 503.8,
        change: 0.7,
        change_pct: 0.14,
      },
      exit_early: { state: "UNAVAILABLE", reason: "No modeled position was supplied." },
      warnings: [],
    },
    data: {
      symbol,
      current_spot: closed ? 505.1 : 500.25,
      as_of: lastAt,
      source: closed ? "last_verified_session" : "live_public",
      atr_14: 4.5,
      expected_move: 3.25,
      levels: [
        { label: "R1", price: 507, distance: 1.9, distance_pct: 0.38, kind: "resistance" },
        { label: "S1", price: 497, distance: -8.1, distance_pct: -1.6, kind: "support" },
      ],
      opportunity_state: { direction: "bullish", caveats: ["Descriptive evidence only."] },
    },
  };
}

test("workspace switches symbols and keeps closed-session evidence historical", async ({ page }) => {
  const requested: string[] = [];
  await page.route("https://s.tradingview.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<!doctype html><title>TradingView fixture</title>" }));
  await page.route("**/api/market?*", async (route) => {
    const symbol = new URL(route.request().url()).searchParams.get("symbol") as "SPY" | "QQQ";
    requested.push(symbol);
    await route.fulfill({ json: marketResponse(symbol, symbol === "SPY") });
  });

  await page.goto("/workspace?symbol=SPY");
  await expect(page.getByRole("heading", { name: "Trading Workspace" })).toBeVisible();
  await expect(page.getByText("LAST VERIFIED SESSION", { exact: true })).toBeVisible();
  await expect(page.getByText("Historical evidence only", { exact: true })).toBeVisible();
  await expect(page.getByText("WAIT / RESEARCH STATE", { exact: true })).toBeVisible();
  await expect(page.getByText("HISTORICAL BUY", { exact: true })).toBeVisible();
  await expect(page.getByText("$505.10", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Options Chain · contracts", exact: true })).toHaveAttribute("href", "/options?symbol=SPY");

  await page.getByRole("button", { name: "Where is the nearest invalidation?" }).click();
  await expect(page.getByText(/Opening-range breakout invalidation: \$504\.75/)).toBeVisible();

  await page.getByRole("button", { name: "QQQ", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\?symbol=QQQ$/);
  await expect(page.getByText("LIVE OBSERVATION", { exact: true })).toBeVisible();
  await expect(page.getByText("$500.25", { exact: true })).toBeVisible();
  await expect(page.getByText("Historical evidence only", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Options Chain · contracts", exact: true })).toHaveAttribute("href", "/options?symbol=QQQ");
  expect(requested).toEqual(["SPY", "QQQ"]);
});
