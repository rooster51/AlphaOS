import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { POST } from '../src/app/api/options/route.ts';
import { defaultLimits, validResearchRequest, validResearchResults } from '../src/lib/options-research.ts';
import { authBindings,cookie } from './auth-fixture.mjs';
const fixtures=JSON.parse(readFileSync(new URL('./fixtures/multi-strategy-live.json',import.meta.url),'utf8'));
const origin='https://preview.test';
const payload={scenarios:fixtures.slice(0,2).map(item=>item.request),limits:{...defaultLimits},entry_fee_per_contract:.65};
const request=(body=payload,auth=true,from=origin)=>new Request(`${origin}/api/options?symbol=SPY&expiration=2026-11-06`,{
  method:'POST',headers:{Origin:from,'Content-Type':'application/json',...(auth?{Cookie:`__Host-alphaos_session=${cookie(origin)}`}:{})},body:JSON.stringify(body),
});

test('all supported family results retain the Python fixture economics and contract identities',()=>{
  for(const item of fixtures){
    assert.equal(validResearchResults([item.result],{...payload,scenarios:[item.request]}),true,item.request.strategy);
  }
  assert.equal(validResearchRequest(payload),true);
  for(const qty of [0,true,1.5,21]){
    const altered=structuredClone(payload);altered.scenarios[0].legs[0].qty=qty;
    assert.equal(validResearchRequest(altered),false);
  }
  const altered=structuredClone(payload);altered.limits.dte_min=altered.limits.dte_max+1;
  assert.equal(validResearchRequest(altered),false);
  const result=structuredClone(fixtures[0].result);result.max_loss=null;
  assert.equal(validResearchResults([result],{...payload,scenarios:[fixtures[0].request]}),false);
});

test('comparison bridge authenticates, rejects CSRF and malformed evidence, and uses one bounded request',async t=>{
  Object.assign(process.env,authBindings,{ALPHAOS_API_URL:'https://backend.test',ALPHAOS_API_TOKEN:'fixture-token'});
  const upstream=t.mock.method(globalThis,'fetch',async(url,options)=>{
    assert.equal(url.pathname,'/v1/options/SPY/chain/2026-11-06');
    assert.equal(options.method,'POST');assert.equal(options.cache,'no-store');assert.equal(options.redirect,'error');
    assert.deepEqual(JSON.parse(options.body),payload);
    return Response.json({meta:{symbol:'SPY'},evidence:{source:'Public',symbol:'SPY',expiration:'2026-11-06',request:payload,
      scenarios:fixtures.slice(0,2).map(item=>item.result)}});
  });
  assert.equal((await POST(request(payload,false))).status,401);
  assert.equal((await POST(request(payload,true,'https://evil.test'))).status,403);
  assert.equal((await POST(request({...payload,scenarios:[]}))).status,400);
  assert.equal(upstream.mock.callCount(),0);
  const response=await POST(request());assert.equal(response.status,200);
  assert.equal(response.headers.get('Cache-Control'),'private, no-store');
  assert.deepEqual((await response.json()).scenarios,fixtures.slice(0,2).map(item=>item.result));
  assert.equal(upstream.mock.callCount(),1);
  upstream.mock.mockImplementation(async()=>Response.json({meta:{symbol:'SPY'},evidence:{source:'Public',symbol:'SPY',expiration:'2026-11-06',request:payload,
    scenarios:fixtures.slice(0,2).map(item=>({...item.result,legs:[{contract:'wrong'}]}))}}));
  assert.equal((await POST(request())).status,502);
});
