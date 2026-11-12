import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHash,createHmac} from 'node:crypto';
import {protectWebsite,issueSession,sessionRole,validOwnerSessionCookie,validSession,SESSION_COOKIE,SESSION_SECONDS} from '../src/lib/website-auth.ts';
import {authBindings,password,cookie} from './auth-fixture.mjs';
import bcrypt from 'bcryptjs';
const serviceEnv={ALPHAOS_API_URL:'https://auth-backend.test',ALPHAOS_API_TOKEN:'synthetic-service-token'};
globalThis.fetch=async(url,init)=>{
  assert.equal(String(url),'https://auth-backend.test/v1/website-auth/verify');
  assert.equal(init.headers.Authorization,'Bearer synthetic-service-token');
  assert.equal(init.redirect,'manual');assert.equal(init.cache,'no-store');
  const data=JSON.parse(init.body);
  return Response.json({verified:await bcrypt.compare(data.password,data.password_hash)});
};
const env={...authBindings};
const allowLimiter={externalLoginRateLimiter:{limit:async()=>({allowed:true,retryAfterSeconds:0})}};
const gate=(request,environment=env,next=downstream,options=allowLimiter)=>protectWebsite(request,environment,next,options);
const sessionValid=(request,environment=env,now,options=allowLimiter)=>validSession(request,environment,now,options);
const origin='https://website.test';
const request=(path,init={})=>new Request(origin+path,init);
const downstream=()=>{throw new Error('Protected data reached without authorization');};
const post=(path,body='password='+password,headers={})=>request(path,{method:'POST',headers:{Origin:origin,'Content-Type':'application/x-www-form-urlencoded',...headers},body});

test('login accepts only correct password and returns persistent hardened cookie without credentials',async()=>{
  const bad=await gate(post('/auth/login','password=wrong'),{...env,...serviceEnv},downstream);
  assert.equal(bad.status,401);assert(!bad.headers.has('set-cookie'));
  const good=await gate(post('/auth/login'),{...env,...serviceEnv},downstream);
  assert.equal(good.status,303);assert.equal(good.headers.get('location'),'/market');
  const set=good.headers.get('set-cookie');
  for(const part of ['__Host-alphaos_session=','HttpOnly','Secure','SameSite=Strict','Max-Age=2592000','Expires=','Path=/'])assert(set.includes(part));
  assert(!set.includes('Domain='));assert(!set.includes(password));assert(!set.includes(authBindings.ALPHAOS_SESSION_KEY));
  const r=request('/api/research/market',{headers:{cookie:set.split(';')[0]}});
  assert(await sessionValid(r,env));
  assert(await sessionValid(r,{...env})); // fresh runtime, no in-memory session state
  assert(!await sessionValid(r,env,Date.now()+SESSION_SECONDS*1000+2000));
});

