import assert from 'node:assert/strict';
import {test,afterEach} from 'node:test';
import {readFileSync} from 'node:fs';
import {POST} from '../src/app/api/research/market/route.ts';
const cases=JSON.parse(readFileSync(new URL('./fixtures/observation-parity.json',import.meta.url),'utf8'));
const oldFetch=globalThis.fetch;
const oldToken=process.env.ALPHAOS_API_TOKEN,oldUrl=process.env.ALPHAOS_API_URL;
afterEach(()=>{globalThis.fetch=oldFetch;
 if(oldToken===undefined) delete process.env.ALPHAOS_API_TOKEN;else process.env.ALPHAOS_API_TOKEN=oldToken;
 if(oldUrl===undefined) delete process.env.ALPHAOS_API_URL;else process.env.ALPHAOS_API_URL=oldUrl;});
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
