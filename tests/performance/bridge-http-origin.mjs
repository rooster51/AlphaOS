// Local HTTPS fixture only: no quotes, bars, contracts or provider connections.
import https from 'node:https';
import { readFileSync, appendFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
const log=data=>appendFileSync('/out/origin.jsonl',JSON.stringify(data)+'\n');
function envelope(symbol,padding='') {return {schema_version:'alphaos-interface-v2',read_only:true,request:{symbol},research:{symbol,as_of:'2030-01-01',archive:{},research_session:{symbol,candidates:[],unavailable_routes:[],status:'no_candidate'}},provenance:{fixture_only:true},caveats:[],opaque_test_padding:padding};}
const cached={};
for(const symbol of ['SPY','QQQ']){
 const big=Buffer.from(JSON.stringify(envelope(symbol,'x'.repeat(13_000_000))));
 cached[symbol]={complete:big,gzip:gzipSync(big),delayed:Buffer.from(JSON.stringify(envelope(symbol,'x'.repeat(500_000)))),unicode:Buffer.concat([Buffer.from([239,187,191]),Buffer.from(JSON.stringify(envelope(symbol,'π🙂é')))])};
}
const server=https.createServer({key:readFileSync('/out/key.pem'),cert:readFileSync('/out/cert.pem')},async(req,res)=>{
 if(req.url==='/health'){res.end('ok');return;}
 let text='';for await(const chunk of req)text+=chunk;
 const request=JSON.parse(text);const symbol=request.symbol;const scenario=request.objective||'complete';const id=req.headers['x-alphaos-request-id'];
 if(!cached[symbol]||!['complete','gzip','delayed','unicode','malformed','partial','interrupted','client_abort','timeout_body','timeout_headers'].includes(scenario)){res.writeHead(400).end();return;}
 const started=performance.now();let closed=false,timer;
 const elapsed=()=>performance.now()-started;
 const record=event=>log({event,request_id:id,scenario,symbol,elapsed_ms:elapsed(),finished:res.writableFinished});
 record('origin_request');res.on('close',()=>{closed=true;clearTimeout(timer);record('origin_close');});
 let raw=cached[symbol][scenario]||cached[symbol].delayed;
 if(scenario==='malformed')raw=Buffer.from('{"private":"BODY_CANARY",broken');
 if(scenario==='partial'||scenario==='interrupted')raw=cached[symbol].complete;
 const headers={'Content-Type':'application/json','X-AlphaOS-Request-ID':id,'Content-Length':raw.length};
 if(scenario==='gzip')headers['Content-Encoding']='gzip';
 function begin(){
  if(closed)return;res.writeHead(200,headers);res.flushHeaders();record('origin_headers');
  if(scenario==='partial'||scenario==='interrupted'){
   res.write(raw.subarray(0,64));timer=setTimeout(()=>res.destroy(),100);return;
  }
  let offset=0;
  function send(){
   if(closed)return;
   if(offset===raw.length){res.end();record('origin_end');return;}
   const chunkSize=scenario==='unicode'?1:scenario==='delayed'||scenario==='client_abort'?32768:65536;
   const chunk=raw.subarray(offset,offset+chunkSize);offset+=chunk.length;
   const ok=res.write(chunk);
   const next=()=>{if(!closed)timer=setTimeout(send,scenario==='delayed'?60:scenario==='client_abort'?600:scenario==='timeout_body'?13000:0);};
   if(ok)next();else res.once('drain',next);
  }
  send();
 }
 if(scenario==='timeout_headers')timer=setTimeout(begin,13000);else begin();
});
server.listen(8768,'0.0.0.0',()=>log({event:'origin_ready',node:process.version}));