test('remote verifier failures and malformed acknowledgements never issue sessions or expose upstream data',async()=>{
  const original=globalThis.fetch;
  try {
    for(const response of [()=>{throw Error('private upstream credential');},
      ()=>new Response('private upstream credential',{status:401}),
      ()=>new Response('private upstream credential',{status:503}),
      ()=>Response.json({verified:'true'}),()=>Response.json({verified:true,extra:true}),
      ()=>new Response('x'.repeat(129)),()=>new Response('{')]) {
      globalThis.fetch=async()=>response();
      const r=await gate(post('/auth/login'),{...env,...serviceEnv},downstream);
      assert.equal(r.status,503);assert(!r.headers.has('set-cookie'));assert(!(await r.text()).includes('private upstream'));
    }
    for(const url of ['http://backend.test','https://user:password@backend.test','https://backend.test/?token=secret']) {
      globalThis.fetch=()=>{throw Error('Unsafe destination was contacted');};
      assert.equal((await gate(post('/auth/login'),{...env,...serviceEnv,ALPHAOS_API_URL:url},downstream)).status,503);
    }
  } finally {globalThis.fetch=original;}
});
test('all pages, API aliases, RSC requests and missing configuration fail closed',async()=>{
  for(const path of ['/','/market','/structures','/strategies','/dashboard','/market?_rsc=x','/_next/static/../../api/market']) {
    const r=await gate(request(path),env,downstream);assert([303,401].includes(r.status));
  }
  for(const path of ['/api/health','/api/market','/api/strategies','/api/research/market','/api/research/structure','/api/research/structures/compare']) {
    for(const method of ['GET','POST','OPTIONS']) assert.equal((await gate(request(path,{method}),env,downstream)).status,401);
  }
  assert.equal((await gate(post('/auth/login'),{},downstream)).status,503);
  for(const name of Object.keys(env))assert(!await sessionValid(request('/',{headers:{cookie:`${SESSION_COOKIE}=${cookie()}`}}),{...env,[name]:undefined}));
});
test('sessions carry an owner role and v1 sessions cannot become owner-private access',async()=>{
  const issued=await issueSession(env,origin);
  const owner=request('/',{headers:{cookie:`${SESSION_COOKIE}=${issued}`}});
  assert.equal(await sessionRole(owner,env),'owner');
  assert(await validOwnerSessionCookie(owner,env));

  const viewer=request('/',{headers:{cookie:`${SESSION_COOKIE}=${cookie(origin,Date.now(),'viewer')}`}});
  assert.equal(await sessionRole(viewer,env),'viewer');
  assert(await sessionValid(viewer,env));
  assert.equal(await validOwnerSessionCookie(viewer,env),false);

  const noRole=request('/',{headers:{cookie:`${SESSION_COOKIE}=${cookie(origin,Date.now(),null)}`}});
  assert.equal(await sessionRole(noRole,env),null);
  assert.equal(await sessionValid(noRole,env),false);

  const iat=Math.floor(Date.now()/1000);
  const payload=Buffer.from(JSON.stringify({v:1,iat,exp:iat+SESSION_SECONDS,aud:origin,nonce:'a'.repeat(43)})).toString('base64url');
  const signature=createHmac('sha256',`${authBindings.ALPHAOS_SESSION_KEY}:${authBindings.ALPHAOS_PASSWORD_HASH}`).update(payload).digest('base64url');
  const legacy=request('/',{headers:{cookie:`${SESSION_COOKIE}=${payload}.${signature}`}});
  assert.equal(await sessionRole(legacy,env),null);
  assert.equal(await sessionValid(legacy,env),false);
});
test('forged, malformed, duplicate, future, expired, wrong-origin and rotated sessions are denied',async()=>{
  const token=await issueSession(env,origin),now=Date.now();
  for(const value of ['garbage',token+'x',token+'.x',cookie(origin,now-31*86400000),cookie(origin,now+100000),cookie('https://other.test')])
    assert(!await sessionValid(request('/',{headers:{cookie:`${SESSION_COOKIE}=${value}`}}),env));
  const r=request('/',{headers:{cookie:`${SESSION_COOKIE}=${token}`}});
  assert(!await sessionValid(r,{...env,ALPHAOS_SESSION_KEY:'a'.repeat(43)}));
  assert(!await sessionValid(r,{...env,ALPHAOS_PASSWORD_HASH:env.ALPHAOS_PASSWORD_HASH.replace('E06','F06')}));
  assert(!await sessionValid(request('/',{headers:{cookie:`${SESSION_COOKIE}=${token}; ${SESSION_COOKIE}=${token}`}}),env));
});
test('CSRF required on login, logout and every authenticated mutation; logout clears cookie',async()=>{
  const session=`${SESSION_COOKIE}=${cookie()}`;
  for(const path of ['/auth/login','/auth/logout','/api/research/market','/api/research/structure','/api/research/structures/compare']) {
    for(const originValue of ['', 'null','https://evil.test']) {
      const r=post(path,'password='+password,{Origin:originValue,cookie:session});
      assert.equal((await gate(r,env,downstream)).status,403);
    }
    assert.equal((await gate(post(path,'',{cookie:session,'Sec-Fetch-Site':'cross-site'}),env,downstream)).status,403);
  }
  const out=await gate(post('/auth/logout','',{cookie:session}),env,downstream);
  assert.equal(out.status,303);assert(out.headers.get('set-cookie').includes('Max-Age=0'));
  assert.equal((await gate(post('/api/research/market','',{cookie:session}),env,async()=>new Response('protected'))).status,200);
});
test('rate limiting and limiter outages fail closed before password validation',async()=>{
  for(const [limit,status] of [[async()=>({allowed:false,retryAfterSeconds:60}),429],[async()=>{throw Error('offline');},503]]) {
    const r=await gate(post('/auth/login'),env,downstream,{externalLoginRateLimiter:{limit}});
    assert.equal(r.status,status);
  }
});
test('Netlify shared limiter is required and an environment variable cannot bypass it',async()=>{
  const netlify={...authBindings,...serviceEnv};
  const spoofed={...netlify,ALPHAOS_LOGIN_LIMITER_MODE:'netlify-edge'};
  assert.equal((await gate(post('/auth/login'),netlify,downstream,{})).status,503);
  assert.equal((await gate(post('/auth/login'),spoofed,downstream,{})).status,503);
  const denied=await gate(post('/auth/login','password=wrong'),netlify,downstream,allowLimiter);
  assert.equal(denied.status,401);
  assert(!denied.headers.has('set-cookie'));
  const accepted=await gate(post('/auth/login'),netlify,downstream,allowLimiter);
  assert.equal(accepted.status,303);
  assert.equal(accepted.headers.get('location'),'/market');
  const token=accepted.headers.get('set-cookie').split(';')[0];
  assert(await sessionValid(request('/api/research/market',{headers:{cookie:token}}),netlify,Date.now(),allowLimiter));
});
test('Netlify global rate limit rejects and fails closed before password verification',async()=>{
  const netlify={...authBindings,...serviceEnv};
  for(const [limit,status,retry] of [
    [async()=>({allowed:false,retryAfterSeconds:23}),429,'23'],
    [async()=>{throw Error('private shared limiter credential');},503,null],
  ]) {
    let verified=false;
    const original=globalThis.fetch;
    globalThis.fetch=async()=>{verified=true;throw Error('Password verifier must not be called');};
    try {
      const response=await gate(post('/auth/login'),netlify,downstream,{
        externalLoginRateLimiter:{limit},
      });
      assert.equal(response.status,status);
      assert.equal(response.headers.get('retry-after'),retry);
      assert.equal(verified,false);
    } finally { globalThis.fetch=original; }
  }
});
test('password truncation, oversized streamed bodies and duplicate fields are rejected; noindex is not auth',async()=>{
  for(const body of ['password='+password+'&password='+password,'password='+'x'.repeat(73),'password='+'x'.repeat(3000)])
    assert.equal((await gate(post('/auth/login',body),env,downstream)).status,401);
  const page=await gate(request('/login'),env,downstream);
  const html=await page.text();assert(html.includes('type="password"'));assert(!html.includes(authBindings.ALPHAOS_PASSWORD_HASH));
  // Approved candidate's exact login markup: authentication transport must not redesign it.
  assert.equal(createHash('sha256').update(html).digest('hex'),'4d327a41395b17c13473e733e749c034b371d311e8a52d3599c1d639d66ec6cb');
  assert.equal(page.headers.get('x-robots-tag'),'noindex, nofollow');assert(page.headers.get('cache-control').includes('no-store'));
  assert((await (await gate(request('/robots.txt'),env,downstream)).text()).includes('Disallow: /'));
});
test('non-loopback HTTP cannot serve a password form or accept credentials',async()=>{
  const get=await gate(new Request('http://website.test/login'),env,downstream);
  assert.equal(get.status,308);assert.equal(get.headers.get('location'),'https://website.test/login');
  assert.equal((await gate(new Request('http://website.test/auth/login',{method:'POST',body:'password='+password}),env,downstream)).status,403);
});
