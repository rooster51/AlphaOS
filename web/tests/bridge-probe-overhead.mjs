// Controlled opaque JSON, not market data or a research-performance benchmark.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const start=performance.now();
const {POST}=await import(process.env.PROBE_ROUTE);
const importMs=performance.now()-start;
const mode=process.env.PROBE_MODE;
process.env.ALPHAOS_API_TOKEN='local-test-only';process.env.ALPHAOS_API_URL='https://controlled.example';
process.env.ALPHAOS_BRIDGE_TIMING_PROBE=mode==='enabled'?'1':'0';
const logs=[];console.warn=s=>logs.push(JSON.parse(s));
const payload='x'.repeat(13_000_000);const expected={};
const bytes=Object.fromEntries(['SPY','QQQ'].map(symbol=>{
 const d={schema_version:'alphaos-interface-v2',read_only:true,request:{symbol},research:{symbol,as_of:'2030-01-01',archive:{},research_session:{symbol,candidates:[],unavailable_routes:[],status:'no_candidate'}},provenance:{},caveats:[],opaque_test_padding:payload};
 expected[symbol]=createHash('sha256').update(JSON.stringify({research:d,verified_for_trading:false,source:'alphaos_research_api'})).digest('hex');
 return [symbol,new TextEncoder().encode(JSON.stringify(d))];
}));
globalThis.fetch=async(_,o)=>{
 const raw=bytes[JSON.parse(o.body).symbol];let offset=0;
 return new Response(new ReadableStream({pull(c){if(o.signal.aborted){c.error(o.signal.reason);return;}if(offset===raw.length){c.close();return;}c.enqueue(raw.subarray(offset,offset+65536));offset=Math.min(offset+65536,raw.length);}}),{headers:{'Content-Type':'application/json','X-AlphaOS-Request-ID':o.headers['X-AlphaOS-Request-ID']}});
};
async function call(symbol){
 const t=performance.now();const r=await POST(new Request('https://controlled.example/api/research/market',{method:'POST',body:JSON.stringify({symbol})}));
 const body=await r.arrayBuffer();const complete=performance.now()-t;
 const hash=createHash('sha256').update(new Uint8Array(body)).digest('hex');
 if(r.status!==200||hash!==expected[symbol])throw Error('controlled response parity failed');
 return {symbol,status:r.status,complete_ms:complete,bytes:body.byteLength,sha256:hash};
}
const batches=[];
async function batch(kind,concurrent){
 const cpu=process.cpuUsage();const t=performance.now();const rows=concurrent?await Promise.all(['SPY','QQQ'].map(call)):[await call('SPY'),await call('QQQ')];
 const used=process.cpuUsage(cpu);batches.push({kind,wall_ms:performance.now()-t,cpu_ms:(used.user+used.system)/1000,rss:process.memoryUsage().rss,rows});
}
await batch('first_imported_request',true);
for(let n=0;n<3;n++)await batch('warm_sequential',false);
for(let n=0;n<6;n++)await batch('warm_concurrent',true);
const cgroup={};for(const f of ['cpu.max','cpu.stat','memory.max','memory.peak','memory.events'])try{cgroup[f]=readFileSync('/sys/fs/cgroup/'+f,'utf8');}catch{}
writeFileSync(process.env.PROBE_OUTPUT,JSON.stringify({mode,node:process.version,platform:process.platform,cpu_model:readFileSync('/proc/cpuinfo','utf8').split('\n').find(s=>s.startsWith('model name')),import_ms:importMs,batches,logs,cgroup},null,2));
