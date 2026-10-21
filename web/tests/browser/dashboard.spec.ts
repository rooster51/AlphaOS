import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

// Offline archive fixture, not a claim about production data availability.
const fixture = JSON.parse(readFileSync("tests/fixtures/unsupported-routes-parity.json", "utf8")).response;
const observations=JSON.parse(readFileSync('tests/fixtures/observation-parity.json','utf8'));
for(const mode of ['current','historical']) test(`compact ${mode} contract keeps both dashboard cards and safety labels`,async({page})=>{
 await page.clock.install({time:new Date(mode==='current'?'2026-10-16T19:33:00Z':'2026-10-20T14:00:00Z')});
 const requests:Array<{view:string}>=[];
 await page.route('**/api/research/market',async route=>{
  const request=route.request().postDataJSON();requests.push(request);
  if(mode==='historical' && request.research_mode==='current') return route.fulfill({status:502,json:{code:'archive_stale'}});
  const data=observations.find((c:{request:{symbol:string;research_mode:string}})=>c.request.symbol===request.symbol && c.request.research_mode===mode).response;
  await route.fulfill({json:{source:'alphaos_research_api',verified_for_trading:false,research:data}});
 });
 await page.goto('/dashboard');
 for(const symbol of ['SPY','QQQ']) {
  const card=page.getByRole('region',{name:`${symbol} evidence`});
  await expect(card.getByText(mode==='current'?'CURRENT — VERIFIED ARCHIVE OBSERVATION':'HISTORICAL — COMPLETED SESSION ARCHIVE',{exact:true})).toBeVisible();
  await expect(card).toContainText('2026-10-16T19:30:00+00:00');
 }
 expect(requests.every(r=>r.view==='observation')).toBe(true);
});
function historical(symbol: string) {
  const data = JSON.parse(JSON.stringify(fixture).replaceAll("QQQ", symbol));
  data.request.research_mode = "historical";
  data.research.research_mode = "historical";
  data.research.archive.freshness = {
    as_of:"2026-10-20T14:00:00Z", age_seconds:325800, max_age_seconds:null,
  };
  return {source:"alphaos_research_api", verified_for_trading:false, research:data};
}

test("dashboard preserves both symbol cards during stale current evidence and labels completed-session context", async ({page}) => {
  await page.clock.install({time:new Date("2026-10-20T14:00:00Z")});
  const requests: Array<{symbol:string;research_mode:string}> = [];
  await page.route("**/api/research/market", async route => {
    const request = route.request().postDataJSON();requests.push(request);
    await route.fulfill(request.research_mode === "current"
      ? {status:502,json:{code:"archive_stale"},headers:{"X-AlphaOS-Request-ID":"a".repeat(32)}}
      : {json:historical(request.symbol)});
  });
  await page.goto("/dashboard");
  await expect(page.getByRole("heading",{name:"Research Terminal Dashboard"})).toBeVisible();
  for (const symbol of ["SPY","QQQ"]) {
    const card=page.getByRole("region",{name:`${symbol} evidence`});
    await expect(card.getByText("HISTORICAL — COMPLETED SESSION ARCHIVE",{exact:true})).toBeVisible();
    await expect(card).toContainText("Live market evidence is unavailable");
    await expect(card).toContainText("not a closing price, live quote, or current trading opportunity");
    await expect(card).toContainText("2026-10-16T19:30:00+00:00");
    await expect(card).toContainText("Session date (New York)2026-10-16");
    await expect(card).toContainText("Public · verified Supabase archive");
    await expect(card).toContainText("Current request ID: "+"a".repeat(32));
    await expect(card).toContainText("Live-only signals, probability estimates, expected value, and actionable trade recommendations are unavailable");
  }
  await expect(page.getByText("CURRENT — VERIFIED ARCHIVE OBSERVATION",{exact:true})).toHaveCount(0);
  expect(requests.filter(r=>r.research_mode==="current")).toHaveLength(2);
  expect(requests.filter(r=>r.research_mode==="historical")).toHaveLength(2);
  await expect(page.getByRole("link",{name:"Strategy explorer — evidence-gated"})).toBeVisible();
});

test("current evidence success stays current and never requests historical mode", async ({page})=>{
  await page.clock.install({time:new Date("2026-10-16T19:33:00Z")});
  const modes:string[]=[];
  await page.route("**/api/research/market",async route=>{
    const request=route.request().postDataJSON();modes.push(request.research_mode);
    const data=JSON.parse(JSON.stringify(fixture).replaceAll("QQQ",request.symbol));
    await route.fulfill({json:{source:"alphaos_research_api",verified_for_trading:false,research:data}});
  });
  await page.goto("/dashboard");
  await expect(page.getByText("CURRENT — VERIFIED ARCHIVE OBSERVATION",{exact:true})).toHaveCount(2);
  await expect(page.getByText("HISTORICAL — COMPLETED SESSION ARCHIVE",{exact:true})).toHaveCount(0);
  expect(modes).toEqual(["current","current"]);
  // A page left open must not continue labeling expired evidence as current.
  await page.clock.fastForward(121000);
  await expect(page.getByText("CURRENT — VERIFIED ARCHIVE OBSERVATION",{exact:true})).toHaveCount(0);
  await expect(page.getByText("Current market evidence is stale. Live market evidence is unavailable.",{exact:true})).toHaveCount(2);
  expect(modes).toEqual(["current","current"]);
});

