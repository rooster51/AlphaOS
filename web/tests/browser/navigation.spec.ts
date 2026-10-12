import { expect, test } from "@playwright/test";

function collectBrowserErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("desktop navigation reaches every page, including a fail-closed market page", async ({ page }) => {
  const clientErrors = collectBrowserErrors(page);
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

test("backend outage stays in the app, keeps retry and symbol controls usable, and invents no prices", async ({ page }) => {
  const clientErrors = collectBrowserErrors(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/market?symbol=QQQ");

  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await expect(page.getByText("No substitute prices, signals, or strategy candidates are shown.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry research" })).toBeVisible();

  const unavailable = await page.request.get("/api/market?symbol=QQQ");
  expect(unavailable.status()).toBe(503);
  expect(await unavailable.json()).toMatchObject({ status: "unavailable" });

  const invalid = await page.request.get("/api/market?symbol=INVALID");
  expect(invalid.status()).toBe(400);
  expect(await invalid.json()).toMatchObject({ status: "invalid_request" });

  await page.getByRole("button", { name: "Retry research" }).click();
  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await page.getByRole("navigation", { name: "Choose market symbol" })
    .getByRole("link", { name: "SPY" }).click();
  await expect(page).toHaveURL(/\/market\?symbol=SPY$/);
  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await expect(page.getByText(/\$[0-9]+\.[0-9]{2}/)).toHaveCount(0);
  expect(clientErrors).toEqual([]);
});

test("mobile backdrop closes the navigation menu", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page.locator('button[aria-controls="mobile-primary-navigation"]').click();
  await page.getByRole("button", { name: "Close navigation menu" }).last().click();
  await expect(page.locator('button[aria-controls="mobile-primary-navigation"]')).toHaveAttribute("aria-expanded", "false");
});
