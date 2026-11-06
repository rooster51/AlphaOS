import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixtures = JSON.parse(readFileSync("tests/fixtures/market-parity.json", "utf8"));
const summaries = JSON.parse(readFileSync("tests/fixtures/market-summary.json", "utf8"));

function fixture(symbol: string, capital: number, expiration?: string) {
  const match = fixtures.find((item: any) =>
    item.request.symbol === symbol &&
    item.request.available_capital === capital &&
    (!expiration || item.request.expiration === expiration),
  );
  if (!match) throw new Error(`Missing offline research fixture for ${symbol} and ${capital}.`);
  return JSON.parse(JSON.stringify(match.response));
}

test("Strategy Research renders verified SPY contracts and reruns the backend filter on budget changes", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/research/market", async (route) => {
    const request = route.request().postDataJSON();
    requests.push(request);
    const body = fixture(request.symbol, request.available_capital, request.expiration);
    body.request.expiration = request.expiration ?? null;
    await route.fulfill({
      status: 200,
      json: { source: "alphaos_research_api", verified_for_trading: false, research: body },
    });
  });

  await page.goto("/strategies?symbol=SPY");
  await expect(page.getByRole("heading", { name: "Strategy Research" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Eligible strategies" })).toBeVisible();
  await expect(page.getByText("Call debit spread", { exact: true })).toBeVisible();
  await expect(page.getByText("BUY 1 Call 500", { exact: true })).toBeVisible();
  await expect(page.getByText("$380.00", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("1 : 3.17", { exact: true })).toBeVisible();

  await page.getByText("Exact contracts, payoff & supporting evidence").click();
  await expect(page.getByText("SPY300102C00500000", { exact: true })).toBeVisible();
  await expect(page.getByText("Bid observed 2030-01-02T20:30:00+00:00", { exact: false }).first()).toBeVisible();
  await page.locator("main").evaluate((element) => element.scrollTo(0, 0));
  await page.screenshot({ path: "test-results/strategy-research-spy.png", fullPage: true });

  await page.getByLabel("Available Buying Power ($)").fill("500");
  await page.getByLabel("Expiration", { exact: true }).selectOption("2030-01-02");
  await page.getByRole("button", { name: "Run research" }).click();
  await expect(page.getByText("Eligible strategies")).toBeVisible();
  await expect(page.getByText("2 verified", { exact: true })).toBeVisible();
  expect(requests.at(-1)).toEqual({
    symbol: "SPY",
    available_capital: 500,
    research_mode: "current",
    expiration: "2030-01-02",
    response_format: "summary-v1",
  });
  await expect(page.getByRole("link", { name: "Full market research" }).first()).toHaveAttribute("href", "/market?symbol=SPY");
});

test("Strategy Research renders verified QQQ contracts from backend evidence", async ({ page }) => {
  await page.route("**/api/research/market", async (route) => {
    const request = route.request().postDataJSON();
    const body = fixture(request.symbol, request.available_capital, request.expiration);
    body.request.expiration = request.expiration ?? null;
    await route.fulfill({
      status: 200,
      json: { source: "alphaos_research_api", verified_for_trading: false, research: body },
    });
  });

  await page.goto("/strategies?symbol=QQQ");
  await expect(page.getByRole("heading", { name: "Strategy Research" })).toBeVisible();
  await expect(page.getByText("Call debit spread", { exact: true })).toBeVisible();
  await expect(page.getByText("BUY 1 Call 500", { exact: true })).toBeVisible();
  await page.getByText("Exact contracts, payoff & supporting evidence").click();
  await expect(page.getByText("QQQ300103C00500000", { exact: true })).toBeVisible();
});

test("Strategy Research keeps QQQ responsive, expands technical evidence, and fails closed on stale quotes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/research/market", async (route) => {
    const request = route.request().postDataJSON();
    const body = fixture(request.symbol, request.available_capital, request.expiration);
    body.request.expiration = request.expiration ?? null;
    for (const candidate of body.research.research_session.candidates) {
      for (const leg of candidate.research.position.legs) delete leg.ask_timestamp;
    }
    await route.fulfill({
      status: 200,
      json: { source: "alphaos_research_api", verified_for_trading: false, research: body },
    });
  });

  await page.goto("/strategies?symbol=QQQ");
  await expect(page.getByRole("heading", { name: "NO TRADE" })).toBeVisible();
  await expect(page.getByText("0", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Unavailable, unaffordable & rejected research")).toBeVisible();
  await page.getByText("Technical analysis & market structure").click();
  await expect(page.getByText("Backend market classification")).toBeVisible();
  await page.locator("main").evaluate((element) => element.scrollTo(0, 0));
  await page.screenshot({ path: "test-results/strategy-research-qqq-mobile.png", fullPage: true });
  const horizontalOverflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(horizontalOverflow).toBe(false);
});

test("Strategy Research keeps API failures distinct from a successful NO TRADE result", async ({ page }) => {
  await page.route("**/api/research/market", (route) => route.fulfill({
    status: 502,
    json: { status: "unavailable", code: "archive_stale" },
  }));
  await page.goto("/strategies?symbol=SPY");
  await expect(page.getByRole("heading", { name: "Research unavailable" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "NO TRADE" })).toHaveCount(0);
  await expect(page.getByText("The latest verified archive is stale. No older snapshot or live data was substituted.")).toBeVisible();
});

for (const changed of [false, true]) {
  test(`Summary research loads pinned full evidence or reports changed evidence (${changed})`, async ({page}) => {
    const golden = summaries.find((item:any) => {
      const source = fixtures[item.fixture_index];
      return source.request.symbol === 'SPY' && source.request.available_capital === 150;
    });
    const original = fixtures[golden.fixture_index].response;
    let initialRequests = 0, detailRequests = 0;
    await page.route('**/api/research/market', async route => {
      const input = route.request().postDataJSON();
      if (input.view === 'candidate') {
        detailRequests++;
        expect(input.detail).toEqual(golden.response.research.research_session.candidates[0].detail);
        if (changed) {
          await route.fulfill({status:502,json:{status:'unavailable',code:'research_evidence_changed'}});
        } else {
          await route.fulfill({status:200,json:{verified_for_trading:false,research:{
            schema_version:'alphaos-candidate-detail-v1',read_only:true,verified_for_trading:false,
            request:original.request, reference:input.detail,archive:original.research.archive,
            candidate:original.research.research_session.candidates[input.detail.index],caveats:original.caveats,
          }}});
        }
      } else {
        initialRequests++;
        expect(input.response_format).toBe('summary-v1');
        const body=structuredClone(golden.response); body.request.expiration=input.expiration??null;
        await route.fulfill({status:200,json:{verified_for_trading:false,research:body}});
      }
    });
    await page.goto('/strategies?symbol=SPY');
    await expect(page.getByRole('heading',{name:'Eligible strategies'})).toBeVisible();
    expect(detailRequests).toBe(0);
    await page.getByText('Exact contracts, payoff & supporting evidence').first().click();
    await page.getByRole('button',{name:'Load complete candidate evidence'}).first().click();
    if (changed) {
      await expect(page.getByText('Evidence changed. Run research again; newer evidence was not substituted.')).toBeVisible();
      await expect(page.getByText('Complete candidate evidence record')).toHaveCount(0);
    } else {
      await expect(page.getByText('Complete candidate evidence record')).toBeVisible();
    }
    expect(initialRequests).toBe(1); expect(detailRequests).toBe(1);
  });
}