for (const [code,message] of [
  ["backend_unreachable","The research backend could not be reached."],
  ["backend_authentication_required","Backend authentication is required. Server credentials were not accepted."],
  ["archive_research_unavailable","This archive cannot support the requested research."],
]) {
  test(`dashboard ${code} keeps layout, links and refresh controls without fallback`,async({page})=>{
    const modes:string[]=[];
    await page.route("**/api/research/market",async route=>{
      modes.push(route.request().postDataJSON().research_mode);
      await route.fulfill({status:502,json:{code}});
    });
    await page.goto("/dashboard");
    await expect(page.getByRole("heading",{name:"Research Terminal Dashboard"})).toBeVisible();
    for (const symbol of ["SPY","QQQ"]) {
      const card=page.getByRole("region",{name:`${symbol} evidence`});
      await expect(card.getByText(message,{exact:true})).toBeVisible();
      await expect(card.getByRole("button",{name:`Refresh ${symbol} evidence`})).toBeVisible();
      await expect(card.getByRole("link",{name:`Open ${symbol} market research`})).toBeVisible();
      await expect(card).toContainText("No substitute or unverified market data has been displayed");
    }
    expect(modes).toEqual(["current","current"]);
    await expect(page.getByText("$500.00",{exact:true})).toHaveCount(0);
  });
}

test("same-session historical evidence is refused, and one failed symbol does not hide the other",async({page})=>{
  await page.clock.install({time:new Date("2026-10-20T14:00:00Z")});
  await page.route("**/api/research/market",async route=>{
    const request=route.request().postDataJSON();
    if (request.research_mode==="current") return route.fulfill({status:502,json:{code:"archive_stale"}});
    const data=historical(request.symbol);
    if (request.symbol==="QQQ") data.research.research.archive.freshness.as_of="2026-10-16T19:33:00Z";
    await route.fulfill({json:data});
  });
  await page.goto("/dashboard");
  const spy=page.getByRole("region",{name:"SPY evidence"});
  const qqq=page.getByRole("region",{name:"QQQ evidence"});
  await expect(spy.getByText("HISTORICAL — COMPLETED SESSION ARCHIVE",{exact:true})).toBeVisible();
  await expect(qqq).toContainText("The latest archive session has not completed");
  await expect(qqq.getByText("HISTORICAL — COMPLETED SESSION ARCHIVE",{exact:true})).toHaveCount(0);
  await expect(qqq).toContainText("No substitute or unverified market data has been displayed");
});

test("both historical timeouts retain stale warnings, correlation, layout and refresh without prices",async({page})=>{
  const requests:Array<{symbol:string;research_mode:string}>=[];
  await page.route("**/api/research/market",async route=>{
    const payload=route.request().postDataJSON();requests.push(payload);
    await route.fulfill({status:502,json:{code:payload.research_mode==="current"?"archive_stale":"backend_timeout"},
      headers:{"X-AlphaOS-Request-ID":(payload.symbol==="SPY"?"a":"b").repeat(32)}});
  });
  await page.goto("/dashboard");
  await expect(page.getByRole("heading",{name:"Research Terminal Dashboard"})).toBeVisible();
  for(const symbol of ["SPY","QQQ"]) {
    const card=page.getByRole("region",{name:`${symbol} evidence`});
    await expect(card).toContainText("Current market evidence is stale");
    await expect(card).toContainText("Historical context unavailable: The research backend request timed out.");
    await expect(card).toContainText("Historical request ID: "+(symbol==="SPY"?"a":"b").repeat(32));
    await expect(card.getByRole("button",{name:`Refresh ${symbol} evidence`})).toBeVisible();
    await expect(card.getByText("$500.00",{exact:true})).toHaveCount(0);
  }
  await expect(page.getByText("HISTORICAL — COMPLETED SESSION ARCHIVE",{exact:true})).toHaveCount(0);
  expect(requests.filter(item=>item.research_mode==="historical")).toHaveLength(2);
  await page.getByRole("button",{name:"Refresh SPY evidence"}).click();
  await expect.poll(()=>requests.filter(item=>item.symbol==="SPY"&&item.research_mode==="historical").length).toBe(2);
});
