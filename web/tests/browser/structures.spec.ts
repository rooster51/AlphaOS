import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

function fixture(name: string) {
  return JSON.parse(readFileSync(`tests/fixtures/${name}.json`, "utf8"));
}

const single = fixture("structure-parity");
const compared = fixture("structure-compare-parity");
const spyPutCredit = fixture("structure-spy-put-credit-parity");

function bridge(envelope: unknown) {
  return { json: { research: envelope, verified_for_trading: false, source: "alphaos_research_structure_api" } };
}

async function openWorkbench(page: import("@playwright/test").Page) {
  await page.goto("/structures");
  // The workbench is a client component; wait for hydration before interacting.
  await page.waitForLoadState("networkidle");
}

async function fillScenario(page: import("@playwright/test").Page) {
  await page.locator("#structure-symbol").selectOption("QQQ");
  await page.locator("#structure-expiration").fill("2030-01-02");
  await page.locator("#structure-as-of").fill("2030-01-02");
  await page.locator("#structure-spot").fill("500");
  await page.locator("#structure-side").selectOption("debit");
  await page.locator("#structure-price").fill("1.20");
  await page.locator("#structure-fees").fill("0");
  await page.locator("#leg-type-0").selectOption("Call");
  await page.locator("#leg-action-0").selectOption("Buy");
  await page.locator("#leg-strike-0").fill("500");
  await page.locator("#leg-quantity-0").fill("1");
  await page.getByRole("button", { name: "Add leg" }).click();
  await page.locator("#leg-type-1").selectOption("Call");
  await page.locator("#leg-action-1").selectOption("Sell");
  await page.locator("#leg-strike-1").fill("505");
  await page.locator("#leg-quantity-1").fill("1");
}

test("a QQQ call debit spread is researched through the backend contract", async ({ page }) => {
  const sent: Array<Record<string, unknown>> = [];
  await page.route("**/api/research/structure", async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill(bridge(single));
  });
  await openWorkbench(page);
  await expect(page.getByRole("heading", { name: "Structure Lab" })).toBeVisible();
  await expect(page.getByText("No structures saved yet.")).toBeVisible();
  // Scenario evaluation must not imply market discovery or monthly/LEAPS availability.
  await expect(page.getByText(/not market opportunity discovery/)).toBeVisible();
  await expect(page.getByText(/implies no monthly or long-dated \(LEAPS\) availability/)).toBeVisible();

  await fillScenario(page);
  await page.getByRole("button", { name: "Research this structure" }).click();

  await expect(page.getByText("CALL_DEBIT_SPREAD")).toBeVisible();
  await expect(page.getByText("Max profit")).toBeVisible();
  await expect(page.getByText("$380.00", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("$120.00", { exact: true })).toHaveCount(2);
  await expect(page.getByText("$501.20", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("$1.20 debit")).toBeVisible();
  await expect(page.getByText("SUPPLIED CASHFLOW", { exact: true })).toBeVisible();
  await expect(page.getByText("UNAVAILABLE").first()).toBeVisible();
  await expect(page.getByText("unsupported expiration session horizon")).toBeVisible();
  await expect(page.getByText(/Pricing assumption: Supplied signed package cashflow/)).toBeVisible();
  await expect(page.getByText(/supported 1, 2, 3, 5 and 10 exchange-session horizons/)).toBeVisible();
  await expect(page.getByText(/no estimate is substituted/)).toBeVisible();

  expect(sent).toHaveLength(1);
  expect(sent[0]).toEqual(single.request);
});

test("a SPY put credit spread shows backend credit economics", async ({ page }) => {
  await page.route("**/api/research/structure", (route) => route.fulfill(bridge(spyPutCredit)));
  await openWorkbench(page);
  await page.locator("#structure-symbol").selectOption("SPY");
  await page.locator("#structure-expiration").fill("2030-01-02");
  await page.locator("#structure-as-of").fill("2030-01-02");
  await page.locator("#structure-spot").fill("610");
  await page.locator("#structure-side").selectOption("credit");
  await page.locator("#structure-price").fill("1.10");
  await page.locator("#structure-fees").fill("0.65");
  await page.locator("#leg-type-0").selectOption("Put");
  await page.locator("#leg-action-0").selectOption("Sell");
  await page.locator("#leg-strike-0").fill("605");
  await page.getByRole("button", { name: "Add leg" }).click();
  await page.locator("#leg-type-1").selectOption("Put");
  await page.locator("#leg-action-1").selectOption("Buy");
  await page.locator("#leg-strike-1").fill("600");
  await page.getByRole("button", { name: "Research this structure" }).click();

  await expect(page.getByText("PUT_CREDIT_SPREAD")).toBeVisible();
  await expect(page.getByText("$109.35", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("$390.65", { exact: true })).toHaveCount(2);
  await expect(page.getByText("$603.91", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("$1.10 credit")).toBeVisible();
});

test("comparison uses saved scenarios in order and never shows a winner", async ({ page }) => {
  const sent: Array<Record<string, unknown>> = [];
  await page.route("**/api/research/structures/compare", async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill(bridge(compared));
  });
  await openWorkbench(page);
  await fillScenario(page);
  await page.getByRole("button", { name: "Save for comparison" }).click();
  await expect(page.getByText(/1\. QQQ 2030-01-02 · Call 500 Buy 1 · Call 505 Sell 1 · debit 1.2/)).toBeVisible();

  await page.locator("#structure-price").fill("2.20");
  await page.getByRole("button", { name: "Save for comparison" }).click();
  await expect(page.getByText("Compare saved structures (2)")).toBeVisible();

  await page.locator("#structure-thesis").fill("debit versus long");
  await page.getByRole("button", { name: "Compare saved structures (2)" }).click();

  await expect(page.getByText("Descriptive comparison")).toBeVisible();
  await expect(page.getByText("supplied input order; not a ranking")).toBeVisible();
  await expect(page.getByRole("cell", { name: "call debit spread", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "long call", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Unlimited", exact: true })).toBeVisible();
  await expect(page.getByText("not comparable (validated historical evidence unavailable)")).toBeVisible();
  await expect(page.getByText(/No winner, score or recommendation is produced/)).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Directly comparable" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "unsupported expiration session horizon" })).toBeVisible();

  expect(sent).toHaveLength(1);
  const payload = sent[0] as { structures: Array<Record<string, unknown>>; thesis?: string };
  expect(payload.structures.map((item) => item.credit)).toEqual([-1.2, -2.2]);
  expect(payload.thesis).toBe("debit versus long");
});

test("invalid input, unsupported structures, timeouts and empty archive evidence invent nothing", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/research/structure", async (route) => {
    calls += 1;
    const mode = route.request().postDataJSON().symbol;
    if (mode === "SPY") {
      await route.fulfill({ status: 502, json: { status: "unavailable", code: "invalid_structure" } });
      return;
    }
    await route.fulfill({ status: 502, json: { status: "unavailable", code: "backend_timeout" } });
  });
  await openWorkbench(page);

  // Invalid form input never reaches the bridge.
  await page.getByRole("button", { name: "Research this structure" }).click();
  await expect(page.getByText("Spot must be a positive number.")).toBeVisible();
  await expect(page.getByText("Package price per share must be a positive number.")).toBeVisible();
  expect(calls).toBe(0);

  await fillScenario(page);
  await page.locator("#structure-symbol").selectOption("SPY");
  await page.getByRole("button", { name: "Research this structure" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "does not support this leg combination" })).toBeVisible();
  await expect(page.getByText("Max profit")).toHaveCount(0);
  await expect(page.getByText("$380.00")).toHaveCount(0);

  await page.locator("#structure-symbol").selectOption("QQQ");
  await page.getByRole("button", { name: "Research this structure" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "timed out" })).toBeVisible();
  await expect(page.getByText("Max profit")).toHaveCount(0);
  expect(calls).toBe(2);
});

