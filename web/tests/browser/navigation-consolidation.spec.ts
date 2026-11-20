import { expect, test } from "@playwright/test";

test("primary navigation exposes only the five active destinations", async ({ page }) => {
  await page.goto("/workspace");
  const navigation = page.getByRole("navigation", { name: "Primary navigation" }).first();
  await expect(navigation.getByRole("link")).toHaveCount(5);
  for (const [label, path] of [
    ["Trading Workspace", "/workspace"],
    ["Strategy Explorer", "/strategies"],
    ["Options Chain", "/options"],
    ["Structure Lab", "/structures"],
    ["Settings", "/settings"],
  ] as const) {
    await expect(navigation.getByRole("link", { name: label })).toHaveAttribute("href", path);
  }
  for (const label of ["Dashboard", "Market Research", "Candles", "Session Review", "Trade Journal", "Portfolio Risk"]) {
    await expect(navigation.getByRole("link", { name: label })).toHaveCount(0);
  }
});

for (const route of ["/dashboard", "/session", "/risk"]) {
  test(`legacy ${route} redirects to the Trading Workspace`, async ({ page }) => {
    await page.goto(route);
    await expect(page).toHaveURL(/\/workspace$/);
  });
}
