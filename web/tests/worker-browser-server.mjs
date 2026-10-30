// Local-only browser harness: real compiled workerd, synthetic remote verifier.
// No test hook or bypass is included in application code or uploaded artifacts.
import {readFileSync,readdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import bcrypt from 'bcryptjs';
import {Miniflare,convertV4MiniflareOptions,Log,LogLevel} from 'miniflare';
import {authBindings} from './auth-fixture.mjs';
const root=resolve('.cloudflare/output/v0/workers/default/bundle');
const files=readdirSync(root,{recursive:true}).filter(n=>n.endsWith('.js'));
files.sort((a,b)=>a==='index.js'?-1:b==='index.js'?1:0);
function worker(remoteAuth) {return new Miniflare(convertV4MiniflareOptions({
  modules:files.map(n=>({type:'ESModule',path:join(root,n),contents:readFileSync(join(root,n),'utf8')})),
  modulesRoot:root,compatibilityDate:'2026-10-26',compatibilityFlags:['nodejs_compat'],
  bindings:{...authBindings,...(remoteAuth?{ALPHAOS_API_URL:'https://auth-backend.test',ALPHAOS_API_TOKEN:'synthetic-service-token'}:{}),ALPHAOS_DEMO_MODE:'false'},
  ratelimits:{ALPHAOS_LOGIN_LIMITER:{namespace_id:'852671',simple:{limit:5,period:60}}},
  serviceBindings:{ASSETS:request=>{
    const directory=resolve('.cloudflare/output/v0/workers/default/assets');
    const path=resolve(directory,'.'+new URL(request.url).pathname);
    if(!path.startsWith(directory+'/')&&!path.startsWith(directory+'\\'))return new Response(null,{status:404});
    try {return new Response(readFileSync(path),{headers:{'Content-Type':path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'application/octet-stream'}});}
    catch {return new Response(null,{status:404});}
  }},
  outboundService:async request=>{
    if(request.url!=='https://auth-backend.test/v1/website-auth/verify')return new Response(null,{status:503});
    assert.equal(request.headers.get('authorization'),'Bearer synthetic-service-token');
    const data=await request.json();
    return Response.json({verified:await bcrypt.compare(data.password,data.password_hash)});
  },log:new Log(LogLevel.NONE)}));}
// Keep existing missing-research-configuration browser scenarios intact. Both
// isolated runtimes use identical session secrets; only the login test runtime
// has synthetic verifier bindings. This routing exists only in this local test.
const main=worker(false),auth=worker(true);
const server=createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://127.0.0.1:3000');
    const directory=resolve('.cloudflare/output/v0/workers/default/assets');
    const asset=resolve(directory,'.'+url.pathname);
    if(asset.startsWith(directory+'/')||asset.startsWith(directory+'\\')) {
      try {
        const contents=readFileSync(asset);
        res.setHeader('Content-Type',asset.endsWith('.js')?'text/javascript':asset.endsWith('.css')?'text/css':'application/octet-stream');
        res.end(contents);return;
      } catch {}
    }
    const parts=[];for await(const part of req)parts.push(part);
    const response=await (url.pathname==='/auth/login'?auth:main).dispatchFetch(url.href,{
      method:req.method,headers:req.headers,redirect:'manual',
      ...(!['GET','HEAD'].includes(req.method)?{body:Buffer.concat(parts)}:{})});
    res.writeHead(response.status,Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  } catch {res.writeHead(503);res.end();}
});
await new Promise(resolve=>server.listen(3000,'127.0.0.1',resolve));
console.log('Local synthetic-auth Worker ready');
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,async()=>{server.close();await Promise.all([main.dispose(),auth.dispose()]);process.exit(0);});
