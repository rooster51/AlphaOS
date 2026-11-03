import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync,readdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {Miniflare,convertV4MiniflareOptions,Log,LogLevel} from 'miniflare';
import {authBindings,password,cookie} from '../auth-fixture.mjs';
import bcrypt from 'bcryptjs';
const root=resolve('.cloudflare/output/v0/workers/default/bundle');
const files=readdirSync(root,{recursive:true}).filter(n=>n.endsWith('.js')).sort((a,b)=>a==='index.js'?-1:b==='index.js'?1:0);
const modules=files.map(n=>({type:'ESModule',path:join(root,n),contents:readFileSync(join(root,n),'utf8')}));
function worker(overrides={},verifier) {
  const mf = new Miniflare(convertV4MiniflareOptions({modules,modulesRoot:root,compatibilityDate:'2026-10-26',
    compatibilityFlags:['nodejs_compat','nodejs_compat_do_not_populate_process_env'],
    bindings:{...authBindings,ALPHAOS_API_URL:'https://auth-backend.test',ALPHAOS_API_TOKEN:'synthetic-service-token',ALPHAOS_DEMO_MODE:'false',...overrides},
    ratelimits:{ALPHAOS_LOGIN_LIMITER:{namespace_id:'852671',simple:{limit:5,period:60}}},
    serviceBindings:{ASSETS:()=>new Response(null,{status:404})},
    outboundService:async request=>{
      if(verifier)return verifier(request);
      assert.equal(request.url,'https://auth-backend.test/v1/website-auth/verify');
      assert.equal(request.headers.get('authorization'),'Bearer synthetic-service-token');
      const data=await request.json();
      assert.equal(data.password_hash,authBindings.ALPHAOS_PASSWORD_HASH);
      return Response.json({verified:await bcrypt.compare(data.password,data.password_hash)});
    },log:new Log(LogLevel.NONE)}));
  return {dispose:()=>mf.dispose(),dispatchFetch:(url,init={})=>mf.dispatchFetch(url,{redirect:'manual',...init})};
}
const origin='https://website.test';
const login=(mf,p=password,headers={})=>mf.dispatchFetch(origin+'/auth/login',{method:'POST',headers:{Origin:origin,'Content-Type':'application/x-www-form-urlencoded',...headers},body:new URLSearchParams({password:p}).toString()});
test('workerd: anonymous data/pages are denied before backend access, across aliases and RSC',async()=>{
  const mf=worker();try{
    for(const path of ['/api/health','/api/market?symbol=SPY','/api/strategies','/api/research/market','/api/research/structure','/api/research/structures/compare']) {
      for(const method of ['GET','POST'])assert.equal((await mf.dispatchFetch(origin+path,{method})).status,401);
    }
    for(const path of ['/market','/structures','/strategies','/market?_rsc=test','/_next/static/%2F..%2Fapi/market'])
      assert.equal((await mf.dispatchFetch(origin+path,{headers:{RSC:'1'}})).status,303);
    const html=await (await mf.dispatchFetch(origin+'/login')).text();
    for(const secret of Object.values(authBindings))assert(!html.includes(secret));
    assert(!html.includes(password));
  }finally{await mf.dispose();}
});

test('workerd: verifier outage, redirect and invalid acknowledgement fail closed without upstream leakage',async()=>{
  for(const upstream of [()=>new Response('private upstream detail',{status:503}),
    ()=>new Response(null,{status:302,headers:{Location:'https://unexpected.test'}}),
    ()=>Response.json({verified:'true'}),()=>{throw Error('private upstream detail');}]) {
    const mf=worker({},upstream);
    try {
      const r=await login(mf);assert.equal(r.status,503);assert(!r.headers.has('set-cookie'));
      assert(!(await r.text()).includes('private upstream detail'));
    } finally {await mf.dispose();}
  }
});
test('workerd: remote bcrypt login, forged/expired sessions, CSRF, logout and rate limit',async()=>{
  const mf=worker();try{
    assert.equal((await login(mf,'incorrect')).status,401);
    assert.equal((await login(mf,password,{Origin:'https://evil.test'})).status,403);
    const good=await login(mf);assert.equal(good.status,303);
    const set=good.headers.get('set-cookie');assert(set.includes('Secure'));assert(set.includes('Max-Age=2592000'));
    const headers={cookie:set.split(';')[0],Origin:origin};
    const allowed=await mf.dispatchFetch(origin+'/api/health',{headers});assert.equal(allowed.status,200);
    assert(!(await allowed.text()).includes(authBindings.ALPHAOS_SESSION_KEY));
    for(const token of ['forged',cookie(origin,Date.now()-31*86400000)])assert.equal((await mf.dispatchFetch(origin+'/api/health',{headers:{cookie:'__Host-alphaos_session='+token}})).status,401);
    assert.equal((await mf.dispatchFetch(origin+'/api/research/market',{method:'POST',headers:{cookie:headers.cookie},body:'{}'})).status,403);
    const logout=await mf.dispatchFetch(origin+'/auth/logout',{method:'POST',headers});assert.equal(logout.status,303);assert(logout.headers.get('set-cookie').includes('Max-Age=0'));
    assert.equal((await mf.dispatchFetch(origin+'/api/health')).status,401);
    for(let i=0;i<3;i++)assert.equal((await login(mf,'incorrect')).status,401);
    const limited=await login(mf);assert.equal(limited.status,429);assert.equal(limited.headers.get('retry-after'),'60');
  }finally{await mf.dispose();}
});
test('workerd: runtime configuration is required, not process.env or build-time secrets',async()=>{
  const mf=worker({ALPHAOS_PASSWORD_HASH:''});try{
    assert.equal((await login(mf)).status,503);
    assert.equal((await mf.dispatchFetch(origin+'/api/health',{headers:{cookie:'__Host-alphaos_session='+cookie()}})).status,401);
  }finally{await mf.dispose();}
});
