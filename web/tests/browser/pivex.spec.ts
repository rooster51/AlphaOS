import { test, expect } from "@playwright/test";
test("Pivex manual research, fixtures, persistent journal and isolation", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET") requests.push(r.url());
  });
  await page.goto("/pivex");
  await expect(
    page.getByRole("heading", { name: "Pivex Challenge", exact: true }),
  ).toBeVisible();
  for (const title of [
    "Challenge Overview",
    "Market Setup Scanner",
    "Trade Planner",
    "Risk Management",
    "Challenge Journal",
    "Strategy Performance",
  ])
    await expect(
      page.getByRole("region", { name: title, exact: true }),
    ).toBeVisible();
  await expect(
    page.getByText("LIVE RESEARCH DISABLED", { exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: "NO TRADE", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Load synthetic long", exact: true })
    .click();
  await page.getByRole("button", { name: "Analyze completed candles" }).click();
  await expect(
    page.getByRole("heading", { name: "CONFIRMED", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator("p")
      .filter({ hasText: /FIXTURE · SYNTHETIC v1 — arbitrary prices/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load synthetic chop" }).click();
  await page.getByRole("button", { name: "Analyze completed candles" }).click();
  await expect(
    page.getByRole("heading", { name: "CHOP", exact: true }),
  ).toBeVisible();
  const journal = page.getByRole("region", {
    name: "Challenge Journal",
    exact: true,
  });
  for (const [label, value] of Object.entries({
    "Entry time UTC ISO": "2026-11-09T14:00:00Z",
    "Exit time UTC ISO": "2026-11-09T15:00:00Z",
    "Journal entry price": "100",
    "Exit price": "110",
    "Initial stop price": "95",
    "Initial target price": "115",
    "Position size lots": "1",
    "Trade fees USD": "2",
    "Other costs USD": "1",
    "Trade gross realized P&L USD": "50",
    "Initial planned risk USD": "25",
    "Setup classification": "trend-pullback-breakout",
    "Exit reason": "target",
    "Trade evidence reference": "Manual test fixture only",
  }))
    await journal.getByLabel(label, { exact: true }).fill(value);
  await journal.getByRole("button", { name: "Record closed trade" }).click();
  await expect(
    journal.getByRole("cell", { name: "$47.00", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    journal.getByRole("cell", { name: "$47.00", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Local challenge label", { exact: true })
    .fill("separate");
  await page
    .getByRole("button", { name: "Open challenge", exact: true })
    .click();
  await expect(
    journal.getByText("0 manually recorded trades", { exact: false }),
  ).toBeVisible();
  await page
    .getByLabel("Local challenge label", { exact: true })
    .fill("challenge-1");
  await page
    .getByRole("button", { name: "Open challenge", exact: true })
    .click();
  await expect(
    journal.getByRole("cell", { name: "$47.00", exact: true }),
  ).toBeVisible();
  expect(requests).toEqual([]);
  await page.screenshot({
    path: "test-results/pivex-dashboard-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Load synthetic long", exact: true })
    .click();
  await page.getByRole("button", { name: "Analyze completed candles" }).click();
  await page
    .getByRole("region", { name: "Market Setup Scanner", exact: true })
    .screenshot({ path: "test-results/pivex-scanner-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("main").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.screenshot({
    path: "test-results/pivex-dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("manual account and contract evidence supports cost-aware sizing, midnight fails closed", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-11-10T14:00:00Z") });
  await page.goto("/pivex");
  const risk = page.getByRole("region", {
    name: "Risk Management",
    exact: true,
  });
  await risk
    .getByText("Record verified user account entry", { exact: true })
    .click();
  for (const [label, value] of Object.entries({
    "Account evidence reference": "SYNTHETIC BROWSER FIXTURE ONLY",
    "Account observation time (UTC ISO)": "2026-11-10T14:00:00Z",
    "Verified equity USD": "10000",
    "Gross realized P&L USD": "0",
    "Floating P&L USD": "0",
    "Cumulative fees USD": "0",
    "Open exposure USD": "0",
    "Open planned risk USD": "0",
    "00:00 UTC equity USD": "10000",
    "Monday 00:00 UTC equity USD": "10000",
    "Trades opened today": "0",
    "Losing trades today": "0",
    "Daily baseline timestamp": "2026-11-10T00:00:00Z",
    "Weekly baseline timestamp": "2026-11-09T00:00:00Z",
  }))
    await risk.getByLabel(label, { exact: true }).fill(value);
  await risk.getByRole("checkbox").check();
  await risk.getByRole("button", { name: "Save account observation" }).click();
  await expect(page.getByRole("status")).toContainText("Saved in this browser");
  const planner = page.getByRole("region", {
    name: "Trade Planner",
    exact: true,
  });
  await planner.getByText(/Contract specifications and costs:/).click();
  const spec = {
    instrument: "NAS100",
    brokerSymbol: "SYNTHETIC",
    source: "TEST ONLY",
    verifiedAt: "2026-11-10T14:00:00Z",
    attested: true,
    tickSize: 0.5,
    tickValue: 1,
    quoteToAccount: 1,
    minLot: 0.1,
    maxLot: 100,
    lotStep: 0.1,
    spreadTicks: 1,
    slippageTicks: 1,
    commissionPerLot: 1,
    fixedFees: 0,
    costsSource: "TEST ONLY",
    marketHours: "TEST ONLY",
    permitted: true,
  };
  await planner
    .getByRole("textbox", { name: /^Contract specification JSON/ })
    .fill(JSON.stringify(spec));
  await planner
    .getByRole("button", { name: "Save attested specifications" })
    .click();
  for (const [label, value] of Object.entries({
    "Entry price": "100",
    "Stop price": "95",
    "Target price": "120",
  }))
    await planner.getByLabel(label, { exact: true }).fill(value);
  await expect(
    planner.getByRole("heading", { name: "MODELED", exact: true }),
  ).toBeVisible();
  await expect(
    planner.locator("dd").filter({ hasText: /^1\.9$/ }),
  ).toBeVisible();
  await expect(
    planner.locator("dd").filter({ hasText: /^\$24\.70$/ }),
  ).toBeVisible();
  await planner.getByText(/Contract specifications and costs:/).click();
  await planner.screenshot({ path: "test-results/pivex-planner-desktop.png" });
  await page.clock.fastForward(10 * 60 * 60 * 1000);
  await expect(
    planner.getByRole("heading", { name: "NO TRADE", exact: true }),
  ).toBeVisible();
  await expect(
    planner.getByText("Unable to verify account equity / UTC risk baseline", {
      exact: true,
    }),
  ).toBeVisible();
});
