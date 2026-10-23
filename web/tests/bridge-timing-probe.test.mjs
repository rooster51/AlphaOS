import assert from 'node:assert/strict';
import { test, afterEach } from 'node:test';
import { BridgeTimingProbe } from '../src/lib/bridge-timing-probe.ts';
import { POST } from '../src/app/api/research/market/route.ts';

const original = { fetch:globalThis.fetch, warn:console.warn, timeout:AbortSignal.timeout,
  token:process.env.ALPHAOS_API_TOKEN, url:process.env.ALPHAOS_API_URL, probe:process.env.ALPHAOS_BRIDGE_TIMING_PROBE };
afterEach(()=>{
 globalThis.fetch=original.fetch;console.warn=original.warn;AbortSignal.timeout=original.timeout;
 for(const [key,value] of [['ALPHAOS_API_TOKEN',original.token],['ALPHAOS_API_URL',original.url],['ALPHAOS_BRIDGE_TIMING_PROBE',original.probe]]) {
  if(value===undefined)delete process.env[key];else process.env[key]=value;
 }
});
function input(signal){return new Request('https://website.example/api/research/market',{method:'POST',body:JSON.stringify({symbol:'SPY'}),signal});}
function envelope(){return {schema_version:'alphaos-interface-v2',read_only:true,request:{symbol:'SPY'},research:{symbol:'SPY',as_of:'2030-01-01',archive:{},research_session:{symbol:'SPY',candidates:[],unavailable_routes:[],status:'no_candidate'}},provenance:{},caveats:[]};}
function config(enabled){process.env.ALPHAOS_API_TOKEN='credential-canary';process.env.ALPHAOS_API_URL='https://backend.example';process.env.ALPHAOS_BRIDGE_TIMING_PROBE=enabled?'1':'0';}

test('disabled route uses native json only, no additional probe logs',async()=>{
 config(false);const logs=[];console.warn=x=>logs.push(JSON.parse(x));let calls=0;
 globalThis.fetch=async()=>({ok:true,status:200,headers:new Headers(),json:async()=>{calls++;return envelope();},arrayBuffer(){throw Error('disabled probe accessed bytes');}});
 const r=await POST(input());assert.equal(r.status,200);assert.equal(calls,1);assert.equal(logs.length,1);assert.equal(logs[0].event,'research_bridge');
});

test('enabled and disabled routes preserve bytes/status/cache and validation/errors',async()=>{
 for(const make of [()=>Response.json(envelope()),()=>new Response('{"private":"BODY_CANARY"'),()=>Response.json({wrong:'BODY_CANARY'}),()=>Response.json({error:{code:'archive_stale'},private:'BODY_CANARY'},{status:503}),()=>new Response(new Uint8Array([0xef,0xbb,0xbf,...new TextEncoder().encode(JSON.stringify(envelope()))]))]) {
  const results=[];
  for(const enabled of [false,true]){
   config(enabled);const logs=[];console.warn=x=>logs.push(JSON.parse(x));globalThis.fetch=async()=>make();
   const r=await POST(input());results.push({status:r.status,body:await r.text(),cache:r.headers.get('cache-control')});
   assert.ok(!JSON.stringify(logs).includes('BODY_CANARY'));assert.ok(!JSON.stringify(logs).includes('credential-canary'));
   const probe=logs.find(x=>x.event==='research_bridge_probe');assert.equal(!!probe,enabled);
   if(probe){assert.match(probe.request_id,/^[a-f0-9]{32}$/);assert.equal(probe.request_id,r.headers.get('x-alphaos-request-id'));assert.ok(probe.decoded_body_bytes>0);}
  }
  assert.deepEqual(results[0],results[1]);
 }
});

test('partial body, client abort and timeout preserve original route classification',async()=>{
 for(const kind of ['partial','client','timeout']){
  const results=[];
  for(const enabled of [false,true]){
   config(enabled);console.warn=()=>{};const client=new AbortController();
   AbortSignal.timeout=ms=>{assert.equal(ms,12000);return kind==='timeout'?AbortSignal.abort(new DOMException('PRIVATE_ERROR','TimeoutError')):new AbortController().signal;};
   globalThis.fetch=async(_,options)=>new Response(new ReadableStream({start(c){
    c.enqueue(new TextEncoder().encode('{"partial":'));
    if(kind==='client')client.abort();
    c.error(kind==='partial'?new TypeError('PRIVATE_ERROR'):kind==='client'?client.signal.reason:new DOMException('PRIVATE_ERROR','AbortError'));
   }}));
   const r=await POST(input(client.signal));results.push({status:r.status,body:await r.text()});
  }
  assert.deepEqual(results[0],results[1]);assert.equal(results[0].status,kind==='client'?499:502);
 }
});

test('JSON parse and UTF8 semantics match native response JSON including malformed bytes',async()=>{
 console.warn=()=>{};
 for(const bytes of [new Uint8Array([0x22,0xff,0x22]),new TextEncoder().encode('  {"x":1,"x":2,"n":-0}  '),new TextEncoder().encode(''),new TextEncoder().encode('{bad')]){
  const p=new BridgeTimingProbe('a'.repeat(32));
  try{const expected=await Promise.allSettled([new Response(bytes).json(),p.json(new Response(bytes))]);assert.equal(expected[0].status,expected[1].status);if(expected[0].status==='fulfilled')assert.deepEqual(expected[0].value,expected[1].value);else assert.equal(expected[0].reason.constructor,expected[1].reason.constructor);}
  finally{p.finish(200,new AbortController().signal);}
 }
});

test('deadline telemetry observes exceeded budget without introducing cancellation or enforcement',async(t)=>{
 let clock=0;t.mock.method(performance,'now',()=>clock);const logs=[];console.warn=x=>logs.push(JSON.parse(x));
 const p=new BridgeTimingProbe('b'.repeat(32));const controller=new AbortController();assert.equal(p.deadline(controller.signal),controller.signal);
 clock=12001;assert.deepEqual(await p.json(Response.json({ok:true})),{ok:true});p.finish(200,new AbortController().signal);
 assert.equal(controller.signal.aborted,false);assert.equal(logs[0].deadline_budget_exceeded,true);assert.equal(logs[0].status,200);assert.equal(logs[0].timeout_signal_aborted,false);
});

test('unexpected exceptions remain thrown without logging their messages or data',async()=>{
 config(true);const logs=[];console.warn=x=>logs.push(JSON.parse(x));globalThis.fetch=async()=>{throw Error('PRIVATE_EXCEPTION');};
 await assert.rejects(POST(input()),/PRIVATE_EXCEPTION/);assert.ok(!JSON.stringify(logs).includes('PRIVATE_EXCEPTION'));assert.equal(logs.filter(x=>x.event==='research_bridge_probe').length,1);
});
