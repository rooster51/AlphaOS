import {expect,test} from "@playwright/test";
import {readFileSync} from "node:fs";

for (const symbol of ["SPY", "QQQ"]) {
  test(`${symbol} defaults to auto and sends exact manual overrides`, async ({page}) => {
    const fixtures = JSON.parse(readFileSync("tests/fixtures/market-parity.json", "utf8"));
    const fixture = fixtures.find((item: any) => item.request.symbol === symbol);
    const requests: Array<Record<string,unknown>> = [];
    await page.route("**/api/research/market", async route => {
      const request = route.request().postDataJSON(); requests.push(request);
      const data = structuredClone(fixture.response);
      data.request.width = request.width ?? null;
      data.research.research_session.diagnostics.width_selection.mode = request.width ? "manual" : "auto";
      await route.fulfill({json:{source:"alphaos_research_api",verified_for_trading:false,research:data}});
    });
    await page.goto(`/market?symbol=${symbol}`);
    await expect(page.getByRole("button", {name:"Run Research"})).toBeEnabled();
    await expect(page.getByLabel("Width mode", {exact:true})).toHaveValue("auto");
    expect(requests[0].width).toBeUndefined();
    await expect(page.getByLabel("Manual width (points)", {exact:true})).toHaveCount(0);
    await page.getByLabel("Width mode", {exact:true}).selectOption("manual");
    await page.getByLabel("Manual width (points)", {exact:true}).fill("1.5");
    await page.getByRole("button", {name:"Run Research"}).click();
    await expect.poll(() => requests.at(-1)?.width).toBe(1.5);
    await expect(page.getByRole("button", {name:"Run Research"})).toBeEnabled();
    await page.getByLabel("Manual width (points)", {exact:true}).fill("0");
    await page.getByRole("button", {name:"Run Research"}).click();
    await expect(page.getByRole("alert").filter({hasText:"Enter a width greater than 0"})).toContainText("Enter a width greater than 0");
    await page.getByLabel("Width mode", {exact:true}).selectOption("auto");
    await page.getByRole("button", {name:"Run Research"}).click();
    await expect.poll(() => requests.at(-1)?.width).toBeUndefined();
  });
}
