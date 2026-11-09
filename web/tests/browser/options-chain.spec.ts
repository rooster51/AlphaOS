import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`dated options research is user-triggered at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const requests: URL[] = [];
    const expiration = "2026-11-06";
    const id = "SPY261106C00500000";
    await page.route("**/api/options?*", async route => {
      const url = new URL(route.request().url());
      requests.push(url);
      if (!url.searchParams.has("expiration")) {
        return route.fulfill({ status: 503, json: { code: "provider_unavailable" } });
      }
      const evaluation = url.searchParams.has("buy");
      return route.fulfill({ json: {
        source: "Public", retrieved_at: "2026-11-04T16:00:00Z", max_quote_age_seconds: 30,
        chain: { calls: [{ contract: id, type: "Call", strike: 500, status: "fresh", bid: 2, ask: 2.1 }], puts: [] },
        scenario: evaluation ? { status: "unavailable", reason: "Fresh underlying quote unavailable." } : undefined,
      } });
    });
    await page.goto("/options");
    await expect(page.getByRole("heading", { name: "Options Chain" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(requests).toHaveLength(0);
    await page.getByRole("button", { name: "Discover expirations" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Expiration discovery unavailable" })).toBeVisible();
    await page.getByLabel("Expiration", { exact: true }).fill(expiration);
    expect(requests).toHaveLength(1);
    await page.getByRole("button", { name: "Refresh chain" }).click();
    await expect(page.getByRole("cell", { name: id })).toBeVisible();
    await page.getByLabel("Buy contract", { exact: true }).selectOption(id);
    await page.getByRole("button", { name: "Evaluate scenario" }).click();
    await expect(page.getByText("NO TRADE · Fresh underlying quote unavailable.")).toBeVisible();
    expect(requests.map(url => url.searchParams.get("expiration"))).toEqual([null, expiration, expiration]);
    await page.getByLabel("Symbol", { exact: true }).selectOption("QQQ");
    await expect(page.getByRole("table")).toHaveCount(0);
    expect(requests).toHaveLength(3);
  });
}
