import { expect, test, type Page } from "@playwright/test";

const AS_OF = "2026-11-04T15:30:00Z";

const TV_STUB = `window.TradingView = { widget: function (options) {
  var el = document.getElementById(options.container_id);
  if (!el) return;
  var node = document.createElement('div');
  node.setAttribute('data-testid', 'tv-widget');
  node.setAttribute('data-symbol', String(options.symbol));
  node.setAttribute('data-interval', String(options.interval));
  node.setAttribute('data-style', String(options.style));
  node.setAttribute('data-theme', String(options.theme));
  el.appendChild(node);
} };`;

function evidence(symbol: string, mode: "current" | "point_in_time" = "current") {
  return {
    status: "ok",
    evidence: {
      symbol,
      mode,
      source: "Public",
      as_of: AS_OF,
      retrieved_at: AS_OF,
      age_seconds: mode === "current" ? 42 : 7_200,
      spot: 500.12,
      atr_14: 6.4,
      levels: [
        { label: "PIVOT_HIGH_20", price: 505.5, kind: "resistance", distance_pct: 1.08 },
        { label: "PIVOT_LOW_20", price: 494.2, kind: "support", distance_pct: -1.18 },
      ],
      market_state: {
        direction: "bullish",
        movement_state: "directional",
        volatility_state: "normal",
        premium_state: null,
      },
      data_status: mode === "current" ? "fresh" : "latest_available",
      freshness: mode === "current" ? "fresh" : "stale",
      market_session: mode === "current" ? "regular_open" : "closed",
      caveats: ["Underlying observations are not executable option quotes."],
    },
  };
}

const REPLY =
  "AlphaOS evidence recorded 2026-11-04T15:30:00Z shows a bullish backend direction with a resistance level at 505.50. This is research, not advice.";

function chatBody(symbol: string, options: { reply?: string; blocked?: boolean } = {}) {
  return {
    status: "ok",
    reply: options.reply ?? REPLY,
    chart_access: "none",
    chart_claim_blocked: options.blocked ?? false,
    model: "test-model",
    evidence: {
      symbol,
      mode: "current",
      source: "Public",
      as_of: AS_OF,
      age_seconds: 42,
      spot: 500.12,
      atr_14: 6.4,
      levels: [],
      data_status: "fresh",
    },
    disclosures: [
      "The assistant receives the selected symbol and AlphaOS research evidence only. It has no access to TradingView candles, indicators, drawings or chart state.",
      "TradingView chart data may be delayed and is not used, read or verified by AlphaOS.",
    ],
  };
}

async function stubChart(page: Page, mode: "current" | "point_in_time" = "current") {
  await page.route("https://s3.tradingview.com/tv.js", (route) =>
    route.fulfill({ status: 200, contentType: "application/javascript", body: TV_STUB }));
  await page.route("**/api/charts/evidence**", (route) => {
    const symbol = new URL(route.request().url()).searchParams.get("symbol") ?? "SPY";
    return route.fulfill({ json: evidence(symbol === "QQQ" ? "QQQ" : "SPY", mode) });
  });
}

async function stubChat(page: Page, body = chatBody("SPY")) {
  const requests: Array<Record<string, unknown>> = [];
  await page.route("**/api/charts/chat", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: body });
  });
  return requests;
}

test("Charting & AI is reachable from navigation and renders the candlestick widget", async ({ page }) => {
  await stubChart(page);
  await stubChat(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dashboard");

  await page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "Charting & AI" }).click();

  await expect(page).toHaveURL(/\/charts$/);
  await expect(page.getByRole("heading", { name: "Charting & AI" })).toBeVisible();

  const widget = page.getByTestId("tv-widget");
  await expect(widget).toHaveAttribute("data-symbol", "AMEX:SPY");
  await expect(widget).toHaveAttribute("data-style", "1");
  await expect(widget).toHaveAttribute("data-theme", "dark");
  await expect(widget).toHaveAttribute("data-interval", "15");

  await expect(page.getByText(/Chart source: TradingView Advanced Chart widget/)).toBeVisible();
  await expect(page.getByText(/may be delayed/).first()).toBeVisible();
  await expect(page.getByText(/Market data as of:/)).toBeVisible();
  await expect(page.getByText("2026-11-04T15:30:00", { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/The assistant cannot see the TradingView chart/)).toBeVisible();
});

