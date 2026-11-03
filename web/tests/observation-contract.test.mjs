import assert from 'node:assert/strict';
import {test,afterEach} from 'node:test';
import {readFileSync} from 'node:fs';
import {POST} from '../src/app/api/research/market/route.ts';
import { issueSession, sessionCookie } from '../src/lib/website-auth.ts';
const cases=JSON.parse(readFileSync(new URL('./fixtures/observation-parity.json',import.meta.url),'utf8'));
const oldFetch=globalThis.fetch;
const oldToken=process.env.ALPHAOS_API_TOKEN,oldUrl=process.env.ALPHAOS_API_URL;
const oldPreviewDiagnostics=process.env.ALPHAOS_PREVIEW_DIAGNOSTICS;
const oldPasswordHash=process.env.ALPHAOS_PASSWORD_HASH,oldSessionKey=process.env.ALPHAOS_SESSION_KEY;
afterEach(()=>{globalThis.fetch=oldFetch;
 if(oldToken===undefined) delete process.env.ALPHAOS_API_TOKEN;else process.env.ALPHAOS_API_TOKEN=oldToken;
 if(oldUrl===undefined) delete process.env.ALPHAOS_API_URL;else process.env.ALPHAOS_API_URL=oldUrl;
 if(oldPreviewDiagnostics===undefined) delete process.env.ALPHAOS_PREVIEW_DIAGNOSTICS;else process.env.ALPHAOS_PREVIEW_DIAGNOSTICS=oldPreviewDiagnostics;
 if(oldPasswordHash===undefined) delete process.env.ALPHAOS_PASSWORD_HASH;else process.env.ALPHAOS_PASSWORD_HASH=oldPasswordHash;
 if(oldSessionKey===undefined) delete process.env.ALPHAOS_SESSION_KEY;else process.env.ALPHAOS_SESSION_KEY=oldSessionKey;});
function request(data){return new Request('https://example.test/api/research/market',{method:'POST',body:JSON.stringify(data),headers:{'Content-Type':'application/json'}});}
function setup(){process.env.ALPHAOS_API_TOKEN='test-token';process.env.ALPHAOS_API_URL='https://backend.test';}
for(const c of cases) test(`real Python compact contract ${c.request.symbol} ${c.request.research_mode}`,async()=>{
 setup();globalThis.fetch=async(url,options)=>{
  assert.equal(String(url),'https://backend.test/v1/research/observation');
  assert.deepEqual(JSON.parse(options.body),c.request);
  return Response.json(c.response);
 };
 const r=await POST(request({...c.request,view:'observation'}));assert.equal(r.status,200);
 assert.deepEqual((await r.json()).research,c.response);
 for(const mutate of [v=>v.research_performed=true,v=>v.verified_for_trading=true,v=>v.symbol='BAD',
   v=>v.archive.storage.archive_sha256='bad',v=>v.archive.freshness.age_seconds=-1,
   v=>v.archive.observation.observed_at='2000-01-01T00:00:00Z',v=>v.candidates=[]]) {
  const bad=structuredClone(c.response);mutate(bad);globalThis.fetch=async()=>Response.json(bad);
  assert.equal((await POST(request({...c.request,view:'observation'}))).status,502);
 }
});
test('observation projection cannot silently accept research knobs or replace full research',async()=>{
 setup();for(const extra of [{width:5},{available_capital:150},{objective:'bullish'}]) {
  assert.equal((await POST(request({symbol:'SPY',view:'observation',...extra}))).status,400);
 }
 globalThis.fetch=async()=>Response.json(cases[0].response);
 assert.equal((await POST(request({symbol:'SPY'}))).status,502);
});

test('empty option archives pass only with zero verified contract counts',async()=>{
 setup();
 const empty=structuredClone(cases.find(c=>c.request.symbol==='QQQ'&&c.request.research_mode==='current').response);
 empty.archive.storage.quality_status='empty';
 empty.archive.storage.contract_count=0;
 empty.archive.observation.options_status='empty';
 empty.archive.diagnostics.total_contract_count=0;
 for(const key of Object.keys(empty.archive.diagnostics.bucket_counts)) empty.archive.diagnostics.bucket_counts[key]=0;
 globalThis.fetch=async()=>Response.json(empty);
 assert.equal((await POST(request({symbol:'QQQ',view:'observation'}))).status,200);

 for(const mutate of [
  value=>value.archive.storage.contract_count=1,
  value=>value.archive.diagnostics.total_contract_count=1,
  value=>value.archive.diagnostics.bucket_counts.valid_contracts=1,
 ]) {
  const inconsistent=structuredClone(empty);mutate(inconsistent);globalThis.fetch=async()=>Response.json(inconsistent);
  assert.equal((await POST(request({symbol:'QQQ',view:'observation'}))).status,502);
 }
});

