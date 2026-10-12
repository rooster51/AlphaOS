import { expect, test } from "@playwright/test";

function collectBrowserErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" &&
        !/Failed to load resource: the server responded with a status of 50[23]/.test(message.text())) {
      errors.push(message.text());
    }
  });
  return errors;
}

function researchResponse(symbol: "SPY" | "QQQ", status = "complete") {
  return {
    source: "alphaos_research_api",
    verified_for_trading: false,
    research: {
      schema_version: "alphaos-interface-v2",
      request: { symbol },
      read_only: true,
      provenance: { source: "Verified Supabase archive" },
      caveats: ["Archive observations are point-in-time evidence."],
      research: {
        version: "alphaos-run-market-v1",
        symbol,
        as_of: "2030-01-02T15:00:00+00:00",
        expiration: "2030-01-02",
        archive: {
          session_date: "2030-01-02",
          observation: { observed_at: "2030-01-02T15:00:00+00:00" },
          freshness: { age_seconds: 120, max_age_seconds: 600 },
        },
        research_session: {
          version: "opportunity-session-v1",
          symbol,
          status,
          candidates: status === "complete" ? [{ strategy_family: "call_debit_spread" }] : [],
          unavailable_routes: [],
        },
      },
    },
  };
}

test("desktop navigation reaches every page, including a fail-closed market page", async ({ page }) => {
  const clientErrors = collectBrowserErrors(page);
  await page.route("**/api/research/market", (route) =>
    route.fulfill({ status: 200, json: researchResponse("QQQ", "no_candidate") }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page).toHaveURL(/\/dashboard$/);

  const destinations = [
    ["Market Research", /\/market$/],
    ["Strategy Explorer", /\/strategies$/],
    ["Session Review", /\/session$/],
    ["Trade Journal", /\/journal$/],
    ["Portfolio Risk", /\/risk$/],
    ["Settings", /\/settings$/],
    ["Dashboard", /\/dashboard$/],
  ] as const;

  for (const [label, route] of destinations) {
    await page.getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: label }).click();
    await expect(page).toHaveURL(route);
    await expect(page.getByRole("main")).toBeVisible();
  }

  await expect(page.getByText("Engine Runtime")).toHaveCount(0);
  expect(clientErrors).toEqual([]);
});

test("mobile menu opens, closes with Escape, and closes after navigation", async ({ page }) => {
  const clientErrors = collectBrowserErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");

  const menuButton = page.locator('button[aria-controls="mobile-primary-navigation"]');
  await expect(menuButton).toBeVisible();
  await menuButton.click();
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");

  await menuButton.click();
  await page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "Strategy Explorer" }).click();
  await expect(page).toHaveURL(/\/strategies$/);
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  expect(clientErrors).toEqual([]);
});

test("backend outage stays in the app and distinguishes missing configuration without inventing data", async ({ page }) => {
  const clientErrors = collectBrowserErrors(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/market?symbol=QQQ");

  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await expect(page.getByText("The website backend URL or server-side API token is not configured.")).toBeVisible();
  await expect(page.getByText("No price, probability, expected value, or candidate has been substituted.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry research" })).toBeVisible();

  const unavailable = await page.request.post("/api/research/market", { data: { symbol: "QQQ" } });
  expect(unavailable.status()).toBe(503);
  expect(await unavailable.json()).toEqual({ status: "unavailable", code: "backend_not_configured" });

  const invalid = await page.request.get("/api/market?symbol=INVALID");
  expect(invalid.status()).toBe(400);
  expect(await invalid.json()).toMatchObject({ status: "invalid_request" });

  await page.getByRole("button", { name: "Retry research" }).click();
  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await page.getByRole("navigation", { name: "Select market symbol" })
    .getByRole("link", { name: "SPY" }).click();
  await expect(page).toHaveURL(/\/market\?symbol=SPY$/);
  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await expect(page.getByText(/\$[0-9]+\.[0-9]{2}/)).toHaveCount(0);
  expect(clientErrors).toEqual([]);
});

for (const symbol of ["SPY", "QQQ"] as const) {
  test(`${symbol} authenticated v2 archive research renders as historical, non-tradable evidence`, async ({ page }) => {
    const clientErrors = collectBrowserErrors(page);
    let postedBody: unknown;
    await page.route("**/api/research/market", async (route) => {
      postedBody = route.request().postDataJSON();
      await route.fulfill({ status: 200, json: researchResponse(symbol) });
    });
    await page.goto(`/market?symbol=${symbol}`);

    await expect(page.getByRole("heading", { name: `${symbol} archived research` })).toBeVisible();
    await expect(page.getByText("2030-01-02T15:00:00+00:00")).toBeVisible();
    await expect(page.getByText("120 seconds at request time")).toBeVisible();
    await expect(page.getByText("call debit spread")).toBeVisible();
    await expect(page.getByText(/not a current market quote, executable price/)).toBeVisible();
    expect(postedBody).toEqual({ symbol });
    await expect(page.getByText(/\bPOP\b|\bEV\b|\$[0-9]+\.[0-9]{2}/)).toHaveCount(0);
    expect(clientErrors).toEqual([]);
  });
}

test("stale archive response gets a specific status instead of a generic unavailable message", async ({ page }) => {
  await page.route("**/api/research/market", (route) => route.fulfill({
    status: 502,
    json: { status: "unavailable", code: "archive_stale" },
  }));
  await page.goto("/market?symbol=QQQ");
  await expect(page.getByText("The latest verified options archive is stale. No older snapshot or live data was substituted.")).toBeVisible();
  await expect(page.getByText(/Market closure does not by itself invalidate/)).toBeVisible();
});

test("mobile backdrop closes the navigation menu", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page.locator('button[aria-controls="mobile-primary-navigation"]').click();
  await page.getByRole("button", { name: "Close navigation menu" }).last().click({ position: { x: 330, y: 400 } });
  await expect(page.locator('button[aria-controls="mobile-primary-navigation"]')).toHaveAttribute("aria-expanded", "false");
});

test("v2 research bridge rejects invalid requests and never exposes backend credentials", async ({ page }) => {
  const invalidSymbol = await page.request.post("/api/research/market", {
    data: { symbol: "INVALID" },
  });
  expect(invalidSymbol.status()).toBe(400);
  expect(await invalidSymbol.json()).toEqual({ error: "Invalid research request" });

  const malformed = await page.request.post("/api/research/market", {
    headers: { "Content-Type": "application/json" },
    data: "{not valid json",
  });
  expect(malformed.status()).toBe(400);

  const unsupportedField = await page.request.post("/api/research/market", {
    data: { symbol: "SPY", force_live: true },
  });
  expect(unsupportedField.status()).toBe(400);

  // In CI the backend credentials are deliberately absent. The bridge must
  // return a controlled unavailable response rather than leaking a token.
  const unavailable = await page.request.post("/api/research/market", {
    data: { symbol: "SPY" },
  });
  expect(unavailable.status()).toBe(503);
  const responseText = await unavailable.text();
  expect(responseText).toContain('"code":"backend_not_configured"');
  expect(responseText).not.toMatch(/Bearer |ALPHAOS_API_TOKEN=/);
});
