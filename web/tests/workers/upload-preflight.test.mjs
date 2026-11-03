import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,readFile,unlink,rmdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {createHash} from 'node:crypto';
import {authBindings} from '../auth-fixture.mjs';

const cli=resolve('node_modules/cf/bin/cf');
const guard=new URL('./fixtures/deny-external-network.mjs',import.meta.url).href;
const account='00000000000000000000000000000001';
const version='11111111-1111-4111-8111-111111111111';
const secrets={...authBindings,ALPHAOS_API_URL:'https://backend.example.invalid',ALPHAOS_API_TOKEN:'synthetic-upload-api-token'};
const context=JSON.parse(await readFile('.cloudflare/output/v0/config.json','utf8'));
test('upload test subprocess cannot contact Cloudflare or any external socket',async()=>{
  const code=`import assert from 'node:assert/strict';import net from 'node:net';
    assert.throws(()=>fetch('https://api.cloudflare.com/client/v4/accounts'),/External network blocked/);
    assert.throws(()=>net.connect(443,'api.cloudflare.com'),/External network blocked/);`;
  const result=await new Promise((done,reject)=>{
    const child=spawn(process.execPath,['--import',guard,'--input-type=module','--eval',code],{stdio:'ignore',windowsHide:true});
    child.once('error',reject);child.once('close',code=>done(code));
  });
  assert.equal(result,0,'External networking must be blocked before CLI validation');
});
function run(args,base) {
  const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>!/^ALPHAOS_|^CLOUDFLARE_|^CF_|proxy/i.test(key)));
  Object.assign(env,{CLOUDFLARE_API_TOKEN:'synthetic-cloudflare-token',CLOUDFLARE_ACCOUNT_ID:account,
    CLOUDFLARE_API_BASE_URL:base,DO_NOT_TRACK:'1',WRANGLER_SEND_METRICS:'false',WRANGLER_WRITE_LOGS:'false'});
  return new Promise((resolveResult,reject)=>{
    const child=spawn(process.execPath,['--import',guard,cli,'workers','versions','create','--prebuilt','--mode','production','--worker','alphaos-web',...args],
      {env,windowsHide:true,stdio:['ignore','pipe','pipe']});
    let output='';
    for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{output+=chunk;});
    const timer=setTimeout(()=>{child.kill();reject(Error('Upload CLI test timed out'));},60000);
    child.once('error',error=>{clearTimeout(timer);reject(error);});
    child.once('close',code=>{clearTimeout(timer);resolveResult({code,output});});
  });
}
async function sandbox(action) {
  const dir=await mkdtemp(join(tmpdir(),'alphaos-synthetic-upload-'));
  const file=join(dir,'secrets.json');await writeFile(file,JSON.stringify(secrets),{mode:0o600});
  const requests=[],unexpected=[];
  let metadata,entryHash;
  const server=createServer(async(req,res)=>{
    const path=new URL(req.url,'http://localhost').pathname;
    const method=req.method;requests.push({method,path});
    const result=(value)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true,errors:[],messages:[],result:value}));};
    if(req.headers.authorization!=='Bearer synthetic-cloudflare-token'){
      unexpected.push({method,path,reason:'Non-synthetic authentication'});res.statusCode=401;return result(null);
    }
    const prefix=`/client/v4/accounts/${account}/workers/scripts/alphaos-web`;
    if(method==='GET'&&path===`/client/v4/accounts/${account}/workers/services/alphaos-web`)
      return result({id:'alphaos-web',default_environment:{environment:'production',script:{tag:'22222222222222222222222222222222',last_deployed_from:''}}});
    if(method==='GET'&&path===`/client/v4/accounts/${account}/workers/workers/alphaos-web`)
      return result({subdomain:{enabled:false,previews_enabled:true,preview_url_suffix:'-alphaos-web.example.invalid'}});
    if(method==='GET'&&path===prefix+'/settings')return result({bindings:[],tags:[],last_deployed_from:'wrangler'});
    if(method==='GET'&&path===prefix+'/deployments')return result({deployments:[]});
    if(method==='GET'&&path===prefix+'/versions')return result({items:[]});
    if(method==='GET'&&path===prefix+'/secrets')return result([]);
    if(method==='POST'&&path===prefix+'/assets-upload-session') {
      const jwt=['e30',Buffer.from(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600})).toString('base64url'),'synthetic'].join('.');
      return result({jwt,buckets:[]});
    }
    if(method==='POST'&&path===prefix+'/versions') {
      const body=await new Response(req,{headers:req.headers}).formData();
      const part=body.get('metadata');metadata=JSON.parse(typeof part==='string'?part:await part.text());
      entryHash=createHash('sha256').update(Buffer.from(await body.get(metadata.main_module).arrayBuffer())).digest('hex');
      return result({id:version,startup_time_ms:1,metadata:{has_preview:true}});
    }
    unexpected.push({method,path});res.statusCode=400;return result(null);
  });
  await new Promise(resolveListen=>server.listen(0,'127.0.0.1',resolveListen));
  try {await action({file,base:`http://127.0.0.1:${server.address().port}/client/v4`,requests,unexpected,metadata:()=>metadata,entryHash:()=>entryHash});}
  finally {server.closeAllConnections();await new Promise(done=>server.close(done));await unlink(file);await rmdir(dir);}
}
test('native version-upload dry run sends no API requests and preserves credential redaction',async()=>{
  await sandbox(async s=>{
    const result=await run(['--dry-run','--secrets-file',s.file],s.base);
    assert.equal(result.code,context.buildContext.isPreview?1:0,'Native CLI must accept production output and reject Preview output');
    assert.equal(s.requests.length,0,'Dry run must not contact even the local mock API');
    for(const value of [...Object.values(secrets),'synthetic-cloudflare-token'])assert(!result.output.includes(value),'Secret value appeared in CLI output');
  });
});
test('native upload of first version is version-only against a local mock API',async t=>{
  if(context.buildContext.isPreview){t.skip('Preview output must not be uploaded through production version commands; rejection is tested above');return;}
  await sandbox(async s=>{
    const result=await run(['--secrets-file',s.file,'--tag','synthetic-preflight'],s.base);
    // Do not print captured CLI output: it could contain secret fixture values.
    assert.equal(result.code,0,'Local mock version upload failed');
    assert.deepEqual(s.unexpected,[],'Unexpected API endpoint');
    assert.equal(s.requests.filter(r=>r.method==='POST'&&r.path.endsWith('/versions')).length,1);
    assert(!s.requests.some(r=>r.method!=='GET'&&/deployments|subdomain|domains|triggers/.test(r.path)));
    const metadata=s.metadata();assert(metadata,'Missing uploaded version metadata');
    assert(!result.output.includes('synthetic-cloudflare-token'),'Cloudflare upload credential appeared in CLI output');
    for(const [name,value] of Object.entries(secrets)) {
      const binding=metadata.bindings.find(b=>b.name===name);
      assert.equal(binding?.type,'secret_text');assert(binding.text===value,'Uploaded secret did not match synthetic input');
      assert(!result.output.includes(value),'Secret value appeared in CLI output');
    }
    assert(metadata.bindings.some(b=>b.name==='ALPHAOS_DEMO_MODE'&&b.text==='false'));
    assert(metadata.bindings.some(b=>b.name==='ALPHAOS_LOGIN_LIMITER'&&b.type==='ratelimit'&&b.namespace_id==='852671'&&b.simple.limit===5&&b.simple.period===60));
    const expected=createHash('sha256').update(await readFile(resolve('.cloudflare/output/v0/workers/default/bundle',metadata.main_module))).digest('hex');
    assert.equal(s.entryHash(),expected,'Version upload must preserve the built authentication entrypoint exactly');
    assert(!s.requests.some(r=>r.path.includes('/alphaos/')),'Unrelated Worker must not be targeted');
  });
});
test('wrong target or mismatched build mode is rejected without API calls',async()=>{
  await sandbox(async s=>{
    for(const args of [['--worker','alphaos'],['--mode','staging']]){
      const result=await run([...args,'--dry-run','--secrets-file',s.file],s.base);
      assert.notEqual(result.code,0,'Wrong target/mode must fail closed');
    }
    assert.equal(s.requests.length,0);
  });
});
