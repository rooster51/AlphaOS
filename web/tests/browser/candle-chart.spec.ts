import { test, expect } from "@playwright/test";

type Interval = "1m" | "5m" | "15m";

function snapshot(interval: Interval, symbol: "SPY" | "QQQ" = "SPY") {
  const start = Date.UTC(2026, 10, 10, 14, 30);
  const candles = Array.from({ length: interval === "15m" ? 26 : 30 }, (_, index) => {
    const price = 600 + index * 0.1;
    return {
      time: new Date(start + index * Number.parseInt(interval, 10) * 60_000).toISOString(),
      open: price,
      high: price + 0.8,
      low: price - 0.5,
      close: price + 0.4,
      volume: 10_000 + index * 100,
    };
  });
  return {
    schema_version: "alphaos-candles-v1",
    symbol,
    interval,
    provider: "Public",
    session: "regular",
    retrieved_at: new Date(Date.parse(candles.at(-1)!.time) + 30_000).toISOString(),
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
      entitlement: {
        provider: "Public",
        owner_private_display: true,
        public_display: false,
      },
    },
    entitlement: {
      provider: "Public",
      use_context: "owner_private_display",
      allowed: true,
      code: "allowed",
      reason: "Synthetic owner-private browser fixture.",
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

  await page.getByRole("button", { name: "15m", exact: true }).click();
  await expect(page.getByRole("img", { name: /SPY 15m candlesticks/ })).toBeVisible();
  expect(requested).toContain("15m");

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
  await expect(page.getByTitle("TradingView AMEX:SPY legacy chart")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open full candle route" })).toBeVisible();
});

test("research handoff preserves QQQ, preserves candle quality, and keeps fallback independent", async ({ page }) => {
  await page.route("https://s.tradingview.com/**", route => route.fulfill({ body: "" }));
  await page.route("**/api/candles/QQQ?*", route => route.fulfill({ json: {
    status: "ok",
    snapshot: {
      ...snapshot("15m", "QQQ"),
      completeness: "complete",
      last_bar_status: "unknown",
      freshness: "latest_available",
      warnings: ["last_bar_completion_unverified", "latest_available_session"],
    },
  } }));
  await page.goto("/market/chart?symbol=SPY&interval=15m");
  const chartNav = page.getByRole("navigation", { name: "Candle symbol and related research" });
  await chartNav.getByRole("link", { name: "QQQ" }).click();
  await expect(page.getByRole("img", { name: /QQQ 15m candlesticks/ })).toBeVisible();
  await expect(page.getByText("LATEST AVAILABLE SNAPSHOT")).toBeVisible();
  await expect(page.getByText("Last bar completion unverified")).toBeVisible();
  await expect(chartNav.getByRole("link", { name: "Trade research" })).toHaveAttribute("href", "/workspace?symbol=QQQ");
  await expect(chartNav.getByRole("link", { name: "Options research" })).toHaveAttribute("href", "/options?symbol=QQQ");
  await chartNav.getByRole("link", { name: "TradingView fallback" }).click();
  await expect(page.getByTitle("TradingView NASDAQ:QQQ legacy chart")).toBeVisible();
  await chartNav.getByRole("link", { name: "Options research" }).click();
  await expect(page.getByRole("combobox", { name: "Symbol" })).toHaveValue("QQQ");
  const related = page.getByRole("navigation", { name: "Related research" });
  await expect(related.getByRole("link", { name: "Trade research" })).toHaveAttribute("href", "/workspace?symbol=QQQ");
  await page.getByRole("combobox", { name: "Symbol" }).selectOption("SPY");
  await expect(related.getByRole("link", { name: "Candle chart" })).toHaveAttribute("href", "/market/chart?symbol=SPY");
});

test("chart opens same-symbol trade research and options when market evidence is unavailable", async ({ page }) => {
  await page.route("**/api/market?symbol=SPY", route => route.fulfill({
    status: 503,
    json: { code: "provider_unavailable" },
  }));
  await page.route("https://s.tradingview.com/**", route => route.fulfill({ body: "" }));
  await page.goto("/market/chart?symbol=SPY&view=legacy");
  await page.getByRole("navigation", { name: "Candle symbol and related research" })
    .getByRole("link", { name: "Trade research" }).click();
  await expect(page.getByRole("button", { name: "SPY", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("region", { name: "Trading research" }).getByText("WAIT", { exact: true }).first())
    .toBeVisible();
  await page.getByRole("link", { name: /Options Chain � contracts/ }).click();
  await expect(page.getByRole("combobox", { name: "Symbol" })).toHaveValue("SPY");
});

test("denied refresh clears candles and preserves the safe fallback", async ({ page }) => {
  let denied = false;
  await page.route("**/api/candles/SPY?*", route => denied
    ? route.fulfill({ status: 403, json: { status: "unavailable", code: "owner_only" } })
    : route.fulfill({ json: { status: "ok", snapshot: snapshot("1m") } }));
  await page.goto("/market/chart?symbol=SPY");
  await expect(page.getByRole("img", { name: /SPY 1m candlesticks/ })).toBeVisible();
  denied = true;
  await page.getByRole("button", { name: "Refresh now" }).click();
  await expect(page.locator("section").and(page.getByRole("alert"))).toContainText("Only the authenticated repository owner");
  await expect(page.getByRole("img", { name: /SPY 1m candlesticks/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "TradingView fallback" })).toHaveAttribute("href", /view=legacy/);
});

test("loading, malformed and unavailable responses never render candles", async ({ page }) => {
  let finishRequest!: () => void;
  const pending = new Promise<void>((resolve) => { finishRequest = resolve; });
  await page.route("**/api/candles/SPY?*", async route => {
    const interval = new URL(route.request().url()).searchParams.get("interval");
    if (interval === "1m") {
      await pending;
      const malformed = snapshot("1m");
      malformed.candles.reverse();
      await route.fulfill({ json: { status: "ok", snapshot: malformed } });
    } else {
      await route.fulfill({ status: 503, json: { status: "unavailable", code: "provider_unavailable" } });
    }
  });
  await page.goto("/market/chart?symbol=SPY");
  await expect(page.getByText(/loading.*candles/i)).toBeVisible();
  finishRequest();
  await expect(page.locator("section").and(page.getByRole("alert"))).toContainText("did not match");
  await expect(page.getByRole("img", { name: /candlesticks/ })).toHaveCount(0);
  await page.getByRole("button", { name: "5m", exact: true }).click();
  await expect(page.locator("section").and(page.getByRole("alert"))).toContainText("temporarily unavailable");
  await expect(page.getByRole("img", { name: /candlesticks/ })).toHaveCount(0);
});
