import {expect,test} from "@playwright/test";
import {readFileSync} from "node:fs";

const fixtures=JSON.parse(readFileSync("tests/fixtures/expiration-parity.json","utf8"));

test("monthly and long-dated requests preserve dates and display archive coverage",async({page})=>{
  for(const fixture of fixtures){
    const requests:Array<Record<string,unknown>>=[];
    await page.route("**/api/research/market",async route=>{
      requests.push(route.request().postDataJSON());
      await route.fulfill({status:200,json:{source:"alphaos_research_api",verified_for_trading:false,research:fixture.response}});
    });
    await page.goto(`/market?symbol=${fixture.request.symbol}`);
    await expect(page.getByRole("region",{name:"Expiration coverage"})).toBeVisible();
    await page.getByLabel("Exact expiration date",{exact:true}).fill(fixture.request.expiration);
    await page.getByLabel("Available Buying Power ($)").fill("500");
    await page.getByRole("button",{name:"Run Research"}).click();
    await expect.poll(()=>requests.at(-1)?.expiration).toBe(fixture.request.expiration);
    await expect(page.getByRole("region",{name:"Expiration coverage"})).toBeVisible();
    await expect(page.getByLabel("Exact expiration date",{exact:true})).toHaveValue(fixture.request.expiration);
    await page.unroute("**/api/research/market");
  }
});

test("explicit date rejects a substituted response and shows missing-date errors",async({page})=>{
  const fixture=fixtures[0];let unavailable=false;
  await page.route("**/api/research/market",async route=>{
    await route.fulfill(unavailable?{status:422,json:{code:"archive_expiration_unavailable"}}:
      {status:200,json:{source:"alphaos_research_api",verified_for_trading:false,research:fixture.response}});
  });
  await page.goto("/market?symbol=SPY");
  await expect(page.getByRole("region",{name:"Expiration coverage"})).toBeVisible();
  await page.getByLabel("Exact expiration date",{exact:true}).fill("2031-01-17");
  await page.getByRole("button",{name:"Run Research"}).click();
  await expect(page.getByText("The backend response did not match the required alphaos-interface-v2 research schema.",{exact:true})).toBeVisible();
  unavailable=true;
  await page.getByRole("button",{name:"Retry research"}).click();
  await expect(page.getByText("The requested expiration is not present in the verified archive. No different expiration was substituted.",{exact:true})).toBeVisible();
});