test('current observations accept the 600-second policy boundary and reject larger limits',async()=>{
 setup();
 const snapshot=structuredClone(cases.find(c=>c.request.symbol==='QQQ'&&c.request.research_mode==='current').response);
 const atBoundary=structuredClone(snapshot);
 atBoundary.requested_as_of='2026-10-16T19:40:00+00:00';
 atBoundary.archive.freshness.as_of=atBoundary.requested_as_of;
 atBoundary.archive.freshness.age_seconds=600;
 atBoundary.archive.freshness.max_age_seconds=600;
 globalThis.fetch=async()=>Response.json(atBoundary);
 assert.equal((await POST(request({symbol:'QQQ',view:'observation'}))).status,200);

 const overLimit=structuredClone(snapshot);
 overLimit.archive.freshness.max_age_seconds=601;
 globalThis.fetch=async()=>Response.json(overLimit);
 const rejected=await POST(request({symbol:'QQQ',view:'observation'}));
 assert.equal(rejected.status,502);
 assert.equal((await rejected.json()).code,'response_schema_mismatch');

 const stale=structuredClone(snapshot);
 stale.requested_as_of='2026-10-16T19:40:01+00:00';
 stale.archive.freshness.as_of=stale.requested_as_of;
 stale.archive.freshness.age_seconds=601;
 stale.archive.freshness.max_age_seconds=600;
 globalThis.fetch=async()=>Response.json(stale);
 const staleResponse=await POST(request({symbol:'QQQ',view:'observation'}));
 assert.equal(staleResponse.status,502);
 assert.equal((await staleResponse.json()).code,'response_schema_mismatch');
});

test('bridge diagnostics identify safe failure categories without logging response data',async()=>{
 setup();
 const current=cases.find(c=>c.request.symbol==='QQQ'&&c.request.research_mode==='current').response;
 const scenarios=[
  {category:'invalid_json',fields:undefined,body:'{"private":"DO_NOT_LOG"'},
  {category:'invalid_numeric_encoding',fields:['spot'],body:JSON.stringify(current).replace('"spot":500','"spot":1e999')},
  {category:'observation_schema_mismatch',fields:['read_only'],data:{...structuredClone(current),read_only:false}},
  {category:'timestamp_freshness_mismatch',fields:['archive.freshness.age_seconds'],data:(()=>{const v=structuredClone(current);v.archive.freshness.age_seconds=1;return v;})()},
  {category:'archive_metadata_quality_mismatch',fields:['archive.observation.options_status'],data:(()=>{const v=structuredClone(current);v.archive.observation.options_status='partial';return v;})()},
 ];
 const logs=[],warn=console.warn;console.warn=value=>logs.push(JSON.parse(value));
 try {
  for(const scenario of scenarios) {
   globalThis.fetch=async()=>scenario.body===undefined?Response.json(scenario.data):new Response(scenario.body,{headers:{'Content-Type':'application/json'}});
   const response=await POST(request({symbol:'QQQ',view:'observation'}));
   assert.equal(response.status,502);
   assert.deepEqual(await response.json(),{status:'unavailable',code:'response_schema_mismatch'});
  }
 } finally {console.warn=warn;}
 for(let index=0;index<scenarios.length;index++) {
  const {category,fields}=scenarios[index],log=logs[index];
  assert.equal(log.validation_category,category);
  if(fields) assert.deepEqual(log.validation_fields,fields);
  assert.ok(!JSON.stringify(log).includes('DO_NOT_LOG'));
  assert.ok(!JSON.stringify(log).includes('test-token'));
 }
});

test('owner diagnostics are restricted to the authenticated PR 82 deploy preview',async()=>{
 setup();
 process.env.ALPHAOS_PREVIEW_DIAGNOSTICS='true';
 process.env.ALPHAOS_PASSWORD_HASH=`$2b$12$${'a'.repeat(53)}`;
 process.env.ALPHAOS_SESSION_KEY='s'.repeat(43);
 const env={ALPHAOS_PASSWORD_HASH:process.env.ALPHAOS_PASSWORD_HASH,ALPHAOS_SESSION_KEY:process.env.ALPHAOS_SESSION_KEY};
 const preview='https://deploy-preview-82--alphaostrading.netlify.app';
 const token=await issueSession(env,preview);
 const malformed=structuredClone(cases.find(c=>c.request.symbol==='QQQ'&&c.request.research_mode==='current').response);
 malformed.research_performed=true;
 globalThis.fetch=async()=>Response.json(malformed);
 const previewRequest=(origin,cookie)=>new Request(`${origin}/api/research/market`,{
  method:'POST',body:JSON.stringify({symbol:'QQQ',view:'observation'}),
  headers:{'Content-Type':'application/json',...(cookie?{Cookie:cookie}:{})},
 });

 const authorized=await POST(previewRequest(preview,sessionCookie(token).split(';')[0]));
 assert.equal(authorized.status,502);
 const authorizedBody=await authorized.json();
 assert.equal(authorizedBody.code,'response_schema_mismatch');
 assert.deepEqual(authorizedBody.diagnostic,{
  request_id:authorized.headers.get('X-AlphaOS-Request-ID'),
  upstream_status:200,
  validation_categories:['observation_schema_mismatch'],
  rejected_fields:['research_performed'],
 });
 assert.equal(JSON.stringify(authorizedBody).includes('test-token'),false);
 assert.equal(JSON.stringify(authorizedBody).includes(JSON.stringify(malformed)),false);

 process.env.ALPHAOS_PREVIEW_DIAGNOSTICS='false';
 const contextDisabled=await POST(previewRequest(preview,sessionCookie(token).split(';')[0]));
 assert.equal(contextDisabled.status,502);
 assert.equal('diagnostic' in await contextDisabled.json(),false);
 process.env.ALPHAOS_PREVIEW_DIAGNOSTICS='true';

 const anonymous=await POST(previewRequest(preview));
 assert.equal(anonymous.status,502);
 assert.equal('diagnostic' in await anonymous.json(),false);

 const production='https://alphaostrading.netlify.app';
 const productionToken=await issueSession(env,production);
 const productionResponse=await POST(previewRequest(production,sessionCookie(productionToken).split(';')[0]));
 assert.equal(productionResponse.status,502);
 assert.equal('diagnostic' in await productionResponse.json(),false);
});
