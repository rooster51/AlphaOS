import {existsSync,readFileSync,writeFileSync,unlinkSync} from 'node:fs';
import {authBindings,cookie} from './auth-fixture.mjs';
const contents=Object.entries(authBindings).map(([k,v])=>`${k}=${JSON.stringify(v)}`).join('\n')+'\n';
/** @returns {import('@playwright/test').StorageState} */
export function setupWorkerBrowserAuth() {
  // Never overwrite a developer's credentials. Test fixtures are never uploaded.
  if(existsSync('.dev.vars') && readFileSync('.dev.vars','utf8')!==contents)throw Error('Move private .dev.vars aside before running isolated browser tests');
  writeFileSync('.dev.vars',contents,{mode:0o600});
  return {cookies:[{name:'__Host-alphaos_session',value:cookie('http://127.0.0.1:3000'),domain:'127.0.0.1',path:'/',
    expires:Math.floor(Date.now()/1000)+2592000,httpOnly:true,secure:true,sameSite:'Strict'}],origins:[]};
}
export default function teardown() {
  if(existsSync('.dev.vars') && readFileSync('.dev.vars','utf8')===contents)unlinkSync('.dev.vars');
}
