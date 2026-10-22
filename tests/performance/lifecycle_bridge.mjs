// Local HTTP adapter around the real POST handler; never deployed.
import {createServer} from 'node:http';
import {appendFileSync} from 'node:fs';
import {PerformanceObserver,constants} from 'node:perf_hooks';
import {pathToFileURL} from 'node:url';
const route=await import(pathToFileURL(process.env.DIAGNOSTIC_REPO+'/web/src/app/api/research/market/route.ts').href);
const log=process.env.LOCAL_PROFILE_LOG;let active=0;
function emit(x){appendFileSync(log,JSON.stringify({time:performance.now(),...x})+'\n');}
new PerformanceObserver(list=>{for(const e of list.getEntries())emit({kind:'gc',duration_ms:e.duration,generation:e.detail.kind});}).observe({entryTypes:['gc']});
const originalFetch=globalThis.fetch,originalJSON=Response.json.bind(Response);
globalThis.fetch=async(...args)=>{
 const start=performance.now(),cpu=process.cpuUsage();const r=await originalFetch(...args);const id=new Headers(args[1]?.headers).get('X-AlphaOS-Request-ID');
 emit({kind:'backend_headers',request_id:id,wall_ms:performance.now()-start,cpu:process.cpuUsage(cpu)});
 const read=r.text.bind(r);
 r.json=async()=>{
  const w=performance.now(),c=process.cpuUsage();const text=await read();
  emit({kind:'backend_body_read_decode',request_id:id,wall_ms:performance.now()-w,cpu:process.cpuUsage(c)});
  const p=performance.now(),pc=process.cpuUsage();const data=JSON.parse(text);
  emit({kind:'backend_json_parse',request_id:id,wall_ms:performance.now()-p,cpu:process.cpuUsage(pc)});
  emit({kind:'backend_body_read_parse',request_id:id,wall_ms:performance.now()-w,cpu:process.cpuUsage(c)});return data;
 };
 return r;
};
Response.json=(value,init)=>{const start=performance.now(),cpu=process.cpuUsage();const r=originalJSON(value,init);emit({kind:'response_construction',wall_ms:performance.now()-start,cpu:process.cpuUsage(cpu),active_requests:active});return r;};
createServer(async(req,res)=>{
 if(req.url==='/health'){res.end('ok');return;}
 active++;const start=performance.now(),cpu=process.cpuUsage();
 try{
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  const response=await route.POST(new Request('http://localhost/api/research/market',{method:'POST',headers:{'Content-Type':'application/json'},body:Buffer.concat(chunks)}));
  const body=Buffer.from(await response.arrayBuffer());const id=response.headers.get('X-AlphaOS-Request-ID');
  res.writeHead(response.status,{'Content-Type':'application/json','X-AlphaOS-Request-ID':id});res.end(body);
  emit({kind:'bridge_complete',request_id:id,status:response.status,wall_ms:performance.now()-start,cpu:process.cpuUsage(cpu),body_bytes:body.length,memory:process.memoryUsage(),max_rss_bytes:process.resourceUsage().maxRSS*1024});
 }catch(e){emit({kind:'error',error:e.name});res.writeHead(500);res.end('{}');}
 finally{active--;}
}).listen(3017,'0.0.0.0');
