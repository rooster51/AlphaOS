import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { readFileSync } from "node:fs";
import { loadDashboardResearch, dashboardMessage } from "../src/lib/dashboard-research.ts";
import { POST } from "../src/app/api/research/market/route.ts";

// Existing deterministic archive/REST/MCP fixture; never live market evidence.
const fixture = JSON.parse(readFileSync(new URL("./fixtures/unsupported-routes-parity.json", import.meta.url))).response;
const freshNow = Date.parse("2026-10-16T19:33:00Z");
const historicalNow = Date.parse("2026-10-20T14:00:00Z");
const id = "a".repeat(32);
const observationCases=JSON.parse(readFileSync(new URL('./fixtures/observation-parity.json',import.meta.url),'utf8'));
function compactBody(symbol,mode) {
  return {source:'alphaos_research_api',verified_for_trading:false,
    research:observationCases.find(c=>c.request.symbol===symbol && c.request.research_mode===mode).response};
}
function body(symbol = "QQQ", mode = "current") {
  const data = JSON.parse(JSON.stringify(fixture).replaceAll("QQQ", symbol));
  data.request.research_mode = mode;
  data.research.research_mode = mode;
  if (mode === "historical") {
    data.research.archive.freshness.max_age_seconds = null;
    data.research.archive.freshness.as_of = new Date(historicalNow).toISOString();
    data.research.archive.freshness.age_seconds = (historicalNow - Date.parse(data.research.as_of)) / 1000;
  }
  return {source:"alphaos_research_api", verified_for_trading:false, research:data};
}
function response(value, status = 200) {
  return Response.json(value, {status, headers:{"X-AlphaOS-Request-ID":id}});
}

for (const symbol of ["SPY", "QQQ"]) {
  test(`${symbol}: current success uses one explicit uncached request, no fallback`, async () => {
    let count = 0;
    const result = await loadDashboardResearch(symbol, async (url, options) => {
      count++;
      assert.equal(url, "/api/research/market");
      assert.equal(options.cache, "no-store");
      assert.deepEqual(JSON.parse(options.body), {symbol,research_mode:"current",view:"observation"});
      assert.equal(options.headers.Authorization, undefined);
      return response(body(symbol));
    }, () => freshNow);
    assert.equal(count, 1);
    assert.equal(result.observation.mode, "current");
    assert.equal(result.observation.spot, 500);
    assert.equal(result.currentFailure, undefined);
  });
  test(`${symbol}: stale current requests explicit historical context and retains correlation`, async () => {
    const modes = [];
    const result = await loadDashboardResearch(symbol, async (_, options) => {
      const mode = JSON.parse(options.body).research_mode; modes.push(mode);
      return mode === "current" ? response({code:"archive_stale"},502) : response(body(symbol,"historical"));
    }, () => historicalNow);
    assert.deepEqual(modes, ["current", "historical"]);
    assert.equal(result.currentFailure.code, "archive_stale");
    assert.equal(result.currentFailure.requestId, id);
    assert.equal(result.observation.mode, "historical");
    assert.equal(result.observation.sessionDate, "2026-10-16");
    assert.equal(result.observation.observedAt, "2026-10-16T19:30:00+00:00");
    assert.equal(result.observation.provider, "Public");
    assert.equal("candidates" in result.observation, false);
  });
}

for (const code of ["backend_authentication_required", "backend_authentication_rejected", "backend_unreachable",
  "backend_timeout", "backend_service_unavailable", "archive_missing", "archive_unavailable",
  "archive_research_unavailable", "backend_endpoint_unavailable"]) {
  test(`${code}: preserves specific failure and never attempts historical fallback`, async () => {
    let count = 0;
    const result = await loadDashboardResearch("QQQ", async () => {count++; return response({code},502);});
    assert.equal(count, 1);
    assert.equal(result.observation, null);
    assert.equal(result.currentFailure.code, code);
    assert.notEqual(dashboardMessage(code), dashboardMessage("unknown"));
  });
}

