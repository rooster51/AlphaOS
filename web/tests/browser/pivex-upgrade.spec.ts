import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("quick update stays unverified, persists, exports and merges without duplicate reports", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-11-10T14:00:00Z") });
  await page.goto("/pivex");
  const quick = page.getByRole("form", { name: "Quick Account Update form" });
  await quick
    .getByLabel("Reported balance or equity USD", { exact: true })
    .fill("10250");
  await quick
    .getByLabel("Today’s reported realized P&L USD", { exact: true })
    .fill("20");
  await quick
    .getByRole("button", { name: "Save quick update", exact: true })
    .click();
  await expect(
    page.getByRole("status", { name: "Pivex save status" }),
  ).toContainText("Saved in this browser");
  const overview = page.getByRole("region", {
    name: "Challenge Overview",
    exact: true,
  });
  await expect(overview.getByText("$750.00", { exact: true })).toBeVisible();
  await expect(
    overview.getByLabel("Indicative challenge progress"),
  ).toHaveAttribute("value", "0.25");
  await expect(overview.getByText(/UNVERIFIED · User-reported/)).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Trade Planner", exact: true })
      .getByRole("heading", { name: "NO TRADE", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(overview.getByText("$750.00", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export backup", exact: true })
    .click();
  const downloaded = await downloadPromise,
    path = await downloaded.path();
  expect(path).toBeTruthy();
  const raw = await readFile(path!, "utf8"),
    backup = JSON.parse(raw);
  expect(backup.quickReports).toHaveLength(1);
  expect(backup.snapshot).toBeNull();
  expect(backup.quickReports[0].kind).toBe("user_reported");
  const journal = page.getByRole("region", {
    name: "Challenge Journal",
    exact: true,
  });
  await journal
    .getByText("Restore or import supported Pivex JSON backup", { exact: true })
    .click();
  await journal.getByRole("textbox", { name: /^Pivex backup JSON/ }).fill(raw);
  await journal
    .getByRole("button", {
      name: "Merge backup without duplicate IDs",
      exact: true,
    })
    .click();
  await journal
    .getByRole("button", {
      name: "Merge backup without duplicate IDs",
      exact: true,
    })
    .click();
  expect(
    await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("alphaos:pivex:local:v1:challenge-1")!)
          .quickReports.length,
    ),
  ).toBe(1);
  await page.locator("main").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.screenshot({
    path: "test-results/pivex-upgrade-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await overview.screenshot({
    path: "test-results/pivex-upgrade-progress.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => (await page.getByRole("complementary").boundingBox())?.x)
    .toBeLessThan(-250);
  await page.locator("main").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.screenshot({
    path: "test-results/pivex-upgrade-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <= innerWidth &&
        document.querySelector("main")!.scrollWidth <=
          document.querySelector("main")!.clientWidth,
    ),
  ).toBe(true);
});
test("synthetic historical replay is separate from user account/journal and shows validation losses", async ({
  page,
}) => {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET") writes.push(r.url());
  });
  await page.goto("/pivex");
  const replay = page.getByRole("region", {
    name: "Historical Strategy Backtesting",
    exact: true,
  });
  await replay
    .getByRole("button", { name: "Load synthetic long replay", exact: true })
    .click();
  await replay
    .getByRole("button", { name: "Run deterministic backtest", exact: true })
    .click();
  await expect(
    replay.locator("p").filter({ hasText: /^HYPOTHETICAL BACKTEST · FIXTURE/ }),
  ).toBeVisible();
  const validation = page.getByRole("region", {
    name: "Out-of-sample validation",
    exact: true,
  });
  await expect(validation.getByText("-$15.00", { exact: true })).toBeVisible();
  await expect(
    validation.getByRole("img", {
      name: "Out-of-sample validation hypothetical equity curve",
    }),
  ).toBeVisible();
  await expect(
    validation.getByText(
      "INCOMPLETE — inspect missing coverage, unfilled signals and unresolved positions.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Challenge Journal", exact: true })
      .getByText("0 manually recorded trades", { exact: false }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("alphaos:pivex:local:v1:challenge-1"),
    ),
  ).toBeNull();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await validation.screenshot({
    animations: "disabled",
    path: "test-results/pivex-upgrade-backtest.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => (await page.getByRole("complementary").boundingBox())?.x)
    .toBeLessThan(-250);
  await validation.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/pivex-upgrade-backtest-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <= innerWidth &&
        document.querySelector("main")!.scrollWidth <=
          document.querySelector("main")!.clientWidth,
    ),
  ).toBe(true);
  expect(writes).toEqual([]);
});
