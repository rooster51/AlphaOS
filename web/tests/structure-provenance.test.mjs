import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {parseStructureRequest,parseCompareRequest} from '../src/lib/structure-contract.ts';
import {structureViewFor,compareViewFor} from '../src/lib/structure-view.ts';
import {requestStructure,requestComparison} from '../src/lib/structure-client.ts';
import {POST as postStructure} from '../src/app/api/research/structure/route.ts';
import {POST as postCompare} from '../src/app/api/research/structures/compare/route.ts';

const fixture=JSON.parse(readFileSync(new URL('./fixtures/structure-provenance-parity.json',import.meta.url),'utf8'));
const wrap=research=>({research,source:'alphaos_research_structure_api',verified_for_trading:false});

for(const symbol of ['SPY','QQQ']) test(`${symbol} canonical archive identity survives request, response and browser client`,async()=>{
  const envelope=fixture.single[symbol], payload=envelope.request;
  assert.deepEqual(parseStructureRequest(payload),payload);
  const view=structureViewFor(envelope,payload);
  assert.equal(view.marketData.kind,'verified_archive');
  assert.equal(view.marketData.legs[0].contract,payload.legs[0].contract);
  assert.equal(view.marketData.snapshotId,payload.market_data.snapshot_id);
  const result=await requestStructure(payload,async()=>Response.json(wrap(envelope)));
  assert.equal(result.ok,true);
  assert.deepEqual(result.view.marketData,view.marketData);
});

test('mixed verified/hypothetical comparison retains source identity per candidate',async()=>{
  const envelope=fixture.comparison;
  assert.deepEqual(parseCompareRequest(envelope.request),envelope.request);
  const view=compareViewFor(envelope,envelope.request);
  assert.deepEqual(view.candidates.map(c=>c.marketData.kind),['verified_archive','verified_archive','hypothetical']);
  assert.equal(view.candidates[0].marketData.legs[0].contract,envelope.request.structures[0].legs[0].contract);
  assert.equal(view.candidates[1].marketData.legs[0].contract,envelope.request.structures[1].legs[0].contract);
  const result=await requestComparison(envelope.request,async()=>Response.json(wrap(envelope)));
  assert.equal(result.ok,true);
  assert.deepEqual(result.view.candidates.map(c=>c.marketData),view.candidates.map(c=>c.marketData));
});

test('microsecond timestamps and wire-number roundoff use the backend tolerance',()=>{
  const envelope=structuredClone(fixture.single.SPY);
  const data=envelope.research.evidence.market_data;
  data.underlying.spot+=1e-9;
  data.signed_package_cashflow+=1e-9;
  data.evaluated_at='2030-01-02T20:33:00.123456+00:00';
  for(const leg of data.legs) Object.assign(leg.freshness,{
    evaluated_at:data.evaluated_at,bid_age_seconds:180.123456,ask_age_seconds:180.123456});
  assert.notEqual(structureViewFor(envelope,envelope.request),null);
});

for(const mutation of ['snapshot','checksum','missing_evidence','hypothetical','stale','future','bid','cashflow',
  'contract','partial','position_quote','trade_quote','entry_side','missing_underlying']) {
  test(`archive evidence fails closed for ${mutation}`,()=>{
    const e=structuredClone(fixture.single.SPY), d=e.research.evidence.market_data;
    if(mutation==='snapshot') d.snapshot.id='different';
    if(mutation==='checksum') d.snapshot.archive_sha256='f'.repeat(64);
    if(mutation==='missing_evidence') delete e.research.evidence.market_data;
    if(mutation==='hypothetical') d.kind='hypothetical';
    if(mutation==='stale') d.legs[0].bid_timestamp='2030-01-02T19:00:00Z';
    if(mutation==='future') d.legs[0].ask_timestamp='2031-01-02T19:00:00Z';
    if(mutation==='bid') d.legs[0].bid=d.legs[0].ask+1;
    if(mutation==='cashflow') d.signed_package_cashflow+=1;
    if(mutation==='contract') d.legs[0].contract='QQQ300118C00500000';
    if(mutation==='partial') d.legs.pop();
    if(mutation==='position_quote') e.research.position.legs[0].ask+=1;
    if(mutation==='trade_quote') e.research.trade.legs[0].bid_timestamp='2020-01-01T00:00:00Z';
    if(mutation==='entry_side') d.legs[0].entry_side='mid';
    if(mutation==='missing_underlying') d.underlying.timestamp=null;
    assert.equal(structureViewFor(e,fixture.single.SPY.request),null);
  });
}

test('comparison rejects dropped provenance or a mismatch in its projection',()=>{
  const e=structuredClone(fixture.comparison);
  delete e.research.candidates[1].evidence.market_data;
  assert.equal(compareViewFor(e,e.request),null);
  const f=structuredClone(fixture.comparison);
  f.research.comparison.candidates[0].market_data.snapshot.id='forged';
  assert.equal(compareViewFor(f,f.request),null);
  const hypothetical=structuredClone(fixture.comparison);
  hypothetical.research.comparison.candidates[2].market_data.kind='verified_archive';
  assert.equal(compareViewFor(hypothetical,hypothetical.request),null);
});

test('clients cannot attach arbitrary quote values or identities to hypothetical requests',()=>{
  const original=fixture.single.QQQ.request;
  for(const change of [p=>delete p.market_data,p=>delete p.legs[1].contract,
    p=>p.legs[0].bid=123,p=>p.market_data.verified=true]) {
    const p=structuredClone(original);change(p);
    assert.equal(parseStructureRequest(p),null);
  }
});

test('website route -> authenticated backend -> browser preserves canonical provenance',async()=>{
  const oldFetch=globalThis.fetch, oldToken=process.env.ALPHAOS_API_TOKEN, oldUrl=process.env.ALPHAOS_API_URL;
  process.env.ALPHAOS_API_TOKEN='provenance-fixture-token';process.env.ALPHAOS_API_URL='https://backend.example.test';
  try {
    for(const [route,path,envelope,client] of [[postStructure,'structure',fixture.single.SPY,requestStructure],
      [postCompare,'structures/compare',fixture.comparison,requestComparison]]) {
      globalThis.fetch=async(url,options)=>{
        assert.equal(options.headers.Authorization,'Bearer provenance-fixture-token');
        assert.deepEqual(JSON.parse(options.body),envelope.request);
        return Response.json(envelope);
      };
      const outcome=await client(envelope.request,async()=>route(new Request(`https://site.example.test/api/research/${path}`,
        {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(envelope.request)})));
      assert.equal(outcome.ok,true);
      assert.equal(JSON.stringify(outcome).includes('provenance-fixture-token'),false);
    }
  } finally {
    globalThis.fetch=oldFetch;
    if(oldToken===undefined) delete process.env.ALPHAOS_API_TOKEN; else process.env.ALPHAOS_API_TOKEN=oldToken;
    if(oldUrl===undefined) delete process.env.ALPHAOS_API_URL; else process.env.ALPHAOS_API_URL=oldUrl;
  }
});