test("verified archive prefill fills the scenario without claiming live quotes", async ({ page }) => {
  const observation = {
    schema_version: "alphaos-observation-v1",
    read_only: true,
    verified_for_trading: false,
    research_performed: false,
    evidence_scope: "archive_observation_only",
    symbol: "QQQ",
    research_mode: "current",
    as_of: "2026-10-26T15:30:00+00:00",
    requested_as_of: "2026-10-26T15:30:01+00:00",
    expiration: "2026-10-30",
    spot: 505.25,
    session: { open: "2026-10-26T13:30:00+00:00", close: "2026-10-26T20:00:00+00:00" },
    archive: {
      session_date: "2026-10-26",
      provider: "Public",
      freshness: { age_seconds: 90, max_age_seconds: 600 },
    },
    request: { symbol: "QQQ", research_mode: "current" },
    caveats: [],
  };
  await page.route("**/api/research/market", (route) =>
    route.fulfill({ json: { research: observation, verified_for_trading: false, source: "alphaos_research_api" } }));
  await openWorkbench(page);
  await page.getByRole("button", { name: "Prefill from verified archive observation" }).click();

  await expect(page.getByText("VERIFIED ARCHIVE OBSERVATION", { exact: true })).toBeVisible();
  await expect(page.getByText(/not a live quote/)).toBeVisible();
  await expect(page.locator("#structure-spot")).toHaveValue("505.25");
  await expect(page.locator("#structure-expiration")).toHaveValue("2026-10-30");
  await expect(page.locator("#structure-as-of")).toHaveValue("2026-10-26");
});

test("the workbench stays usable on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openWorkbench(page);
  await page.locator('button[aria-controls="mobile-primary-navigation"]').click();
  await page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "Structure Lab" }).click();
  await expect(page).toHaveURL(/\/structures$/);
  await expect(page.getByRole("heading", { name: "Structure Lab" })).toBeVisible();
  await expect(page.locator("#structure-symbol")).toBeVisible();
  await expect(page.getByRole("button", { name: "Research this structure" })).toBeVisible();

  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