test("switching SPY to QQQ updates the chart and the assistant request", async ({ page }) => {
  await stubChart(page);
  const requests = await stubChat(page, chatBody("QQQ"));
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/charts?symbol=SPY");

  await expect(page.getByTestId("tv-widget")).toHaveAttribute("data-symbol", "AMEX:SPY");
  await page.getByRole("button", { name: "QQQ", exact: true }).click();

  await expect(page.getByTestId("tv-widget")).toHaveAttribute("data-symbol", "NASDAQ:QQQ");
  await expect(page.getByRole("heading", { name: /AlphaOS AI · QQQ/ })).toBeVisible();
  await expect(page).toHaveURL(/symbol=QQQ$/);

  const question = "Where are the important support and resistance levels?";
  await page.getByRole("button", { name: question }).click();
  await expect(page.getByText(REPLY)).toBeVisible();

  expect(requests.at(-1)).toEqual({
    symbol: "QQQ",
    messages: [{ role: "user", content: question }],
  });
});

test("conversation history is retained and resent within the page session", async ({ page }) => {
  await stubChart(page);
  const requests = await stubChat(page);
  await page.goto("/charts");

  await page.getByRole("button", { name: "What is the current market structure?" }).click();
  await expect(page.getByText(REPLY)).toBeVisible();

  await page.getByLabel("Ask the AlphaOS assistant about SPY").fill("What would invalidate a bullish setup?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("What would invalidate a bullish setup?")).toBeVisible();

  const last = requests.at(-1) as { symbol: string; messages: Array<{ role: string; content: string }> };
  expect(last.symbol).toBe("SPY");
  expect(last.messages.map((message) => message.role)).toEqual(["user", "assistant", "user"]);
  expect(last.messages[0].content).toBe("What is the current market structure?");
  expect(last.messages[1].content).toBe(REPLY);
});

test("stale evidence is labelled point-in-time beside the timestamp", async ({ page }) => {
  await stubChart(page, "point_in_time");
  await stubChat(page);
  await page.goto("/charts?symbol=SPY");

  await expect(page.getByText("POINT-IN-TIME").first()).toBeVisible();
  await expect(page.getByText(/not current market conditions/).first()).toBeVisible();
  await expect(page.getByText("2026-11-04T15:30:00", { exact: false }).first()).toBeVisible();
});

test("unconfigured assistant shows an explicit unavailable state, never a fake reply", async ({ page }) => {
  await stubChart(page);
  await page.route("**/api/charts/chat", (route) => route.fulfill({
    status: 503,
    json: {
      status: "unavailable",
      code: "chat_not_configured",
      message: "Assistant not configured.",
    },
  }));
  await page.goto("/charts");

  await page.getByRole("button", { name: "Is the market trending or consolidating?" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "not configured" }).first();
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("not configured");
  await expect(alert.getByRole("button", { name: "Retry question" })).toBeVisible();
  await expect(page.getByText(REPLY)).toHaveCount(0);
  await expect(page.getByText("Guardrail:")).toHaveCount(0);
});

test("assistant network failure and TradingView failure stay isolated and retryable", async ({ page }) => {
  await page.route("https://s3.tradingview.com/tv.js", (route) => route.abort());
  await page.route("**/api/charts/evidence**", (route) => route.fulfill({ json: evidence("SPY") }));
  await page.route("**/api/charts/chat", (route) => route.abort());

  await page.goto("/charts");
  await expect(page.getByText(/TradingView widget could not be loaded/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry chart" })).toBeVisible();

  await page.getByRole("button", { name: "Are there any options strategies worth researching?" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "could not be reached" }).first();
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("could not be reached");
});

test("a chart-access claim from the model is surfaced as a blocked guardrail", async ({ page }) => {
  await stubChart(page);
  await stubChat(page, chatBody("SPY", {
    reply: "I can't read the TradingView chart. AlphaOS does not receive its candles, indicators, drawings or widget state, so I can't describe what it currently shows.",
    blocked: true,
  }));
  await page.goto("/charts");

  await page.getByRole("button", { name: "Is this a breakout or a potential fakeout?" }).click();
  await expect(page.getByText(/Guardrail: the model tried to describe the TradingView chart/)).toBeVisible();
});

test("mobile layout keeps chart, timestamp and chat usable without horizontal overflow", async ({ page }) => {
  await stubChart(page);
  await stubChat(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/charts");

  await expect(page.getByTestId("tv-widget")).toHaveAttribute("data-symbol", "AMEX:SPY");
  await expect(page.getByText(/Market data as of:/)).toBeVisible();
  await page.getByLabel("Ask the AlphaOS assistant about SPY").fill("Is the market trending or consolidating?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(REPLY)).toBeVisible();

  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
