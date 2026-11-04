// Launched by pytest against a loopback bridge to the real FastAPI application.
import assert from 'node:assert/strict';
import {protectWebsite,validSession,SESSION_COOKIE} from '../src/lib/website-auth.ts';
import {authBindings,password} from './auth-fixture.mjs';
const nativeFetch=globalThis.fetch;
const backend=new URL(process.argv[2]);
assert.equal(backend.hostname,'127.0.0.1');
globalThis.fetch=(url,init)=>{
  assert.equal(String(url),'https://auth-backend.test/v1/website-auth/verify');
  assert.equal(init.redirect,'manual');
  return nativeFetch(new URL('/v1/website-auth/verify',backend),init);
};
const env={...authBindings,ALPHAOS_API_URL:'https://auth-backend.test',ALPHAOS_API_TOKEN:'synthetic-api-token',
  ALPHAOS_LOGIN_LIMITER:{limit:async()=>({success:true})}};
async function login(value) {
  return protectWebsite(new Request('https://website.test/auth/login',{method:'POST',
    headers:{Origin:'https://website.test','Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({password:value})}),env,()=>{throw Error('Unexpected downstream');});
}
const bad=await login('incorrect');assert.equal(bad.status,401);assert(!bad.headers.has('set-cookie'));
const good=await login(password);assert.equal(good.status,303);
const cookie=good.headers.get('set-cookie').split(';')[0];
assert(cookie.startsWith(SESSION_COOKIE+'='));assert(!cookie.includes(password));
assert(await validSession(new Request('https://website.test/api/health',{headers:{cookie}}),env));
env.ALPHAOS_API_TOKEN='forged';
const denied=await login(password);assert.equal(denied.status,503);assert(!denied.headers.has('set-cookie'));
console.log('Worker auth exchange -> real FastAPI bearer validation -> native cost-12 bcrypt -> signed session: PASS');
