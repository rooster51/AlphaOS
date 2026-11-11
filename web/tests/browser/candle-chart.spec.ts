import { test, expect } from "@playwright/test";

type Interval = "1m" | "5m" | "15m";

function snapshot(interval: Interval) {
  const start = Date.UTC(2026, 10, 10, 14, 30);
  const candles = Array.from({ length: 30 }, (_, index) => {
    const price = 600 + index * 0.1;
    return {
      time: new Date(start + index * 60_000).toISOString(),
      open: price,
      high: price + 0.8,
      low: price - 0.5,
      close: price + 0.4,
      volume: 10_000 + index * 100,
    };
  });
  return {
    schema_version: "alphaos-candles-v1",
    symbol: "SPY",
    interval,
    provider: "Public",
    session: "regular",
    retrieved_at: "2026-11-10T15:01:00Z",
    latest_candle_at: candles.at(-1)!.time,
    snapshot_id: (interval === "1m" ? "a" : interval === "5m" ? "b" : "c").repeat(64),
    expected_bars: 390,
    received_bars: candles.length,
    returned_bars: candles.length,
    completeness: "incomplete",
    last_bar_status: "partial",
    freshness: "stale",
    warnings: [
      "missing_bars",
      "incomplete_session",
      "last_bar_window_open",
      "last_bar_completion_unverified",
      "stale_candles",
    ],
    candles,
    provider_capabilities: {
      provider: "Public",
      symbols: ["SPY", "QQQ"],
      intervals: ["1m", "5m", "15m"],
      sessions: ["regular"],
      latest_quotes: true,
      native_candles: true,
      provider_native_intervals: true,
      expected_bar_metadata: true,
      entitlement: {},
    },
    entitlement: {
      provider: "Public",
      use_context: "private_research",
      allowed: true,
      code: "allowed",
      reason: "Synthetic browser fixture.",
      basis: "Test only.",
      policy_version: "alphaos-data-use-v1",
      authorization_required: false,
      authorization_reference_present: false,
    },
  };
}

test("native candle chart renders quality state, switches intervals and remains mobile-safe", async ({ page }) => {
  const requested: Interval[] = [];
  await page.route("**/api/candles/SPY*", async (route) => {
    const interval = (new URL(route.request().url()).searchParams.get("interval") ?? "1m") as Interval;
    requested.push(interval);
    await route.fulfill({ json: { status: "ok", snapshot: snapshot(interval) } });
  });
  await page.route("**/api/current-quote?symbol=SPY", async (route) => {
    await route.fulfill({
      json: {
        status: "fresh",
        symbol: "SPY",
        last: 602.25,
        bid: 602.2,
        ask: 602.3,
        lastAt: new Date(Date.now() - 4_000).toISOString(),
        retrievedAt: new Date().toISOString(),
        ageSeconds: 4,
      },
    });
  });

  await page.goto("/market/chart?symbol=SPY&interval=1m");
  // The headless VM has no usable font metrics, so a shrink-to-fit H1 has a
  // zero box. Padded controls and the chart remain measurable and meaningful.
  await expect(page.getByRole("button", { name: "1m" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("link", { name: "Archive research" })).toBeVisible();
  await expect(page.getByRole("img", { name: /SPY 1m candlesticks/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Current quote marker" })).toBeVisible();
  await expect(page.getByText("602.25")).toHaveText("602.25");
  const warnings = page.getByRole("list", { name: "Candle quality warnings" });
  await expect(warnings).toBeVisible();
  await expect(warnings.getByRole("listitem")).toHaveCount(5);
  await expect(warnings.getByText("Missing bars", { exact: true })).toHaveText("Missing bars");
  await expect(warnings.getByText("Last-bar window open", { exact: true })).toHaveText("Last-bar window open");
  await expect(page.getByText("partial · interval window open", { exact: true })).toHaveText("partial · interval window open");
  await expect(page.getByText("STALE SNAPSHOT")).toHaveText("STALE SNAPSHOT");
  await expect(page.locator("section[data-snapshot-id]")).toHaveAttribute("data-snapshot-id", "a".repeat(64));

  await page.getByRole("button", { name: "5m", exact: true }).click();
  await expect(page.getByRole("button", { name: "5m", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("img", { name: /SPY 5m candlesticks/ })).toBeVisible();
  await expect(page.locator("section[data-snapshot-id]")).toHaveAttribute("data-snapshot-id", "b".repeat(64));
  expect(requested).toContain("5m");

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "15m", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("route-level fallback keeps a legacy TradingView path available", async ({ page }) => {
  await page.route("https://s.tradingview.com/**", async (route) => {
    await route.fulfill({ contentType: "text/html", body: "<!doctype html><title>TradingView fixture</title>" });
  });
  await page.goto("/market/chart?symbol=SPY&view=legacy", { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/legacy fallback/)).toBeVisible();
  await expect(page.getByTitle("TradingView SPY legacy chart")).toBeVisible();
  await expect(page.getByRole("link", { name: "Return to AlphaOS candles" })).toBeVisible();
});