test("total failure, invalid JSON, unknown errors and unsafe correlation stay sanitized", async () => {
  for (const fetcher of [async () => {throw new TypeError("secret");},
    async () => new Response("secret",{status:503}),
    async () => Response.json({code:"secret",message:"secret"},{status:502,headers:{"X-AlphaOS-Request-ID":"secret"}})]) {
    const result = await loadDashboardResearch("QQQ",fetcher);
    assert.equal(result.observation, null);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("malformed success or stale success cannot bypass validation or trigger fallback", async () => {
  for (const mutate of [
    b => {b.research.research.archive.storage.archive_sha256="bad";},
    b => {b.research.research.archive.storage.symbol="SPY";},
    b => {b.research.research.archive.storage.session_date="2026-10-15";},
    b => {b.research.research.archive.storage.observed_at="2026-10-16T19:29:00Z";},
    b => {b.research.research.archive.observation.options_status="failed";},
    b => {b.research.research.research_session.market.spot=0;},
    b => {b.research.research.archive.freshness.age_seconds=601;},
    b => {b.research.research.archive.freshness.max_age_seconds=86400;},
    b => {b.research.research.research_mode="historical";},
    b => {b.verified_for_trading=true;},
  ]) {
    let count=0;const data=body();mutate(data);
    const result=await loadDashboardResearch("QQQ",async () => {count++;return response(data);},()=>freshNow);
    assert.equal(result.observation,null);
    assert.equal(result.currentFailure.code,"response_schema_mismatch");
    assert.equal(count,1);
  }
  const stale = await loadDashboardResearch("QQQ",async()=>response(body()),()=>freshNow+601000);
  assert.equal(stale.observation,null);
});

test("historical fallback rejects incomplete sessions, relabeled current, invalid provenance and backend failure", async () => {
  for (const defect of ["open_session","unknown_session","current_mode","checksum","timestamp","backend"]) {
    const data=body("QQQ","historical");
    if (defect === "open_session") data.research.research.archive.freshness.as_of="2026-10-16T19:33:00Z";
    if (defect === "unknown_session") delete data.research.research.research_session.opportunity_state.evidence.time_state.observations.session;
    if (defect === "current_mode") data.research.research.research_mode="current";
    if (defect === "checksum") delete data.research.research.archive.storage.archive_sha256;
    if (defect === "timestamp") data.research.research.archive.observation.observed_at="invalid";
    let count=0;
    const result=await loadDashboardResearch("QQQ",async()=>++count===1
      ? response({code:"archive_stale"},502) : defect === "backend"
        ? response({code:"backend_service_unavailable"},502) : response(data),()=>historicalNow);
    assert.equal(count,2);
    assert.equal(result.observation,null);
    assert.equal(result.currentFailure.code,"archive_stale");
    assert.ok(result.historicalFailure);
    if (defect === "open_session") assert.equal(result.historicalFailure.code,"historical_session_incomplete");
  }
});

const originalFetch=globalThis.fetch;
const originalToken=process.env.ALPHAOS_API_TOKEN;
const originalUrl=process.env.ALPHAOS_API_URL;
afterEach(()=>{
  globalThis.fetch=originalFetch;
  if (originalToken===undefined) delete process.env.ALPHAOS_API_TOKEN; else process.env.ALPHAOS_API_TOKEN=originalToken;
  if (originalUrl===undefined) delete process.env.ALPHAOS_API_URL; else process.env.ALPHAOS_API_URL=originalUrl;
});
test("dashboard -> real website bridge preserves auth, correlation, stale code and historical contract", async()=>{
  process.env.ALPHAOS_API_TOKEN="test-only-token";
  process.env.ALPHAOS_API_URL="https://backend.example.test";
  const modes=[];
  globalThis.fetch=async(url,options)=>{
    assert.equal(String(url),"https://backend.example.test/v1/research/observation");
    assert.equal(options.headers.Authorization,"Bearer test-only-token");
    assert.match(options.headers["X-AlphaOS-Request-ID"],/^[a-f0-9]{32}$/);
    const mode=JSON.parse(options.body).research_mode;modes.push(mode);
    return mode==="current" ? Response.json({error:{code:"archive_stale"}},{status:503})
      : Response.json(compactBody("QQQ","historical").research);
  };
  const result=await loadDashboardResearch("QQQ",(_,options)=>POST(new Request("http://localhost/api/research/market",options)),()=>historicalNow);
  assert.deepEqual(modes,["current","historical"]);
  assert.equal(result.observation.mode,"historical");
  assert.match(result.currentFailure.requestId,/^[a-f0-9]{32}$/);
});

for(const symbol of ['SPY','QQQ']) for(const mode of ['current','historical']) {
 test(`compact ${symbol} ${mode} displays only verified observation`,async()=>{
  const result=await loadDashboardResearch(symbol,async(_,options)=>{
   const request=JSON.parse(options.body);assert.equal(request.view,'observation');
   return mode==='historical' && request.research_mode==='current' ? response({code:'archive_stale'},502) : response(compactBody(symbol,mode));
  },()=>mode==='current'?freshNow:historicalNow);
  assert.equal(result.observation.mode,mode);assert.equal(result.observation.spot,500);
  assert.equal('candidates' in result.observation,false);
 });
}
